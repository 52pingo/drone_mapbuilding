from pathlib import Path

import pytest

from drone_gui.commands import CommandBuilder, windows_path_to_wsl
from drone_gui.models import MissionPlan, RuntimeConfig


def make_config(repo: Path) -> RuntimeConfig:
    config = RuntimeConfig.defaults(repo)
    config.weights = repo / "best.pt"
    config.results_dir = repo / "results"
    return config


def test_windows_path_to_wsl_preserves_spaces_and_unicode():
    assert windows_path_to_wsl(Path(r"E:\无人机 视觉\repo")) == (
        "/mnt/e/无人机 视觉/repo"
    )


def test_ue4_command_uses_argument_array(tmp_path):
    builder = CommandBuilder(make_config(tmp_path))
    command = builder.launch_ue4()
    assert command.program == "powershell.exe"
    assert "-Ue4EditorPath" in command.arguments
    assert str(builder.config.ue4_project) in command.arguments
    assert command.arguments[command.arguments.index("-LaunchMode") + 1] == "editor"
    assert command.arguments[command.arguments.index("-ExistingInstancePolicy") + 1] == "reuse"


def test_ue4_command_supports_packaged_environment(tmp_path):
    config = make_config(tmp_path)
    config.ue4_launch_mode = "standalone"
    config.ue4_executable = tmp_path / "Park.exe"
    command = CommandBuilder(config).launch_ue4()
    assert str(config.ue4_executable) in command.arguments
    assert command.arguments[command.arguments.index("-LaunchMode") + 1] == "standalone"


def test_stack_command_forwards_runtime_paths(tmp_path):
    config = make_config(tmp_path)
    command = CommandBuilder(config).restart_stack()
    assert command.program == "wsl.exe"
    assert f"ROS_WORKSPACE={config.ros_workspace}" in command.arguments
    assert command.arguments[-2] == "bash"


def test_probe_and_control_commands_use_argument_arrays(tmp_path):
    builder = CommandBuilder(make_config(tmp_path))
    probe = builder.probe_stack()
    control = builder.mission_control("land")
    assert probe.program == "wsl.exe"
    assert probe.arguments[-2] == "bash"
    assert control.arguments[-1] == "land"
    assert "gui_mission_control.sh" in control.arguments[-2]


def test_unknown_control_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        CommandBuilder(make_config(tmp_path)).mission_control("disarm")


def test_mission_command_contains_validated_route(tmp_path):
    command = CommandBuilder(make_config(tmp_path)).run_mission(
        MissionPlan.citypark_default()
    )
    goals_index = command.arguments.index("-Goals") + 1
    assert command.arguments[goals_index].endswith(";0,0")
    assert "-ResultRoot" in command.arguments
    assert "-PerceptionInterval" in command.arguments
    assert "-EnvironmentName" in command.arguments
    assert "-RosWorkspace" in command.arguments


def test_setup_command_forwards_all_workflow_locations(tmp_path):
    config = make_config(tmp_path)
    command = CommandBuilder(config).setup_environment("check")
    assert command.program == "powershell.exe"
    assert "-WslDistro" in command.arguments
    assert config.ros_workspace in command.arguments
    assert str(config.ue4_project) in command.arguments


def test_qgc_command_requires_configured_path(tmp_path):
    config = make_config(tmp_path)
    config.qgc_executable = None
    with pytest.raises(ValueError):
        CommandBuilder(config).launch_qgc()
