"""Read-only discovery of mission results and semantic evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


@dataclass
class SessionSummary:
    path: Path
    class_images: Dict[str, List[Path]] = field(default_factory=dict)
    map_images: List[Path] = field(default_factory=list)

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
        if class_images or map_images:
            sessions.append(SessionSummary(folder, class_images, map_images))
    return sorted(sessions, key=lambda item: item.path.stat().st_mtime, reverse=True)
