import rclpy
import numpy as np
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image


class DepthClamp(Node):
    # AirSim 的 DepthPerspective 深度图中，没有打到物体的像素（天空/远景）会返回
    # 远平面距离（本场景高达 ~16km），point_cloud_xyz_radial_node 会把它们转成
    # 十几公里外的点，octomap 计算射线时全部 out of bounds。这里把超过 max_depth
    # 的深度置为 NaN，depth_image_proc 会把 NaN 当作无效像素跳过。
    def __init__(self):
        super().__init__('depth_clamp')
        self.max_depth = self.declare_parameter('max_depth', 25.0).value
        self.get_logger().info(f'depth_clamp max_depth = {self.max_depth} m')
        qos = QoSProfile(
            depth=5,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
        )
        self.sub = self.create_subscription(Image, 'image_in', self.on_depth, qos)
        self.pub = self.create_publisher(Image, 'image_out', qos)

    def on_depth(self, msg):
        a = np.frombuffer(msg.data, dtype=np.float32).copy()
        a[a > self.max_depth] = np.nan
        msg.data = a.tobytes()
        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = DepthClamp()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
