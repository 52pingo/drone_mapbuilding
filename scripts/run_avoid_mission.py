#!/usr/bin/env python3
"""Run AvoidNode until DONE and stream structured GUI telemetry."""

import json
import time

import rclpy
from hw_insight.avoid_node import AvoidNode


def main() -> int:
    rclpy.init()
    node = AvoidNode()
    last_status = 0.0
    try:
        while rclpy.ok() and node.state != "DONE":
            rclpy.spin_once(node, timeout_sec=0.25)
            now = time.monotonic()
            if now - last_status >= 0.5:
                print(
                    "GUI_STATUS " + json.dumps(
                        node.status_snapshot(), ensure_ascii=False,
                        separators=(",", ":")
                    ),
                    flush=True,
                )
                last_status = now
        if rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.25)
            print(
                "GUI_STATUS " + json.dumps(
                    node.status_snapshot(), ensure_ascii=False,
                    separators=(",", ":")
                ),
                flush=True,
            )
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
