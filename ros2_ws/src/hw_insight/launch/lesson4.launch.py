import os
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
    #
    # 参数据实测调整过，改动理由逐条记在这里，避免以后被当成随手改的：
    #
    # frame_id: 原来是 world_enu。实测 tf2_monitor 显示 world_enu 的时间戳
    #   相对其它帧偏了约 21 秒，而 world_ned 只有 46ms。octomap 的消息过滤器
    #   因此对不上时间，持续报 "the timestamp on the message is earlier than
    #   all the data in the transform cache" 并丢帧。改用 world_ned。
    #
    # sensor_model/max_range: 12.0 -> 15.0。上游 depth_clamp 裁到 25m，
    #   12m 之外的点既不记 occupied 也不投 miss 射线，地面/结构整片丢失。
    #   取 15.0 是在保留远处结构与限制 free-space 视锥体积之间折中。
    #
    # sensor_model/hit: 0.99 -> 0.7。0.99 对应的 log-odds 增量约 +4.6，
    #   单帧一次命中就把体素顶到 max(0.97) 饱和 —— 深度相机在远距离的量化
    #   噪声和边缘像素会被永久固化成障碍物，之后 miss 也清不掉。这是地图
    #   出现大量飞点的主因。0.7 需要多次观测才确认，配合 miss 可被清除。
    #
    # resolution: 0.1 -> 0.15。0.1m 对 20m 级室外深度过细，点密度随距离
    #   平方衰减，远处同一体素内几乎没有点，噪声被放大成独立体素；实测
    #   八叉树节点数一度涨到 262 万。0.15 使体素数约降到 1/3.4。
    #
    # pointcloud_min_z/max_z: 这两个是在**传感器坐标系**下生效的，z 沿光轴
    #   向前；实测点云 z∈[1.59, 22.73]。原来设 -2..6 等于只保留前方 1.6~6m
    #   的点，6m 外全被砍掉。改为 0.5..15.0，与 max_range 对齐。
    #   （occupancy_min_z/max_z 才是在 frame_id 世界系下生效，两者别混。）
    octomap_server_node = Node(
        package='octomap_server',
        executable='octomap_server_node',
        name='octomap_server',
        remappings=[('cloud_in', '/depth/points_relay')],
        parameters=[{
            'resolution': 0.15,
            'frame_id': 'world_ned',
            'sensor_model/max_range': 15.0,
            'sensor_model/hit': 0.7,
            'sensor_model/miss': 0.4,
            'sensor_model/min': 0.12,
            'sensor_model/max': 0.97,
            'pointcloud_min_z': 0.5,
            'pointcloud_max_z': 15.0,
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
