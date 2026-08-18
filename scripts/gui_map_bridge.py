#!/usr/bin/env python3
"""Bridge the latched OctoMap cloud into atomic Windows-readable snapshots."""

from __future__ import annotations

import argparse
from pathlib import Path
import time

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.time import Time
from rclpy.qos import (
    DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy,
)
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from tf2_ros import Buffer, TransformException, TransformListener

try:
    from scripts.map_bridge_core import MapSnapshotWriter
except ImportError:
    from map_bridge_core import MapSnapshotWriter


def parse_args():
    parser = argparse.ArgumentParser(description="Publish GUI OctoMap snapshots")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--topic", default="/octomap_point_cloud_centers")
    parser.add_argument("--max-points", type=int, default=80000)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--world-ned-frame", default="world_ned")
    parser.add_argument("--vehicle-frame", default="PX4")
    return parser.parse_args()


def message_points(message) -> np.ndarray:
    values = np.array(list(point_cloud2.read_points(
        message, field_names=("x", "y", "z"), skip_nans=True
    )))
    if values.size == 0:
        return np.empty((0, 3), dtype=np.float32)
    if values.dtype.names:
        return np.column_stack((values["x"], values["y"], values["z"]))
    return np.asarray(values[:, :3], dtype=np.float32)


class GuiMapBridge(Node):
    def __init__(self, args) -> None:
        super().__init__("gui_map_bridge")
        self.writer = MapSnapshotWriter(Path(args.output_dir), args.max_points)
        self.interval = max(0.1, float(args.interval))
        self.last_write = 0.0
        self.last_origin_warning = 0.0
        self.origin_ned = None
        self.world_ned_frame = args.world_ned_frame
        self.vehicle_frame = args.vehicle_frame
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.subscription = self.create_subscription(
            PointCloud2, args.topic, self.on_cloud, qos
        )
        self.get_logger().info(
            f"map bridge waiting on {args.topic} -> {args.output_dir}")

    def world_origin_ned(self):
        if self.origin_ned is not None:
            return self.origin_ned
        try:
            transform = self.tf_buffer.lookup_transform(
                self.world_ned_frame, self.vehicle_frame, Time()
            )
        except TransformException as error:
            now = time.monotonic()
            if now - self.last_origin_warning >= 5.0:
                self.get_logger().warning(
                    "waiting for %s -> %s origin transform: %s" % (
                        self.world_ned_frame, self.vehicle_frame, error,
                    )
                )
                self.last_origin_warning = now
            return None
        translation = transform.transform.translation
        self.origin_ned = (
            float(translation.x), float(translation.y), float(translation.z)
        )
        self.get_logger().info(
            "PX4 local origin in world NED: %.3f %.3f %.3f" % self.origin_ned
        )
        return self.origin_ned

    def on_cloud(self, message) -> None:
        now = time.monotonic()
        if now - self.last_write < self.interval:
            return
        origin_ned = self.world_origin_ned()
        if origin_ned is None:
            return
        points = message_points(message)
        if not len(points):
            self.get_logger().warning("received empty OctoMap point cloud")
            return
        metadata = self.writer.publish(
            points, message.header.frame_id, origin_ned
        )
        self.last_write = now
        self.get_logger().info(
            "snapshot %d: %d/%d points" % (
                metadata["sequence"], metadata["point_count"],
                metadata["original_count"],
            ))


def main() -> int:
    args = parse_args()
    rclpy.init()
    node = GuiMapBridge(args)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
