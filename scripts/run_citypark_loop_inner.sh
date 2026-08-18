#!/bin/bash
# CityPark perimeter loop: three broad legs and a return to the safe spawn.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${DRONE_MAPBUILDING_ROOT_WSL:-$(cd "$SCRIPT_DIR/.." && pwd)}"
WIN_DEST="${1:-$PROJECT_ROOT/results/citypark_loop_unknown}"
LOG_DIR="${LOG_DIR:-$HOME/logs}"
ROS_WORKSPACE="${ROS_WORKSPACE:-$HOME/hw-ros2/ros2}"
MAP_BRIDGE_PID=""
MAP_BRIDGE_LOG="$LOG_DIR/gui_map_bridge.log"

stop_map_bridge() {
    if [ -n "$MAP_BRIDGE_PID" ] && kill -0 "$MAP_BRIDGE_PID" 2>/dev/null; then
        kill "$MAP_BRIDGE_PID" 2>/dev/null || true
        wait "$MAP_BRIDGE_PID" 2>/dev/null || true
    fi
    MAP_BRIDGE_PID=""
}
trap stop_map_bridge EXIT
trap 'stop_map_bridge; exit 130' INT
trap 'stop_map_bridge; exit 143' TERM

# Coordinates are PX4 local NED metres relative to the safe CityPark spawn
# (AirSim world X=-134.09, Y=258.15).  The three remote points are verified
# paved/playground regions, producing one large clockwise loop without zigzags.
GOALS="${CITYPARK_GOALS:-181.55,-583.34;-395.53,-409.16;-159.49,25.13;0,0}"
FLIGHT_Z="${CITYPARK_FLIGHT_Z:--15.0}"
MAX_TIME="${CITYPARK_MAX_TIME:-1200.0}"

source /opt/ros/humble/setup.bash
source "$ROS_WORKSPACE/install/setup.bash"

# Ensure no previous offboard controller can publish competing setpoints.
for pid in $(ps -eo pid,cmd | grep -E \
    'avoid_node|run_avoid_mission|qgc_mission_runner' \
    | grep -v grep | awk '{print $1}'); do
    kill -9 "$pid" 2>/dev/null || true
done
sleep 1

mkdir -p "$WIN_DEST/live_map"

echo "== 等待 PX4 位置/状态就绪 =="
for i in $(seq 1 40); do
    if timeout 3 ros2 topic echo --once \
        --qos-reliability best_effort --qos-durability transient_local \
        /fmu/out/vehicle_local_position px4_msgs/msg/VehicleLocalPosition \
        >/dev/null 2>&1; then
        echo "telemetry ready"
        break
    fi
    sleep 2
    if [ "$i" -eq 40 ]; then
        echo "telemetry not ready"
        exit 1
    fi
done

echo "== 启动 GUI OctoMap 实时桥接 =="
python3 "$SCRIPT_DIR/gui_map_bridge.py" \
    --output-dir "$WIN_DEST/live_map" \
    --max-points 80000 --interval 1.0 \
    > "$MAP_BRIDGE_LOG" 2>&1 &
MAP_BRIDGE_PID=$!
sleep 1
if ! kill -0 "$MAP_BRIDGE_PID" 2>/dev/null; then
    echo "warning: GUI map bridge did not stay alive; see $MAP_BRIDGE_LOG"
    MAP_BRIDGE_PID=""
fi

echo "== 启动 CityPark 大环线 VFH 任务 =="
echo "goals=$GOALS flight_z=$FLIGHT_Z"
MISSION_CONSOLE_LOG="$LOG_DIR/citypark_mission_console.log"
python3 "$SCRIPT_DIR/run_avoid_mission.py" --ros-args \
    -p goals:="$GOALS" \
    -p flight_z:="$FLIGHT_Z" \
    -p cruise_speed:=3.0 \
    -p max_speed:=4.0 \
    -p arrive_dist:=3.0 \
    -p max_mission_time:="$MAX_TIME" \
    -p mode:="navigate" 2>&1 | tee "$MISSION_CONSOLE_LOG"

echo "== 生成轨迹图与 OctoMap 图 =="
python3 "$SCRIPT_DIR/plot_flight.py" \
    "$LOG_DIR/avoid_flight.log" \
    "$LOG_DIR/flight_trajectory_citypark_loop.png" \
    "$GOALS" \
    "CityPark"
timeout 30 python3 "$SCRIPT_DIR/render_map.py" \
    "$LOG_DIR/octomap_map_citypark_loop.png"
timeout 15 python3 "$SCRIPT_DIR/capture_depth_topic.py" \
    "$LOG_DIR/depth_rviz_citypark.png"
MAP_BT="$LOG_DIR/octomap_citypark_loop.bt"
if ! timeout 30 ros2 run octomap_server octomap_saver_node --ros-args \
    -p octomap_path:="$MAP_BT" -p full:=false; then
    echo "warning: OctoMap BT export failed"
fi
stop_map_bridge

echo "== 拷回 Windows 交付目录 =="
mkdir -p "$WIN_DEST"
cp "$LOG_DIR/avoid_flight.log" "$WIN_DEST/"
cp "$LOG_DIR/flight_trajectory_citypark_loop.png" "$WIN_DEST/"
cp "$LOG_DIR/octomap_map_citypark_loop.png" "$WIN_DEST/"
cp "$LOG_DIR/depth_rviz_citypark.png" "$WIN_DEST/"
cp "$MISSION_CONSOLE_LOG" "$WIN_DEST/mission_console.log"
cp "$MAP_BRIDGE_LOG" "$WIN_DEST/map_bridge.log" 2>/dev/null || true
if [ -f "$MAP_BT" ]; then
    cp "$MAP_BT" "$WIN_DEST/octomap_citypark_loop.bt"
fi

echo "== 完成：$WIN_DEST =="
