#!/usr/bin/env python3
"""Shared class schema and source-dataset mappings for UAV semantics."""

from __future__ import annotations


CLASSES = [
    "person",
    "bicycle",
    "motorcycle",
    "car",
    "van",
    "bus",
    "truck",
    "tricycle",
    "dog",
    "tree",
    "shrub",
    "building",
    "fence",
    "pole",
    "traffic_sign",
    "traffic_light",
    "cone",
    "barrier",
    "fire_hydrant",
    "trash_bin",
    "bench",
    "rock",
    "bridge",
    "crosswalk",
    "blind_road",
    "playground_equipment",
    "umbrella",
]

CLASS_TO_ID = {name: index for index, name in enumerate(CLASSES)}


ROAD20_NAMES = [
    "car",
    "dog",
    "person",
    "bus",
    "truck",
    "green_light",
    "pole",
    "sign",
    "warning_column",
    "tree",
    "red_light",
    "fire_hydrant",
    "motorcycle",
    "ashcan",
    "bicycle",
    "reflective_cone",
    "blind_road",
    "crosswalk",
    "tricycle",
    "roadblock",
]

ROAD20_TO_TARGET = {
    0: CLASS_TO_ID["car"],
    1: CLASS_TO_ID["dog"],
    2: CLASS_TO_ID["person"],
    3: CLASS_TO_ID["bus"],
    4: CLASS_TO_ID["truck"],
    5: CLASS_TO_ID["traffic_light"],
    6: CLASS_TO_ID["pole"],
    7: CLASS_TO_ID["traffic_sign"],
    8: CLASS_TO_ID["cone"],
    9: CLASS_TO_ID["tree"],
    10: CLASS_TO_ID["traffic_light"],
    11: CLASS_TO_ID["fire_hydrant"],
    12: CLASS_TO_ID["motorcycle"],
    13: CLASS_TO_ID["trash_bin"],
    14: CLASS_TO_ID["bicycle"],
    15: CLASS_TO_ID["cone"],
    16: CLASS_TO_ID["blind_road"],
    17: CLASS_TO_ID["crosswalk"],
    18: CLASS_TO_ID["tricycle"],
    19: CLASS_TO_ID["barrier"],
}


# Standard VisDrone2019-DET YOLO order used by the local converted dataset.
VISDRONE_NAMES = [
    "pedestrian",
    "people",
    "bicycle",
    "car",
    "van",
    "truck",
    "tricycle",
    "awning-tricycle",
    "bus",
    "motor",
]

VISDRONE_TO_TARGET = {
    0: CLASS_TO_ID["person"],
    1: CLASS_TO_ID["person"],
    2: CLASS_TO_ID["bicycle"],
    3: CLASS_TO_ID["car"],
    4: CLASS_TO_ID["van"],
    5: CLASS_TO_ID["truck"],
    6: CLASS_TO_ID["tricycle"],
    7: CLASS_TO_ID["tricycle"],
    8: CLASS_TO_ID["bus"],
    9: CLASS_TO_ID["motorcycle"],
}


# 每类物体在世界系下合理的**半**尺寸上限（米），用来给单目估计出来的体积兜底。
#
# 单目只能给出「深度 × 像素尺寸 / 焦距」，而框里常常混着背景，深度取的又是稳健
# 统计量，于是远处或框偏大的观测会把物体估爆。2026-09-25 实测：不设上限时 tree
# 的半宽中位数是 13.6m、最大 58.5m（一棵 117m 宽的树），551 个树盒子把整张图盖住，
# 语义标注率 99.2% —— 判据全过，但那是把地图涂成了树，不是地图。
#
# 上限取得宽松（真实物体不会超过），目的是挡住数量级错误，不是精细塑形。
DEFAULT_MAX_HALF_EXTENT_M = 8.0

CLASS_MAX_HALF_EXTENT_M = {
    "person": 1.2,
    "bicycle": 1.5,
    "motorcycle": 1.5,
    "car": 3.0,
    "van": 3.5,
    "truck": 6.0,
    "bus": 7.0,
    "tricycle": 1.5,
    "dog": 1.0,
    # 树冠实测 5~8m 宽（半宽 2.5~4）；7m 太大，630 个树盒子会铺掉大半个园区。
    "tree": 4.0,
    "shrub": 3.0,
    "building": 25.0,
    "fence": 4.0,
    "pole": 1.0,
    "traffic_sign": 1.0,
    "traffic_light": 1.0,
    "cone": 1.0,
    "barrier": 2.0,
    "fire_hydrant": 1.0,
    "trash_bin": 1.0,
    "bench": 2.0,
    "rock": 3.0,
    "bridge": 25.0,
    "crosswalk": 8.0,
    "blind_road": 4.0,
    "playground_equipment": 8.0,
    "umbrella": 2.0,
}


def max_half_extent_m(label: str, default: float = DEFAULT_MAX_HALF_EXTENT_M
                      ) -> float:
    """该类物体合理的半尺寸上限；未知类别用 ``default``。"""
    return float(CLASS_MAX_HALF_EXTENT_M.get(label, default))
