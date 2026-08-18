#!/usr/bin/env python3
"""Run AvoidNode standalone until the mission reports DONE."""

import rclpy
from hw_insight.avoid_node import AvoidNode


def main() -> int:
    rclpy.init()
    node = AvoidNode()
    try:
        while rclpy.ok() and node.state != "DONE":
            rclpy.spin_once(node, timeout_sec=0.25)
        if rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(node, "log_fh"):
            node.log_fh.close()
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
