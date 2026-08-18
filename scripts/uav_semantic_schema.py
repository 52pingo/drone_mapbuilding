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
