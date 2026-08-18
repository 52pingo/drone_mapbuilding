#!/usr/bin/env python3
"""Render the current latched OctoMap point cloud as a top-down PNG."""

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2


OUTPUT = (
    sys.argv[1] if len(sys.argv) > 1 else "/home/hw/logs/octomap_map_qgc.png"
)


class MapRenderer(Node):
    def __init__(self):
        super().__init__("qgc_map_renderer")
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.create_subscription(
            PointCloud2, "/octomap_point_cloud_centers", self.render, qos
        )
        print("Waiting for the latched OctoMap cloud...", flush=True)

    def render(self, message):
        points = np.array(
            list(
                point_cloud2.read_points(
                    message, field_names=("x", "y", "z"), skip_nans=True
                )
            )
        )
        if points.size == 0:
            print("OctoMap cloud is empty", flush=True)
            os._exit(1)
        if points.dtype.names:
            x = points["x"].astype(float)
            y = points["y"].astype(float)
            z = points["z"].astype(float)
        else:
            x = points[:, 0].astype(float)
            y = points[:, 1].astype(float)
            z = points[:, 2].astype(float)

        original_count = len(x)
        if original_count > 150000:
            indices = np.linspace(0, original_count - 1, 150000).astype(int)
            x, y, z = x[indices], y[indices], z[indices]

        figure, axes = plt.subplots(figsize=(9, 8))
        occupancy = axes.scatter(
            x, y, c=-z, s=2.2, cmap="viridis_r", linewidths=0
        )
        axes.scatter(
            0, 0, marker="*", s=200, color="red", label="local origin", zorder=5
        )
        axes.set_xlabel("x (m, North)")
        axes.set_ylabel("y (m, East)")
        axes.set_title(
            "QGC autonomous mission - OctoMap occupancy\n"
            "0.1 m resolution, color = height"
        )
        colorbar = figure.colorbar(occupancy, ax=axes)
        colorbar.set_label("height above ground (m)")
        axes.legend(loc="upper right", fontsize=9)
        axes.grid(alpha=0.3)
        axes.set_aspect("equal", adjustable="box")
        plt.tight_layout()
        plt.savefig(OUTPUT, dpi=110)
        print(
            f"Rendered {original_count} OctoMap points -> {OUTPUT}", flush=True
        )
        os._exit(0)


def main():
    rclpy.init()
    rclpy.spin(MapRenderer())


if __name__ == "__main__":
    main()
