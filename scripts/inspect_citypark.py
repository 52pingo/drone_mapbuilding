#!/usr/bin/env python3
"""Inspect named CityPark actors through the local AirSim RPC server."""

import argparse
import math
import re
import sys


DEFAULT_RPC_DEPS = r"E:\无人机视觉避障建图\.tools\airsim_rpc"
DEFAULT_AIRSIM_CLIENT = (
    r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient"
)


def finite_pose(pose):
    values = (
        pose.position.x_val,
        pose.position.y_val,
        pose.position.z_val,
    )
    return all(math.isfinite(value) for value in values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pattern",
        default=(
            r"road|street|path|parking|plaza|ground|player|spawn|camera|"
            r"plane|fountain|bridge|pavilion|building|playground"
        ),
    )
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()

    sys.path[:0] = [DEFAULT_RPC_DEPS, DEFAULT_AIRSIM_CLIENT]
    import airsim

    client = airsim.MultirotorClient()
    client.confirmConnection()
    vehicle_pose = client.simGetVehiclePose(vehicle_name="PX4")
    print(
        "PX4 "
        f"x={vehicle_pose.position.x_val:.2f} "
        f"y={vehicle_pose.position.y_val:.2f} "
        f"z={vehicle_pose.position.z_val:.2f}"
    )

    pattern = re.compile(args.pattern, re.IGNORECASE)
    names = sorted(client.simListSceneObjects(".*"))
    matched = [name for name in names if pattern.search(name)]
    print(f"objects={len(names)} matched={len(matched)}")
    for name in matched[: args.limit]:
        pose = client.simGetObjectPose(name)
        if not finite_pose(pose):
            continue
        print(
            f"{name}\t"
            f"x={pose.position.x_val:.2f}\t"
            f"y={pose.position.y_val:.2f}\t"
            f"z={pose.position.z_val:.2f}"
        )


if __name__ == "__main__":
    main()
