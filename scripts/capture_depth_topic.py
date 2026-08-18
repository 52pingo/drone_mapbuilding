#!/usr/bin/env python3
"""Save one RViz-equivalent heatmap from the ROS /depth/clamped topic."""

import argparse
from pathlib import Path
import sys

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class DepthSnapshot(Node):
    def __init__(self, output: Path, max_depth: float):
        super().__init__("depth_snapshot")
        self.output = output
        self.max_depth = max_depth
        self.saved = False
        self.create_subscription(
            Image, "/depth/clamped", self.on_depth, qos_profile_sensor_data
        )

    def on_depth(self, message: Image) -> None:
        if self.saved:
            return
        if message.encoding.lower() != "32fc1":
            self.get_logger().error(
                f"expected 32FC1, received {message.encoding}"
            )
            return
        row_values = message.step // 4
        values = np.frombuffer(message.data, dtype=np.float32)
        if values.size < message.height * row_values:
            self.get_logger().error("truncated depth image payload")
            return
        depth = values[:message.height * row_values].reshape(
            message.height, row_values
        )[:, :message.width]
        valid = np.isfinite(depth) & (depth > 0.1)
        scaled = np.zeros(depth.shape, dtype=np.uint8)
        scaled[valid] = np.clip(
            (1.0 - depth[valid] / self.max_depth) * 255.0, 0.0, 255.0
        ).astype(np.uint8)
        heatmap = cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)
        heatmap[~valid] = 0
        finite = depth[valid]
        stats = (
            f"32FC1 0-{self.max_depth:g}m | "
            f"min {float(finite.min()):.2f}m | "
            f"median {float(np.median(finite)):.2f}m"
            if finite.size else "/depth/clamped: no valid pixels"
        )
        cv2.rectangle(heatmap, (0, 0), (heatmap.shape[1], 28), (0, 0, 0), -1)
        cv2.putText(
            heatmap, stats, (7, 19), cv2.FONT_HERSHEY_SIMPLEX,
            0.40, (255, 255, 255), 1, cv2.LINE_AA,
        )
        self.output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(self.output), heatmap):
            raise RuntimeError(f"failed to save {self.output}")
        self.saved = True
        self.get_logger().info(f"saved {self.output}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--max-depth", type=float, default=25.0)
    args = parser.parse_args()
    if args.max_depth <= 0:
        raise SystemExit("--max-depth must be positive")
    rclpy.init()
    node = DepthSnapshot(Path(args.output), args.max_depth)
    try:
        while rclpy.ok() and not node.saved:
            rclpy.spin_once(node, timeout_sec=1.0)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0 if node.saved else 1


if __name__ == "__main__":
    sys.exit(main())
