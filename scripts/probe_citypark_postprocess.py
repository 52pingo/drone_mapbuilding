#!/usr/bin/env python3
"""Temporarily remove selected CityPark post-process actors and sample depth."""

import argparse
import sys
import time

import numpy as np


RPC_DEPS = r"E:\无人机视觉避障建图\.tools\airsim_rpc"
AIRSIM_CLIENT = r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "names",
        nargs="*",
        default=["PostProcessVolumeMAIN"],
        help="actor names to remove for this UE4 session",
    )
    args = parser.parse_args()
    sys.path[:0] = [RPC_DEPS, AIRSIM_CLIENT]
    import airsim

    client = airsim.MultirotorClient()
    client.confirmConnection()
    available = sorted(client.simListSceneObjects(".*PostProcess.*"))
    print(f"post_process_actors={available}")
    for name in args.names:
        print(f"destroy {name}: {client.simDestroyObject(name)}")
    time.sleep(1.0)
    response = client.simGetImages(
        [airsim.ImageRequest(
            "CameraDepth", airsim.ImageType.DepthPerspective, True, False
        )],
        vehicle_name="PX4",
    )[0]
    values = np.asarray(response.image_data_float, dtype=np.float32)
    valid = values[np.isfinite(values) & (values > 0.0)]
    p = np.percentile(valid, [0, 1, 25, 50, 75, 99, 100])
    print(
        f"depth unique={np.unique(valid).size} "
        f"min={p[0]:.3f} p1={p[1]:.3f} p25={p[2]:.3f} "
        f"p50={p[3]:.3f} p75={p[4]:.3f} p99={p[5]:.3f} "
        f"max={p[6]:.3f}"
    )


if __name__ == "__main__":
    main()
