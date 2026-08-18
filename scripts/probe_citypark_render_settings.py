#!/usr/bin/env python3
"""Probe CityPark renderer CVars against raw AirSim depth output."""

import sys
import time

import numpy as np


RPC_DEPS = r"E:\无人机视觉避障建图\.tools\airsim_rpc"
AIRSIM_CLIENT = r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient"
COMMANDS = [
    ("baseline", None),
    ("early_z_off", "r.EarlyZPass 0"),
    ("global_clip_off", "r.AllowGlobalClipPlane 0"),
    ("lpv_off", "r.LightPropagationVolume 0"),
    ("separate_translucency_on", "r.SeparateTranslucency 1"),
    ("mesh_distance_fields_off", "r.GenerateMeshDistanceFields 0"),
]


def sample(client, airsim, label):
    response = client.simGetImages(
        [airsim.ImageRequest(
            "CameraDepth", airsim.ImageType.DepthPerspective, True, False
        )],
        vehicle_name="PX4",
    )[0]
    values = np.asarray(response.image_data_float, dtype=np.float32)
    valid = values[np.isfinite(values) & (values > 0.0)]
    if valid.size == 0:
        print(f"{label}: no valid depth")
        return
    percentiles = np.percentile(valid, [0, 25, 50, 75, 100])
    unique = np.unique(valid)
    print(
        f"{label}: unique={unique.size} "
        f"min={percentiles[0]:.3f} p25={percentiles[1]:.3f} "
        f"p50={percentiles[2]:.3f} p75={percentiles[3]:.3f} "
        f"max={percentiles[4]:.3f}"
    )


def main():
    sys.path[:0] = [RPC_DEPS, AIRSIM_CLIENT]
    import airsim

    client = airsim.MultirotorClient()
    client.confirmConnection()
    for label, command in COMMANDS:
        if command is not None:
            result = client.simRunConsoleCommand(command)
            print(f"command={command!r} accepted={result}")
            time.sleep(1.0)
        sample(client, airsim, label)


if __name__ == "__main__":
    main()
