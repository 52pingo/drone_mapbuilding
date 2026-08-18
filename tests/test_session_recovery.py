import json

from drone_gui.session_archive import initialize_session
from drone_gui.session_recovery import SessionRecoveryController


def test_recovery_runs_outside_gui_thread(qtbot, tmp_path):
    root = tmp_path / "partial"
    initialize_session(root, {"name": "partial"})
    (root / "mission_console.log").write_text(
        'GUI_STATUS {"elapsed":1,"state":"LAND","armed":true}\n'
        'GUI_STATUS {"elapsed":2,"state":"DONE","armed":false}\n',
        encoding="utf-8",
    )
    controller = SessionRecoveryController()
    with qtbot.waitSignal(controller.recovered, timeout=5000) as signal:
        assert controller.recover(root)
    manifest = signal.args[0]
    assert manifest["status"] == "completed"
    assert json.loads((root / "manifest.json").read_text("utf-8"))["status"] == "completed"
    qtbot.waitUntil(lambda: controller.thread is None, timeout=5000)
