"""Read-only discovery of mission results and semantic evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from drone_gui.session_archive import load_manifest


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
DELIVERABLE_SUFFIXES = {".ply", ".pcd", ".bt", ".ot", ".json", ".csv", ".html"}


@dataclass
class SessionSummary:
    path: Path
    class_images: Dict[str, List[Path]] = field(default_factory=dict)
    map_images: List[Path] = field(default_factory=list)
    deliverables: List[Path] = field(default_factory=list)
    status: str = "legacy"
    telemetry_samples: int = 0
    point_count: int = 0
    semantic_objects: int = 0

    @property
    def image_count(self) -> int:
        return sum(len(images) for images in self.class_images.values())


def scan_sessions(results_dir: Path) -> List[SessionSummary]:
    if not results_dir.is_dir():
        return []
    sessions: List[SessionSummary] = []
    for folder in results_dir.iterdir():
        if not folder.is_dir():
            continue
        detected = folder / "detected_classes"
        class_images: Dict[str, List[Path]] = {}
        if detected.is_dir():
            for class_dir in sorted(path for path in detected.iterdir() if path.is_dir()):
                images = sorted(
                    path for path in class_dir.iterdir()
                    if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
                )
                if images:
                    class_images[class_dir.name] = images
        map_images = sorted(
            path for path in folder.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".png"
            and any(token in path.name.lower() for token in ("map", "depth", "trajectory"))
        )
        manifest = load_manifest(folder)
        deliverables = sorted(
            path for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in DELIVERABLE_SUFFIXES
        )
        if class_images or map_images or deliverables or manifest:
            summary = manifest.get("summary", {})
            sessions.append(SessionSummary(
                path=folder,
                class_images=class_images,
                map_images=map_images,
                deliverables=deliverables,
                status=str(manifest.get("status", "legacy")),
                telemetry_samples=int(summary.get("telemetry_samples", 0)),
                point_count=int(summary.get("point_count", 0)),
                semantic_objects=int(summary.get("semantic_objects", 0)),
            ))
    return sorted(sessions, key=lambda item: item.path.stat().st_mtime, reverse=True)


def session_payload(root: Path, offline: bool = True) -> dict:
    root = root.resolve()
    return {
        "result_root": str(root),
        "semantic_dir": str(root / "detected_classes"),
        "live_dir": str(root / "live_feed"),
        "map_dir": str(root / "live_map"),
        "offline": offline,
    }
