import numpy as np
import pytest

pytest.importorskip("rclpy")

from std_msgs.msg import Header
from sensor_msgs_py import point_cloud2

from scripts.gui_map_bridge import message_points


def test_ros_cloud_message_converts_to_xyz_array():
    message = point_cloud2.create_cloud_xyz32(
        Header(frame_id="world_enu"), [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]
    )
    points = message_points(message)
    assert points.shape == (2, 3)
    np.testing.assert_allclose(points, [[1, 2, 3], [4, 5, 6]])
