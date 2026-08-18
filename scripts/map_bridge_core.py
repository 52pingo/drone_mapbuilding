"""Pure point-cloud conversion and atomic snapshot helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time

import numpy as np


def world_enu_to_ned(points) -> np.ndarray:
    """Convert AirSim ROS world ENU xyz into PX4 local NED xyz."""
    values = np.asarray(points, dtype=np.float32).reshape((-1, 3))
    if values.size == 0:
        return values.copy()
    return np.column_stack((values[:, 1], values[:, 0], -values[:, 2])).astype(
        np.float32, copy=False
    )


def world_enu_to_local_ned(points, world_origin_ned=(0.0, 0.0, 0.0)) -> np.ndarray:
    """Convert world ENU points into PX4 local NED coordinates."""
    converted = world_enu_to_ned(points)
    origin = np.asarray(world_origin_ned, dtype=np.float32).reshape(3)
    return (converted - origin).astype(np.float32, copy=False)


def finite_downsample(points, max_points: int) -> np.ndarray:
    """Drop invalid rows and deterministically limit rendering payload size."""
    if max_points < 1:
        raise ValueError("max_points must be positive")
    values = np.asarray(points, dtype=np.float32).reshape((-1, 3))
    values = values[np.isfinite(values).all(axis=1)]
    if len(values) <= max_points:
        return values
    indices = np.linspace(0, len(values) - 1, max_points, dtype=np.int64)
    return values[indices]


def bounds_payload(points) -> dict:
    """Return rounded xyz bounds for status and camera framing."""
    values = np.asarray(points, dtype=np.float32).reshape((-1, 3))
    if not len(values):
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}
    return {
        "min": [round(float(value), 3) for value in values.min(axis=0)],
        "max": [round(float(value), 3) for value in values.max(axis=0)],
    }


class MapSnapshotWriter:
    """Write NPY first and metadata last, retaining three complete snapshots."""

    def __init__(self, directory: Path, max_points: int = 80000) -> None:
        self.directory = directory
        self.max_points = max_points
        self.sequence = 0
        self.directory.mkdir(parents=True, exist_ok=True)

    def publish(
        self,
        world_enu_points,
        frame_id: str = "world_enu",
        world_origin_ned=(0.0, 0.0, 0.0),
    ) -> dict:
        self.sequence += 1
        original_count = len(world_enu_points)
        points = finite_downsample(
            world_enu_to_local_ned(world_enu_points, world_origin_ned),
            self.max_points,
        )
        name = f"points_{self.sequence:06d}.npy"
        temporary = self.directory / (name + ".tmp")
        with temporary.open("wb") as output:
            np.save(output, points, allow_pickle=False)
        os.replace(temporary, self.directory / name)
        metadata = {
            "schema": 1,
            "sequence": self.sequence,
            "captured_at": time.time(),
            "source_frame": frame_id,
            "coordinate_frame": "px4_local_ned",
            "world_origin_ned": [
                round(float(value), 6) for value in world_origin_ned
            ],
            "original_count": int(original_count),
            "point_count": int(len(points)),
            "bounds": bounds_payload(points),
            "points": name,
        }
        payload = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
        meta_tmp = self.directory / "latest.json.tmp"
        meta_tmp.write_bytes(payload)
        os.replace(meta_tmp, self.directory / "latest.json")
        for old in sorted(self.directory.glob("points_*.npy"))[:-3]:
            try:
                old.unlink()
            except OSError:
                pass
        return metadata


def write_ply(path: Path, points, semantic_objects=()) -> None:
    """Export occupancy and semantic marker vertices in N/E/height-up axes."""
    values = np.asarray(points, dtype=np.float32).reshape((-1, 3))
    markers = [
        item for item in semantic_objects
        if isinstance(item, dict) and len(item.get("position_ned", [])) == 3
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as output:
        output.write("ply\nformat ascii 1.0\n")
        output.write("comment axes north east height_up metres\n")
        output.write(f"element vertex {len(values) + len(markers)}\n")
        output.write("property float x\nproperty float y\nproperty float z\n")
        output.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        output.write("property int semantic_id\nend_header\n")
        height = -values[:, 2] if len(values) else np.empty(0)
        lo = float(height.min()) if len(height) else 0.0
        span = max(0.1, float(height.max()) - lo) if len(height) else 1.0
        for point, point_height in zip(values, height):
            ratio = max(0.0, min(1.0, (float(point_height) - lo) / span))
            output.write(
                f"{point[0]:.4f} {point[1]:.4f} {-point[2]:.4f} "
                f"{int(45 + 40 * ratio)} {int(115 + 105 * ratio)} "
                f"{int(145 + 90 * ratio)} -1\n"
            )
        for index, item in enumerate(markers):
            north, east, down = item["position_ned"]
            output.write(
                f"{float(north):.4f} {float(east):.4f} {-float(down):.4f} "
                f"238 180 74 {index}\n"
            )
