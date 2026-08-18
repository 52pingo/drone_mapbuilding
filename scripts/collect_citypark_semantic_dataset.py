#!/usr/bin/env python3
"""Generate boxed CityPark training data from AirSim segmentation masks."""

from __future__ import annotations

import argparse
from collections import defaultdict
import datetime as dt
import json
import math
from pathlib import Path
import random
import re
import time
from typing import Dict, Iterable, List, Sequence, Tuple

import cv2
import numpy as np

from semantic_perception import import_airsim
from uav_semantic_schema import CLASSES, CLASS_TO_ID


# AirSim object ID, target class, AirSim/Python-compatible scene-name regex.
SEGMENTATION_GROUPS: Sequence[Tuple[int, str, str]] = (
    (1, "tree", r"(SM_AmurCork|SM_Elm|SM_Maple|SM_WeepingWillow)[\w]*"),
    (2, "shrub", r"(SM_Bush|Ivy)[\w]*"),
    (3, "building", r"(CafeBuilding|House0|FoodStalls|Tribune0|Bower0)[\w]*"),
    (4, "fence", r"(SM_Fence|Fence0|ParkFence|MergedFence|MergedParkFence|BaseballGate|FootballGate)[\w]*"),
    (5, "pole", r"(LampPost|SM_LampPost|TennisFloodlight)[\w]*"),
    (6, "traffic_sign", r"RoadSigns[\w]*"),
    (7, "traffic_light", r"TrafficLight[\w]*"),
    (8, "cone", r"SM_TrafficBarrel[\w]*"),
    (9, "barrier", r"RoadBlock[\w]*"),
    (10, "trash_bin", r"TrashCan[\w]*"),
    (11, "bench", r"(Bench0|SM_Bench)[\w]*"),
    (12, "rock", r"SM_Rock[\w]*"),
    (13, "bridge", r"(Bridge0|SM_Bridge|MergedBridge)[\w]*"),
    (14, "playground_equipment", r"(PlayGround|SM_PlayGround|BasketballHoop|TennisNet|TennisUmpiresChair)[\w]*"),
    (15, "umbrella", r"Umbrella[\w]*"),
)

# CityPark foliage is composed from instanced mesh fragments. Assigning each mesh
# a separate color produces dozens of boxes for a single visible tree. Category-
# level masks intentionally produce stable boxes for tree/building groups instead.
INSTANCE_SEPARATED_CLASSES = set()


def parse_args() -> argparse.Namespace:
    workspace = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(workspace / "datasets" / "raw" / "citypark_semantic_v1"),
    )
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--camera", default="CameraDepth")
    parser.add_argument("--vehicle", default="PX4")
    parser.add_argument("--settle-seconds", type=float, default=0.12)
    parser.add_argument("--min-component-pixels", type=int, default=45)
    parser.add_argument("--preview-count", type=int, default=12)
    parser.add_argument(
        "--airsim-client",
        default=r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient",
    )
    parser.add_argument(
        "--airsim-rpc-vendor",
        default=str(workspace / ".tools" / "airsim_rpc"),
    )
    parser.add_argument(
        "--seg-rgbs",
        default=r"D:\PycharmProjects\PythonProject19\AirSim\docs\seg_rgbs.txt",
    )
    return parser.parse_args()


def load_palette(path: Path) -> Dict[int, Tuple[int, int, int]]:
    palette: Dict[int, Tuple[int, int, int]] = {}
    pattern = re.compile(r"^(\d+)\s+\[(\d+),\s*(\d+),\s*(\d+)\]")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            palette[int(match.group(1))] = tuple(map(int, match.groups()[1:]))
    return palette


