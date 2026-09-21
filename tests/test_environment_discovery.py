from __future__ import annotations

from pathlib import Path

import pytest

from drone_gui.environment_discovery import discover_runtime
from drone_gui.models import RuntimeConfig


def make_config(tmp_path: Path, **overrides) -> RuntimeConfig:
    base = dict(
        ue4_launch_mode="editor",
        ue4_executable=None,
        ue4_editor=tmp_path / "missing_editor.exe",
        ue4_map="CityPark",
        ue4_project=tmp_path / "missing.uproject",
        environment_name="CityPark",
        perception_python=tmp_path / "python.exe",
        weights=tmp_path / "yolo.pt",
        airsim_client=tmp_path / "missing_airsim",
        repo_root=tmp_path / "repo",
        qgc_executable=None,
        results_dir=tmp_path / "results",
        ros_workspace="/home/user/ros2_ws",
    )
    base.update(overrides)
    return RuntimeConfig(**base)


def _fake_fs(monkeypatch, files=(), dirs=()):
    file_set = {str(p) for p in files}
    dir_set = {str(p) for p in dirs}
    monkeypatch.setattr(Path, "is_file", lambda self: str(self) in file_set)
    monkeypatch.setattr(Path, "is_dir", lambda self: str(self) in dir_set)


def test_discover_finds_ue4_editor(tmp_path, monkeypatch):
    target = Path(r"D:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe")
    _fake_fs(monkeypatch, files=[target])
    config = make_config(tmp_path)
    changes = discover_runtime(config)
    assert config.ue4_editor == target
    assert len(changes) == 1
    assert changes[0].startswith("UE4 Editor：")


def test_discover_ue4_editor_first_candidate_wins(tmp_path, monkeypatch):
    first = Path(r"D:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe")
    second = Path(
        r"C:\Program Files\Epic Games\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe"
    )
    _fake_fs(monkeypatch, files=[first, second])
    config = make_config(tmp_path)
    discover_runtime(config)
    assert config.ue4_editor == first


def test_discover_ue4_editor_no_candidate_leaves_unchanged(tmp_path, monkeypatch):
    _fake_fs(monkeypatch, files=[])
    config = make_config(tmp_path)
    original = config.ue4_editor
    changes = discover_runtime(config)
    assert config.ue4_editor == original
    assert changes == []


def test_discover_ue4_project_updates_environment_name(tmp_path, monkeypatch):
    target = Path(r"D:\CityParkEnvironmentCollec\CityPark.uproject")
    _fake_fs(monkeypatch, files=[target])
    config = make_config(tmp_path)
    discover_runtime(config)
    assert config.ue4_project == target
    assert config.environment_name == "CityPark"


def test_discover_airsim_client_relative_to_repo(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    expected = config.repo_root.parent / "AirSim" / "PythonClient"
    _fake_fs(monkeypatch, dirs=[expected])
    discover_runtime(config)
    assert config.airsim_client == expected


def test_discover_airsim_client_falls_back_to_windows_path(tmp_path, monkeypatch):
    target = Path(r"D:\AirSim\PythonClient")
    _fake_fs(monkeypatch, dirs=[target])
    config = make_config(tmp_path)
    discover_runtime(config)
    assert config.airsim_client == target


def test_discover_qgc_chinese_path(tmp_path, monkeypatch):
    target = Path(
        r"E:\无人机视觉避障建图\QGroundControl\bin\QGroundControl.exe"
    )
    _fake_fs(monkeypatch, files=[target])
    config = make_config(tmp_path)
    changes = discover_runtime(config)
    assert config.qgc_executable == target
    assert any("QGroundControl" in c for c in changes)


def test_discover_qgc_relative_to_repo(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    expected = (
        config.repo_root.parent / "QGroundControl" / "bin" / "QGroundControl.exe"
    )
    _fake_fs(monkeypatch, files=[expected])
    discover_runtime(config)
    assert config.qgc_executable == expected


def test_no_changes_when_all_present(tmp_path, monkeypatch):
    qgc = tmp_path / "QGC.exe"
    config = make_config(tmp_path, qgc_executable=qgc)
    _fake_fs(
        monkeypatch,
        files=[config.ue4_editor, config.ue4_project, qgc],
        dirs=[config.airsim_client],
    )
    changes = discover_runtime(config)
    assert changes == []


def test_discover_returns_multiple_changes(tmp_path, monkeypatch):
    editor = Path(r"D:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe")
    project = Path(r"D:\CityParkEnvironmentCollec\CityPark.uproject")
    _fake_fs(monkeypatch, files=[editor, project])
    config = make_config(tmp_path)
    changes = discover_runtime(config)
    assert len(changes) == 2
    assert any(c.startswith("UE4 Editor：") for c in changes)
    assert any(c.startswith("UE4 工程：") for c in changes)


def test_discover_does_not_overwrite_existing_editor(tmp_path, monkeypatch):
    existing = tmp_path / "existing_editor.exe"
    config = make_config(tmp_path, ue4_editor=existing)
    candidate = Path(r"D:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe")
    _fake_fs(monkeypatch, files=[existing, candidate])
    discover_runtime(config)
    assert config.ue4_editor == existing


def test_discover_path_with_spaces(tmp_path, monkeypatch):
    target = Path(
        r"C:\Program Files\Epic Games\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe"
    )
    _fake_fs(monkeypatch, files=[target])
    config = make_config(tmp_path)
    discover_runtime(config)
    assert config.ue4_editor == target
    assert " " in str(config.ue4_editor)
