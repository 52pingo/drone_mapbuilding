#!/usr/bin/env python3
"""Capture downward views above candidate CityPark spawn regions."""

import math
import os
import sys
import time


RPC_DEPS = r"E:\无人机视觉避障建图\.tools\airsim_rpc"
AIRSIM_CLIENT = r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient"
OUTPUT_DIR = r"E:\无人机视觉避障建图\results\citypark_spawn_probe"
SURVEY_HEIGHT = 15.0

CANDIDATES = [
    ("field_center", -176.0, 110.0, 0.0),
    ("field_x_plus_10", -166.0, 110.0, 0.0),
    ("field_x_minus_10", -186.0, 110.0, 0.0),
    ("field_y_plus_10", -176.0, 120.0, 0.0),
    ("field_y_minus_10", -176.0, 100.0, 0.0),
]


def main():
    sys.path[:0] = [RPC_DEPS, AIRSIM_CLIENT]
    import airsim

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    client = airsim.MultirotorClient()
    client.confirmConnection()
    original_pose = client.simGetVehiclePose(vehicle_name="PX4")
    forward_camera_pose = airsim.Pose(
        airsim.Vector3r(0.0, 0.0, -1.0),
        airsim.to_quaternion(0.0, 0.0, 0.0),
    )
    camera_pose = airsim.Pose(
        airsim.Vector3r(0.0, 0.0, 0.0),
        airsim.to_quaternion(-math.pi / 2.0, 0.0, 0.0),
    )

    client.simPause(False)
    try:
        for name, x, y, ground_z in CANDIDATES:
            survey_pose = airsim.Pose(
                airsim.Vector3r(x, y, ground_z - SURVEY_HEIGHT),
                airsim.to_quaternion(0.0, 0.0, 0.0),
            )
            client.simSetVehiclePose(
                survey_pose, ignore_collision=True, vehicle_name="PX4"
            )
            client.simSetCameraPose(
                "CameraDepth", camera_pose, vehicle_name="PX4"
            )
            # PX4/ROS is stopped while this probe runs. Give the render target
            # a moment to refresh, then pin the pose once more before capture.
            time.sleep(0.35)
            client.simSetVehiclePose(
                survey_pose, ignore_collision=True, vehicle_name="PX4"
            )
            time.sleep(0.10)
            actual_pose = client.simGetVehiclePose(vehicle_name="PX4")
            response = client.simGetImages(
                [
                    airsim.ImageRequest(
                        "CameraDepth",
                        airsim.ImageType.Scene,
                        pixels_as_float=False,
                        compress=True,
                    )
                ],
                vehicle_name="PX4",
            )[0]
            output = os.path.join(OUTPUT_DIR, name + ".png")
            if response.image_data_uint8:
                airsim.write_file(output, response.image_data_uint8)
                print(
                    f"saved {name}: requested=({x:.2f},{y:.2f},"
                    f"{ground_z - SURVEY_HEIGHT:.2f}) "
                    f"actual=({actual_pose.position.x_val:.2f},"
                    f"{actual_pose.position.y_val:.2f},"
                    f"{actual_pose.position.z_val:.2f}) -> {output}"
                )
            else:
                print(f"empty image for {name}")
    finally:
        client.simSetCameraPose(
            "CameraDepth", forward_camera_pose, vehicle_name="PX4"
        )
        client.simSetVehiclePose(
            original_pose, ignore_collision=True, vehicle_name="PX4"
        )


if __name__ == "__main__":
    main()
