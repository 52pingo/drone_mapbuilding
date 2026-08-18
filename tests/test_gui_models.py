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
