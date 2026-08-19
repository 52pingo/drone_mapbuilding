#!/bin/bash
# 重启 PX4 + MicroXRCEAgent + lesson4 建图链路
# 全部 setsid 脱离会话、日志写入 ~/logs/，避免后台任务输出膨胀被杀
set -u
LOG="${LOG_DIR:-$HOME/logs}"
PX4_DIR="${PX4_DIR:-$HOME/px4v1.15.2}"
ROS_WORKSPACE="${ROS_WORKSPACE:-$HOME/hw-ros2/ros2}"
MICRO_XRCE_AGENT="${MICRO_XRCE_AGENT:-$HOME/Micro-XRCE-DDS-Agent/build/MicroXRCEAgent}"
mkdir -p "$LOG"
cd "$HOME"

# 清理旧进程。先杀 launch 管理器，再显式清掉各子节点：
# 只 pkill "ros2 launch" 时，launch 被强杀后子节点会成孤儿继续运行，导致
# airsim_node/depth_clamp 等出现双实例，故必须逐个清理。
pkill -f "MicroXRCEAgent" 2>/dev/null
pkill -f "hw_insight.lesson4" 2>/dev/null
pkill -f "ros2 launch" 2>/dev/null
pkill -f "airsim_node" 2>/dev/null
pkill -f "depth_clamp" 2>/dev/null
pkill -f "point_cloud_xyz_radial_node" 2>/dev/null
pkill -f "cloud_relay" 2>/dev/null
pkill -f "octomap_server_node" 2>/dev/null
pkill -f "rviz2" 2>/dev/null
sleep 2
# PX4 的 pxh 进程
pkill -f "px4 px4_sitl" 2>/dev/null
pkill -f "px4_sitl_default" 2>/dev/null
sleep 2

# 1. PX4 SITL：用 script 分配 80x24 pty，避免 WSLG 误报 131072x1 屏幕导致
#    pxh 提示符无限重绘、日志膨胀
echo "== starting PX4 =="
cd "$PX4_DIR"
setsid script -qfc "make px4_sitl_default none_iris 2>&1" "$LOG/px4.log" </dev/null >/dev/null 2>&1 &
echo "PX4 pid=$!"

# 2. MicroXRCEAgent
sleep 4
echo "== starting MicroXRCEAgent =="
setsid "$MICRO_XRCE_AGENT" udp4 -p 8888 > "$LOG/agent.log" 2>&1 </dev/null &
echo "agent pid=$!"

# 3. lesson4 launch（含 airsim_node + depth_clamp + 点云 + octomap）
# 注意：直接从脚本后台启动时，若脚本立刻退出，wsl 会话清理会连带杀掉尚未完全
# 脱离的 setsid 进程。因此启动后保持脚本存活并循环验证，不健康就重启。
sleep 8
start_launch() {
    cd "$ROS_WORKSPACE"
    setsid bash -c 'source /opt/ros/humble/setup.bash && source install/setup.bash && exec ros2 launch hw_insight lesson4.launch.py' > "$LOG/lesson4.log" 2>&1 </dev/null &
    echo "  launch started pid=$!"
}
start_launch
for attempt in 1 2 3; do
    sleep 12
    if pgrep -f "ros2 launch hw_insight" >/dev/null; then
        echo "  launch alive (attempt $attempt)"
        break
    fi
    echo "  launch not alive, restarting (attempt $attempt)"
    start_launch
done

# Do not tell the GUI that the stack is ready merely because the launch
# process exists.  AirSim cameras and OctoMap can need tens of seconds after
# ROS discovery.  Waiting for one real message here prevents the automatic
# post-start probe from producing a misleading red status.
# ROS/ament setup files legitimately inspect variables that may be unset.
# Temporarily disable nounset while sourcing them, then restore strict mode.
set +u
source /opt/ros/humble/setup.bash >/dev/null 2>&1
source "$ROS_WORKSPACE/install/setup.bash" >/dev/null 2>&1
set -u

wait_for_topic() {
    local label="$1"
    local topic="$2"
    local type="$3"
    shift 3
    for attempt in 1 2 3 4 5 6; do
        if timeout 8 ros2 topic echo --once "$@" "$topic" "$type" >/dev/null 2>&1; then
            echo "  ready: $label"
            return 0
        fi
        echo "  waiting for $label (attempt $attempt/6)"
    done
    echo "ERROR: no live $label message after startup"
    return 1
}

readiness_failed=0
wait_for_topic "PX4 telemetry" "/fmu/out/vehicle_local_position" \
    "px4_msgs/msg/VehicleLocalPosition" \
    --qos-reliability best_effort --qos-durability transient_local || readiness_failed=1
wait_for_topic "metric depth" "/depth/clamped" "sensor_msgs/msg/Image" \
    --qos-reliability best_effort || readiness_failed=1
wait_for_topic "OctoMap point cloud" "/octomap_point_cloud_centers" \
    "sensor_msgs/msg/PointCloud2" \
    --qos-reliability reliable --qos-durability transient_local || readiness_failed=1

if [ "$readiness_failed" -ne 0 ]; then
    echo "Stack processes started, but one or more live data paths are not ready."
    exit 2
fi

echo "== all started. logs: $LOG =="
ps -eo pid,cmd | grep -E 'px4_sitl|MicroXRCEAgent|ros2 launch' | grep -v grep
