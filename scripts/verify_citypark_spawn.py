#!/usr/bin/env python3
"""Report the current CityPark spawn and capture a downward validation image."""

import math
import os
import sys


RPC_DEPS = r"E:\无人机视觉避障建图\.tools\airsim_rpc"
AIRSIM_CLIENT = r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient"
OUTPUT = r"E:\无人机视觉避障建图\results\citypark_spawn_verified.png"
FORWARD_OUTPUT = (
    r"E:\无人机视觉避障建图\results\citypark_camera_forward_verified.png"
)


def main():
    sys.path[:0] = [RPC_DEPS, AIRSIM_CLIENT]
    import airsim

    client = airsim.MultirotorClient()
    client.confirmConnection()
    forward_camera_pose = airsim.Pose(
        airsim.Vector3r(0.0, 0.0, -1.0),
        airsim.to_quaternion(0.0, 0.0, 0.0),
    )
    pose = client.simGetVehiclePose(vehicle_name="PX4")
    collision = client.simGetCollisionInfo(vehicle_name="PX4")
    print(
        "local_pose "
        f"x={pose.position.x_val:.3f} "
        f"y={pose.position.y_val:.3f} "
        f"z={pose.position.z_val:.3f}"
    )
    print(
        f"collision={collision.has_collided} "
        f"object={collision.object_name!r}"
    )

    camera_pose = airsim.Pose(
        airsim.Vector3r(0.0, 0.0, 0.0),
        airsim.to_quaternion(-math.pi / 2.0, 0.0, 0.0),
    )
    try:
        client.simSetCameraPose("CameraDepth", camera_pose, vehicle_name="PX4")
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
        if not response.image_data_uint8:
            raise RuntimeError("CameraDepth returned an empty scene image")
        os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
        airsim.write_file(OUTPUT, response.image_data_uint8)
        print(f"image={OUTPUT}")
    finally:
        client.simSetCameraPose(
            "CameraDepth", forward_camera_pose, vehicle_name="PX4"
        )

    camera_info = client.simGetCameraInfo("CameraDepth", vehicle_name="PX4")
    q = camera_info.pose.orientation
    print(
        "forward_camera_quaternion "
        f"w={q.w_val:.3f} x={q.x_val:.3f} "
        f"y={q.y_val:.3f} z={q.z_val:.3f}"
    )
    forward_response = client.simGetImages(
        [airsim.ImageRequest(
            "CameraDepth", airsim.ImageType.Scene, False, True
        )],
        vehicle_name="PX4",
    )[0]
    if not forward_response.image_data_uint8:
        raise RuntimeError("CameraDepth returned an empty forward scene image")
    airsim.write_file(FORWARD_OUTPUT, forward_response.image_data_uint8)
    print(f"forward_image={FORWARD_OUTPUT}")


if __name__ == "__main__":
    main()
