from pathlib import Path
import sys

import pytest

pytest.importorskip("PySide6")

from drone_gui.main_window import MainWindow
from drone_gui.commands import CommandSpec
from drone_gui.models import MissionPlan, RuntimeConfig, Waypoint
from drone_gui.runtime import RuntimeController
from drone_gui.widgets.mission_page import MissionPage
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

    assert window.shell.pages.count() == 4
    assert window.shell.log.accessibleName() == "外部任务实时日志"
    window.shell.page_requested.emit(1)
    assert window.shell.pages.currentIndex() == 1
    assert window.shell.page_title.text() == "航线规划"


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