def decode_png(response) -> np.ndarray:
    data = np.frombuffer(response.image_data_uint8, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("AirSim returned an invalid compressed image")
    return image


def write_jpeg(path: Path, image: np.ndarray, quality: int = 94) -> None:
    success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not success:
        raise RuntimeError(f"OpenCV failed to encode {path}")
    encoded.tofile(str(path))


def classify_scene_objects(names: Iterable[str]) -> Dict[str, str]:
    compiled = [(class_name, re.compile(rf"^(?:{pattern})$")) for _, class_name, pattern in SEGMENTATION_GROUPS]
    classified: Dict[str, str] = {}
    for name in names:
        for class_name, pattern in compiled:
            if pattern.match(name):
                classified[name] = class_name
                break
    return classified


def valid_position(position) -> bool:
    values = (position.x_val, position.y_val, position.z_val)
    return all(math.isfinite(value) and abs(value) < 5000 for value in values)


def collect_anchors(client, classified: Dict[str, str]) -> List[dict]:
    anchors: List[dict] = []
    seen = set()
    for name, class_name in classified.items():
        pose = client.simGetObjectPose(name)
        if not valid_position(pose.position):
            continue
        key = (
            class_name,
            round(pose.position.x_val, 1),
            round(pose.position.y_val, 1),
            round(pose.position.z_val, 1),
        )
        if key in seen:
            continue
        seen.add(key)
        anchors.append({
            "name": name,
            "class": class_name,
            "x": float(pose.position.x_val),
            "y": float(pose.position.y_val),
            "z": float(pose.position.z_val),
        })
    if not anchors:
        raise RuntimeError("No classified CityPark objects returned valid poses")
    return anchors


def balance_anchors(anchors: List[dict], rng: random.Random) -> List[dict]:
    buckets = defaultdict(list)
    for anchor in anchors:
        buckets[anchor["class"]].append(anchor)
    for values in buckets.values():
        rng.shuffle(values)
    class_names = sorted(buckets)
    maximum = max(len(values) for values in buckets.values())
    balanced = []
    for index in range(maximum):
        for class_name in class_names:
            values = buckets[class_name]
            balanced.append(values[index % len(values)])
    return balanced


def assign_segmentation_ids(client, classified: Dict[str, str]) -> Tuple[Dict[int, str], List[dict]]:
    if not client.simSetSegmentationObjectID(r"[\w]*", 0, True):
        raise RuntimeError("Failed to reset CityPark segmentation IDs")

    id_to_class: Dict[int, str] = {}
    assignments = []
    next_id = 1
    for name, class_name in sorted(classified.items()):
        if class_name not in INSTANCE_SEPARATED_CLASSES:
            continue
        if next_id > 255:
            raise RuntimeError("Ran out of AirSim segmentation object IDs")
        success = client.simSetSegmentationObjectID(name, next_id, False)
        if success:
            id_to_class[next_id] = class_name
            assignments.append({
                "object_id": next_id,
                "class": class_name,
                "scene_object": name,
            })
            next_id += 1

    for _, class_name, pattern in SEGMENTATION_GROUPS:
        if class_name in INSTANCE_SEPARATED_CLASSES:
            continue
        if next_id > 255:
            raise RuntimeError("Ran out of AirSim segmentation object IDs")
        success = client.simSetSegmentationObjectID(pattern, next_id, True)
        if success:
            id_to_class[next_id] = class_name
            assignments.append({
                "object_id": next_id,
                "class": class_name,
                "pattern": pattern,
            })
            next_id += 1

    if not id_to_class:
        raise RuntimeError("No CityPark segmentation IDs were assigned")
    return id_to_class, assignments


def boxes_from_mask(mask: np.ndarray, min_pixels: int) -> List[Tuple[int, int, int, int, int]]:
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    boxes = []
    for component in range(1, count):
        x, y, width, height, area = map(int, stats[component])
        if area < min_pixels or width < 3 or height < 3:
            continue
        boxes.append((x, y, x + width, y + height, area))
    return boxes


def yolo_line(class_id: int, box: Tuple[int, int, int, int, int], width: int, height: int) -> str:
    x1, y1, x2, y2, _ = box
    center_x = ((x1 + x2) / 2.0) / width
    center_y = ((y1 + y2) / 2.0) / height
    box_width = (x2 - x1) / width
    box_height = (y2 - y1) / height
    return f"{class_id} {center_x:.6f} {center_y:.6f} {box_width:.6f} {box_height:.6f}"


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    image_dir = output_dir / "images"
    label_dir = output_dir / "labels"
    preview_dir = output_dir / "previews"
    for directory in (image_dir, label_dir, preview_dir):
        directory.mkdir(parents=True, exist_ok=True)

    airsim = import_airsim(args.airsim_client, args.airsim_rpc_vendor)
    client = airsim.MultirotorClient()
    client.confirmConnection()

    scene_names = client.simListSceneObjects()
    classified = classify_scene_objects(scene_names)
    print(f"scene_objects={len(scene_names)} classified={len(classified)}", flush=True)

    palette = load_palette(Path(args.seg_rgbs))
    id_to_class, assignments = assign_segmentation_ids(client, classified)
    missing_palette = [object_id for object_id in id_to_class if object_id not in palette]
    if missing_palette:
        raise RuntimeError(f"AirSim palette is missing object IDs: {missing_palette}")
    assignment_counts = {
        class_name: sum(1 for value in classified.values() if value == class_name)
        for class_name in CLASSES
        if class_name in set(classified.values())
    }
    print(
        f"segmentation_ids={len(id_to_class)} "
        f"instance_separated={sorted(INSTANCE_SEPARATED_CLASSES)}",
        flush=True,
    )
    for class_name, count in sorted(assignment_counts.items()):
        print(f"segmentation class={class_name} scene_objects={count}", flush=True)
    anchors = collect_anchors(client, classified)
    rng = random.Random(args.seed)
    anchors = balance_anchors(anchors, rng)

    requests = [
        airsim.ImageRequest(args.camera, airsim.ImageType.Scene, False, True),
        airsim.ImageRequest(args.camera, airsim.ImageType.Segmentation, False, True),
    ]
    distances = (18.0, 28.0, 40.0, 55.0)
    altitudes = (5.0, 8.0, 12.0, 18.0)
    records = []
    class_box_counts = {name: 0 for name in CLASSES}
    attempts = 0

    while len(records) < args.frames and attempts < max(args.frames * 8, 100):
        anchor = anchors[attempts % len(anchors)]
        attempts += 1
        angle = rng.uniform(-math.pi, math.pi)
        distance = rng.choice(distances) + rng.uniform(-2.0, 2.0)
        altitude = rng.choice(altitudes)
        x = anchor["x"] + math.cos(angle) * distance
        y = anchor["y"] + math.sin(angle) * distance
        z = min(anchor["z"] - altitude, -3.0)
        yaw = math.atan2(anchor["y"] - y, anchor["x"] - x)
        pitch = math.radians(rng.uniform(-5.0, 7.0))
        pose = airsim.Pose(
            airsim.Vector3r(x, y, z),
            airsim.to_quaternion(pitch, 0.0, yaw),
        )
        client.simSetVehiclePose(pose, True, vehicle_name=args.vehicle)
        time.sleep(args.settle_seconds)

        responses = client.simGetImages(requests, vehicle_name=args.vehicle)
        if len(responses) != 2 or not responses[0].image_data_uint8 or not responses[1].image_data_uint8:
            continue
        scene_bgr = decode_png(responses[0])
        segmentation_bgr = decode_png(responses[1])
        if scene_bgr.shape[:2] != segmentation_bgr.shape[:2]:
            segmentation_bgr = cv2.resize(
                segmentation_bgr,
                (scene_bgr.shape[1], scene_bgr.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )
        segmentation_rgb = cv2.cvtColor(segmentation_bgr, cv2.COLOR_BGR2RGB)
        height, width = scene_bgr.shape[:2]
        labels = []
        evidence = []
        visible_mask = np.zeros((height, width), dtype=bool)
        for object_id, class_name in id_to_class.items():
            color = np.array(palette[object_id], dtype=np.uint8)
            mask = np.all(segmentation_rgb == color, axis=2)
            visible_mask |= mask
            for box in boxes_from_mask(mask, args.min_component_pixels):
                labels.append(yolo_line(CLASS_TO_ID[class_name], box, width, height))
                evidence.append((class_name, box))
                class_box_counts[class_name] += 1
        minimum_useful_area = max(300, int(width * height * 0.001))
        visible_ratio = float(visible_mask.mean())
        if (
            not labels
            or max(box[4] for _, box in evidence) < minimum_useful_area
            or visible_ratio < 0.02
        ):
            continue

        index = len(records) + 1
        stem = f"citypark_{index:06d}"
        image_path = image_dir / f"{stem}.jpg"
        label_path = label_dir / f"{stem}.txt"
        write_jpeg(image_path, scene_bgr, 94)
        label_path.write_text("\n".join(labels) + "\n", encoding="utf-8")

        if index <= args.preview_count:
            preview = scene_bgr.copy()
            for class_name, (x1, y1, x2, y2, _) in evidence:
                cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    preview,
                    class_name,
                    (x1, max(16, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 255, 0),
                    1,
                    cv2.LINE_AA,
                )
            write_jpeg(preview_dir / f"{stem}.jpg", preview, 92)

        records.append({
            "image": image_path.name,
            "label": label_path.name,
            "anchor": anchor,
            "camera_pose": {"x": x, "y": y, "z": z, "yaw_rad": yaw, "pitch_rad": pitch},
            "boxes": len(labels),
            "labeled_pixel_ratio": round(visible_ratio, 6),
        })
        if index == 1 or index % 25 == 0:
            print(f"captured={index}/{args.frames} attempts={attempts} boxes={len(labels)}", flush=True)

    metadata = {
        "created_at": dt.datetime.now().astimezone().isoformat(),
        "requested_frames": args.frames,
        "captured_frames": len(records),
        "attempts": attempts,
        "seed": args.seed,
        "classes": CLASSES,
        "segmentation_assignments": assignments,
        "assignment_counts": assignment_counts,
        "class_box_counts": class_box_counts,
        "records": records,
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "output_dir": str(output_dir),
        "captured_frames": len(records),
        "class_box_counts": {k: v for k, v in class_box_counts.items() if v},
    }, ensure_ascii=False, indent=2), flush=True)
    if len(records) < args.frames:
        raise RuntimeError(f"Only captured {len(records)} of {args.frames} requested frames")


if __name__ == "__main__":
    main()
