#!/usr/bin/env python3
"""Dump the latched OctoMap cloud to a top-down PNG."""

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


OUTPUT = sys.argv[1] if len(sys.argv) > 1 else "/home/hw/logs/octomap_map_qgc.png"


class MapRenderer(Node):
    def __init__(self):
        super().__init__("qgc_map_renderer")
        self._done = False
        self._exit_code = 0
        # octomap_server 用 latched 话题发点云，得 TRANSIENT_LOCAL 才收得到
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

    @property
    def done(self):
        return self._done

    @property
    def exit_code(self):
        return self._exit_code

    def _finish(self, code):
        self._exit_code = code
        self._done = True

    def render(self, message):
        try:
            points = point_cloud2.read_points_numpy(
                message, field_names=("x", "y", "z"), skip_nans=True
            )
        except Exception as exc:
            print(f"Failed to read point cloud: {exc}", flush=True)
            self._finish(1)
            return

        if points.size == 0:
            print("OctoMap cloud is empty", flush=True)
            self._finish(1)
            return

        # read_points_numpy 返回 structured array 还是普通二维数组，看版本
        if points.dtype.names:
            x = points["x"].astype(np.float64, copy=False)
            y = points["y"].astype(np.float64, copy=False)
            z = points["z"].astype(np.float64, copy=False)
        else:
            x = points[:, 0].astype(np.float64, copy=False)
            y = points[:, 1].astype(np.float64, copy=False)
            z = points[:, 2].astype(np.float64, copy=False)

        original_count = len(x)
        # 点太多 scatter 会卡，均匀抽到 15 万
        if original_count > 150000:
            indices = np.linspace(0, original_count - 1, 150000).astype(int)
            x, y, z = x[indices], y[indices], z[indices]

        figure = None
        try:
            figure, axes = plt.subplots(figsize=(9, 8))
            # z 是 NED 高度，向下为正；取负号后高处偏黄
            occupancy = axes.scatter(
                x, y, c=-z, s=2.2, cmap="viridis_r", linewidths=0
            )
            axes.scatter(
                0, 0, marker="*", s=200, color="red",
                label="local origin", zorder=5,
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
        except Exception as exc:
            print(f"Failed to render map: {exc}", flush=True)
            self._finish(1)
            return
        finally:
            if figure is not None:
                plt.close(figure)

        print(
            f"Rendered {original_count} OctoMap points -> {OUTPUT}", flush=True
        )
        self._finish(0)


def main():
    rclpy.init()
    node = MapRenderer()
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return node.exit_code


if __name__ == "__main__":
    sys.exit(main())
