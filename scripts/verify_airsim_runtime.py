#!/usr/bin/env python3
"""Verify that a generic AirSim environment exposes usable RGB and depth."""

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--airsim-client", default="")
    parser.add_argument("--airsim-rpc-vendor", default=RPC_DEPS)
    parser.add_argument("--vehicle", default="PX4")
    parser.add_argument("--camera", default="CameraDepth")
    args = parser.parse_args()
    airsim = import_airsim(args.airsim_client, args.airsim_rpc_vendor)
    deadline = time.monotonic() + args.timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 41451), timeout=1.0):
                break
        except OSError:
            time.sleep(1.0)
    else:
        raise TimeoutError("AirSim RPC port 41451 did not become ready")
    client = airsim.MultirotorClient()
    if not client.ping():
        raise RuntimeError("AirSim RPC ping failed")
    responses = client.simGetImages(
        [
            airsim.ImageRequest(args.camera, airsim.ImageType.Scene, False, True),
            airsim.ImageRequest(args.camera, airsim.ImageType.DepthPerspective, True, False),
        ],
        vehicle_name=args.vehicle,
    )
    if len(responses) != 2 or not responses[0].image_data_uint8:
        raise RuntimeError(f"{args.vehicle}/{args.camera} returned no RGB frame")
    values = [
        float(value) for value in responses[1].image_data_float
        if math.isfinite(value) and value > 0.0
    ]
    if not values:
        raise RuntimeError(f"{args.vehicle}/{args.camera} returned no valid depth samples")
    values.sort()
    median = values[len(values) // 2]
    print(
        "AirSim verified: vehicle=%s camera=%s depth_min=%.3fm "
        "depth_median=%.3fm depth_max=%.3fm" % (
            args.vehicle, args.camera, values[0], median, values[-1]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
