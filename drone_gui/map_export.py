"""Export the current 3D occupancy and semantic scene."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.map_bridge_core import write_ply


def export_map(directory: Path, points, semantic_objects, image=None) -> list[Path]:
    """Write PLY, semantic JSON, and an optional rendered PNG."""
    directory.mkdir(parents=True, exist_ok=True)
    ply_path = directory / "semantic_map.ply"
    json_path = directory / "semantic_objects.json"
    write_ply(ply_path, points, semantic_objects)
    json_path.write_text(json.dumps({
        "coordinate_frame": "px4_local_ned",
        "render_axes": "north_east_height_up",
        "objects": list(semantic_objects),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    outputs = [ply_path, json_path]
    if image is not None and not image.isNull():
        image_path = directory / "semantic_map_view.png"
        if image.save(str(image_path), "PNG"):
            outputs.append(image_path)
    return outputs
