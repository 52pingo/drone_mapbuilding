"""Pure configuration and mission models shared by the Qt presentation layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
import math
from pathlib import Path
from typing import Iterable, List, Optional


CITYPARK_GOALS = (
    (181.55, -583.34),
    (-395.53, -409.16),
    (-159.49, 25.13),
    (0.0, 0.0),
)


@dataclass(frozen=True)
class Waypoint:
    north_m: float
    east_m: float

    def distance_to(self, other: "Waypoint") -> float:
        return math.hypot(
            self.north_m - other.north_m,
            self.east_m - other.east_m,
        )


@dataclass(frozen=True)
class ValidationIssue:
    level: str
    message: str


@dataclass
class MissionPlan:
    name: str = "CityPark 大环线"
    waypoints: List[Waypoint] = field(default_factory=list)
    flight_z: float = -15.0
    cruise_speed: float = 3.0
    max_speed: float = 4.0
    arrive_dist: float = 3.0
    max_mission_time: float = 1200.0

    @classmethod
    def citypark_default(cls) -> "MissionPlan":
        return cls(waypoints=[Waypoint(*point) for point in CITYPARK_GOALS])

    def goals_string(self) -> str:
        def compact(value: float) -> str:
            return f"{value:.3f}".rstrip("0").rstrip(".") or "0"

        return ";".join(
            f"{compact(point.north_m)},{compact(point.east_m)}"
            for point in self.waypoints
        )

    def route_distance(self) -> float:
        previous = Waypoint(0.0, 0.0)
        total = 0.0
        for point in self.waypoints:
            total += previous.distance_to(point)
            previous = point
        return total

    def estimated_seconds(self) -> float:
        return self.route_distance() / max(self.cruise_speed, 0.1) + 45.0

    def validate(self) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        if not self.waypoints:
            issues.append(ValidationIssue("error", "至少需要一个航点"))
        if self.flight_z >= -1.0:
            issues.append(ValidationIssue("error", "NED 飞行高度必须小于 -1 m"))
        if self.cruise_speed <= 0 or self.max_speed < self.cruise_speed:
            issues.append(ValidationIssue("error", "最大速度必须不小于巡航速度"))
        if self.arrive_dist <= 0:
            issues.append(ValidationIssue("error", "到达半径必须为正数"))
        if self.estimated_seconds() > self.max_mission_time:
            issues.append(ValidationIssue("error", "预计用时超过任务超时"))
        for index, point in enumerate(self.waypoints, 1):
            if not all(math.isfinite(v) for v in (point.north_m, point.east_m)):
                issues.append(ValidationIssue("error", f"航点 {index} 坐标无效"))
            if math.hypot(point.north_m, point.east_m) > 2000.0:
                issues.append(ValidationIssue("warning", f"航点 {index} 距原点超过 2 km"))
        if self.waypoints and self.waypoints[-1].distance_to(Waypoint(0, 0)) > 3.0:
            issues.append(ValidationIssue("warning", "末航点不是返航原点 (0,0)"))
        return issues

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["waypoints"] = [asdict(point) for point in self.waypoints]
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "MissionPlan":
        values = dict(payload)
        values["waypoints"] = [Waypoint(**point) for point in payload.get("waypoints", [])]
        return cls(**values)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "MissionPlan":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass
class RuntimeConfig:
    repo_root: Path
    ue4_editor: Path
    ue4_project: Path
    ue4_map: str
    perception_python: Path
    airsim_client: Path
    weights: Path
    results_dir: Path
    environment_name: str = "CityPark"
    ue4_launch_mode: str = "editor"
    ue4_executable: Optional[Path] = None
    airsim_settings: Optional[Path] = None
    qgc_executable: Optional[Path] = None
    ue4_validation: str = "auto"
    airsim_vehicle: str = "PX4"
    airsim_camera: str = "CameraDepth"
    wsl_distro: str = "Ubuntu-22.04"
    wsl_user: str = "hw"
    ros_workspace: str = "/home/hw/hw-ros2/ros2"
    px4_dir: str = "/home/hw/px4v1.15.2"
    micro_xrce_agent: str = "/home/hw/Micro-XRCE-DDS-Agent/build/MicroXRCEAgent"
    log_dir: str = "/home/hw/logs"
    confidence: float = 0.25
    perception_interval: float = 0.20

    @classmethod
    def defaults(cls, repo_root: Path) -> "RuntimeConfig":
        repo_root = repo_root.resolve()
        asset_root = repo_root.parent if (repo_root.parent / "best.pt").is_file() else repo_root
        return cls(
            repo_root=repo_root,
            ue4_editor=Path(r"D:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe"),
            ue4_project=Path(r"D:\CityParkEnvironmentCollec\CityPark.uproject"),
            ue4_map="/Game/CityPark/Maps/Showcase?game=/Script/AirSim.AirSimGameMode",
            perception_python=Path(
                r"C:\Users\29593\anaconda3\envs\deeplearning\python.exe"
            ),
            airsim_client=Path(
                r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient"
            ),
            weights=asset_root / "best.pt",
            results_dir=asset_root / "results",
            environment_name="CityPark",
            ue4_launch_mode="editor",
            airsim_settings=repo_root / "config" / "airsim_settings.citypark.example.json",
            qgc_executable=Path(
                r"E:\无人机视觉避障建图\QGroundControl\bin\QGroundControl.exe"
            ),
        )

    @classmethod
    def load(cls, path: Path | None, repo_root: Path) -> "RuntimeConfig":
        config = cls.defaults(repo_root)
        if path is None or not path.is_file():
            return config
        payload = json.loads(path.read_text(encoding="utf-8"))
        path_names = {
            "repo_root", "ue4_editor", "ue4_project", "perception_python",
            "airsim_client", "weights", "results_dir", "ue4_executable",
            "airsim_settings", "qgc_executable",
        }
        known = {item.name for item in fields(cls)}
        for name, value in payload.items():
            if name not in known:
                continue
            setattr(
                config,
                name,
                Path(value) if name in path_names and value else value,
            )
        config.repo_root = repo_root.resolve()
        return config

    def to_dict(self) -> dict:
        return {
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(self).items()
        }


def replace_waypoints(points: Iterable[Waypoint]) -> List[Waypoint]:
    return [Waypoint(float(point.north_m), float(point.east_m)) for point in points]
