#!/bin/bash
set -eo pipefail

source /opt/ros/humble/setup.bash
source /home/hw/hw-ros2/ros2/install/setup.bash

LOG_DIR=/home/hw/logs
TOOLS_DIR=/home/hw/tools

python3 "$TOOLS_DIR/plot_flight.py" \
    "$LOG_DIR/avoid_flight.log" \
    "$LOG_DIR/flight_trajectory_qgc.png" \
    "$LOG_DIR/qgc_mission_route.json"

timeout 30 ros2 run octomap_server octomap_saver_node --ros-args \
    -p octomap_path:="$LOG_DIR/octomap_qgc.bt" \
    -p full:=false

timeout 30 python3 "$TOOLS_DIR/render_map.py" \
    "$LOG_DIR/octomap_map_qgc.png"
