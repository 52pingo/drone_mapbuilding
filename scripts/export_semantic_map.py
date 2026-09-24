#!/usr/bin/env python3
"""Combine a mission's map snapshot and its semantic objects into one map.

Both halves are produced by a CityPark run but they were never joined on the
command-line path: ``gui_map_bridge.py`` writes the octomap snapshot into
``<session>/live_map/``, and ``semantic_perception.py`` writes the tracked
objects into ``<session>/detected_classes/semantic_objects.json``.  The GUI
joins them in its session archiver; a headless run did not, so every exported
map came out with ``semantic_id`` of -1 on every point and the semantic layers
were effectively absent.

    python3 scripts/export_semantic_map.py results/citypark_semantic_20260923
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

try:
    from scripts.map_bridge_core import write_pcd, write_ply
except ImportError:  # run with scripts/ itself on sys.path
    from map_bridge_core import write_pcd, write_ply


FRAME = {
    "coordinate_frame": "px4_local_ned",
    "render_axes": "north_east_height_up",
}


def load_points(session: Path):
    """Read the newest occupancy snapshot the map bridge published."""
    latest = session / "live_map" / "latest.json"
    if not latest.is_file():
        raise FileNotFoundError(f"{latest} missing; did the map bridge run?")
    metadata = json.loads(latest.read_text(encoding="utf-8"))
    name = metadata.get("points")
    if not name:
        raise ValueError(f"{latest} has no 'points' entry")
    path = session / "live_map" / Path(str(name)).name
    points = np.load(path, allow_pickle=False)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError(f"{path}: expected an (N, 3) array, got {points.shape}")
    return points.astype(np.float32, copy=False), metadata


def load_objects(session: Path):
    """Find the tracked semantic objects, whichever directory wrote them."""
    for candidate in (session / "detected_classes" / "semantic_objects.json",
                      session / "semantic_objects.json"):
        if not candidate.is_file():
            continue
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        objects = payload.get("objects", []) if isinstance(payload, dict) else []
        return [item for item in objects if isinstance(item, dict)], candidate
    return [], None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--radius", type=float, default=None,
                        help="metres a point may sit from an object centre")
    parser.add_argument("--check", action="store_true",
                        help="run check_acceptance.py on the result")
    args = parser.parse_args()

    session = args.session
    if not session.is_dir():
        print(f"找不到会话目录: {session}")
        return 2

    points, metadata = load_points(session)
    objects, source = load_objects(session)

    # write_ply/write_pcd take the radius through, so pass it only when set.
    extra = {} if args.radius is None else {"semantic_radius": args.radius}
    ply = session / "semantic_map.ply"
    pcd = session / "semantic_map.pcd"
    write_ply(ply, points, objects, **extra)
    write_pcd(pcd, points, objects, **extra)

    (session / "semantic_objects.json").write_text(json.dumps({
        **FRAME,
        "objects": list(objects),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    from collections import Counter
    histogram = Counter(item.get("label") for item in objects)
    print(f"会话       {session}")
    print(f"占据点     {len(points)}  (快照 {metadata.get('points')})")
    print(f"语义对象   {len(objects)}  来自 {source if source else '（没有找到）'}")
    if histogram:
        print("            " + ", ".join(
            f"{name}×{count}" for name, count in histogram.most_common()))
    print(f"写出       {ply.name} / {pcd.name} / semantic_objects.json")

    if args.check:
        from check_acceptance import evaluate
        checks = evaluate(ply, session / "semantic_objects.json")
        failed = 0
        skipped = 0
        for item in checks:
            if item["passed"] is None:
                mark, skipped = "SKIP", skipped + 1
            else:
                mark = "PASS" if item["passed"] else "FAIL"
                failed += 0 if item["passed"] else 1
            print(f"  [{mark}] {item['criterion']:<38} {item['detail']}")
        print(f"\n通过 {len(checks)-failed-skipped}，不通过 {failed}，跳过 {skipped}")
        return 1 if failed else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
