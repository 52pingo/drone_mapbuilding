import json

import numpy as np
from PySide6.QtGui import QColor, QImage

from drone_gui.app import parse_args
from drone_gui.map_export import export_map
from drone_gui.map_feed import MapFeed
from drone_gui.widgets.map_3d_widget import render_coordinates
from drone_gui.widgets.map_view_page import MapViewPage


def test_cli_accepts_offline_session_directory(tmp_path):
    arguments = parse_args(["--session-dir", str(tmp_path), "--screenshot", "map.png"])
    assert arguments.session_dir == tmp_path
    assert arguments.screenshot.name == "map.png"


def test_render_coordinates_uses_height_up():
    points = render_coordinates([[1.0, 2.0, -3.0], [-4.0, 5.0, 6.0]])
    np.testing.assert_allclose(points, [[1.0, 2.0, 3.0], [-4.0, 5.0, -6.0]])


def test_map_feed_reads_atomic_snapshot(qtbot, tmp_path):
    points = np.array([[1.0, 2.0, -3.0], [4.0, 5.0, -6.0]], dtype=np.float32)
    np.save(tmp_path / "points_000001.npy", points, allow_pickle=False)
    (tmp_path / "latest.json").write_text(json.dumps({
        "sequence": 1,
        "points": "points_000001.npy",
        "coordinate_frame": "px4_local_ned",
    }), encoding="utf-8")
    feed = MapFeed()
    received = []
    feed.snapshot_ready.connect(lambda values, meta: received.append((values, meta)))
    assert feed.start({"map_dir": str(tmp_path)})
    feed.timer.stop()
    feed._poll()
    assert len(received) == 1
    np.testing.assert_allclose(received[0][0], points)
    assert received[0][1]["coordinate_frame"] == "px4_local_ned"


def test_export_map_writes_portable_scene(tmp_path):
    image = QImage(8, 8, QImage.Format_RGB32)
    image.fill(QColor("#123456"))
    outputs = export_map(
        tmp_path,
        np.array([[1.0, 2.0, -3.0]], dtype=np.float32),
        [{"id": "tree-001", "label": "tree", "position_ned": [2, 3, -4]}],
        image,
    )
    assert {path.name for path in outputs} == {
        "semantic_map.ply", "semantic_objects.json", "semantic_map_view.png",
    }
    payload = json.loads((tmp_path / "semantic_objects.json").read_text("utf-8"))
    assert payload["coordinate_frame"] == "px4_local_ned"
    assert payload["objects"][0]["id"] == "tree-001"
    assert "element vertex 2" in (tmp_path / "semantic_map.ply").read_text("ascii")


def test_map_page_filters_semantic_labels_by_class(qtbot):
    page = MapViewPage()
    qtbot.addWidget(page)
    page.update_semantics({"semantic_objects": [
        {"id": "tree-001", "label": "tree", "position_ned": [1, 2, -3]},
        {"id": "car-001", "label": "car", "position_ned": [4, 5, -1]},
    ]})
    assert page.class_filter.count() == 3
    assert len(page.view._labels) == 2
    page.class_filter.setCurrentText("tree")
    assert len(page.view._labels) == 1
    assert page.metrics["objects"].text() == "1 / 2 语义目标"
