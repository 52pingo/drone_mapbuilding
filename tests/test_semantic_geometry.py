import math

import pytest

from scripts.semantic_geometry import (
    SemanticObjectTracker, project_box_center_ned, rotate_by_quaternion,
)
from scripts.semantic_perception import Detection


def test_center_pixel_projects_forward_in_ned():
    point = project_box_center_ned(
        (310, 170, 330, 190), 10.0, (360, 640, 3), 90.0,
        (2.0, 3.0, -5.0), (1.0, 0.0, 0.0, 0.0),
    )
    assert point == pytest.approx((12.0, 3.0, -5.0), abs=0.02)


def test_projection_rejects_non_finite_depth_or_pose():
    arguments = ((0, 0, 10, 10), 5.0, (20, 20, 3), 90.0)
    assert project_box_center_ned(
        *arguments, (0, 0, 0), (float("nan"), 0, 0, 0)
    ) is None
    assert project_box_center_ned(
        arguments[0], float("inf"), *arguments[2:], (0, 0, 0), (1, 0, 0, 0)
    ) is None


def test_quaternion_yaw_rotates_forward_toward_east():
    half = math.sqrt(0.5)
    assert rotate_by_quaternion((4, 0, 0), (half, 0, 0, half)) == (
        pytest.approx(0.0), pytest.approx(4.0), pytest.approx(0.0)
    )


def test_semantic_tracker_merges_nearby_same_class_only():
    tracker = SemanticObjectTracker(merge_distance=4.0)
    tracker.update([
        Detection(9, "tree", 0.8, (0, 0, 1, 1), 5.0, (10.0, 2.0, -1.0)),
        Detection(9, "tree", 0.9, (0, 0, 1, 1), 5.0, (11.0, 2.0, -1.0)),
        Detection(3, "car", 0.7, (0, 0, 1, 1), 5.0, (10.0, 2.0, -1.0)),
    ], seen_at=20.0)
    objects = tracker.snapshot()
    assert len(objects) == 2
    tree = next(item for item in objects if item["label"] == "tree")
    assert tree["observations"] == 2
    assert tree["max_confidence"] == 0.9
