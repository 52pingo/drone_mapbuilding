#!/bin/bash
# Emit one machine-readable health snapshot for the desktop GUI.
set +e

ROS_WORKSPACE="${ROS_WORKSPACE:-$HOME/hw-ros2/ros2}"
workspace=false
px4=false
xrce=false
airsim=false
depth=false
octomap=false
telemetry=false
mission_service=false

if [ -r "$ROS_WORKSPACE/install/setup.bash" ]; then
    workspace=true
fi
if pgrep -f "px4 px4_sitl\|px4_sitl_default" >/dev/null 2>&1; then
    px4=true
fi
if pgrep -f "MicroXRCEAgent" >/dev/null 2>&1; then
    xrce=true
fi

if [ "$workspace" = true ]; then
    source /opt/ros/humble/setup.bash >/dev/null 2>&1
    source "$ROS_WORKSPACE/install/setup.bash" >/dev/null 2>&1
    nodes="$(timeout 6 ros2 node list 2>/dev/null)"
    topics="$(timeout 6 ros2 topic list 2>/dev/null)"
    services="$(timeout 6 ros2 service list 2>/dev/null)"
    if printf '%s\n' "$nodes" | grep -q "airsim_node"; then airsim=true; fi
    if printf '%s\n' "$topics" | grep -Fxq "/depth/clamped" && \
            timeout 4 ros2 topic echo --once --qos-reliability best_effort \
            /depth/clamped sensor_msgs/msg/Image >/dev/null 2>&1; then
        depth=true
    fi
    if printf '%s\n' "$topics" | grep -Fxq "/octomap_point_cloud_centers" && \
            timeout 4 ros2 topic echo --once --qos-reliability reliable \
            --qos-durability transient_local /octomap_point_cloud_centers \
            sensor_msgs/msg/PointCloud2 >/dev/null 2>&1; then
        octomap=true
    fi
    if printf '%s\n' "$topics" | grep -Fxq "/fmu/out/vehicle_local_position" && \
            timeout 4 ros2 topic echo --once --qos-reliability best_effort \
            --qos-durability transient_local /fmu/out/vehicle_local_position \
            px4_msgs/msg/VehicleLocalPosition >/dev/null 2>&1; then
        telemetry=true
    fi
    if printf '%s\n' "$services" | grep -Fxq "/hw_insight/mission/hold"; then mission_service=true; fi
fi

printf 'GUI_PROBE {"ros_workspace":%s,"px4":%s,"xrce":%s,"airsim":%s,"depth":%s,"octomap":%s,"telemetry":%s,"mission_service":%s}\n' \
    "$workspace" "$px4" "$xrce" "$airsim" "$depth" "$octomap" "$telemetry" "$mission_service"
