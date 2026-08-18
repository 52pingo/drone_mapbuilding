#!/usr/bin/env python3
"""Capture a four-tile bird's-eye survey around the CityPark spawn."""

import math
import os
import sys
import time


RPC_DEPS = r"E:\无人机视觉避障建图\.tools\airsim_rpc"
AIRSIM_CLIENT = r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient"
OUTPUT_DIR = r"E:\无人机视觉避障建图\results\citypark_route_survey"
SURVEY_Z = -180.0
TILES = [
    ("north_east_spawn", -70.0, 20.0),
    ("south_east", -70.0, -260.0),
    ("north_west", -350.0, 20.0),
    ("south_west", -350.0, -260.0),
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
    down = airsim.Pose(
        airsim.Vector3r(0.0, 0.0, 0.0),
        airsim.to_quaternion(-math.pi / 2.0, 0.0, 0.0),
    )
    client.simPause(False)
    try:
        for name, x, y in TILES:
            pose = airsim.Pose(
                airsim.Vector3r(x, y, SURVEY_Z),
                airsim.to_quaternion(0.0, 0.0, 0.0),
            )
            client.simSetVehiclePose(pose, True, vehicle_name="PX4")
            client.simSetCameraPose("CameraDepth", down, vehicle_name="PX4")
            time.sleep(0.45)
            client.simSetVehiclePose(pose, True, vehicle_name="PX4")
            time.sleep(0.10)
            response = client.simGetImages(
                [airsim.ImageRequest(
                    "CameraDepth", airsim.ImageType.Scene, False, True
                )],
                vehicle_name="PX4",
            )[0]
            if not response.image_data_uint8:
                raise RuntimeError(f"empty survey image: {name}")
            output = os.path.join(OUTPUT_DIR, name + ".png")
            airsim.write_file(output, response.image_data_uint8)
            print(f"saved {name}: center=({x:.1f},{y:.1f}) -> {output}")
    finally:
        client.simSetCameraPose(
            "CameraDepth", forward_camera_pose, vehicle_name="PX4"
        )
        client.simSetVehiclePose(original_pose, True, vehicle_name="PX4")


if __name__ == "__main__":
    main()
