#!/usr/bin/env python3
"""Prepare CityPark for AirSim depth capture and fail if depth is clipped."""

import argparse
import math
import socket
import time
from pathlib import Path

try:
    from scripts.airsim_compat import import_airsim
except ImportError:
    from airsim_compat import import_airsim


RPC_DEPS = str(Path(__file__).resolve().parents[1] / ".tools" / "airsim_rpc")
AIRSIM_CLIENT = r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient"
DEPTH_BREAKING_VOLUME = "PostProcessVolumeMAIN"


def percentile(sorted_values, fraction):
    if not sorted_values:
        return math.nan
    index = int(round((len(sorted_values) - 1) * fraction))
    return sorted_values[index]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--airsim-client", default=AIRSIM_CLIENT)
    parser.add_argument("--airsim-rpc-vendor", default=RPC_DEPS)
    parser.add_argument("--depth-breaking-volume", default=DEPTH_BREAKING_VOLUME)
    parser.add_argument("--vehicle", default="PX4")
    parser.add_argument("--camera", default="CameraDepth")
    args = parser.parse_args()

    airsim = import_airsim(args.airsim_client, args.airsim_rpc_vendor)

    deadline = time.monotonic() + args.timeout_seconds
    while True:
        try:
            with socket.create_connection(("127.0.0.1", 41451), timeout=1.0):
                break
        except OSError:
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError("CityPark AirSim RPC did not become ready")
        time.sleep(1.0)
    client = airsim.MultirotorClient()
    if not client.ping():
        raise RuntimeError("CityPark AirSim RPC port opened but ping failed")
    print("CityPark AirSim RPC ready")

    # RPC can become ready a few seconds before level actors are fully ready
    # for mutation. Retry instead of failing the complete launch on that race.
    while True:
        actors = client.simListSceneObjects(".*PostProcess.*")
        if args.depth_breaking_volume not in actors:
            print(f"{args.depth_breaking_volume} already absent")
            break
        if client.simDestroyObject(args.depth_breaking_volume):
            print(f"runtime-disabled {args.depth_breaking_volume}")
            break
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"failed to remove {args.depth_breaking_volume} before timeout"
            )
        time.sleep(1.0)
    time.sleep(1.0)

    response = client.simGetImages(
        [airsim.ImageRequest(
            args.camera, airsim.ImageType.DepthPerspective, True, False
        )],
        vehicle_name=args.vehicle,
    )[0]
    values = sorted(
        float(value)
        for value in response.image_data_float
        if math.isfinite(value) and value > 0.0
    )
    if not values:
        raise RuntimeError("CameraDepth returned no valid depth samples")
    depth_min = values[0]
    depth_median = percentile(values, 0.5)
    depth_max = values[-1]
    print(
        f"CameraDepth verified: min={depth_min:.3f}m "
        f"median={depth_median:.3f}m max={depth_max:.3f}m"
    )
    if depth_max <= 5.0 or depth_median <= 1.01:
        raise RuntimeError(
            "CityPark depth is still clipped; refusing to start the mission stack"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
