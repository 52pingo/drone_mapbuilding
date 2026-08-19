"""Build external commands without depending on Qt or shell string interpolation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath
import re
from typing import Sequence

from drone_gui.models import MissionPlan, RuntimeConfig


@dataclass(frozen=True)
class CommandSpec:
    program: str
    arguments: Sequence[str]
    working_directory: Path

    def display(self) -> str:
        parts = [self.program, *self.arguments]
        return " ".join(f'"{part}"' if " " in part else part for part in parts)


def windows_path_to_wsl(path: Path) -> str:
    value = str(path)
    pure = PureWindowsPath(value)
    if not pure.drive:
        pure = PureWindowsPath(str(path.resolve()))
        value = str(pure)
    if not pure.drive or len(pure.drive) != 2:
        raise ValueError(f"需要 Windows 盘符绝对路径: {value}")
    drive = pure.drive[0].lower()
    tail = "/".join(pure.parts[1:])
    return f"/mnt/{drive}/{tail}"


class CommandBuilder:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    def launch_ue4(self) -> CommandSpec:
        script = self.config.repo_root / "scripts" / "launch_ue4.ps1"
        args = [
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-TimeoutSeconds", "300",
            "-LaunchMode", self.config.ue4_launch_mode,
            "-Ue4EditorPath", str(self.config.ue4_editor),
            "-ProjectPath", str(self.config.ue4_project),
            "-StandaloneExecutable", str(self.config.ue4_executable or ""),
            "-Map", self.config.ue4_map,
            "-Python", str(self.config.perception_python),
            "-AirSimClientPath", str(self.config.airsim_client),
            "-ValidationMode", self.config.ue4_validation,
            "-VehicleName", self.config.airsim_vehicle,
            "-CameraName", self.config.airsim_camera,
        ]
        return CommandSpec("powershell.exe", args, self.config.repo_root)

    def launch_qgc(self) -> CommandSpec:
        if self.config.qgc_executable is None:
            raise ValueError("尚未配置 QGroundControl 路径")
        return CommandSpec(
            str(self.config.qgc_executable), (), self.config.qgc_executable.parent
        )

    def setup_environment(self, mode: str) -> CommandSpec:
        if mode not in {"check", "install"}:
            raise ValueError(f"不支持的环境配置模式：{mode}")
        script = self.config.repo_root / "scripts" / "setup_workflow_environment.ps1"
        args = [
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-Mode", mode,
            "-PerceptionPython", str(self.config.perception_python),
            "-AirSimClientPath", str(self.config.airsim_client),
            "-AirSimSettings", str(self.config.airsim_settings or ""),
            "-QgcExecutable", str(self.config.qgc_executable or ""),
            "-Ue4Project", str(self.config.ue4_project),
            "-WslDistro", self.config.wsl_distro,
            "-WslUser", self.config.wsl_user,
            "-RosWorkspace", self.config.ros_workspace,
            "-Px4Dir", self.config.px4_dir,
            "-MicroXrceAgent", self.config.micro_xrce_agent,
        ]
        return CommandSpec("powershell.exe", args, self.config.repo_root)

    def restart_stack(self) -> CommandSpec:
        script = windows_path_to_wsl(
            self.config.repo_root / "scripts" / "restart_stack.sh"
        )
        args = [
            "-d", self.config.wsl_distro,
            "-u", self.config.wsl_user,
            "--", "env",
            f"ROS_WORKSPACE={self.config.ros_workspace}",
            f"PX4_DIR={self.config.px4_dir}",
            f"MICRO_XRCE_AGENT={self.config.micro_xrce_agent}",
            f"LOG_DIR={self.config.log_dir}",
            "bash", script,
        ]
        return CommandSpec("wsl.exe", args, self.config.repo_root)

    def probe_stack(self) -> CommandSpec:
        script = windows_path_to_wsl(
            self.config.repo_root / "scripts" / "gui_backend_probe.sh"
        )
        args = [
            "-d", self.config.wsl_distro,
            "-u", self.config.wsl_user,
            "--", "env", f"ROS_WORKSPACE={self.config.ros_workspace}",
            "bash", script,
        ]
        return CommandSpec("wsl.exe", args, self.config.repo_root)

    def mission_control(self, action: str) -> CommandSpec:
        if action not in {"hold", "resume", "land"}:
            raise ValueError(f"不支持的任务控制: {action}")
        script = windows_path_to_wsl(
            self.config.repo_root / "scripts" / "gui_mission_control.sh"
        )
        args = [
            "-d", self.config.wsl_distro,
            "-u", self.config.wsl_user,
            "--", "env", f"ROS_WORKSPACE={self.config.ros_workspace}",
            "bash", script, action,
        ]
        return CommandSpec("wsl.exe", args, self.config.repo_root)

    def run_mission(self, plan: MissionPlan) -> CommandSpec:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", self.config.environment_name).strip("_")
        result_root = self.config.results_dir / f"gui_{slug or 'environment'}_{stamp}"
        script = self.config.repo_root / "scripts" / "run_citypark_semantic_mission.ps1"
        args = [
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-Weights", str(self.config.weights),
            "-Python", str(self.config.perception_python),
            "-WslDistro", self.config.wsl_distro,
            "-WslUser", self.config.wsl_user,
            "-Confidence", f"{self.config.confidence:.3f}",
            "-PerceptionInterval", f"{self.config.perception_interval:.3f}",
            "-EnvironmentName", self.config.environment_name,
            "-AirSimClientPath", str(self.config.airsim_client),
            "-VehicleName", self.config.airsim_vehicle,
            "-CameraName", self.config.airsim_camera,
            "-RosWorkspace", self.config.ros_workspace,
            "-LogDir", self.config.log_dir,
            "-Goals", plan.goals_string(),
            "-FlightZ", f"{plan.flight_z:.3f}",
            "-MaxMissionTime", f"{plan.max_mission_time:.1f}",
            "-ResultRoot", str(result_root),
        ]
        return CommandSpec("powershell.exe", args, self.config.repo_root)
