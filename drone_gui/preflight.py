"""Fast local preflight checks used before starting external processes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import List

from drone_gui.models import RuntimeConfig


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str
    required: bool = True


def _path_check(name: str, path: Path, kind: str = "file") -> CheckResult:
    exists = path.is_file() if kind == "file" else path.is_dir()
    return CheckResult(
        name,
        "pass" if exists else "fail",
        str(path) if exists else f"未找到：{path}",
    )


def run_local_preflight(config: RuntimeConfig) -> List[CheckResult]:
    if config.ue4_launch_mode == "standalone":
        ue4_checks = [
            _path_check("UE4 仿真程序", config.ue4_executable or Path("")),
        ]
    else:
        ue4_checks = [
            _path_check("UE4 编辑器", config.ue4_editor),
            _path_check(f"{config.environment_name} 工程", config.ue4_project),
        ]
    checks = ue4_checks + [
        _path_check("视觉 Python", config.perception_python),
        _path_check("YOLO 权重", config.weights),
        _path_check("AirSim PythonClient", config.airsim_client, "directory"),
        _path_check(
            "UE4 启动脚本", config.repo_root / "scripts" / "launch_ue4.ps1"
        ),
        _path_check(
            "任务总控脚本",
            config.repo_root / "scripts" / "run_citypark_semantic_mission.ps1",
        ),
    ]
    qgc_ready = config.qgc_executable is not None and config.qgc_executable.is_file()
    checks.append(CheckResult(
        "QGroundControl",
        "pass" if qgc_ready else "warning",
        str(config.qgc_executable) if qgc_ready else "未配置；自主任务可运行，但不能打开 QGC",
        required=False,
    ))
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    checks.append(CheckResult("WSL", "pass" if wsl else "fail", wsl or "未找到 wsl.exe"))
    parent = config.results_dir if config.results_dir.exists() else config.results_dir.parent
    writable = parent.exists() and parent.is_dir()
    checks.append(CheckResult(
        "成果目录",
        "pass" if writable else "fail",
        str(config.results_dir) if writable else f"父目录不可用：{parent}",
    ))
    checks.append(CheckResult(
        "ROS2 工作区",
        "warning",
        f"将在 WSL 内检查：{config.ros_workspace}",
        required=False,
    ))
    return checks


def has_required_failures(checks: List[CheckResult]) -> bool:
    return any(item.required and item.status == "fail" for item in checks)
