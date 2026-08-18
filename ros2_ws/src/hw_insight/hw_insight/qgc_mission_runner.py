#!/usr/bin/env python3
"""Run the proven ROS 2 obstacle avoider from a mission uploaded by QGC.

QGroundControl uploads the plan to PX4 over the normal GCS link (UDP 14550).
This program uses PX4's separate API link (UDP 14540), downloads the stored
mission, converts global MAVLink coordinates to the current PX4 local NED
frame, and then hands the resulting route to ``AvoidNode``.  QGC therefore
remains the mission editor while the ROS 2 node remains the flight controller.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Callable, Iterable, Optional


# MAVLink constants used by the pure conversion layer.  Keeping these here
# makes the coordinate/mission tests runnable without ROS 2 or pymavlink.
MAV_FRAME_GLOBAL = 0
MAV_FRAME_LOCAL_NED = 1
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3
MAV_FRAME_GLOBAL_INT = 5
MAV_FRAME_GLOBAL_RELATIVE_ALT_INT = 6
MAV_FRAME_GLOBAL_TERRAIN_ALT = 10
MAV_FRAME_GLOBAL_TERRAIN_ALT_INT = 11

MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_LOITER_UNLIM = 17
MAV_CMD_NAV_LOITER_TURNS = 18
MAV_CMD_NAV_LOITER_TIME = 19
MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
MAV_CMD_NAV_LAND = 21
MAV_CMD_NAV_TAKEOFF = 22

GLOBAL_FRAMES = {
    MAV_FRAME_GLOBAL,
    MAV_FRAME_GLOBAL_RELATIVE_ALT,
    MAV_FRAME_GLOBAL_INT,
    MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
    MAV_FRAME_GLOBAL_TERRAIN_ALT,
    MAV_FRAME_GLOBAL_TERRAIN_ALT_INT,
}
RELATIVE_ALT_FRAMES = {
    MAV_FRAME_GLOBAL_RELATIVE_ALT,
    MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
    MAV_FRAME_GLOBAL_TERRAIN_ALT,
    MAV_FRAME_GLOBAL_TERRAIN_ALT_INT,
}
NAV_COMMANDS = {
    MAV_CMD_NAV_WAYPOINT,
    MAV_CMD_NAV_RETURN_TO_LAUNCH,
    MAV_CMD_NAV_LAND,
    MAV_CMD_NAV_TAKEOFF,
}
LOITER_COMMANDS = {
    MAV_CMD_NAV_LOITER_UNLIM,
    MAV_CMD_NAV_LOITER_TURNS,
    MAV_CMD_NAV_LOITER_TIME,
}


@dataclass(frozen=True)
class VehicleReference:
    """Simultaneous global/local vehicle position used as a NED anchor."""

    latitude_deg: float
    longitude_deg: float
    altitude_amsl_m: float
    local_north_m: float
    local_east_m: float
    local_down_m: float

    @property
    def reference_altitude_amsl_m(self) -> float:
        # NED z is positive down: global altitude = reference altitude - z.
        return self.altitude_amsl_m + self.local_down_m


@dataclass(frozen=True)
class RoutePoint:
    north_m: float
    east_m: float
    down_m: float
    mission_seq: int
    command: int
    terminal: str = ""


def global_to_local_ned(
    latitude_deg: float,
    longitude_deg: float,
    reference: VehicleReference,
) -> tuple[float, float]:
    """Convert WGS84 degrees to a short-range tangent-plane NED position."""

    earth_radius_m = 6378137.0
    d_lat = math.radians(latitude_deg - reference.latitude_deg)
    d_lon = math.radians(longitude_deg - reference.longitude_deg)
    north = reference.local_north_m + earth_radius_m * d_lat
    east = (
        reference.local_east_m
        + earth_radius_m * math.cos(math.radians(reference.latitude_deg)) * d_lon
    )
    return north, east


def _item_value(item, name: str, default=0):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _item_lat_lon(item, frame: int) -> tuple[float, float]:
    x = float(_item_value(item, "x"))
    y = float(_item_value(item, "y"))
    message_type = str(_item_value(item, "_type", ""))
    # MISSION_ITEM_INT uses degrees * 1e7 globally and metres * 1e4 locally.
    if message_type == "MISSION_ITEM_INT" or abs(x) > 1000 or abs(y) > 1000:
        scale = 1e7 if frame in GLOBAL_FRAMES else 1e4
        return x / scale, y / scale
    return x, y


def mission_to_route(
    items: Iterable,
    reference: VehicleReference,
    default_flight_down_m: float = -8.0,
) -> tuple[list[RoutePoint], list[str]]:
    """Convert supported MAVLink mission items to local NED route points.

    Camera/ROI/speed commands are deliberately ignored. Land/RTL are retained
    as terminal *locations*; actual landing is performed by AvoidNode only
    after obstacle-aware arrival at the final point.
    """

    route: list[RoutePoint] = []
    warnings: list[str] = []
    home_global: Optional[tuple[float, float]] = None
    cruise_down = float(default_flight_down_m)

    for item in sorted(items, key=lambda value: int(_item_value(value, "seq"))):
        seq = int(_item_value(item, "seq"))
        command = int(_item_value(item, "command"))
        frame = int(_item_value(item, "frame"))

        if command in LOITER_COMMANDS:
            warnings.append(f"seq {seq}: loiter is treated as a waypoint")
            command = MAV_CMD_NAV_WAYPOINT
        elif command not in NAV_COMMANDS:
            continue

        if command == MAV_CMD_NAV_RETURN_TO_LAUNCH:
            if home_global is None:
                north, east = 0.0, 0.0
                warnings.append(
                    f"seq {seq}: RTL has no takeoff location; using local origin"
                )
            else:
                north, east = global_to_local_ned(*home_global, reference)
            down = cruise_down
            terminal = "rtl"
        else:
            if frame in GLOBAL_FRAMES:
                latitude, longitude = _item_lat_lon(item, frame)
                north, east = global_to_local_ned(latitude, longitude, reference)
                if command == MAV_CMD_NAV_TAKEOFF and home_global is None:
                    home_global = (latitude, longitude)
            elif frame == MAV_FRAME_LOCAL_NED:
                north, east = _item_lat_lon(item, frame)
            else:
                warnings.append(f"seq {seq}: unsupported MAVLink frame {frame}")
                continue

            altitude = float(_item_value(item, "z"))
            if command == MAV_CMD_NAV_LAND:
                # Fly to the land coordinate at the preceding safe altitude;
                # AvoidNode issues the actual land command after arrival.
                down = cruise_down
                terminal = "land"
            elif frame in RELATIVE_ALT_FRAMES:
                down = -altitude
                cruise_down = down
                terminal = ""
            elif frame in (MAV_FRAME_GLOBAL, MAV_FRAME_GLOBAL_INT):
                down = reference.reference_altitude_amsl_m - altitude
                cruise_down = down
                terminal = ""
            else:  # LOCAL_NED
                down = altitude
                cruise_down = down
                terminal = ""

        route.append(
            RoutePoint(
                north_m=float(north),
                east_m=float(east),
                down_m=float(down),
                mission_seq=seq,
                command=int(_item_value(item, "command")),
                terminal=terminal,
            )
        )

    # PX4/QGC can include co-located mission items (for example takeoff plus
    # the first waypoint). Retain altitude changes, but remove exact duplicates.
    deduplicated: list[RoutePoint] = []
    for point in route:
        if deduplicated:
            previous = deduplicated[-1]
            same = (
                math.hypot(point.north_m - previous.north_m,
                           point.east_m - previous.east_m) < 0.05
                and abs(point.down_m - previous.down_m) < 0.05
                and not point.terminal
            )
            if same:
                continue
        deduplicated.append(point)

    if not deduplicated:
        raise ValueError("QGC/PX4 mission contains no supported navigation points")
    return deduplicated, warnings


def _load_mavlink(px4_root: str):
    os.environ.setdefault("MAVLINK20", "1")
    bundled = str(Path(px4_root) / "src/modules/mavlink/mavlink")
    if bundled not in sys.path:
        sys.path.insert(0, bundled)
    from pymavlink import mavutil  # pylint: disable=import-outside-toplevel

    return mavutil


def _receive_until(connection, types, deadline: float, on_message: Callable):
    while time.monotonic() < deadline:
        message = connection.recv_match(blocking=True, timeout=0.25)
        if message is None:
            continue
        on_message(message)
        if message.get_type() in types:
            return message
    return None


class TelemetryCollector:
    def __init__(self):
        self.global_position = None
        self.local_position = None

    def consume(self, message) -> None:
        message_type = message.get_type()
        if message_type == "GLOBAL_POSITION_INT":
            self.global_position = message
        elif message_type == "LOCAL_POSITION_NED":
            self.local_position = message

    def ready(self) -> bool:
        return self.global_position is not None and self.local_position is not None

    def reference(self) -> VehicleReference:
        if not self.ready():
            raise RuntimeError("PX4 global/local position telemetry is not ready")
        return VehicleReference(
            latitude_deg=self.global_position.lat / 1e7,
            longitude_deg=self.global_position.lon / 1e7,
            altitude_amsl_m=self.global_position.alt / 1000.0,
            local_north_m=float(self.local_position.x),
            local_east_m=float(self.local_position.y),
            local_down_m=float(self.local_position.z),
        )


def download_mission(connection, target_system: int, target_component: int,
                     collector: TelemetryCollector, retries: int = 4):
    """Download one MAVLink mission using the standard request-list handshake."""

    for _ in range(retries):
        connection.mav.mission_request_list_send(target_system, target_component)
        count_message = _receive_until(
            connection, {"MISSION_COUNT"}, time.monotonic() + 2.0, collector.consume
        )
        if count_message is None:
            continue
        count = int(count_message.count)
        if count == 0:
            return []

        items = []
        for seq in range(count):
            item = None
            for _item_retry in range(retries):
                connection.mav.mission_request_int_send(
                    target_system, target_component, seq
                )
                candidate = _receive_until(
                    connection,
                    {"MISSION_ITEM_INT", "MISSION_ITEM"},
                    time.monotonic() + 1.5,
                    collector.consume,
                )
                if candidate is not None and int(candidate.seq) == seq:
                    item = candidate
                    break
            if item is None:
                break
            items.append(item)
        if len(items) == count:
            # MAV_MISSION_ACCEPTED = 0. The bundled PX4 pymavlink supports the
            # MAVLink-1 compatible call on every version used by this project.
            connection.mav.mission_ack_send(target_system, target_component, 0)
            return items
    raise TimeoutError("unable to download a complete mission from PX4")


def wait_for_qgc_route(args):
    mavutil = _load_mavlink(args.px4_root)
    connection = mavutil.mavlink_connection(
        args.connection,
        source_system=args.source_system,
        source_component=args.source_component,
        autoreconnect=True,
    )
    print(f"[QGC] waiting for PX4 heartbeat on {args.connection}", flush=True)
    heartbeat = None
    heartbeat_deadline = time.monotonic() + args.heartbeat_timeout
    while time.monotonic() < heartbeat_deadline:
        candidate = connection.recv_match(
            type="HEARTBEAT", blocking=True, timeout=0.5
        )
        if candidate is None:
            continue
        # PX4 forwards traffic between MAVLink links, so QGC's own heartbeat
        # (normally sysid 255 / MAV_TYPE_GCS / invalid autopilot) can arrive on
        # UDP 14540 before the vehicle heartbeat. Never select the GCS as the
        # mission target.
        if (
            int(candidate.type) == int(mavutil.mavlink.MAV_TYPE_GCS)
            or int(candidate.autopilot)
            == int(mavutil.mavlink.MAV_AUTOPILOT_INVALID)
        ):
            print(
                f"[QGC] ignoring forwarded GCS heartbeat "
                f"sys={candidate.get_srcSystem()} comp={candidate.get_srcComponent()}",
                flush=True,
            )
            continue
        heartbeat = candidate
        break
    if heartbeat is None:
        raise TimeoutError("PX4 heartbeat not received on the API link")
    target_system = int(heartbeat.get_srcSystem())
    target_component = int(heartbeat.get_srcComponent() or 1)
    print(f"[QGC] PX4 connected sys={target_system} comp={target_component}", flush=True)

    collector = TelemetryCollector()
    telemetry_deadline = time.monotonic() + args.telemetry_timeout
    while not collector.ready() and time.monotonic() < telemetry_deadline:
        message = connection.recv_match(blocking=True, timeout=0.5)
        if message is not None:
            collector.consume(message)
    if not collector.ready():
        raise TimeoutError("GLOBAL_POSITION_INT/LOCAL_POSITION_NED not received")

    while True:
        try:
            items = download_mission(
                connection, target_system, target_component, collector
            )
        except TimeoutError as error:
            print(f"[QGC] {error}; retrying", flush=True)
            time.sleep(args.poll_interval)
            continue
        if items:
            reference = collector.reference()
            route, warnings = mission_to_route(
                items, reference, args.default_flight_down
            )
            for warning in warnings:
                print(f"[QGC] warning: {warning}", flush=True)
            return route, reference, items
        print("[QGC] no mission stored; create and Upload a plan in QGC", flush=True)
        time.sleep(args.poll_interval)


def save_route(path: str, route: list[RoutePoint], reference: VehicleReference,
               items) -> None:
    def json_safe(value):
        """Replace MAVLink NaN/Inf placeholders with strict-JSON null values."""
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {key: json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_safe(item) for item in value]
        return value

    output = {
        "created_unix": time.time(),
        "reference": asdict(reference),
        "route": [asdict(point) for point in route],
        "source_mission": [item.to_dict() for item in items],
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(json_safe(output), indent=2, allow_nan=False), encoding="utf-8"
    )
    temporary.replace(destination)


def run_avoider(route: list[RoutePoint], ros_args: Optional[list[str]] = None) -> None:
    import rclpy  # pylint: disable=import-outside-toplevel
    from hw_insight.avoid_node import AvoidNode  # pylint: disable=import-outside-toplevel

    class QgcAvoidNode(AvoidNode):
        def __init__(self, mission_route):
            super().__init__()
            self.goal_list = [
                (point.north_m, point.east_m) for point in mission_route
            ]
            self.goal_altitudes = [point.down_m for point in mission_route]
            self.goal_idx = 0
            self.goal_x, self.goal_y = self.goal_list[0]
            self.flight_z = self.goal_altitudes[0]
            self.get_logger().info(
                "QGC mission loaded: %d points, route=%s"
                % (
                    len(mission_route),
                    ";".join(
                        "%.1f,%.1f,%.1f"
                        % (point.north_m, point.east_m, point.down_m)
                        for point in mission_route
                    ),
                )
            )

        def compute_avoid(self, now):
            self.flight_z = self.goal_altitudes[
                min(self.goal_idx, len(self.goal_altitudes) - 1)
            ]
            return super().compute_avoid(now)

    rclpy.init(args=ros_args or [])
    node = QgcAvoidNode(route)
    try:
        while rclpy.ok() and node.state != "DONE":
            rclpy.spin_once(node, timeout_sec=0.25)
        # Let the DONE branch emit its final log line before closing the file.
        if rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(node, "log_fh"):
            node.log_fh.close()
        node.destroy_node()
        rclpy.shutdown()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download the QGC mission from PX4 and run obstacle avoidance"
    )
    parser.add_argument("--connection", default="udpin:0.0.0.0:14540")
    parser.add_argument("--px4-root", default="/home/hw/px4v1.15.2")
    parser.add_argument("--source-system", type=int, default=245)
    parser.add_argument("--source-component", type=int, default=190)
    parser.add_argument("--heartbeat-timeout", type=float, default=120.0)
    parser.add_argument("--telemetry-timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--default-flight-down", type=float, default=-8.0)
    parser.add_argument(
        "--route-file", default="/home/hw/logs/qgc_mission_route.json"
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="download/convert/save the QGC mission without arming or flying",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args, ros_args = build_parser().parse_known_args(argv)
    try:
        route, reference, items = wait_for_qgc_route(args)
        save_route(args.route_file, route, reference, items)
        print(f"[QGC] route saved to {args.route_file}", flush=True)
        for index, point in enumerate(route):
            print(
                "[QGC] %02d seq=%d NED=(%.1f, %.1f, %.1f) %s"
                % (
                    index,
                    point.mission_seq,
                    point.north_m,
                    point.east_m,
                    point.down_m,
                    point.terminal,
                ),
                flush=True,
            )
        if args.download_only:
            print("[QGC] download-only check complete; vehicle was not commanded", flush=True)
            return 0
        run_avoider(route, ros_args)
        return 0
    except Exception as error:  # Keep a useful error in the detached log.
        print(f"[QGC] fatal: {type(error).__name__}: {error}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
