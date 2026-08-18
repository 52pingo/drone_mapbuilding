from pathlib import Path

from drone_gui import app_paths


def test_source_application_root_is_repository():
    assert app_paths.application_root() == Path(__file__).resolve().parents[1]


def test_frozen_application_root_uses_executable(tmp_path, monkeypatch):
    executable = tmp_path / "DroneMapbuilding.exe"
    monkeypatch.setattr(app_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(app_paths.sys, "executable", str(executable))
    assert app_paths.application_root() == tmp_path
