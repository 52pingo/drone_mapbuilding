#!/bin/bash
# Invoke one of the operator-safe Trigger services exposed by AvoidNode.
set -euo pipefail

ACTION="${1:-}"
ROS_WORKSPACE="${ROS_WORKSPACE:-$HOME/hw-ros2/ros2}"
case "$ACTION" in
    hold|resume|land) ;;
    *) echo "unsupported mission control: $ACTION" >&2; exit 2 ;;
esac

source /opt/ros/humble/setup.bash
source "$ROS_WORKSPACE/install/setup.bash"
SERVICE="/hw_insight/mission/$ACTION"
if ! timeout 4 ros2 service list | grep -Fxq "$SERVICE"; then
    echo "mission service is unavailable: $SERVICE" >&2
    exit 3
fi
timeout 10 ros2 service call "$SERVICE" std_srvs/srv/Trigger "{}"
