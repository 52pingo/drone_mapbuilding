#!/usr/bin/env python3
"""Inspect raw AirSim depth values without changing the vehicle or camera."""

import os
import sys

import numpy as np


RPC_DEPS = r"E:\无人机视觉避障建图\.tools\airsim_rpc"
AIRSIM_CLIENT = r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient"
OUTPUT_DIR = r"E:\无人机视觉避障建图\results"


def describe(name, response):
    values = np.asarray(response.image_data_float, dtype=np.float32)
    valid = values[np.isfinite(values) & (values > 0.0)]
    if valid.size == 0:
        print(f"{name}: no finite positive values")
        return
    percentiles = np.percentile(valid, [0, 1, 5, 25, 50, 75, 95, 99, 100])
    summary = " ".join(
        f"p{label}={value:.3f}"
        for label, value in zip(
            (0, 1, 5, 25, 50, 75, 95, 99, 100), percentiles
        )
    )
    print(
        f"{name}: shape={response.height}x{response.width} "
        f"valid={valid.size}/{values.size} {summary}"
    )


def main():
    sys.path[:0] = [RPC_DEPS, AIRSIM_CLIENT]
    import airsim

    client = airsim.MultirotorClient()
    client.confirmConnection()
    pose = client.simGetVehiclePose(vehicle_name="PX4")
    print(
        f"vehicle=({pose.position.x_val:.3f},{pose.position.y_val:.3f},"
        f"{pose.position.z_val:.3f})"
    )
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for camera_name in ("CameraDepth", "front_center"):
        camera = client.simGetCameraInfo(camera_name, vehicle_name="PX4")
        p = camera.pose.position
        q = camera.pose.orientation
        print(
            f"camera={camera_name} "
            f"pos=({p.x_val:.3f},{p.y_val:.3f},{p.z_val:.3f}) "
            f"q=({q.w_val:.3f},{q.x_val:.3f},{q.y_val:.3f},{q.z_val:.3f})"
        )
        responses = client.simGetImages(
            [
                airsim.ImageRequest(
                    camera_name, airsim.ImageType.DepthPlanar, True, False
                ),
                airsim.ImageRequest(
                    camera_name, airsim.ImageType.DepthPerspective, True, False
                ),
                airsim.ImageRequest(
                    camera_name, airsim.ImageType.Scene, False, True
                ),
            ],
            vehicle_name="PX4",
        )
        describe(f"{camera_name}/DepthPlanar", responses[0])
        describe(f"{camera_name}/DepthPerspective", responses[1])
        if not responses[2].image_data_uint8:
            raise RuntimeError(f"empty scene image: {camera_name}")
        scene_output = os.path.join(
            OUTPUT_DIR, f"citypark_depth_scene_{camera_name}.png"
        )
        airsim.write_file(scene_output, responses[2].image_data_uint8)
        print(f"scene={scene_output}")


if __name__ == "__main__":
    main()
