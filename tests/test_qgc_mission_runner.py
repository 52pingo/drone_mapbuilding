#!/usr/bin/env python3
"""Unit tests for hw_insight.qgc_mission_runner pure logic.

Covers coordinate conversion, mission parsing/validation, telemetry
collection, mission download handshake, and JSON serialization.  No
MAVLink connection or ROS 2 runtime is required.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import pytest

# Make the ROS 2 package importable without a colcon build.
_HERE = Path(__file__).resolve()
for _parent in _HERE.parents:
    _candidate = _parent / "ros2_ws" / "src" / "hw_insight"
    if _candidate.is_dir():
        sys.path.insert(0, str(_candidate))
        break

from hw_insight import qgc_mission_runner as qmr


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class FakeMessage:
    """Minimal stand-in for a pymavlink message."""

    def __init__(self, msg_type: str, **fields):
        self._type = msg_type
        for key, value in fields.items():
            setattr(self, key, value)

    def get_type(self) -> str:
        return self._type


class FakeItem:
    def __init__(self, payload: dict):
        self._payload = payload

    def to_dict(self) -> dict:
        return dict(self._payload)


class FakeMav:
    def __init__(self):
        self.calls: list[tuple] = []

    def mission_request_list_send(self, *args):
        self.calls.append(("list", args))

    def mission_request_int_send(self, *args):
        self.calls.append(("int", args))

    def mission_ack_send(self, *args):
        self.calls.append(("ack", args))


class FakeConnection:
    def __init__(self, messages):
        self.mav = FakeMav()
        self._messages = list(messages)

    def recv_match(self, blocking=True, timeout=0.25):
        if self._messages:
            return self._messages.pop(0)
        return None


# ---------------------------------------------------------------------------
# VehicleReference
# ---------------------------------------------------------------------------

def test_reference_altitude_amsl_at_zero_down():
    ref = qmr.VehicleReference(0.0, 0.0, 100.0, 0.0, 0.0, 0.0)
    assert ref.reference_altitude_amsl_m == 100.0


def test_reference_altitude_amsl_positive_down():
    # NED z is positive down, so a positive local_down means the vehicle is
    # below the reference altitude.
    ref = qmr.VehicleReference(0.0, 0.0, 100.0, 0.0, 0.0, 10.0)
    assert ref.reference_altitude_amsl_m == 110.0


def test_reference_altitude_amsl_negative_down():
    ref = qmr.VehicleReference(0.0, 0.0, 100.0, 0.0, 0.0, -5.0)
    assert ref.reference_altitude_amsl_m == 95.0


# ---------------------------------------------------------------------------
# global_to_local_ned
# ---------------------------------------------------------------------------

def test_global_to_local_ned_at_reference_returns_local_offset():
    ref = qmr.VehicleReference(47.0, 8.0, 100.0, 10.0, 20.0, 30.0)
    north, east = qmr.global_to_local_ned(47.0, 8.0, ref)
    assert north == 10.0
    assert east == 20.0


def test_global_to_local_ned_one_degree_north():
    ref = qmr.VehicleReference(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    north, east = qmr.global_to_local_ned(1.0, 0.0, ref)
    assert north == pytest.approx(6378137.0 * math.pi / 180.0, rel=1e-9)
    assert east == 0.0


def test_global_to_local_ned_one_degree_east_at_equator():
    ref = qmr.VehicleReference(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    north, east = qmr.global_to_local_ned(0.0, 1.0, ref)
    assert north == 0.0
    assert east == pytest.approx(6378137.0 * math.pi / 180.0, rel=1e-9)


def test_global_to_local_ned_east_scaled_by_reference_latitude():
    ref = qmr.VehicleReference(60.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    north, east = qmr.global_to_local_ned(60.0, 1.0, ref)
    expected = 6378137.0 * math.cos(math.radians(60.0)) * math.pi / 180.0
    assert north == 0.0
    assert east == pytest.approx(expected, rel=1e-9)


def test_global_to_local_ned_uses_degrees_not_radians():
    # 1 degree of latitude is ~111 km, not ~6.4 million metres.
    ref = qmr.VehicleReference(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    north, _ = qmr.global_to_local_ned(1.0, 0.0, ref)
    assert 110000.0 < north < 112000.0


def test_global_to_local_ned_adds_reference_offset():
    ref = qmr.VehicleReference(47.0, 8.0, 100.0, 100.0, 200.0, 0.0)
    north, east = qmr.global_to_local_ned(47.001, 8.001, ref)
    assert north > 100.0
    assert east > 200.0


# ---------------------------------------------------------------------------
# _item_value
# ---------------------------------------------------------------------------

def test_item_value_dict_present():
    assert qmr._item_value({"a": 1}, "a") == 1


def test_item_value_dict_missing_uses_default():
    assert qmr._item_value({"a": 1}, "b", 99) == 99


def test_item_value_object_attribute():
    class Obj:
        a = 5

    assert qmr._item_value(Obj(), "a") == 5


def test_item_value_object_missing_uses_default():
    class Obj:
        a = 5

    assert qmr._item_value(Obj(), "b", 7) == 7


# ---------------------------------------------------------------------------
# _item_lat_lon
# ---------------------------------------------------------------------------

def test_item_lat_lon_float_message_global():
    item = {"x": 47.0, "y": 8.0, "_type": "MISSION_ITEM"}
    lat, lon = qmr._item_lat_lon(item, qmr.MAV_FRAME_GLOBAL)
    assert lat == 47.0
    assert lon == 8.0


def test_item_lat_lon_int_message_global_scaled_by_1e7():
    item = {"x": 470000000, "y": 80000000, "_type": "MISSION_ITEM_INT"}
    lat, lon = qmr._item_lat_lon(item, qmr.MAV_FRAME_GLOBAL)
    assert lat == 47.0
    assert lon == 8.0


def test_item_lat_lon_int_message_local_scaled_by_1e4():
    item = {"x": 10000, "y": 20000, "_type": "MISSION_ITEM_INT"}
    north, east = qmr._item_lat_lon(item, qmr.MAV_FRAME_LOCAL_NED)
    assert north == 1.0
    assert east == 2.0


def test_item_lat_lon_large_values_scaled_even_without_int_type():
    item = {"x": 470000000, "y": 80000000}
    lat, lon = qmr._item_lat_lon(item, qmr.MAV_FRAME_GLOBAL)
    assert lat == 47.0
    assert lon == 8.0


def test_item_lat_lon_small_float_values_not_scaled():
    item = {"x": 47.5, "y": 8.5}
    lat, lon = qmr._item_lat_lon(item, qmr.MAV_FRAME_GLOBAL)
    assert lat == 47.5
    assert lon == 8.5


# ---------------------------------------------------------------------------
# mission_to_route
# ---------------------------------------------------------------------------

def _ref():
    return qmr.VehicleReference(47.0, 8.0, 100.0, 0.0, 0.0, 0.0)


def test_mission_to_route_empty_raises():
    with pytest.raises(ValueError, match="no supported navigation points"):
        qmr.mission_to_route([], _ref())


def test_mission_to_route_single_waypoint_global_relative():
    items = [
        {
            "seq": 0,
            "command": qmr.MAV_CMD_NAV_WAYPOINT,
            "frame": qmr.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            "x": 47.001,
            "y": 8.001,
            "z": 50.0,
        }
    ]
    route, warnings = qmr.mission_to_route(items, _ref())
    assert len(route) == 1
    assert warnings == []
    point = route[0]
    assert point.north_m == pytest.approx(6378137.0 * math.radians(0.001), rel=1e-6)
    assert point.east_m == pytest.approx(
        6378137.0 * math.cos(math.radians(47.0)) * math.radians(0.001), rel=1e-6
    )
    assert point.down_m == -50.0
    assert point.mission_seq == 0
    assert point.command == qmr.MAV_CMD_NAV_WAYPOINT
    assert point.terminal == ""


def test_mission_to_route_local_ned_frame_passthrough():
    items = [
        {
            "seq": 0,
            "command": qmr.MAV_CMD_NAV_WAYPOINT,
            "frame": qmr.MAV_FRAME_LOCAL_NED,
            "x": 10.0,
            "y": 20.0,
            "z": -5.0,
        }
    ]
    route, _ = qmr.mission_to_route(items, _ref())
    assert route[0].north_m == 10.0
    assert route[0].east_m == 20.0
    assert route[0].down_m == -5.0


def test_mission_to_route_global_absolute_altitude_uses_reference():
    items = [
        {
            "seq": 0,
            "command": qmr.MAV_CMD_NAV_WAYPOINT,
            "frame": qmr.MAV_FRAME_GLOBAL,
            "x": 47.001,
            "y": 8.001,
            "z": 50.0,
        }
    ]
    route, _ = qmr.mission_to_route(items, _ref())
    # reference altitude is 100 m AMSL, target is 50 m AMSL -> 50 m down
    assert route[0].down_m == 50.0


def test_mission_to_route_sorts_by_seq():
    items = [
        {"seq": 2, "command": 16, "frame": 3, "x": 47.003, "y": 8.0, "z": 50.0},
        {"seq": 0, "command": 16, "frame": 3, "x": 47.001, "y": 8.0, "z": 50.0},
        {"seq": 1, "command": 16, "frame": 3, "x": 47.002, "y": 8.0, "z": 50.0},
    ]
    route, _ = qmr.mission_to_route(items, _ref())
    assert [p.mission_seq for p in route] == [0, 1, 2]


def test_mission_to_route_loiter_becomes_waypoint_with_warning():
    items = [
        {
            "seq": 0,
            "command": qmr.MAV_CMD_NAV_LOITER_UNLIM,
            "frame": qmr.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            "x": 47.001,
            "y": 8.001,
            "z": 50.0,
        }
    ]
    route, warnings = qmr.mission_to_route(items, _ref())
    assert len(route) == 1
    assert route[0].command == qmr.MAV_CMD_NAV_LOITER_UNLIM
    assert any("loiter" in w for w in warnings)


def test_mission_to_route_unsupported_command_skipped():
    items = [
        {"seq": 0, "command": 999, "frame": 3, "x": 47.001, "y": 8.001, "z": 50.0}
    ]
    with pytest.raises(ValueError):
        qmr.mission_to_route(items, _ref())


def test_mission_to_route_unsupported_frame_skipped():
    items = [
        {"seq": 0, "command": 16, "frame": 99, "x": 1.0, "y": 2.0, "z": 3.0}
    ]
    with pytest.raises(ValueError):
        qmr.mission_to_route(items, _ref())


def test_mission_to_route_missing_command_defaults_to_zero_and_skipped():
    items = [{"seq": 0, "x": 47.001, "y": 8.001, "z": 50.0}]
    with pytest.raises(ValueError):
        qmr.mission_to_route(items, _ref())


def test_mission_to_route_rtl_without_takeoff_uses_origin():
    items = [
        {
            "seq": 0,
            "command": qmr.MAV_CMD_NAV_RETURN_TO_LAUNCH,
            "frame": qmr.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
        }
    ]
    route, warnings = qmr.mission_to_route(items, _ref())
    assert len(route) == 1
    assert route[0].north_m == 0.0
    assert route[0].east_m == 0.0
    assert route[0].terminal == "rtl"
    assert any("RTL has no takeoff" in w for w in warnings)


def test_mission_to_route_rtl_after_takeoff_uses_home():
    items = [
        {
            "seq": 0,
            "command": qmr.MAV_CMD_NAV_TAKEOFF,
            "frame": qmr.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            "x": 47.001,
            "y": 8.001,
            "z": 50.0,
        },
        {
            "seq": 1,
            "command": qmr.MAV_CMD_NAV_RETURN_TO_LAUNCH,
            "frame": qmr.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
        },
    ]
    route, warnings = qmr.mission_to_route(items, _ref())
    assert len(route) == 2
    assert route[1].terminal == "rtl"
    assert route[1].north_m == pytest.approx(route[0].north_m)
    assert route[1].east_m == pytest.approx(route[0].east_m)
    assert not any("RTL has no takeoff" in w for w in warnings)


def test_mission_to_route_land_uses_cruise_altitude_and_terminal():
    items = [
        {
            "seq": 0,
            "command": qmr.MAV_CMD_NAV_WAYPOINT,
            "frame": qmr.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            "x": 47.001,
            "y": 8.001,
            "z": 50.0,
        },
        {
            "seq": 1,
            "command": qmr.MAV_CMD_NAV_LAND,
            "frame": qmr.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            "x": 47.002,
            "y": 8.002,
            "z": 0.0,
        },
    ]
    route, _ = qmr.mission_to_route(items, _ref())
    assert route[1].terminal == "land"
    assert route[1].down_m == -50.0


def test_mission_to_route_deduplicates_identical_non_terminal_points():
    items = [
        {"seq": 0, "command": 16, "frame": 3, "x": 47.001, "y": 8.001, "z": 50.0},
        {"seq": 1, "command": 16, "frame": 3, "x": 47.001, "y": 8.001, "z": 50.0},
    ]
    route, _ = qmr.mission_to_route(items, _ref())
    assert len(route) == 1


def test_mission_to_route_keeps_terminal_duplicate():
    items = [
        {"seq": 0, "command": 16, "frame": 3, "x": 47.001, "y": 8.001, "z": 50.0},
        {"seq": 1, "command": 21, "frame": 3, "x": 47.001, "y": 8.001, "z": 0.0},
    ]
    route, _ = qmr.mission_to_route(items, _ref())
    assert len(route) == 2
    assert route[1].terminal == "land"


def test_mission_to_route_keeps_altitude_change_at_same_location():
    items = [
        {"seq": 0, "command": 16, "frame": 3, "x": 47.001, "y": 8.001, "z": 50.0},
        {"seq": 1, "command": 16, "frame": 3, "x": 47.001, "y": 8.001, "z": 80.0},
    ]
    route, _ = qmr.mission_to_route(items, _ref())
    assert len(route) == 2
    assert route[0].down_m == -50.0
    assert route[1].down_m == -80.0


def test_mission_to_route_default_flight_down_used_for_rtl():
    items = [
        {
            "seq": 0,
            "command": qmr.MAV_CMD_NAV_RETURN_TO_LAUNCH,
            "frame": qmr.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            "x": 0.0,
            "y": 0.0,
            "z": 0.0,
        }
    ]
    route, _ = qmr.mission_to_route(items, _ref(), default_flight_down_m=-12.5)
    assert route[0].down_m == -12.5


def test_mission_to_route_accepts_object_items():
    class Item:
        seq = 0
        command = 16
        frame = 3
        x = 47.001
        y = 8.001
        z = 50.0
        _type = "MISSION_ITEM"

    route, _ = qmr.mission_to_route([Item()], _ref())
    assert len(route) == 1
    assert route[0].mission_seq == 0


# ---------------------------------------------------------------------------
# TelemetryCollector
# ---------------------------------------------------------------------------

def test_telemetry_collector_not_ready_initially():
    collector = qmr.TelemetryCollector()
    assert collector.ready() is False
    with pytest.raises(RuntimeError, match="not ready"):
        collector.reference()


def test_telemetry_collector_ready_after_both_messages():
    collector = qmr.TelemetryCollector()
    collector.consume(
        FakeMessage("GLOBAL_POSITION_INT", lat=470000000, lon=80000000, alt=100000)
    )
    assert collector.ready() is False
    collector.consume(FakeMessage("LOCAL_POSITION_NED", x=1.0, y=2.0, z=3.0))
    assert collector.ready() is True


def test_telemetry_collector_reference_values():
    collector = qmr.TelemetryCollector()
    collector.consume(
        FakeMessage("GLOBAL_POSITION_INT", lat=470000000, lon=80000000, alt=100000)
    )
    collector.consume(FakeMessage("LOCAL_POSITION_NED", x=1.5, y=2.5, z=3.5))
    ref = collector.reference()
    assert ref.latitude_deg == 47.0
    assert ref.longitude_deg == 8.0
    assert ref.altitude_amsl_m == 100.0
    assert ref.local_north_m == 1.5
    assert ref.local_east_m == 2.5
    assert ref.local_down_m == 3.5


def test_telemetry_collector_ignores_other_messages():
    collector = qmr.TelemetryCollector()
    collector.consume(FakeMessage("HEARTBEAT"))
    assert collector.global_position is None
    assert collector.local_position is None


# ---------------------------------------------------------------------------
# _receive_until
# ---------------------------------------------------------------------------

def test_receive_until_returns_matching_message():
    conn = FakeConnection(
        [FakeMessage("HEARTBEAT"), FakeMessage("MISSION_COUNT", count=3)]
    )
    seen = []
    result = qmr._receive_until(
        conn, {"MISSION_COUNT"}, time.monotonic() + 1.0, seen.append
    )
    assert result is not None
    assert result.get_type() == "MISSION_COUNT"
    assert len(seen) == 2


def test_receive_until_returns_none_on_timeout():
    conn = FakeConnection([])
    result = qmr._receive_until(
        conn, {"MISSION_COUNT"}, time.monotonic() + 0.3, lambda m: None
    )
    assert result is None


# ---------------------------------------------------------------------------
# download_mission
# ---------------------------------------------------------------------------

def test_download_mission_empty_returns_empty_list():
    conn = FakeConnection([FakeMessage("MISSION_COUNT", count=0)])
    result = qmr.download_mission(conn, 1, 1, qmr.TelemetryCollector(), retries=1)
    assert result == []


def test_download_mission_returns_items_in_order():
    conn = FakeConnection(
        [
            FakeMessage("MISSION_COUNT", count=2),
            FakeMessage("MISSION_ITEM_INT", seq=0),
            FakeMessage("MISSION_ITEM_INT", seq=1),
        ]
    )
    result = qmr.download_mission(conn, 1, 1, qmr.TelemetryCollector(), retries=1)
    assert len(result) == 2
    assert [int(m.seq) for m in result] == [0, 1]


def test_download_mission_sends_ack_on_success():
    conn = FakeConnection(
        [
            FakeMessage("MISSION_COUNT", count=1),
            FakeMessage("MISSION_ITEM_INT", seq=0),
        ]
    )
    qmr.download_mission(conn, 7, 8, qmr.TelemetryCollector(), retries=1)
    ack_calls = [c for c in conn.mav.calls if c[0] == "ack"]
    assert len(ack_calls) == 1
    assert ack_calls[0][1] == (7, 8, 0)


def test_download_mission_timeout_raises():
    conn = FakeConnection([])
    with pytest.raises(TimeoutError):
        qmr.download_mission(conn, 1, 1, qmr.TelemetryCollector(), retries=1)


# ---------------------------------------------------------------------------
# save_route
# ---------------------------------------------------------------------------

def test_save_route_writes_expected_json(tmp_path):
    ref = qmr.VehicleReference(47.0, 8.0, 100.0, 1.0, 2.0, 3.0)
    route = [qmr.RoutePoint(10.0, 20.0, -30.0, 0, 16, "")]
    items = [FakeItem({"seq": 0, "command": 16})]
    path = tmp_path / "route.json"
    qmr.save_route(str(path), route, ref, items)
    data = json.loads(path.read_text())
    assert data["reference"]["latitude_deg"] == 47.0
    assert data["reference"]["local_north_m"] == 1.0
    assert data["route"][0]["north_m"] == 10.0
    assert data["route"][0]["down_m"] == -30.0
    assert data["source_mission"][0]["seq"] == 0
    assert "created_unix" in data


def test_save_route_replaces_nan_with_null(tmp_path):
    ref = qmr.VehicleReference(float("nan"), 8.0, 100.0, 0.0, 0.0, 0.0)
    route = [qmr.RoutePoint(1.0, 2.0, -3.0, 0, 16)]
    items = [FakeItem({"seq": 0})]
    path = tmp_path / "route.json"
    qmr.save_route(str(path), route, ref, items)
    data = json.loads(path.read_text())
    assert data["reference"]["latitude_deg"] is None


def test_save_route_creates_parent_directory(tmp_path):
    ref = qmr.VehicleReference(47.0, 8.0, 100.0, 0.0, 0.0, 0.0)
    route = [qmr.RoutePoint(1.0, 2.0, -3.0, 0, 16)]
    items = [FakeItem({"seq": 0})]
    path = tmp_path / "nested" / "dir" / "route.json"
    qmr.save_route(str(path), route, ref, items)
    assert path.is_file()


def test_save_route_no_tmp_file_left_behind(tmp_path):
    ref = qmr.VehicleReference(47.0, 8.0, 100.0, 0.0, 0.0, 0.0)
    route = [qmr.RoutePoint(1.0, 2.0, -3.0, 0, 16)]
    items = [FakeItem({"seq": 0})]
    path = tmp_path / "route.json"
    qmr.save_route(str(path), route, ref, items)
    assert not (tmp_path / "route.json.tmp").exists()


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------

def test_build_parser_defaults():
    args = qmr.build_parser().parse_args([])
    assert args.connection == "udpin:0.0.0.0:14540"
    assert args.source_system == 245
    assert args.source_component == 190
    assert args.default_flight_down == -8.0
    assert args.download_only is False


def test_build_parser_custom_values():
    args = qmr.build_parser().parse_args(
        [
            "--connection",
            "udp:127.0.0.1:14550",
            "--default-flight-down",
            "-15.0",
            "--download-only",
        ]
    )
    assert args.connection == "udp:127.0.0.1:14550"
    assert args.default_flight_down == -15.0
    assert args.download_only is True


# ---------------------------------------------------------------------------
# constants sanity
# ---------------------------------------------------------------------------

def test_global_frames_contains_expected_members():
    assert qmr.MAV_FRAME_GLOBAL in qmr.GLOBAL_FRAMES
    assert qmr.MAV_FRAME_GLOBAL_RELATIVE_ALT in qmr.GLOBAL_FRAMES
    assert qmr.MAV_FRAME_LOCAL_NED not in qmr.GLOBAL_FRAMES


def test_relative_alt_frames_subset_of_global_frames():
    assert qmr.RELATIVE_ALT_FRAMES.issubset(qmr.GLOBAL_FRAMES)


def test_nav_commands_contains_expected_members():
    assert qmr.MAV_CMD_NAV_WAYPOINT in qmr.NAV_COMMANDS
    assert qmr.MAV_CMD_NAV_LAND in qmr.NAV_COMMANDS
    assert qmr.MAV_CMD_NAV_RETURN_TO_LAUNCH in qmr.NAV_COMMANDS
    assert qmr.MAV_CMD_NAV_TAKEOFF in qmr.NAV_COMMANDS


def test_loiter_commands_disjoint_from_nav_commands():
    assert qmr.LOITER_COMMANDS.isdisjoint(qmr.NAV_COMMANDS)
