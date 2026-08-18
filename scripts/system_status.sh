#!/bin/bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /home/hw/hw-ros2/ros2/install/setup.bash

echo "=== Processes ==="
pgrep -af 'px4$|MicroXRCEAgent|ros2 launch hw_insight|qgc_mission_runner' || true
echo "=== Latest mission ==="
grep -E 'WAYPOINT|MISSION DONE|TIMEOUT|STUCK' /home/hw/logs/qgc_mission_runner.log 2>/dev/null | tail -30 || true
echo "=== Vehicle status ==="
timeout 5 ros2 topic echo --once \
    --qos-reliability best_effort --qos-durability transient_local \
    /fmu/out/vehicle_status px4_msgs/msg/VehicleStatus \
    | grep -E 'arming_state:|nav_state:|failsafe:|pre_flight_checks_pass:' || true
echo "=== Vehicle local position ==="
timeout 5 ros2 topic echo --once \
    --qos-reliability best_effort --qos-durability transient_local \
    /fmu/out/vehicle_local_position px4_msgs/msg/VehicleLocalPosition \
    | grep -E '^(x|y|z):' || true
