#!/bin/bash
# Run after a mission has been uploaded from QGroundControl to PX4.
set -eo pipefail

LOG_DIR=/home/hw/logs
ROS_WORKSPACE=/home/hw/hw-ros2/ros2
mkdir -p "$LOG_DIR"

source /opt/ros/humble/setup.bash
source "$ROS_WORKSPACE/install/setup.bash"

# Prevent two offboard controllers from commanding the same vehicle.
mapfile -t old_pids < <(pgrep -f 'qgc_mission_runner|avoid_node' || true)
for pid in "${old_pids[@]}"; do
    if [[ "$pid" != "$$" && "$pid" != "$PPID" ]]; then
        kill -9 "$pid" 2>/dev/null || true
    fi
done

echo "[$(date -Is)] Downloading the QGC mission and starting obstacle avoidance"
exec ros2 run hw_insight qgc_mission_runner -- \
    --route-file "$LOG_DIR/qgc_mission_route.json" \
    --default-flight-down -8 \
    --ros-args \
    -p max_mission_time:=1500.0 \
    -p flight_log:="$LOG_DIR/avoid_flight.log" \
    2>&1 | tee "$LOG_DIR/qgc_mission_runner.log"
