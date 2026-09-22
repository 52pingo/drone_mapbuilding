#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 GUI 会话目录里的 OctoMap 快照渲染成俯视图。

数据就是 GUI 自己读的那份 points_*.npy，所以这张图 = 软件里应该显示的东西。
用 Qt 的 QImage 出图，避免依赖 matplotlib（GUI venv 里没装）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage, QColor, QPainter, QFont, QPen
from PySide6.QtCore import Qt

SESSION = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "E:/无人机视觉避障建图/.publish_repo/results/octomap_demo")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
    "E:/无人机视觉避障建图/.publish_repo/results/octomap_demo/octomap_topdown.png")

live = SESSION / "live_map"
latest = json.loads((live / "latest.json").read_text(encoding="utf-8"))
print("latest.json 内容:", json.dumps(latest, ensure_ascii=False)[:300])

name = latest.get("points") or latest.get("file") or latest.get("npy")
cand = [p for p in [name, latest.get("snapshot"), latest.get("points_file")] if p]
npy = None
for c in cand:
    p = live / Path(str(c)).name
    if p.is_file():
        npy = p
        break
if npy is None:
    files = sorted(live.glob("points_*.npy"))
    if not files:
        print("没有找到快照文件"); sys.exit(1)
    npy = files[-1]
print("使用快照:", npy.name)

arr = np.load(npy)
print("数组形状:", arr.shape, "dtype:", arr.dtype)
if arr.dtype.names:
    x = arr["x"].astype(float); y = arr["y"].astype(float); z = arr["z"].astype(float)
else:
    x = arr[:, 0].astype(float); y = arr[:, 1].astype(float); z = arr[:, 2].astype(float)

ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
x, y, z = x[ok], y[ok], z[ok]
print(f"有效点 {len(x)}   x∈[{x.min():.1f},{x.max():.1f}]  y∈[{y.min():.1f},{y.max():.1f}]  z∈[{z.min():.1f},{z.max():.1f}]")

# 俯视图：x 向北朝上，y 向东朝右
W, H, PAD = 1200, 1100, 60
sx = (W - 2 * PAD) / max(1e-6, x.max() - x.min())
sy = (H - 2 * PAD) / max(1e-6, y.max() - y.min())
s = min(sx, sy)

img = QImage(W, H, QImage.Format_RGB32)
img.fill(QColor("#0f171c"))
painter = QPainter(img)
painter.setRenderHint(QPainter.Antialiasing, False)

zmin, zmax = float(z.min()), float(z.max())
zr = max(1e-6, zmax - zmin)
cx = (x.min() + x.max()) / 2
cy = (y.min() + y.max()) / 2

# 高度着色：低=青绿，高=黄
for xi, yi, zi in zip(x, y, z):
    px = int(W / 2 + (yi - cy) * s)
    py = int(H / 2 - (xi - cx) * s)
    if not (0 <= px < W and 0 <= py < H):
        continue
    t = (zi - zmin) / zr
    r = int(90 + 180 * t)
    g = int(210 - 40 * t)
    b = int(170 - 90 * t)
    img.setPixel(px, py, QColor(r, g, b).rgb())

# 起点/终点标记
ox = int(W / 2 + (0 - cy) * s)
oy = int(H / 2 - (0 - cx) * s)
painter.setPen(QPen(QColor("#ff8d86"), 3))
painter.drawLine(ox - 9, oy - 9, ox + 9, oy + 9)
painter.drawLine(ox - 9, oy + 9, ox + 9, oy - 9)

painter.setPen(QColor("#f2c56d"))
painter.setFont(QFont("Microsoft YaHei UI", 13))
painter.drawText(PAD, PAD - 22, f"OctoMap 俯视图 · {len(x)} 个占据点（软件会话里的同一份数据）")
painter.setFont(QFont("Microsoft YaHei UI", 10))
painter.setPen(QColor("#83959f"))
painter.drawText(PAD, H - 18,
                 f"x 向北↑ 范围[{x.min():.0f},{x.max():.0f}]m   y 向东→ 范围[{y.min():.0f},{y.max():.0f}]m   "
                 f"高度 z[{z.min():.1f},{z.max():.1f}]m   红叉=起降点(0,0)")
painter.end()

OUT.parent.mkdir(parents=True, exist_ok=True)
img.save(str(OUT))
print("已保存:", OUT)
