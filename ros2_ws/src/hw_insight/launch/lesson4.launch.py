import os
import launch
import launch_ros.actions
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch_ros.actions import Node
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    # 深度限幅：AirSim 深度图中天空/远景像素返回远平面距离（本场景 ~16km），
    # 直接转点云会产生十几公里外的点，octomap 射线 out of bounds。先把超过
    # max_depth 的深度置为 NaN，depth_image_proc 会跳过 NaN 像素。
    depth_clamp_node = Node(
        package='hw_insight',
        executable='depth_clamp',
        name='depth_clamp',
        remappings=[
            ('image_in', '/airsim_node/PX4/CameraDepth/DepthPerspective'),
            ('image_out', '/depth/clamped')
        ],
        parameters=[{'max_depth': 25.0}],
        output='screen'
    )

    # 深度图(32FC1, DepthPerspective) + camera_info -> 点云(PointCloud2)
    # 注意：ROS2 image_transport 把原始图像发在基础话题名上（无 /Image 后缀）
    depth_to_points_node = Node(
        package='depth_image_proc',
        executable='point_cloud_xyz_radial_node',
        name='depth_to_points',
        remappings=[
            ('image_raw', '/depth/clamped'),
            ('camera_info', '/airsim_node/PX4/CameraDepth/DepthPerspective/camera_info'),
            ('points', '/depth/points')
        ],
        parameters=[{'use_exact_sync': True}],
        output='screen'
    )

    # 点云 QoS 转换：depth_image_proc 用 BEST_EFFORT 发 /depth/points，
    # octomap_server 默认 RELIABLE 订阅，二者不兼容，转发成 RELIABLE 后再喂给 octomap
    cloud_relay_node = Node(
        package='hw_insight',
        executable='cloud_relay',
        name='cloud_relay',
        output='screen'
    )

    # 点云 -> octomap 三维栅格地图
    octomap_server_node = Node(
        package='octomap_server',
        executable='octomap_server_node',
        name='octomap_server',
        remappings=[('cloud_in', '/depth/points_relay')],
        parameters=[{
            'resolution': 0.1,
            'frame_id': 'world_enu',
            'sensor_model/max_range': 12.0,
            'sensor_model/hit': 0.99,
            'sensor_model/miss': 0.4,
            'sensor_model/min': 0.12,
            'sensor_model/max': 0.97,
            'pointcloud_min_z': -2.0,
            'pointcloud_max_z': 6.0,
            'occupancy_min_z': -2.0,
            'occupancy_max_z': 6.0,
            'latch': True,
        }],
        output='screen'
    )

    # rviz 显示 octomap
    pkg_share = get_package_share_directory('hw_insight')
    octomap_rviz_path = os.path.join(pkg_share, 'rviz/octomap.rviz')
    hw_rviz_octomap_node = Node(
        package='rviz2',
        executable='rviz2',
        name='octomap_rviz2',
        arguments=['-d', octomap_rviz_path]
    )

    airsim_node_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('airsim_ros_pkgs'), 'launch/airsim_node.launch.py')
        ),
        launch_arguments=[('host', '127.0.0.1')]
    )

    ld = LaunchDescription()
    ld.add_action(airsim_node_launch)
    ld.add_action(depth_clamp_node)
    ld.add_action(depth_to_points_node)
    ld.add_action(cloud_relay_node)
    ld.add_action(octomap_server_node)
    ld.add_action(hw_rviz_octomap_node)
    return ld
