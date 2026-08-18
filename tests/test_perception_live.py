import json

import pytest

from scripts.perception_live import (
    FrameRateMeter, LiveFrameWriter, build_snapshot, evidence_catalog,
)
from scripts.semantic_perception import Detection


def test_snapshot_serializes_detections_and_first_evidence():
    detection = Detection(2, "tree", 0.91, (10, 20, 80, 140), 7.25)
    events = [{
        "label": "tree", "class_image_index": 1,
        "confidence": 0.91, "depth_m": 7.25,
        "image": "tree/scene_001.jpg",
    }]
    snapshot = build_snapshot(8, (360, 640, 3), 4.75, [detection], events)
    assert snapshot["size"] == [640, 360]
    assert snapshot["detections"][0]["bbox_xyxy"] == [10, 20, 80, 140]
    assert snapshot["catalog"][0]["first_image"] == "tree/scene_001.jpg"


def test_evidence_catalog_preserves_first_image_and_latest_count():
    catalog = evidence_catalog([
        {"label": "car", "class_image_index": 1, "confidence": 0.7,
         "depth_m": 12.0, "image": "car/first.jpg"},
        {"label": "car", "class_image_index": 2, "confidence": 0.9,
         "depth_m": 9.0, "image": "car/second.jpg"},
    ])
    assert catalog == [{
        "label": "car", "saved_count": 2,
        "first_image": "car/first.jpg", "last_image": "car/second.jpg",
        "max_confidence": 0.9, "last_depth_m": 9.0,
    }]


def test_frame_rate_meter_uses_recent_intervals():
    meter = FrameRateMeter(window=3)
    assert meter.tick(1.0) == 0.0
    assert meter.tick(1.2) == pytest.approx(5.0)
    assert meter.tick(1.4) == pytest.approx(5.0)
    assert meter.tick(1.6) == pytest.approx(5.0)


def test_live_writer_atomically_rotates_recent_frames(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    writer = LiveFrameWriter(tmp_path, cv2)
    frame = np.zeros((60, 80, 3), dtype=np.uint8)
    for index in range(1, 6):
        writer.publish(frame, [], [], index, 5.0)
    assert [path.name for path in sorted(tmp_path.glob("frame_*.jpg"))] == [
        "frame_000003.jpg", "frame_000004.jpg", "frame_000005.jpg",
    ]
    snapshot = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert snapshot["frame_index"] == 5
    assert snapshot["image"] == "frame_000005.jpg"
