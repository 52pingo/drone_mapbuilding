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


def _join_columns(columns, separator: str = " ") -> np.ndarray:
    """Join equal-length string columns with a separator, vectorised."""
    result = columns[0]
    for column in columns[1:]:
        result = np.char.add(np.char.add(result, separator), column)
    return result


def _format_vertices(x, y, z, red, green, blue, semantic_id) -> str:
    """Render vertex rows as ASCII text, one row per line, vectorised."""
    if not len(x):
        return ""
    lines = _join_columns(
        (
            np.char.mod("%.4f", x),
            np.char.mod("%.4f", y),
            np.char.mod("%.4f", z),
            np.char.mod("%d", red),
            np.char.mod("%d", green),
            np.char.mod("%d", blue),
            np.char.mod("%d", semantic_id),
        )
    )
    return "\n".join(lines.tolist()) + "\n"


def _format_markers(markers, red: int, green: int, blue: int) -> str:
    """Render semantic marker rows; markers are few so a loop is fine."""
    if not markers:
        return ""
    rows = []
    for index, item in enumerate(markers):
        north, east, down = item["position_ned"]
        rows.append(
            f"{float(north):.4f} {float(east):.4f} {-float(down):.4f} "
            f"{red} {green} {blue} {index}\n"
        )
    return "".join(rows)


def _semantic_markers(semantic_objects):
    return [
        item
        for item in semantic_objects
        if isinstance(item, dict) and len(item.get("position_ned", [])) == 3
    ]


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


def read_snapshot(directory, retries: int = 5, retry_delay: float = 0.01):
    """Read a version-consistent (metadata, points) pair.

    ``latest.json`` is written atomically *after* the NPY payload and the
    payload filename embeds the manifest ``sequence``.  Resolving the payload
    name through the manifest therefore guarantees the index and the data come
    from the same publish; a reader that globs ``points_*.npy`` on its own can
    otherwise pair a fresh index with stale data.  Retries cover the narrow
    window where the writer has already rotated the payload out of the
    three-file retention window.
    """
    directory = Path(directory)
    last_error = None
    for _ in range(max(1, retries)):
        try:
            metadata = json.loads((directory / "latest.json").read_text("utf-8"))
        except FileNotFoundError as error:
            last_error = error
            time.sleep(retry_delay)
            continue
        sequence = int(metadata["sequence"])
        name = metadata["points"]
        if name != f"points_{sequence:06d}.npy":
            raise ValueError(
                f"manifest sequence {sequence} does not match payload {name}"
            )
        try:
            points = np.load(directory / name, allow_pickle=False)
        except FileNotFoundError as error:
            last_error = error
            time.sleep(retry_delay)
            continue
        return metadata, points
    if last_error is not None:
        raise last_error
    raise FileNotFoundError(directory / "latest.json")


def write_ply(path: Path, points, semantic_objects=()) -> None:
    """Export occupancy and semantic marker vertices in N/E/height-up axes."""
    values = np.asarray(points, dtype=np.float32).reshape((-1, 3))
    markers = _semantic_markers(semantic_objects)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = len(values) + len(markers)
    header = (
        "ply\nformat ascii 1.0\n"
        "comment axes north east height_up metres\n"
        f"element vertex {count}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property int semantic_id\nend_header\n"
    )
    if len(values):
        height = -values[:, 2].astype(np.float64)
        lo = float(height.min())
        span = max(0.1, float(height.max()) - lo)
        ratio = np.clip((height - lo) / span, 0.0, 1.0)
        red = (45.0 + 40.0 * ratio).astype(np.int64)
        green = (115.0 + 105.0 * ratio).astype(np.int64)
        blue = (145.0 + 90.0 * ratio).astype(np.int64)
        semantic_id = np.full(len(values), -1, dtype=np.int64)
        body = _format_vertices(
            values[:, 0], values[:, 1], -values[:, 2], red, green, blue, semantic_id
        )
    else:
        body = ""
    body += _format_markers(markers, 238, 180, 74)
    with path.open("w", encoding="ascii", newline="\n") as output:
        output.write(header)
        output.write(body)


def write_pcd(path: Path, points, semantic_objects=()) -> None:
    """Export an ASCII PCD scene in north/east/height-up coordinates."""
    values = np.asarray(points, dtype=np.float32).reshape((-1, 3))
    markers = _semantic_markers(semantic_objects)
    count = len(values) + len(markers)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# .PCD v0.7 - Point Cloud Data file format\n"
        "VERSION 0.7\n"
        "FIELDS x y z red green blue semantic_id\n"
        "SIZE 4 4 4 1 1 1 4\n"
        "TYPE F F F U U U I\n"
        "COUNT 1 1 1 1 1 1 1\n"
        f"WIDTH {count}\nHEIGHT 1\n"
        "VIEWPOINT 0 0 0 1 0 0 0\n"
        f"POINTS {count}\nDATA ascii\n"
    )
    if len(values):
        red = np.full(len(values), 54, dtype=np.int64)
        green = np.full(len(values), 154, dtype=np.int64)
        blue = np.full(len(values), 188, dtype=np.int64)
        semantic_id = np.full(len(values), -1, dtype=np.int64)
        body = _format_vertices(
            values[:, 0], values[:, 1], -values[:, 2], red, green, blue, semantic_id
        )
    else:
        body = ""
    body += _format_markers(markers, 238, 180, 74)
    with path.open("w", encoding="ascii", newline="\n") as output:
        output.write(header)
        output.write(body)
