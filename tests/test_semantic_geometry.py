import math

import pytest

from scripts.semantic_geometry import (
    SemanticObjectTracker, project_box_center_ned, project_box_extent_ned,
    rotate_by_quaternion,
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


def test_box_extent_scales_with_depth_and_pixel_size():
    """World size = depth * pixels / focal, so both must move it."""
    near = project_box_extent_ned((300, 140, 340, 180), 10.0, (240, 320, 3), 90.0)
    far = project_box_extent_ned((300, 140, 340, 180), 20.0, (240, 320, 3), 90.0)
    assert near is not None and far is not None
    # 40 px wide at 10m with fx = 160 -> 2.5m across, so half of 1.25m.
    assert near[0] == pytest.approx(1.25, abs=0.01)
    assert near[1] == pytest.approx(1.25, abs=0.01)
    assert far[0] == pytest.approx(2.5, abs=0.01)

    wider = project_box_extent_ned((280, 140, 360, 180), 10.0, (240, 320, 3), 90.0)
    assert wider[0] > near[0]


def test_box_extent_rejects_unusable_depth():
    assert project_box_extent_ned((0, 0, 10, 10), None, (240, 320, 3), 90.0) is None
    assert project_box_extent_ned((0, 0, 10, 10), 0.0, (240, 320, 3), 90.0) is None
    assert project_box_extent_ned(
        (0, 0, 10, 10), float("inf"), (240, 320, 3), 90.0) is None
    assert project_box_extent_ned((0, 0, 10, 10), 5.0, (0, 0, 3), 90.0) is None


def test_tracker_extent_is_a_median_so_one_bad_box_cannot_inflate_it():
    """Taking the max let a single far/loose box blow an object up for good.

    Measured 2026-09-25: with max(), trees came out with a median half-width of
    13.6m and a worst case of 58.5m; 551 of those boxes covered the whole map
    and 99.2% of every point was labelled -- which passed all the shape
    criteria while being a painted map rather than a mapped one.
    """
    tracker = SemanticObjectTracker(merge_distance=2.0)
    honest = [5.0, 5.4, 4.8, 5.2, 5.1]
    for index, width in enumerate(honest):
        tracker.update([Detection(3, "building", 0.8, (0, 0, 200, 200), 20.0,
                                  (0.0, 0.0, 0.0), (width, width / 2))],
                       seen_at=float(index))
    # ...then one wild observation from far away.
    tracker.update([Detection(3, "building", 0.8, (0, 0, 200, 200), 60.0,
                              (0.0, 0.0, 0.0), (40.0, 30.0))], seen_at=99.0)

    object_ = tracker.snapshot()[0]
    assert object_["half_width"] == pytest.approx(5.2, abs=0.45)
    assert object_["half_height"] < 4.0


def test_a_single_observation_is_also_capped():
    """Regression: the cap used to live only on the merge path.

    The median object is seen once, so it never merged and never met the cap.
    Measured 2026-09-25: trees kept a median half-width of 13.3m against a 7m
    cap, 630 of those boxes covered 841,424 m^2, and 97.2% of every point was
    labelled -- passing the shape criteria by painting the map.
    """
    from scripts.uav_semantic_schema import max_half_extent_m
    tracker = SemanticObjectTracker(merge_distance=2.0)
    tracker.update([Detection(9, "tree", 0.8, (0, 0, 400, 300), 60.0,
                              (0.0, 0.0, 0.0), (40.0, 30.0))], seen_at=0.0)
    object_ = tracker.snapshot()[0]
    assert object_["observations"] == 1
    assert object_["half_width"] == pytest.approx(max_half_extent_m("tree"))
    assert object_["half_height"] == pytest.approx(max_half_extent_m("tree"))


def test_tracker_extent_is_capped_by_the_class():
    """Even after the median, a class gets no more than it plausibly occupies."""
    from scripts.uav_semantic_schema import max_half_extent_m
    tracker = SemanticObjectTracker(merge_distance=2.0)
    for index in range(4):
        tracker.update([Detection(9, "tree", 0.8, (0, 0, 400, 300), 40.0,
                                  (0.0, 0.0, 0.0), (30.0, 25.0))],
                       seen_at=float(index))
    object_ = tracker.snapshot()[0]
    cap = max_half_extent_m("tree")
    assert object_["half_width"] == pytest.approx(cap)
    assert object_["half_height"] == pytest.approx(cap)


def test_max_half_extent_falls_back_for_unknown_labels():
    from scripts.uav_semantic_schema import (
        DEFAULT_MAX_HALF_EXTENT_M, max_half_extent_m,
    )
    assert max_half_extent_m("tree") < DEFAULT_MAX_HALF_EXTENT_M
    assert max_half_extent_m("unicorn") == pytest.approx(DEFAULT_MAX_HALF_EXTENT_M)


def test_tracker_extent_falls_back_to_a_floor_when_unknown():
    """An unsized detection still has to label something."""
    tracker = SemanticObjectTracker(merge_distance=2.0)
    tracker.update([Detection(9, "tree", 0.8, (0, 0, 5, 5), 30.0,
                              (1.0, 1.0, 0.0))], seen_at=0.0)
    object_ = tracker.snapshot()[0]
    assert object_["half_width"] == SemanticObjectTracker.MIN_HALF_WIDTH_M
    assert object_["half_height"] == SemanticObjectTracker.MIN_HALF_HEIGHT_M


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
