import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from sensor_msgs.msg import PointCloud2


class CloudRelay(Node):
    def __init__(self):
        super().__init__('cloud_relay')
        # depth_image_proc 以 BEST_EFFORT 发布点云，而 octomap_server 默认以
        # RELIABLE 订阅，两者不兼容导致 octomap 收不到数据。这里做一次 QoS 转换：
        # 以 BEST_EFFORT 订阅 /depth/points，再以 RELIABLE 转发到 /depth/points_relay。
        best_effort_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
        )
        reliable_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
        )
        self.sub = self.create_subscription(
            PointCloud2, '/depth/points', self.on_cloud, best_effort_qos)
        self.pub = self.create_publisher(
            PointCloud2, '/depth/points_relay', reliable_qos)

    def on_cloud(self, msg):
        self.pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = CloudRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
