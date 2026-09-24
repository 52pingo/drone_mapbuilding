#!/usr/bin/env python3
"""Render an exported semantic map into a four-panel PNG for review.

Panels, clockwise from top-left:
  by class    top-down, coloured by semantic class (grey = untagged occupancy)
  by height   top-down, coloured by the height ramp -- shows terrain relief
  elevation   side view along north, which is where a clipped map gives itself away
  histogram   height distribution; a single spike means the map is a sheet

Self-contained PNG writer (zlib) so this does not depend on matplotlib.

    python3 scripts/render_semantic_map.py results/.../semantic_map.ply
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

try:
    from scripts.check_acceptance import read_ascii_ply
    from scripts.map_bridge_core import SEMANTIC_CLASS_COLORS
    from scripts.uav_semantic_schema import CLASSES
except ImportError:  # run with scripts/ itself on sys.path
    from check_acceptance import read_ascii_ply
    from map_bridge_core import SEMANTIC_CLASS_COLORS
    from uav_semantic_schema import CLASSES


PANEL = 620
GUTTER = 16
BACKGROUND = (16, 18, 22)
GRID = (44, 48, 56)
UNTAGGED = (96, 100, 108)


def write_png(path: Path, rgb: np.ndarray) -> None:
    height, width, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(height))

    def chunk(tag, data):
        payload = tag + data
        return (struct.pack(">I", len(data)) + payload
                + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def height_colors(z):
    lo, hi = float(z.min()), float(z.max())
    t = np.clip((z - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
    red = np.clip(1.5 - np.abs(4 * t - 3), 0, 1)
    green = np.clip(1.5 - np.abs(4 * t - 2), 0, 1)
    blue = np.clip(1.5 - np.abs(4 * t - 1), 0, 1)
    return (np.stack([red, green, blue], axis=-1) * 255).astype(np.uint8)


def class_colors(ids):
    """Palette indexed by class id, grey for untagged."""
    palette = np.tile(np.array(UNTAGGED, dtype=np.uint8), (max(ids.max() + 1, 1), 1))
    for class_id, name in enumerate(CLASSES):
        if class_id < len(palette) and name in SEMANTIC_CLASS_COLORS:
            palette[class_id] = SEMANTIC_CLASS_COLORS[name]
    safe = np.where(ids >= 0, ids, 0)
    colors = palette[np.clip(safe, 0, len(palette) - 1)].copy()
    colors[ids < 0] = UNTAGGED
    return colors


def scatter(a, b, colors, size=PANEL, pad=26, flip_b=True):
    panel = np.full((size, size, 3), BACKGROUND, dtype=np.uint8)
    for tick in range(0, size, size // 6):
        panel[tick, :] = GRID
        panel[:, tick] = GRID
    if not len(a):
        return panel
    lo_a, hi_a = float(a.min()), float(a.max())
    lo_b, hi_b = float(b.min()), float(b.max())
    span = max(hi_a - lo_a, hi_b - lo_b, 1e-6)
    scale = (size - 2 * pad) / span
    off_a = pad + (size - 2 * pad - (hi_a - lo_a) * scale) / 2
    off_b = pad + (size - 2 * pad - (hi_b - lo_b) * scale) / 2
    ia = ((a - lo_a) * scale + off_a).astype(np.int64)
    ib = (((hi_b - b) if flip_b else (b - lo_b)) * scale + off_b).astype(np.int64)
    ok = (ia >= 0) & (ia < size) & (ib >= 0) & (ib < size)
    panel[ib[ok], ia[ok]] = colors[ok]
    return panel


def histogram(z, size=PANEL):
    panel = np.full((size, size, 3), BACKGROUND, dtype=np.uint8)
    counts, edges = np.histogram(z, bins=60)
    peak = max(int(counts.max()), 1)
    colors = height_colors(0.5 * (edges[:-1] + edges[1:]))
    bar_w = (size - 2 * 26) / len(counts)
    for index, count in enumerate(counts):
        x0 = int(26 + index * bar_w)
        x1 = max(x0 + 1, int(26 + (index + 1) * bar_w))
        top = int((size - 40) - (size - 70) * count / peak)
        panel[top:size - 40, x0:x1] = colors[index]
    panel[size - 40, :] = GRID
    return panel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ply", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if not args.ply.is_file():
        print(f"找不到 PLY: {args.ply}")
        return 2
    out = args.out or args.ply.parent / "semantic_map_view.png"

    xyz, ids = read_ascii_ply(args.ply)
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    print(f"点 {len(xyz)}   x[{x.min():.0f},{x.max():.0f}] "
          f"y[{y.min():.0f},{y.max():.0f}] z[{z.min():.2f},{z.max():.2f}]")

    order = np.argsort(z)  # draw low first so peaks stay visible
    size = PANEL * 2 + GUTTER
    canvas = np.full((size, size, 3), (8, 9, 11), dtype=np.uint8)
    canvas[:PANEL, :PANEL] = scatter(x[order], y[order], class_colors(ids)[order])
    canvas[:PANEL, PANEL + GUTTER:] = scatter(
        x[order], y[order], height_colors(z)[order])
    canvas[PANEL + GUTTER:, :PANEL] = scatter(x[order], z[order], class_colors(ids)[order])
    canvas[PANEL + GUTTER:, PANEL + GUTTER:] = histogram(z)
    write_png(out, canvas)
    print(f"已写 {out}")

    tagged = ids >= 0
    print(f"\n带类别点 {int(tagged.sum())} / {len(ids)} "
          f"({100.0 * tagged.sum() / len(ids):.1f}%)")
    for class_id, name in enumerate(CLASSES):
        count = int((ids == class_id).sum())
        if count:
            print(f"  {name:24s} {count:8d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
