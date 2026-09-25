"""Pure point-cloud conversion and atomic snapshot helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time

import numpy as np

try:  # normal case: imported as ``scripts.map_bridge_core``
    from scripts.uav_semantic_schema import CLASS_TO_ID
except ImportError:  # run with ``scripts/`` itself on sys.path
    from uav_semantic_schema import CLASS_TO_ID


# Fallback radius for objects that carry no extent -- either older snapshots or
# detections the camera could not size.  Objects with a half_width/half_height
# are labelled by their own box instead; see assign_semantic_ids.
SEMANTIC_ASSIGN_RADIUS_M = 3.0

# Chunk size for the point-to-object distance sweep.  2.5M points against ~20
# objects is 50M float32 distances if done in one shot; blocking keeps the
# temporary under a few tens of MB.
_SEMANTIC_CHUNK = 200_000

# Deliberately off the blue/teal height ramp, so a tagged point reads as tagged
# at a glance in the exported cloud.
SEMANTIC_CLASS_COLORS = {
    "tree": (58, 138, 62),
    "shrub": (34, 92, 46),
    "building": (156, 156, 162),
    "fence": (216, 186, 62),
    "pole": (130, 128, 124),
    "playground_equipment": (206, 118, 54),
    "bench": (150, 104, 66),
    "barrier": (196, 92, 52),
    "rock": (110, 108, 104),
    "bridge": (120, 130, 150),
}
SEMANTIC_FALLBACK_COLOR = (198, 88, 150)


def _class_id_for_label(label) -> int:
    """Map a tracker label onto the shared class schema; -1 when unknown."""
    if not isinstance(label, str):
        return -1
    return int(CLASS_TO_ID.get(label, -1))


def _class_color_for_label(label):
    if label in SEMANTIC_CLASS_COLORS:
        return SEMANTIC_CLASS_COLORS[label]
    return SEMANTIC_FALLBACK_COLOR


def _labeled_objects(semantic_objects):
    """Collect (class_id, colour, centre, half_width, half_height).

    ``half_width``/``half_height`` are None for objects that predate extents
    (or whose detector could not size them); those fall back to a sphere.
    """
    collected = []
    for item in semantic_objects:
        if not isinstance(item, dict):
            continue
        position = item.get("position_ned")
        if not isinstance(position, (list, tuple)) or len(position) != 3:
            continue
        class_id = _class_id_for_label(item.get("label"))
        if class_id < 0:
            continue
        try:
            centre = [float(value) for value in position]
        except (TypeError, ValueError):
            continue
        extent = None
        if item.get("half_width") and item.get("half_height"):
            try:
                extent = (float(item["half_width"]), float(item["half_height"]))
            except (TypeError, ValueError):
                extent = None
        collected.append((
            class_id,
            _class_color_for_label(item.get("label")),
            centre,
            extent[0] if extent else None,
            extent[1] if extent else None,
        ))
    return collected


def assign_semantic_ids(points, semantic_objects, radius=None) -> np.ndarray:
    """Label each point with the class of the object whose box contains it.

    ``points`` and the objects' ``position_ned`` must share a frame -- both are
    PX4 local NED here.

    An object that carries ``half_width``/``half_height`` is treated as an
    axis-aligned box centred on its position: horizontally within half_width
    (in the north/east plane) and vertically within half_height.  Objects
    without an extent fall back to a sphere of ``radius``, which is what the
    caller tuned before extents existed.

    Extents matter because a sphere labels a blob, not the object: measured on
    a real run, buildings came out as 3.9m-tall lumps with no vertical facade
    and fences failed a straight-line fit by 0.52m -- both because the ball
    around each centre is wider than the thing being labelled.

    Overlaps go to the object the point sits deepest inside relative to that
    object's own size, so a fence post is not swallowed by the building behind
    it.  Ties keep the earlier object.
    """
    values = np.asarray(points, dtype=np.float32).reshape((-1, 3))
    ids = np.full(len(values), -1, dtype=np.int64)
    objects = _labeled_objects(semantic_objects)
    if not len(values) or not objects:
        return ids

    limit = SEMANTIC_ASSIGN_RADIUS_M if radius is None else float(radius)
    if limit <= 0.0:
        raise ValueError("semantic radius must be positive")

    for start in range(0, len(values), _SEMANTIC_CHUNK):
        block = values[start:start + _SEMANTIC_CHUNK]
        rows = np.arange(len(block))
        best = np.full(len(block), np.inf, dtype=np.float64)
        for class_id, _color, centre, half_width, half_height in objects:
            delta = block - np.asarray(centre, dtype=np.float32)
            horizontal = np.maximum(np.abs(delta[:, 0]), np.abs(delta[:, 1]))
            vertical = np.abs(delta[:, 2])
            if half_width is None:
                distance = np.hypot(horizontal, vertical)
                inside = distance <= limit
                score = distance / limit
            else:
                inside = (horizontal <= half_width) & (vertical <= half_height)
                score = np.maximum(horizontal / max(half_width, 1e-6),
                                   vertical / max(half_height, 1e-6))
            better = inside & (score < best)
            best[better] = score[better]
            ids[start + rows[better]] = class_id
    return ids


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


def world_ned_to_local_ned(points, world_origin_ned=(0.0, 0.0, 0.0)) -> np.ndarray:
    """Shift world NED points into PX4 local NED.

    No axis swap and no sign flip: the cloud is already north/east/down, only
    the origin moves.  Running it through the ENU path instead transposes the
    map, which is invisible in the point count but puts every point in the
    wrong place on the ground.
    """
    values = np.asarray(points, dtype=np.float32).reshape((-1, 3))
    origin = np.asarray(world_origin_ned, dtype=np.float32).reshape(3)
    return (values - origin).astype(np.float32, copy=False)


def frame_to_local_ned(points, frame_id, world_origin_ned=(0.0, 0.0, 0.0)
                       ) -> np.ndarray:
    """Convert a cloud expressed in ``frame_id`` into PX4 local NED.

    Picks the conversion from the frame name instead of assuming ENU.  An
    unrecognised frame raises rather than guessing: silently applying the wrong
    handedness produces a plausible-looking map in the wrong place, which is
    exactly the bug this replaces.
    """
    name = (frame_id or "").strip().lower().lstrip("/")
    if name.endswith("enu"):
        return world_enu_to_local_ned(points, world_origin_ned)
    if name.endswith("ned"):
        return world_ned_to_local_ned(points, world_origin_ned)
    raise ValueError(
        f"map snapshot frame must end in 'enu' or 'ned', got {frame_id!r}")


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
    """Render semantic marker rows; markers are few so a loop is fine.

    The semantic_id column carries the marker's *class* id, not its index.
    Index ids used to be written here, which collided head-on with the class
    ids used for occupancy points: a marker at index 9 was indistinguishable
    from a real tree (``CLASS_TO_ID["tree"] == 9``) and inflated the
    per-class acceptance counts.  Individual objects stay addressable through
    ``semantic_objects.json``, which lists every marker with its own id.
    """
    if not markers:
        return ""
    rows = []
    for item in markers:
        north, east, down = item["position_ned"]
        rows.append(
            f"{float(north):.4f} {float(east):.4f} {-float(down):.4f} "
            f"{red} {green} {blue} {_class_id_for_label(item.get('label'))}\n"
        )
    return "".join(rows)


def _semantic_markers(semantic_objects):
    return [
        item
        for item in semantic_objects
        if isinstance(item, dict) and len(item.get("position_ned", [])) == 3
    ]


def snapshot_sequence(path) -> int | None:
    """Parse the integer sequence out of a ``points_<seq>.npy`` file name.

    Returns ``None`` for anything that does not match the snapshot naming
    scheme.  Always sort/compare snapshots through this helper: the raw file
    name is zero padded but *lexicographic* order still diverges from numeric
    order once the width overflows (``points_1000000.npy`` < ``points_999999.npy``).
    """
    name = Path(path).name
    prefix = "points_"
    suffix = ".npy"
    if not name.startswith(prefix) or not name.endswith(suffix):
        return None
    digits = name[len(prefix) : len(name) - len(suffix)]
    if not digits.isdigit():
        return None
    return int(digits)


def _snapshot_files(directory: Path):
    """Return ``(sequence, path)`` pairs for every well-formed snapshot."""
    found = []
    for path in Path(directory).glob("points_*.npy"):
        sequence = snapshot_sequence(path)
        if sequence is not None:
            found.append((sequence, path))
    return found


def _latest_sequence(directory: Path) -> int:
    """Highest sequence already on disk, or 0 when the directory is empty."""
    return max((sequence for sequence, _ in _snapshot_files(directory)), default=0)


class MapSnapshotWriter:
    """Write NPY first and metadata last, retaining three complete snapshots."""

    def __init__(self, directory: Path, max_points: int = 80000) -> None:
        self.directory = directory
        self.max_points = max_points
        self.directory.mkdir(parents=True, exist_ok=True)
        # Resume numbering from whatever survived the previous process so a
        # restart never re-uses (and therefore never clobbers) an existing
        # snapshot name.
        self.sequence = _latest_sequence(self.directory)

    def publish(
        self,
        points_in,
        frame_id: str = "world_enu",
        world_origin_ned=(0.0, 0.0, 0.0),
    ) -> dict:
        self.sequence += 1
        original_count = len(points_in)
        points = finite_downsample(
            frame_to_local_ned(points_in, frame_id, world_origin_ned),
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
        self._rotate()
        return metadata

    def _rotate(self, keep: int = 3) -> None:
        """Delete all but the ``keep`` numerically newest snapshots."""
        snapshots = _snapshot_files(self.directory)
        snapshots.sort(key=lambda item: item[0])
        for _, old in snapshots[:-keep]:
            try:
                old.unlink()
            except OSError:
                pass


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


def write_ply(path: Path, points, semantic_objects=(), semantic_radius=None) -> None:
    """Export occupancy and semantic marker vertices in N/E/height-up axes.

    Occupancy points near a tracked object are tagged with that object's class
    id and painted in the class colour; everything else keeps the height ramp
    and a semantic_id of -1.
    """
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
        semantic_id = assign_semantic_ids(values, semantic_objects, semantic_radius)
        tagged = semantic_id >= 0
        if tagged.any():
            palette = {}
            for object_id, color, _, _, _ in _labeled_objects(semantic_objects):
                palette.setdefault(object_id, color)
            keys = np.asarray(sorted(palette), dtype=np.int64)
            table = np.asarray([palette[int(key)] for key in keys], dtype=np.int64)
            picked = table[np.searchsorted(keys, semantic_id[tagged])]
            red[tagged] = picked[:, 0]
            green[tagged] = picked[:, 1]
            blue[tagged] = picked[:, 2]
        body = _format_vertices(
            values[:, 0], values[:, 1], -values[:, 2], red, green, blue, semantic_id
        )
    else:
        body = ""
    body += _format_markers(markers, 238, 180, 74)
    with path.open("w", encoding="ascii", newline="\n") as output:
        output.write(header)
        output.write(body)


def write_pcd(path: Path, points, semantic_objects=(), semantic_radius=None) -> None:
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
        semantic_id = assign_semantic_ids(values, semantic_objects, semantic_radius)
        tagged = semantic_id >= 0
        if tagged.any():
            palette = {}
            for object_id, color, _, _, _ in _labeled_objects(semantic_objects):
                palette.setdefault(object_id, color)
            keys = np.asarray(sorted(palette), dtype=np.int64)
            table = np.asarray([palette[int(key)] for key in keys], dtype=np.int64)
            picked = table[np.searchsorted(keys, semantic_id[tagged])]
            red[tagged] = picked[:, 0]
            green[tagged] = picked[:, 1]
            blue[tagged] = picked[:, 2]
        body = _format_vertices(
            values[:, 0], values[:, 1], -values[:, 2], red, green, blue, semantic_id
        )
    else:
        body = ""
    body += _format_markers(markers, 238, 180, 74)
    with path.open("w", encoding="ascii", newline="\n") as output:
        output.write(header)
        output.write(body)
