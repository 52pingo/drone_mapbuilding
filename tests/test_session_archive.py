import csv
import json

import numpy as np

from drone_gui.session_archive import (
    finalize_session, initialize_session, recover_session,
)


def _write_fixture(root, closed_loop=True):
    live_map = root / "live_map"
    semantic = root / "detected_classes"
    live_map.mkdir(parents=True)
    semantic.mkdir(parents=True)
    points = np.array([[1.0, 2.0, -3.0], [4.0, 5.0, -6.0]], dtype=np.float32)
    np.save(live_map / "points_000001.npy", points, allow_pickle=False)
    (live_map / "latest.json").write_text(json.dumps({
        "sequence": 1, "points": "points_000001.npy",
        "coordinate_frame": "px4_local_ned",
    }), encoding="utf-8")
    (semantic / "semantic_objects.json").write_text(json.dumps({
        "objects": [{
            "id": "tree-001", "label": "tree", "position_ned": [2, 3, -4],
        }],
    }), encoding="utf-8")
    final_armed = "false" if closed_loop else "true"
    (root / "mission_console.log").write_text(
        'log GUI_STATUS {"elapsed":0.0,"state":"TAKEOFF","armed":true,'
        '"position":[0,0,0],"velocity":[0,0,0]}\n'
        f'GUI_STATUS {{"elapsed":12.5,"state":"DONE","armed":{final_armed},'
        '"position":[1,2,0],"velocity":[0,0,0]}\n',
        encoding="utf-8",
    )


def test_finalize_builds_portable_closed_loop_session(tmp_path):
    root = tmp_path / "run_001"
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    initialize_session(
        root, {"name": "loop", "goals": "1,2;0,0"}, weights,
        {"confidence": 0.25},
    )
    _write_fixture(root)

    manifest = recover_session(root)

    assert manifest["status"] == "completed"
    assert manifest["summary"] == {
        "telemetry_samples": 2,
        "point_count": 2,
        "semantic_objects": 1,
        "closed_loop": True,
        "final_state": "DONE",
        "final_armed": False,
    }
    assert (root / "semantic_map.ply").is_file()
    assert (root / "semantic_map.pcd").is_file()
    assert (root / "report.html").is_file()
    assert "无人机任务报告" in (root / "report.html").read_text("utf-8")
    with (root / "telemetry.csv").open(encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    assert rows[-1]["state"] == "DONE"
    assert any(item["path"] == "semantic_map.pcd" for item in manifest["artifacts"])


def test_completed_request_without_disarm_is_incomplete(tmp_path):
    root = tmp_path / "unsafe_finish"
    initialize_session(root, {"name": "loop"})
    _write_fixture(root, closed_loop=False)
    manifest = finalize_session(root, "completed")
    assert manifest["status"] == "incomplete"
    assert not manifest["summary"]["closed_loop"]


def test_legacy_flight_log_recovers_only_with_done_and_disarmed(tmp_path):
    root = tmp_path / "legacy"
    initialize_session(root, {"name": "legacy"})
    (root / "avoid_flight.log").write_text(
        "# t state x y z dc dl dr action vx vy vz yaw yawspeed\n"
        "0.50 WAIT 0 0 0 999 999 999 wait 0 0 0 0 0\n"
        "8.00 LAND 1 2 0.2 999 999 999 land 0 0 0 0 0\n",
        encoding="utf-8",
    )
    (root / "mission_console.log").write_text(
        "DISARMED -> mission done\n=== MISSION DONE === elapsed=8.5s\n",
        encoding="utf-8",
    )
    manifest = finalize_session(root, "completed")
    assert manifest["status"] == "completed"
    assert manifest["summary"]["telemetry_samples"] == 3
    assert manifest["summary"]["final_armed"] is False
