from pathlib import Path
import os
import sys

import pytest

pytest.importorskip("PySide6")

from drone_gui.main_window import MainWindow
from drone_gui.commands import CommandSpec
from drone_gui.models import MissionPlan, RuntimeConfig, Waypoint
from drone_gui.runtime import RuntimeController, _sanitize_search_path
from drone_gui.widgets.mission_page import MissionPage
from drone_gui.widgets.preflight_page import PreflightPage
from drone_gui.widgets.live_page import LivePage
from drone_gui.widgets.waypoint_canvas import WaypointCanvas


def test_waypoint_canvas_coordinate_round_trip():
    point = Waypoint(125.5, -48.25)
    restored = WaypointCanvas.scene_to_world(WaypointCanvas.world_to_scene(point))
    assert restored == point


def test_mission_page_starts_with_valid_citypark_route(qtbot):
    page = MissionPage()
    qtbot.addWidget(page)
    plan = page.current_plan()
    assert plan.goals_string() == MissionPlan.citypark_default().goals_string()
    assert not [issue for issue in plan.validate() if issue.level == "error"]


def test_main_window_navigation_and_accessible_surfaces(qtbot, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    config = RuntimeConfig.defaults(repo_root)
    config.results_dir = tmp_path / "results"
    window = MainWindow(config)
    qtbot.addWidget(window)
    window.show()

    assert window.shell.pages.count() == 5
    assert window.shell.log.accessibleName() == "外部任务实时日志"
    window.shell.page_requested.emit(MainWindow.MISSION_PAGE)
    assert window.shell.pages.currentIndex() == MainWindow.MISSION_PAGE
    assert window.shell.page_title.text() == "航线规划"


def test_environment_page_applies_standalone_simulator(qtbot, tmp_path):
    config = RuntimeConfig.defaults(tmp_path)
    config.results_dir = tmp_path / "results"
    window = MainWindow(config, tmp_path / "gui_config.json")
    qtbot.addWidget(window)
    simulator = tmp_path / "Park.exe"
    simulator.write_bytes(b"exe")
    page = window.environment_page
    page.simulation.mode.setCurrentIndex(page.simulation.mode.findData("standalone"))
    page.simulation.name.setText("Local Park")
    page.simulation.executable.set_value(simulator)
    with qtbot.waitSignal(page.config_saved, timeout=1000):
        page._save()
    assert window.config.ue4_launch_mode == "standalone"
    assert window.config.ue4_executable == simulator
    assert window.config.environment_name == "Local Park"


def test_main_window_accepts_structured_done_only_when_disarmed(qtbot, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    config = RuntimeConfig.defaults(repo_root)
    config.results_dir = tmp_path / "results"
    window = MainWindow(config)
    qtbot.addWidget(window)

    window._task_output("mission", 'GUI_STATUS {"state":"DONE","armed":true}')
    assert not window._mission_closed_loop
    window._task_output("mission", 'GUI_STATUS {"state":"DONE","armed":false}')
    assert window._mission_closed_loop
    assert window.shell.mission_status.text() == "已降落 / 已解锁"


def test_main_window_starts_perception_feed_from_session_protocol(qtbot, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    config = RuntimeConfig.defaults(repo_root)
    config.results_dir = tmp_path / "results"
    window = MainWindow(config)
    qtbot.addWidget(window)
    live_dir = tmp_path / "live"
    semantic_dir = tmp_path / "semantic"
    map_dir = tmp_path / "map"
    message = (
        'GUI_SESSION {"live_dir":"%s","semantic_dir":"%s","map_dir":"%s"}'
        % (str(live_dir).replace("\\", "\\\\"),
           str(semantic_dir).replace("\\", "\\\\"),
           str(map_dir).replace("\\", "\\\\"))
    )
    window._task_output("mission", message)
    assert window.perception.timer.isActive()
    assert window.perception.live_dir == live_dir
    assert window.results_page.map_view.feed.timer.isActive()
    assert window.results_page.map_view.feed.directory == map_dir
    window.perception.stop()
    window.results_page.map_view.feed.stop()


def test_runtime_controller_streams_process_output(qtbot, tmp_path):
    controller = RuntimeController()
    output = []
    controller.task_output.connect(lambda _name, text: output.append(text))
    command = CommandSpec(
        sys.executable,
        ("-c", "print('qprocess-ready')"),
        tmp_path,
    )
    with qtbot.waitSignal(controller.task_finished, timeout=5000) as signal:
        assert controller.start("probe", command)
    assert signal.args == ["probe", 0]
    assert any("qprocess-ready" in text for text in output)


def test_external_process_path_excludes_pyinstaller_bundle(tmp_path):
    bundle = tmp_path / "DroneMapbuilding" / "_internal"
    system = tmp_path / "Windows" / "System32"
    value = os.pathsep.join((str(bundle), str(bundle / "PySide6"), str(system)))
    assert _sanitize_search_path(value, bundle) == str(system)


def test_runtime_controller_reassembles_split_lines(qtbot, tmp_path):
    controller = RuntimeController()
    output = []
    controller.task_output.connect(lambda _name, text: output.append(text))
    command = CommandSpec(
        sys.executable,
        ("-c", "import sys;sys.stdout.write('GUI_');sys.stdout.flush();"
         "sys.stdout.write('STATUS {\\\"state\\\":\\\"HOLD\\\"}\\n')"),
        tmp_path,
    )
    with qtbot.waitSignal(controller.task_finished, timeout=5000):
        assert controller.start("split", command)
    assert output == ['GUI_STATUS {"state":"HOLD"}']


def test_live_status_enables_only_safe_controls(qtbot):
    page = LivePage()
    qtbot.addWidget(page)
    page.update_status({
        "state": "NAVIGATE", "armed": True,
        "position": [1, 2, -15], "nearest_obstacle": 4.5, "elapsed": 65,
    })
    assert page.controls.hold_button.isEnabled()
    assert not page.controls.resume_button.isEnabled()
    assert page.controls.land_button.isEnabled()
    assert page.telemetry["位置 N/E/Z"].text() == "1.0 / 2.0 / -15.0"

    page.update_status({"state": "HOLD", "armed": True, "elapsed": 66})
    assert not page.controls.hold_button.isEnabled()
    assert page.controls.resume_button.isEnabled()


def test_preflight_requires_successful_runtime_probe(qtbot, tmp_path):
    config = RuntimeConfig.defaults(tmp_path)
    page = PreflightPage(config)
    qtbot.addWidget(page)
    assert not page.required_ready
    assert "本地配置问题" in page.summary.text()
    page.apply_runtime_probe({key: True for key, _name, _required in page.RUNTIME_COMPONENTS})
    # Runtime is healthy, but deliberately missing local fixture files still block start.
    assert not page.required_ready


def test_preflight_locks_stack_button_until_ue4_is_ready(qtbot, tmp_path):
    page = PreflightPage(RuntimeConfig.defaults(tmp_path))
    qtbot.addWidget(page)

    # 默认锁定：UE4 没起来之前不给放 PX4 出去。
    assert not page.stack_button.isEnabled()
    assert not page.ue4_ready
    assert "锁定" in page.gate_hint.text()
    assert page.gate_hint.property("state") == "warning"
    # 第 1 步必须始终可用，否则就绪状态永远补不上，按钮变成死路。
    assert page.launch_button.isEnabled()

    page.apply_ue4_state(True, "UE4 窗口与 AirSim RPC 均已就绪")
    assert page.stack_button.isEnabled()
    assert page.ue4_ready
    assert "已就绪" in page.gate_hint.text()
    assert page.gate_hint.property("state") == "pass"

    # 仿真退出后必须重新锁上。
    page.apply_ue4_state(False, "UE4 窗口未确认")
    assert not page.stack_button.isEnabled()
    assert page.stack_button.toolTip()


def test_main_window_gate_follows_the_ue4_readiness_lines(qtbot, tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    config = RuntimeConfig.defaults(repo_root)
    config.results_dir = tmp_path / "results"
    window = MainWindow(config)
    qtbot.addWidget(window)
    stack_button = window.preflight_page.stack_button

    assert not stack_button.isEnabled()

    window._task_started("ue4", "powershell.exe launch_ue4.ps1")
    assert not stack_button.isEnabled()

    # 窗口起来了但 RPC 还没通 —— 这时候放 airsim_node 出去就是连不上。
    window._task_output("ue4", 'GUI_UE4 {"window_ready":true,"airsim_ready":false}')
    assert not stack_button.isEnabled()
    assert "RPC" in window.preflight_page.gate_hint.text()

    window._task_output("ue4", 'GUI_UE4 {"window_ready":true,"airsim_ready":true}')
    assert stack_button.isEnabled()
    assert window.shell.ue_status.property("state") == "ready"

    window._task_finished("ue4", 0)
    assert stack_button.isEnabled()

    # 启动器非零退出 = 仿真没起来，就绪状态必须作废。
    window._task_finished("ue4", 1)
    assert not stack_button.isEnabled()
    assert window.shell.ue_status.text() == "UE4 启动失败"


def test_main_window_refuses_to_start_the_stack_before_ue4(qtbot, tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    config = RuntimeConfig.defaults(repo_root)
    config.results_dir = tmp_path / "results"
    window = MainWindow(config)
    qtbot.addWidget(window)

    def explode():
        raise AssertionError("restart_stack must not run while UE4 is not ready")

    monkeypatch.setattr(window.commands, "restart_stack", explode)
    warnings = []
    monkeypatch.setattr(
        "drone_gui.main_window.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args[1]),
    )
    window._restart_stack()
    assert warnings == ["UE4 未就绪"]
    # 挡下来之后要把用户带到自检页，否则他不知道去哪补第 1 步。
    assert window.shell.pages.currentIndex() == MainWindow.PREFLIGHT_PAGE


def test_main_window_stack_guard_opens_once_ue4_is_ready(qtbot, tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    config = RuntimeConfig.defaults(repo_root)
    config.results_dir = tmp_path / "results"
    window = MainWindow(config)
    qtbot.addWidget(window)

    window._task_output("ue4", 'GUI_UE4 {"window_ready":true,"airsim_ready":true}')
    started = []
    monkeypatch.setattr(
        window.runtime, "start", lambda name, spec: started.append(name)
    )
    monkeypatch.setattr(
        "drone_gui.main_window.QMessageBox.warning",
        lambda *args, **kwargs: pytest.fail("ready UE4 should not be blocked"),
    )
    window._restart_stack()
    assert started == ["stack"]
