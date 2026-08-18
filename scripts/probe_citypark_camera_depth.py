#!/usr/bin/env python3
"""Probe AirSim depth at several camera mounts/pitches in CityPark."""

import math
import sys
import time

import numpy as np


RPC_DEPS = r"E:\无人机视觉避障建图\.tools\airsim_rpc"
AIRSIM_CLIENT = r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient"
PROBES = [
    ("z_minus_1_pitch_0", 0.0, 0.0, -1.0, 0.0),
    ("z_0_pitch_0", 0.0, 0.0, 0.0, 0.0),
    ("x_plus_1_pitch_0", 1.0, 0.0, 0.0, 0.0),
    ("z_minus_1_pitch_down_5", 0.0, 0.0, -1.0, -5.0),
    ("z_minus_1_pitch_down_15", 0.0, 0.0, -1.0, -15.0),
    ("z_minus_1_pitch_down_30", 0.0, 0.0, -1.0, -30.0),
]


def main():
    sys.path[:0] = [RPC_DEPS, AIRSIM_CLIENT]
    import airsim

    client = airsim.MultirotorClient()
    client.confirmConnection()
    try:
        for label, x, y, z, pitch_deg in PROBES:
            camera_pose = airsim.Pose(
                airsim.Vector3r(x, y, z),
                airsim.to_quaternion(math.radians(pitch_deg), 0.0, 0.0),
            )
            client.simSetCameraPose(
                "CameraDepth", camera_pose, vehicle_name="PX4"
            )
            time.sleep(0.5)
            response = client.simGetImages(
                [airsim.ImageRequest(
                    "CameraDepth", airsim.ImageType.DepthPerspective, True, False
                )],
                vehicle_name="PX4",
            )[0]
            values = np.asarray(response.image_data_float, dtype=np.float32)
            valid = values[np.isfinite(values) & (values > 0.0)]
            p = np.percentile(valid, [0, 25, 50, 75, 100])
            print(
                f"{label}: unique={np.unique(valid).size} "
                f"min={p[0]:.3f} p25={p[1]:.3f} p50={p[2]:.3f} "
                f"p75={p[3]:.3f} max={p[4]:.3f}"
            )
    finally:
        client.simSetCameraPose(
            "CameraDepth",
            airsim.Pose(
                airsim.Vector3r(0.0, 0.0, -1.0),
                airsim.to_quaternion(0.0, 0.0, 0.0),
            ),
            vehicle_name="PX4",
        )


if __name__ == "__main__":
    main()
