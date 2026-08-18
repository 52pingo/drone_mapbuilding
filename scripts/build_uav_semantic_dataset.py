#!/usr/bin/env python3
"""Build a reproducible unified YOLO dataset from local UAV sources."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Dict, List, Optional

from uav_semantic_schema import (
    CLASSES,
    ROAD20_TO_TARGET,
    VISDRONE_TO_TARGET,
)


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


def parse_args() -> argparse.Namespace:
    workspace = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(workspace / "datasets" / "uav_semantic_v1"))
    parser.add_argument("--road20-root", default=r"E:\YOLOv8\data")
    parser.add_argument(
        "--visdrone-root",
        default=r"D:\PycharmProjects\PythonProject21\QueryDet-PyTorch\data\visdrone_yolo",
    )
    parser.add_argument(
        "--citypark-root",
        default=str(workspace / "datasets" / "raw" / "citypark_semantic_v1"),
    )
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def prepare_output(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {output_dir}; pass --overwrite to rebuild")
        workspace = Path(__file__).resolve().parents[1]
        if workspace not in output_dir.parents or output_dir.name != "uav_semantic_v1":
            raise RuntimeError(f"Refusing to remove unexpected path: {output_dir}")
        shutil.rmtree(output_dir)
    for split in ("train", "val", "test"):
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)


def link_or_copy(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        shutil.copy2(source, destination)
        return "copy"


def remap_label(
    source: Path,
    destination: Path,
    mapping: Dict[int, int],
    skip_unmapped: bool = False,
) -> Counter:
    output_lines: List[str] = []
    counts: Counter = Counter()
    for line_number, raw_line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        fields = raw_line.split()
        if not fields:
            continue
        if len(fields) != 5:
            raise ValueError(f"{source}:{line_number}: expected 5 YOLO fields")
        source_id = int(fields[0])
        if source_id not in mapping:
            if skip_unmapped:
                continue
            raise ValueError(f"{source}:{line_number}: unmapped source class {source_id}")
        values = [float(value) for value in fields[1:]]
        if not all(0.0 <= value <= 1.0 for value in values):
            raise ValueError(f"{source}:{line_number}: coordinates outside [0,1]")
        target_id = mapping[source_id]
        output_lines.append(" ".join([str(target_id), *fields[1:]]))
        counts[target_id] += 1
    destination.write_text("\n".join(output_lines) + ("\n" if output_lines else ""), encoding="utf-8")
    return counts


def copy_target_label(source: Path, destination: Path) -> Counter:
    identity = {index: index for index in range(len(CLASSES))}
    return remap_label(source, destination, identity)


def add_example(
    source_image: Path,
    source_label: Path,
    output_dir: Path,
    split: str,
    prefix: str,
    label_mapping: Optional[Dict[int, int]],
    stats: dict,
    skip_unmapped: bool = False,
) -> None:
    if not source_image.is_file():
        raise FileNotFoundError(source_image)
    if not source_label.is_file():
        raise FileNotFoundError(source_label)
    stem = f"{prefix}_{source_image.stem}"
    destination_image = output_dir / "images" / split / f"{stem}{source_image.suffix.lower()}"
    destination_label = output_dir / "labels" / split / f"{stem}.txt"
    mode = link_or_copy(source_image, destination_image)
    counts = (
        remap_label(source_label, destination_label, label_mapping, skip_unmapped)
        if label_mapping is not None
        else copy_target_label(source_label, destination_label)
    )
    stats["images"][split] += 1
    stats["transfer_modes"][mode] += 1
    stats["boxes"][split].update(counts)


def load_coco_names(path: Path) -> List[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [str(item["file_name"]) for item in payload["images"]]


def add_road20(root: Path, output_dir: Path, stats: dict) -> None:
    sources = {
        "train": ("train_coco.json", root / "train" / "images", root / "train" / "labels"),
        # The local test/images directory is the union of the original val and test images.
        "val": ("valid_coco.json", root / "test" / "images", root / "val" / "labels"),
        "test": ("test_coco.json", root / "test" / "images", root / "test" / "labels"),
    }
    for split, (manifest, image_dir, label_dir) in sources.items():
        for file_name in load_coco_names(root / manifest):
            image = image_dir / file_name
            label = label_dir / f"{Path(file_name).stem}.txt"
            add_example(image, label, output_dir, split, "road20", ROAD20_TO_TARGET, stats)


def add_visdrone(root: Path, output_dir: Path, stats: dict) -> None:
    for split in ("train", "val"):
        image_dir = root / "images" / split
        label_dir = root / "labels" / split
        images = sorted(path for path in image_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
        for image in images:
            label = label_dir / f"{image.stem}.txt"
            add_example(image, label, output_dir, split, "visdrone", VISDRONE_TO_TARGET, stats)


def citypark_split(name: str) -> str:
    bucket = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 80:
        return "train"
    if bucket < 90:
        return "val"
    return "test"


def add_citypark(root: Path, output_dir: Path, stats: dict) -> None:
    image_dir = root / "images"
    label_dir = root / "labels"
    if not image_dir.is_dir() or not label_dir.is_dir():
        raise FileNotFoundError(f"CityPark raw data is incomplete: {root}")
    images = sorted(path for path in image_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        raise RuntimeError(f"No CityPark images found in {image_dir}")
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    source_classes = metadata["classes"]
    target_by_name = {name: index for index, name in enumerate(CLASSES)}
    mapping = {
        source_id: target_by_name[name]
        for source_id, name in enumerate(source_classes)
        if name in target_by_name
    }
    for image in images:
        split = citypark_split(image.name)
        label = label_dir / f"{image.stem}.txt"
        add_example(
            image,
            label,
            output_dir,
            split,
            "sim",
            mapping,
            stats,
            skip_unmapped=True,
        )


def write_yaml(output_dir: Path) -> Path:
    yaml_path = output_dir / "data.yaml"
    names = "\n".join(f"  {index}: {name}" for index, name in enumerate(CLASSES))
    text = (
        f"path: {output_dir.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n\n"
        f"names:\n{names}\n"
    )
    yaml_path.write_text(text, encoding="utf-8")
    return yaml_path


def validate_dataset(output_dir: Path, stats: dict) -> None:
    for split in ("train", "val", "test"):
        images = list((output_dir / "images" / split).iterdir())
        labels = list((output_dir / "labels" / split).glob("*.txt"))
        if len(images) != len(labels) or len(images) != stats["images"][split]:
            raise RuntimeError(
                f"{split} image/label mismatch: images={len(images)} labels={len(labels)} "
                f"expected={stats['images'][split]}"
            )
        for label in labels:
            for line_number, line in enumerate(label.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                fields = line.split()
                class_id = int(fields[0])
                if not 0 <= class_id < len(CLASSES):
                    raise ValueError(f"{label}:{line_number}: invalid class {class_id}")


def serializable_stats(stats: dict) -> dict:
    return {
        "classes": CLASSES,
        "images": dict(stats["images"]),
        "transfer_modes": dict(stats["transfer_modes"]),
        "boxes": {
            split: {CLASSES[class_id]: count for class_id, count in sorted(counter.items())}
            for split, counter in stats["boxes"].items()
        },
    }


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    prepare_output(output_dir, args.overwrite)
    stats = {
        "images": Counter(),
        "transfer_modes": Counter(),
        "boxes": defaultdict(Counter),
    }
    add_road20(Path(args.road20_root), output_dir, stats)
    add_visdrone(Path(args.visdrone_root), output_dir, stats)
    add_citypark(Path(args.citypark_root), output_dir, stats)
    validate_dataset(output_dir, stats)
    yaml_path = write_yaml(output_dir)
    payload = serializable_stats(stats)
    payload["data_yaml"] = str(yaml_path)
    (output_dir / "stats.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
