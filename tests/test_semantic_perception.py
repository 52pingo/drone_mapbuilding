from scripts.semantic_perception import (
    ClassEvidenceTracker,
    Detection,
    FirstSeenTracker,
    best_detection_per_class,
)


def detection(label, confidence=0.8):
    return Detection(0, label, confidence, (1, 2, 20, 30), 12.0)


def test_first_seen_requires_consecutive_confirmation():
    tracker = FirstSeenTracker(confirm_frames=2)
    assert tracker.update([detection("tree")]) == []
    events = tracker.update([detection("tree", 0.9)])
    assert [event.label for event in events] == ["tree"]
    assert tracker.update([detection("tree")]) == []


def test_missing_frame_resets_streak():
    tracker = FirstSeenTracker(confirm_frames=2)
    assert tracker.update([detection("car")]) == []
    assert tracker.update([]) == []
    assert tracker.update([detection("car")]) == []
    assert [event.label for event in tracker.update([detection("car")])] == [
        "car"
    ]


def test_highest_confidence_box_represents_new_class():
    tracker = FirstSeenTracker(confirm_frames=1)
    low = detection("person", 0.55)
    high = detection("person", 0.91)
    events = tracker.update([low, high])
    assert len(events) == 1
    assert events[0].confidence == 0.91


def test_classes_are_tracked_independently():
    tracker = FirstSeenTracker(confirm_frames=1)
    events = tracker.update([detection("tree"), detection("car")])
    assert {event.label for event in events} == {"tree", "car"}
    assert tracker.update([detection("tree"), detection("car")]) == []


def test_evidence_keeps_one_best_box_per_class():
    selected = best_detection_per_class([
        detection("tree", 0.51),
        detection("tree", 0.82),
        detection("pole", 0.63),
    ])
    assert {(item.label, item.confidence) for item in selected} == {
        ("tree", 0.82),
        ("pole", 0.63),
    }


def test_class_evidence_requires_confirmation_and_obeys_interval():
    tracker = ClassEvidenceTracker(
        confirm_frames=2, capture_interval=4.0, max_images_per_class=3
    )
    assert tracker.update([detection("tree")], now=10.0) == []
    assert [item.label for item in tracker.update(
        [detection("tree", 0.9)], now=11.0
    )] == ["tree"]
    assert tracker.update([detection("tree")], now=14.9) == []
    assert [item.label for item in tracker.update(
        [detection("tree")], now=15.0
    )] == ["tree"]


def test_class_evidence_limits_each_class_independently():
    tracker = ClassEvidenceTracker(
        confirm_frames=1, capture_interval=0.0, max_images_per_class=1
    )
    events = tracker.update(
        [detection("tree"), detection("car")], now=1.0
    )
    assert {item.label for item in events} == {"tree", "car"}
    assert tracker.update(
        [detection("tree"), detection("car")], now=2.0
    ) == []
    assert tracker.counts == {"tree": 1, "car": 1}
