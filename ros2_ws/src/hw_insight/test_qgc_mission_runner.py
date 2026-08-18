import math
import unittest

from hw_insight.qgc_mission_runner import (
    MAV_CMD_NAV_LAND,
    MAV_CMD_NAV_RETURN_TO_LAUNCH,
    MAV_CMD_NAV_TAKEOFF,
    MAV_CMD_NAV_WAYPOINT,
    MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
    RoutePoint,
    VehicleReference,
    global_to_local_ned,
    mission_to_route,
)


REFERENCE = VehicleReference(
    latitude_deg=47.397742,
    longitude_deg=8.545594,
    altitude_amsl_m=488.0,
    local_north_m=2.0,
    local_east_m=-1.0,
    local_down_m=-0.5,
)


def item(seq, command, north=0.0, east=0.0, altitude=8.0):
    metres_per_degree_lat = 6378137.0 * math.pi / 180.0
    metres_per_degree_lon = metres_per_degree_lat * math.cos(
        math.radians(REFERENCE.latitude_deg)
    )
    latitude = REFERENCE.latitude_deg + (
        north - REFERENCE.local_north_m
    ) / metres_per_degree_lat
    longitude = REFERENCE.longitude_deg + (
        east - REFERENCE.local_east_m
    ) / metres_per_degree_lon
    return {
        "_type": "MISSION_ITEM_INT",
        "seq": seq,
        "command": command,
        "frame": MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        "x": round(latitude * 1e7),
        "y": round(longitude * 1e7),
        "z": altitude,
    }


class MissionConversionTests(unittest.TestCase):
    def test_global_to_local_uses_current_local_anchor(self):
        north, east = global_to_local_ned(
            REFERENCE.latitude_deg, REFERENCE.longitude_deg, REFERENCE
        )
        self.assertAlmostEqual(north, 2.0)
        self.assertAlmostEqual(east, -1.0)

    def test_qgc_takeoff_waypoints_and_land(self):
        route, warnings = mission_to_route(
            [
                item(0, MAV_CMD_NAV_TAKEOFF, 0.0, 0.0, 8.0),
                item(1, MAV_CMD_NAV_WAYPOINT, 30.0, 10.0, 8.0),
                item(2, MAV_CMD_NAV_WAYPOINT, 0.0, -10.0, 12.0),
                item(3, MAV_CMD_NAV_LAND, 0.0, 0.0, 0.0),
            ],
            REFERENCE,
        )
        self.assertEqual(warnings, [])
        self.assertEqual(len(route), 4)
        self.assertAlmostEqual(route[1].north_m, 30.0, places=2)
        self.assertAlmostEqual(route[1].east_m, 10.0, places=2)
        self.assertAlmostEqual(route[1].down_m, -8.0)
        self.assertAlmostEqual(route[2].down_m, -12.0)
        self.assertEqual(route[-1].terminal, "land")
        self.assertAlmostEqual(route[-1].down_m, -12.0)

    def test_rtl_targets_takeoff_location_at_safe_height(self):
        route, _ = mission_to_route(
            [
                item(0, MAV_CMD_NAV_TAKEOFF, 5.0, 3.0, 8.0),
                item(1, MAV_CMD_NAV_WAYPOINT, 20.0, 5.0, 10.0),
                {"seq": 2, "command": MAV_CMD_NAV_RETURN_TO_LAUNCH, "frame": 0},
            ],
            REFERENCE,
        )
        self.assertEqual(route[-1].terminal, "rtl")
        self.assertAlmostEqual(route[-1].north_m, 5.0, delta=0.02)
        self.assertAlmostEqual(route[-1].east_m, 3.0, delta=0.02)
        self.assertAlmostEqual(route[-1].down_m, -10.0)

    def test_non_navigation_commands_are_ignored(self):
        route, _ = mission_to_route(
            [
                {"seq": 0, "command": 178, "frame": 2, "x": 0, "y": 0, "z": 0},
                item(1, MAV_CMD_NAV_WAYPOINT, 10.0, 1.0, 8.0),
            ],
            REFERENCE,
        )
        self.assertEqual(len(route), 1)
        self.assertIsInstance(route[0], RoutePoint)


if __name__ == "__main__":
    unittest.main()
