import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QImage

from drone_gui.perception_feed import PerceptionFeed
from drone_gui.widgets.live_page import LivePage


def make_feed_files(tmp_path):
    live_dir = tmp_path / "live_feed"
    semantic_dir = tmp_path / "detected_classes"
    evidence_dir = semantic_dir / "tree"
    live_dir.mkdir()
    evidence_dir.mkdir(parents=True)
    image = QImage(320, 180, QImage.Format_RGB32)
    image.fill(0x24464E)
    assert image.save(str(live_dir / "frame.jpg"), "JPG")
    assert image.save(str(evidence_dir / "first.jpg"), "JPG")
    snapshot = {
        "frame_index": 3, "fps": 5.2, "size": [320, 180],
        "image": "frame.jpg",
        "detections": [{
            "label": "tree", "confidence": 0.88,
            "depth_m": 6.4, "bbox_xyxy": [1, 2, 30, 40],
        }],
        "catalog": [{
            "label": "tree", "saved_count": 1, "max_confidence": 0.88,
            "first_image": "tree/first.jpg", "last_image": "tree/first.jpg",
        }],
    }
    (live_dir / "latest.json").write_text(json.dumps(snapshot), encoding="utf-8")
    return live_dir, semantic_dir


def test_perception_feed_reads_atomic_snapshot(qtbot, tmp_path):
    live_dir, semantic_dir = make_feed_files(tmp_path)
    feed = PerceptionFeed()
    frames = []
    snapshots = []
    feed.frame_ready.connect(frames.append)
    feed.snapshot_ready.connect(snapshots.append)
    assert feed.start({"live_dir": str(live_dir), "semantic_dir": str(semantic_dir)})
    feed.timer.stop()
    feed._poll()
    assert frames and not frames[0].isNull()
    assert Path(snapshots[0]["catalog"][0]["first_image"]) == (
        semantic_dir / "tree" / "first.jpg"
    )


def test_live_page_renders_frame_detections_and_catalog(qtbot, tmp_path):
    live_dir, semantic_dir = make_feed_files(tmp_path)
    payload = json.loads((live_dir / "latest.json").read_text(encoding="utf-8"))
    payload["catalog"][0]["first_image"] = str(semantic_dir / "tree" / "first.jpg")
    page = LivePage()
    qtbot.addWidget(page)
    page.resize(1200, 720)
    page.set_frame(QImage(str(live_dir / "frame.jpg")))
    page.update_perception(payload)
    assert page.video.pixmap() is not None
    assert page.objects.topLevelItemCount() == 1
    assert page.sidebar.catalog.topLevelItem(0).text(0) == "tree"
    assert page.sidebar.evidence.pixmap() is not None
