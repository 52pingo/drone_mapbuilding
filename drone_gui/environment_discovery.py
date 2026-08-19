"""Conservative discovery of common local workflow installations."""

from __future__ import annotations

from pathlib import Path

from drone_gui.models import RuntimeConfig


def _first_file(candidates) -> Path | None:
    return next((path for path in candidates if path.is_file()), None)


def _first_dir(candidates) -> Path | None:
    return next((path for path in candidates if path.is_dir()), None)


def discover_runtime(config: RuntimeConfig) -> list[str]:
    """Fill missing paths from bounded, known locations without scanning whole drives."""
    changes: list[str] = []
    if not config.ue4_editor.is_file():
        found = _first_file((
            Path(r"D:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe"),
            Path(r"C:\Program Files\Epic Games\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe"),
            Path(r"E:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe"),
        ))
        if found:
            config.ue4_editor = found
            changes.append(f"UE4 Editor：{found}")
    if not config.ue4_project.is_file():
        found = _first_file((
            Path(r"D:\CityParkEnvironmentCollec\CityPark.uproject"),
            Path(r"D:\AirSim\Unreal\Environments\Blocks\Blocks.uproject"),
            Path(r"D:\PycharmProjects\PythonProject19\AirSim\Unreal\Environments\Blocks\Blocks.uproject"),
        ))
        if found:
            config.ue4_project = found
            config.environment_name = found.stem
            changes.append(f"UE4 工程：{found}")
    if not config.airsim_client.is_dir():
        found = _first_dir((
            config.repo_root.parent / "AirSim" / "PythonClient",
            Path(r"D:\AirSim\PythonClient"),
            Path(r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient"),
        ))
        if found:
            config.airsim_client = found
            changes.append(f"AirSim PythonClient：{found}")
    if config.qgc_executable is None or not config.qgc_executable.is_file():
        found = _first_file((
            config.repo_root.parent / "QGroundControl" / "bin" / "QGroundControl.exe",
            Path(r"E:\无人机视觉避障建图\QGroundControl\bin\QGroundControl.exe"),
            Path(r"D:\QGC\QGroundControl\bin\QGroundControl.exe"),
            Path(r"C:\Program Files\QGroundControl\QGroundControl.exe"),
        ))
        if found:
            config.qgc_executable = found
            changes.append(f"QGroundControl：{found}")
    return changes
