import json

import numpy as np

from drone_gui.replay import ReplayController, trajectory_until
from drone_gui.sessions import session_payload
from drone_gui.widgets.map_view_page import MapViewPage


FRAMES = [
    {"elapsed": 0.0, "state": "TAKEOFF", "position": [0, 0, 0]},
    {"elapsed": 1.0, "state": "NAVIGATE", "position": [0.1, 0, 0]},
    {"elapsed": 2.0, "state": "DONE", "armed": False, "position": [2, 3, 0]},
]


def _write_session(root):
    root.mkdir()
    (root / "telemetry.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in FRAMES), encoding="utf-8"
    )
    map_dir = root / "live_map"
    map_dir.mkdir()
    points = np.array([[1, 2, -3], [4, 5, -6]], dtype=np.float32)
    np.save(map_dir / "points_000001.npy", points, allow_pickle=False)
    (map_dir / "latest.json").write_text(json.dumps({
        "sequence": 1, "points": "points_000001.npy",
        "coordinate_frame": "px4_local_ned",
    }), encoding="utf-8")
    (root / "semantic_objects.json").write_text(json.dumps({
        "objects": [{
            "id": "tree-001", "label": "tree", "position_ned": [1, 2, -3],
        }],
    }), encoding="utf-8")


def test_trajectory_history_filters_stationary_samples():
    assert trajectory_until(FRAMES, 2) == [[0.0, 0.0, 0.0], [2.0, 3.0, 0.0]]


def test_replay_controller_loads_and_seeks(qtbot, tmp_path):
    root = tmp_path / "session"
    _write_session(root)
    controller = ReplayController()
    received = []
    controller.frame_ready.connect(lambda frame, path: received.append((frame, path)))
    assert controller.load(root)
    controller.seek(2)
    assert received[-1][0]["state"] == "DONE"
    assert received[-1][1][-1] == [2.0, 3.0, 0.0]


def test_offline_map_page_loads_static_map_semantics_and_replay(qtbot, tmp_path):
    root = tmp_path / "session"
    _write_session(root)
    page = MapViewPage()
    qtbot.addWidget(page)
    page.start_session(session_payload(root, offline=True))
    page.feed.timer.stop()
    page.feed._poll()
    assert not page.replay.isHidden()
    assert len(page.replay.controller.frames) == 3
    assert len(page.points) == 2
    assert len(page.semantic_objects) == 1
