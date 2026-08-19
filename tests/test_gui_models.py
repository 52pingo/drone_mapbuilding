from pathlib import Path

from drone_gui.models import MissionPlan, RuntimeConfig, Waypoint


def test_citypark_plan_formats_goals_and_returns_home():
    plan = MissionPlan.citypark_default()
    assert plan.goals_string() == (
        "181.55,-583.34;-395.53,-409.16;-159.49,25.13;0,0"
    )
    assert plan.route_distance() > 1500
    assert not [issue for issue in plan.validate() if issue.level == "error"]


def test_plan_validation_rejects_unsafe_parameters():
    plan = MissionPlan(
        waypoints=[Waypoint(10, 10)],
        flight_z=0,
        cruise_speed=4,
        max_speed=2,
        max_mission_time=1,
    )
    messages = [issue.message for issue in plan.validate()]
    assert any("飞行高度" in message for message in messages)
    assert any("最大速度" in message for message in messages)
    assert any("任务超时" in message for message in messages)
    assert any("返航原点" in message for message in messages)


def test_plan_json_round_trip(tmp_path):
    path = tmp_path / "mission.json"
    expected = MissionPlan.citypark_default()
    expected.save(path)
    actual = MissionPlan.load(path)
    assert actual.to_dict() == expected.to_dict()


def test_runtime_defaults_find_assets_in_parent(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "best.pt").write_bytes(b"weight")
    config = RuntimeConfig.defaults(repo)
    assert config.weights == tmp_path / "best.pt"
    assert config.results_dir == tmp_path / "results"


def test_runtime_config_loads_optional_environment_paths(tmp_path):
    config_path = tmp_path / "gui.json"
    config_path.write_text(
        '{"environment_name":"Park","ue4_launch_mode":"standalone",'
        '"ue4_executable":"D:\\\\Park\\\\Park.exe","qgc_executable":null}',
        encoding="utf-8",
    )
    config = RuntimeConfig.load(config_path, tmp_path)
    assert config.environment_name == "Park"
    assert config.ue4_launch_mode == "standalone"
    assert config.ue4_executable == Path(r"D:\Park\Park.exe")
    assert config.qgc_executable is None
