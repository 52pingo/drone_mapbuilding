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


def test_tracker_default_gate_keeps_a_bad_box_from_dragging_the_centre():
    """4.0m let one bad box move a sparsely observed object past the 1.0m bar."""
    assert SemanticObjectTracker.DEFAULT_MERGE_DISTANCE == pytest.approx(2.0)
    tracker = SemanticObjectTracker()
    assert tracker.merge_distance == pytest.approx(2.0)
    # A detection 2.5m out must start a new object rather than merge.
    tracker.update([Detection(9, "tree", 0.8, (0, 0, 1, 1), 5.0,
                              (0.0, 0.0, 0.0))], seen_at=0.0)
    tracker.update([Detection(9, "tree", 0.8, (0, 0, 1, 1), 5.0,
                              (2.5, 0.0, 0.0))], seen_at=1.0)
    assert len(tracker.snapshot()) == 2


def test_tracker_trail_records_the_centroid_not_the_raw_detection():
    """The drift criterion is about the tracked centroid, not detector noise.

    Storing raw per-frame estimates made one bad box -- which projects metres
    off -- look like the object had moved, so the criterion measured the
    detector rather than the tracker.
    """
    tracker = SemanticObjectTracker(merge_distance=4.0)
    tracker.update([Detection(9, "tree", 0.8, (0, 0, 1, 1), 5.0,
                              (0.0, 0.0, 0.0))], seen_at=0.0)
    # A wildly wrong estimate for the same tree, still within merge distance.
    tracker.update([Detection(9, "tree", 0.8, (0, 0, 1, 1), 5.0,
                              (3.0, 0.0, 0.0))], seen_at=1.0)

    trail = tracker.snapshot()[0]["trail"]
    assert [entry["position_ned"][0] for entry in trail] == [0.0, 1.5]
    # The raw 3.0m observation must not appear as a track position.
    assert all(entry["position_ned"][0] != 3.0 for entry in trail)


def test_tracker_trail_is_bounded():
    tracker = SemanticObjectTracker(merge_distance=4.0)
    for step in range(SemanticObjectTracker.TRAIL_LIMIT + 10):
        tracker.update([Detection(9, "tree", 0.8, (0, 0, 1, 1), 5.0,
                                  (0.0, 0.0, 0.0))], seen_at=float(step))
    trail = tracker.snapshot()[0]["trail"]
    assert len(trail) == SemanticObjectTracker.TRAIL_LIMIT
    # The newest observation is kept, the oldest dropped.
    assert trail[-1]["seen_at"] == float(SemanticObjectTracker.TRAIL_LIMIT + 9)
