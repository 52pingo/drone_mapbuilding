from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from drone_gui.models import RuntimeConfig
from drone_gui.preflight import (
    CheckResult,
    has_required_failures,
    run_local_preflight,
)


def make_config(tmp_path: Path, **overrides) -> RuntimeConfig:
    base = dict(
        ue4_launch_mode="editor",
        ue4_executable=None,
        ue4_editor=tmp_path / "UE4Editor.exe",
        ue4_map="CityPark",
        ue4_project=tmp_path / "CityPark.uproject",
        environment_name="CityPark",
        perception_python=tmp_path / "python.exe",
        weights=tmp_path / "yolo.pt",
        airsim_client=tmp_path / "AirSim" / "PythonClient",
        repo_root=tmp_path / "repo",
        qgc_executable=None,
        results_dir=tmp_path / "results",
        ros_workspace="/home/user/ros2_ws",
    )
    base.update(overrides)
    return RuntimeConfig(**base)


def _create_all(config: RuntimeConfig) -> None:
    config.ue4_editor.parent.mkdir(parents=True, exist_ok=True)
    config.ue4_editor.touch()
    config.ue4_project.touch()
    config.perception_python.touch()
    config.weights.touch()
    config.airsim_client.mkdir(parents=True, exist_ok=True)
    (config.repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (config.repo_root / "scripts" / "launch_ue4.ps1").touch()
    (config.repo_root / "scripts" / "run_citypark_semantic_mission.ps1").touch()
    config.results_dir.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def wsl_found(monkeypatch):
    monkeypatch.setattr(
        shutil, "which",
        lambda name: "wsl.exe" if name in ("wsl.exe", "wsl") else None,
    )


def _by_name(checks):
    return {c.name: c for c in checks}


def test_all_checks_pass(tmp_path, wsl_found):
    config = make_config(tmp_path)
    _create_all(config)
    checks = run_local_preflight(config)
    by_name = _by_name(checks)
    assert by_name["UE4 编辑器"].status == "pass"
    assert by_name["CityPark 工程"].status == "pass"
    assert by_name["视觉 Python"].status == "pass"
    assert by_name["YOLO 权重"].status == "pass"
    assert by_name["AirSim PythonClient"].status == "pass"
    assert by_name["UE4 启动脚本"].status == "pass"
    assert by_name["任务总控脚本"].status == "pass"
    assert by_name["WSL"].status == "pass"
    assert by_name["成果目录"].status == "pass"
    assert has_required_failures(checks) is False


def test_missing_weights_fails_and_aggregates(tmp_path, wsl_found):
    config = make_config(tmp_path)
    _create_all(config)
    config.weights.unlink()
    checks = run_local_preflight(config)
    by_name = _by_name(checks)
    assert by_name["YOLO 权重"].status == "fail"
    assert by_name["YOLO 权重"].required is True
    assert "未找到" in by_name["YOLO 权重"].detail
    assert has_required_failures(checks) is True


def test_missing_ue4_editor_fails(tmp_path, wsl_found):
    config = make_config(tmp_path)
    _create_all(config)
    config.ue4_editor.unlink()
    checks = run_local_preflight(config)
    by_name = _by_name(checks)
    assert by_name["UE4 编辑器"].status == "fail"
    assert has_required_failures(checks) is True


def test_missing_airsim_client_dir_fails(tmp_path, wsl_found):
    config = make_config(tmp_path)
    _create_all(config)
    shutil.rmtree(config.airsim_client)
    checks = run_local_preflight(config)
    by_name = _by_name(checks)
    assert by_name["AirSim PythonClient"].status == "fail"
    assert has_required_failures(checks) is True


def test_qgc_missing_is_warning_not_failure(tmp_path, wsl_found):
    config = make_config(tmp_path)
    _create_all(config)
    checks = run_local_preflight(config)
    by_name = _by_name(checks)
    assert by_name["QGroundControl"].status == "warning"
    assert by_name["QGroundControl"].required is False
    assert "未配置" in by_name["QGroundControl"].detail
    assert has_required_failures(checks) is False


def test_qgc_present_passes(tmp_path, wsl_found):
    qgc = tmp_path / "QGroundControl.exe"
    qgc.touch()
    config = make_config(tmp_path, qgc_executable=qgc)
    _create_all(config)
    checks = run_local_preflight(config)
    by_name = _by_name(checks)
    assert by_name["QGroundControl"].status == "pass"
    assert by_name["QGroundControl"].detail == str(qgc)


def test_standalone_mode_uses_executable(tmp_path, wsl_found):
    exe = tmp_path / "UE4.exe"
    exe.touch()
    config = make_config(
        tmp_path, ue4_launch_mode="standalone", ue4_executable=exe
    )
    _create_all(config)
    checks = run_local_preflight(config)
    names = [c.name for c in checks]
    assert "UE4 仿真程序" in names
    assert "UE4 编辑器" not in names
    assert _by_name(checks)["UE4 仿真程序"].status == "pass"


def test_standalone_mode_missing_executable_fails(tmp_path, wsl_found):
    config = make_config(
        tmp_path, ue4_launch_mode="standalone", ue4_executable=None
    )
    _create_all(config)
    checks = run_local_preflight(config)
    assert _by_name(checks)["UE4 仿真程序"].status == "fail"
    assert has_required_failures(checks) is True


def test_wsl_missing_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    config = make_config(tmp_path)
    _create_all(config)
    checks = run_local_preflight(config)
    by_name = _by_name(checks)
    assert by_name["WSL"].status == "fail"
    assert by_name["WSL"].detail == "未找到 wsl.exe"
    assert has_required_failures(checks) is True


def test_results_dir_missing_but_parent_writable(tmp_path, wsl_found):
    config = make_config(tmp_path, results_dir=tmp_path / "results")
    _create_all(config)
    config.results_dir.rmdir()
    checks = run_local_preflight(config)
    assert _by_name(checks)["成果目录"].status == "pass"


def test_results_dir_and_parent_missing_fails(tmp_path, wsl_found):
    config = make_config(tmp_path, results_dir=tmp_path / "a" / "b" / "results")
    _create_all(config)
    shutil.rmtree(tmp_path / "a")
    checks = run_local_preflight(config)
    detail = _by_name(checks)["成果目录"]
    assert detail.status == "fail"
    assert "父目录不可用" in detail.detail
    assert has_required_failures(checks) is True


def test_ros_workspace_is_warning(tmp_path, wsl_found):
    config = make_config(tmp_path)
    _create_all(config)
    checks = run_local_preflight(config)
    entry = _by_name(checks)["ROS2 工作区"]
    assert entry.status == "warning"
    assert entry.required is False
    assert "/home/user/ros2_ws" in entry.detail


def test_has_required_failures_ignores_warnings():
    checks = [
        CheckResult("a", "warning", "x", required=False),
        CheckResult("b", "pass", "y", required=True),
    ]
    assert has_required_failures(checks) is False


def test_has_required_failures_detects_required_fail():
    checks = [CheckResult("a", "fail", "x", required=True)]
    assert has_required_failures(checks) is True


def test_has_required_failures_ignores_optional_fail():
    checks = [CheckResult("a", "fail", "x", required=False)]
    assert has_required_failures(checks) is False


def test_has_required_failures_empty_list():
    assert has_required_failures([]) is False
