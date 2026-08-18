#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lesson4 自主避障节点（VFH+ 增强版）。

前视深度相机(DepthPerspective 32FC1)检测障碍 -> VFH+ 局部避障 -> PX4 offboard 速度控制，
从起点自主飞往终点。沿途点云链路(depth_clamp -> point_cloud -> octomap)同时建图。

坐标：全部使用 PX4 NED 局部系（x=北, y=东, z=下，高度为负）。目标点 goal_x/goal_y
为 NED 米制坐标，flight_z 为飞行高度（负=向上）。深度图列左/右对应机体左/右。
"""

import math
import os
import time

import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
    VehicleLocalPosition,
    VehicleStatus,
)
from sensor_msgs.msg import Image, CameraInfo, PointCloud2
from sensor_msgs_py import point_cloud2

from hw_insight.avoid_vfh import (
    VfhParams,
    best_gap_heading,
    blend_corridor_heading,
    compute_vfh_motion,
)
from hw_insight.avoid_planner import OccupancyGridPlanner, select_subgoal
from hw_insight.mission_safety import is_landed_candidate, should_request_disarm

try:
    import cv2
    HAS_CV = True
except Exception:
    HAS_CV = False


def _qos():
    return QoSProfile(
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
    )


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _wrap_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


class AvoidNode(Node):
    def __init__(self):
        super().__init__('avoid_node')
        self.declare_parameter('mode', 'navigate')   # navigate | scan
        self.declare_parameter('goal_x', 25.0)
        self.declare_parameter('goal_y', -15.0)
        self.declare_parameter('goals', '')          # 多航点 "x1,y1;x2,y2;..."
        self.declare_parameter('flight_z', -15.0)
        self.declare_parameter('cruise_speed', 2.5)
        self.declare_parameter('max_speed', 3.5)
        self.declare_parameter('avoid_front', 10.0)
        self.declare_parameter('avoid_brake', 5.0)
        self.declare_parameter('avoid_near', 2.5)
        self.declare_parameter('max_steer', 2.5)
        self.declare_parameter('arrive_dist', 2.0)
        self.declare_parameter('max_mission_time', 300.0)
        self.declare_parameter('stop_progress_time', 20.0)
        self.declare_parameter('flight_log', '/home/hw/logs/avoid_flight.log')
        self.declare_parameter('capture_dir', '/home/hw/logs/depth_captures')

        self.declare_parameter('use_vfh', True)
        self.declare_parameter('vfh_bins', 72)
        self.declare_parameter('vfh_robot_width', 1.0)
        self.declare_parameter('vfh_safety_radius', 1.0)
        self.declare_parameter('vfh_threshold_high', 0.65)
        self.declare_parameter('vfh_threshold_low', 0.30)
        self.declare_parameter('vfh_smooth_window', 1)
        self.declare_parameter('vfh_w_goal', 5.0)
        self.declare_parameter('vfh_w_current', 1.0)
        self.declare_parameter('vfh_w_smooth', 2.0)
        self.declare_parameter('vfh_w_obstacle', 3.0)
        self.declare_parameter('creep_speed', 0.5)
        self.declare_parameter('backup_speed', 0.8)
        self.declare_parameter('vfh_turn_speed', 0.6)
        self.declare_parameter('vfh_behind_fov_extra_deg', 15.0)
        self.declare_parameter('vfh_behind_turn_gain', 1.0)
        self.declare_parameter('exit_on_done', True)

        self.declare_parameter('land_command_retry_sec', 5.0)
        self.declare_parameter('land_timeout_sec', 45.0)
        self.declare_parameter('landed_confirm_sec', 2.0)
        self.declare_parameter('landed_z_tolerance', 0.40)
        self.declare_parameter('landed_xy_speed_tolerance', 0.30)
        self.declare_parameter('landed_z_speed_tolerance', 0.20)
        self.declare_parameter('land_disarm_retry_sec', 3.0)

        self.declare_parameter('use_global_planner', False)
        self.declare_parameter('planner_resolution', 0.5)
        self.declare_parameter('planner_inflation', 1.0)
        self.declare_parameter('planner_lookahead', 8.0)
        self.declare_parameter('planner_cloud_frame', 'world_enu')

        self.mode = self.get_parameter('mode').value
        self.goal_x = float(self.get_parameter('goal_x').value)
        self.goal_y = float(self.get_parameter('goal_y').value)
        goals_str = self.get_parameter('goals').value
        self.goal_list = []
        if goals_str:
            for pair in goals_str.split(';'):
                parts = pair.split(',')
                if len(parts) == 2:
                    self.goal_list.append((float(parts[0]), float(parts[1])))
        if not self.goal_list:
            self.goal_list = [(self.goal_x, self.goal_y)]
        self.goal_idx = 0
        self.goal_x, self.goal_y = self.goal_list[0]
        self.flight_z = float(self.get_parameter('flight_z').value)
        self.cruise = float(self.get_parameter('cruise_speed').value)
        self.max_spd = float(self.get_parameter('max_speed').value)
        self.avoid_front = float(self.get_parameter('avoid_front').value)
        self.avoid_brake = float(self.get_parameter('avoid_brake').value)
        self.avoid_near = float(self.get_parameter('avoid_near').value)
        self.max_steer = float(self.get_parameter('max_steer').value)
        self.arrive_dist = float(self.get_parameter('arrive_dist').value)
        self.max_mission = float(self.get_parameter('max_mission_time').value)
        self.stop_prog = float(self.get_parameter('stop_progress_time').value)
        self.log_path = self.get_parameter('flight_log').value
        self.cap_dir = self.get_parameter('capture_dir').value
        os.makedirs(self.cap_dir, exist_ok=True)

        self.use_vfh = bool(self.get_parameter('use_vfh').value)
        self.exit_on_done = bool(self.get_parameter('exit_on_done').value)
        self.land_command_retry = float(
            self.get_parameter('land_command_retry_sec').value)
        self.land_timeout = float(self.get_parameter('land_timeout_sec').value)
        self.landed_confirm = float(self.get_parameter('landed_confirm_sec').value)
        self.landed_z_tolerance = float(
            self.get_parameter('landed_z_tolerance').value)
        self.landed_xy_speed_tolerance = float(
            self.get_parameter('landed_xy_speed_tolerance').value)
        self.landed_z_speed_tolerance = float(
            self.get_parameter('landed_z_speed_tolerance').value)
        self.land_disarm_retry = float(
            self.get_parameter('land_disarm_retry_sec').value)
        self.vfh_params = VfhParams(
            avoid_front=self.avoid_front,
            avoid_brake=self.avoid_brake,
            avoid_near=self.avoid_near,
            cruise_speed=self.cruise,
            max_speed=self.max_spd,
            creep_speed=float(self.get_parameter('creep_speed').value),
            backup_speed=float(self.get_parameter('backup_speed').value),
            turn_speed=float(self.get_parameter('vfh_turn_speed').value),
            bins=int(self.get_parameter('vfh_bins').value),
            robot_width=float(self.get_parameter('vfh_robot_width').value),
            safety_radius=float(self.get_parameter('vfh_safety_radius').value),
            threshold_high=float(self.get_parameter('vfh_threshold_high').value),
            threshold_low=float(self.get_parameter('vfh_threshold_low').value),
            smooth_window=int(self.get_parameter('vfh_smooth_window').value),
            w_goal=float(self.get_parameter('vfh_w_goal').value),
            w_current=float(self.get_parameter('vfh_w_current').value),
            w_smooth=float(self.get_parameter('vfh_w_smooth').value),
            w_obstacle=float(self.get_parameter('vfh_w_obstacle').value),
            behind_fov_extra_deg=float(self.get_parameter('vfh_behind_fov_extra_deg').value),
            behind_turn_gain=float(self.get_parameter('vfh_behind_turn_gain').value),
        )
        self.last_vfh_theta = 0.0
        self.vfh_recovery_theta = 0.0

        self.use_global_planner = bool(self.get_parameter('use_global_planner').value)
        self.planner_cloud_frame = str(self.get_parameter('planner_cloud_frame').value)
        self.planner = OccupancyGridPlanner(
            resolution=float(self.get_parameter('planner_resolution').value),
            inflation_radius=float(self.get_parameter('planner_inflation').value),
        )
        self.planner_lookahead = float(self.get_parameter('planner_lookahead').value)
        self.global_route = []
        self.planner_t = 0.0

        self.pub_ocm = self.create_publisher(
            OffboardControlMode, '/fmu/in/offboard_control_mode', _qos())
        self.pub_tsp = self.create_publisher(
            TrajectorySetpoint, '/fmu/in/trajectory_setpoint', _qos())
        self.pub_vcmd = self.create_publisher(
            VehicleCommand, '/fmu/in/vehicle_command', _qos())

        dqos = QoSProfile(
            depth=2,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
        )
        self.sub_depth = self.create_subscription(
            Image, '/depth/clamped', self.on_depth, dqos)
        self.sub_pos = self.create_subscription(
            VehicleLocalPosition, '/fmu/out/vehicle_local_position', self.on_pos, _qos())
        self.sub_st = self.create_subscription(
            VehicleStatus, '/fmu/out/vehicle_status', self.on_status, _qos())
        self.sub_cam = self.create_subscription(
            CameraInfo,
            '/airsim_node/PX4/CameraDepth/DepthPerspective/camera_info',
            self.on_cam,
            dqos,
        )
        octo_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.sub_octomap = self.create_subscription(
            PointCloud2,
            '/octomap_point_cloud_centers',
            self.on_octomap,
            octo_qos,
        )

        self.depth = None
        self.depth_t = 0.0
        self.camera_info = None
        self.pos = VehicleLocalPosition()
        self.pos_t = 0.0
        self.have_pos = False
        self.st = VehicleStatus()
        self.st_t = 0.0
        self.have_st = False

        self.setpoint_counter = 0
        self.state = 'WAIT'
        self.last_yaw = 0.0
        self.scan_yaw = 0.0
        self.scan_step_t = 0.0
        self.t0 = time.time()
        self.state_t = self.t0
        self.dc = 999.0
        self.dl = 999.0
        self.dr = 999.0
        self.action = 'init'
        self.tick = 0
        self.best_dist = 1e9
        self.best_dist_t = time.time()
        self.cap_t = 0.0
        self.land_cmd_sent = False
        self.land_cmd_t = 0.0
        self.land_cmd_count = 0
        self.disarm_cmd_t = 0.0
        self.disarm_cmd_count = 0
        self.landed_since = None
        self.land_warn_t = 0.0
        self.ground_z = 0.0
        self.hover_until = 0.0
        self.recover_until = 0.0
        self.recover_turn = 0.0
        self.rearm_t = 0.0
        self.turn_start_yaw = None
        self.turn_target_yaw = None

        self.log_fh = open(self.log_path, 'w')
        self.log_fh.write('# t state x y z dc dl dr action vx vy vz yaw yawspeed\n')
        self.log_fh.flush()
        self.get_logger().info(
            f'goal=({self.goal_x},{self.goal_y}) flight_z={self.flight_z} '
            f'cruise={self.cruise} max_spd={self.max_spd} '
            f'avoid_front={self.avoid_front} avoid_brake={self.avoid_brake} '
            f'use_vfh={self.use_vfh} use_global_planner={self.use_global_planner}')
        self.get_logger().info(f'flight_log -> {self.log_path}')

        self.timer = self.create_timer(0.1, self.on_timer)

    # ---------- callbacks ----------
    def on_depth(self, msg):
        a = np.frombuffer(msg.data, dtype=np.float32)
        try:
            self.depth = a.reshape((msg.height, msg.width))
        except Exception:
            self.depth = None
        self.depth_t = time.time()

    def on_pos(self, msg):
        self.pos = msg
        self.pos_t = time.time()
        self.have_pos = True

    def on_status(self, msg):
        self.st = msg
        self.st_t = time.time()
        self.have_st = True

    def on_cam(self, msg):
        self.camera_info = msg

    def on_octomap(self, msg):
        if not self.use_global_planner:
            return
        try:
            pts = np.array(list(point_cloud2.read_points(
                msg, field_names=('x', 'y', 'z'), skip_nans=True)))
            if pts.size == 0:
                return
            if pts.dtype.names:
                x = pts['x'].astype(float)
                y = pts['y'].astype(float)
                z = pts['z'].astype(float)
            else:
                x = pts[:, 0].astype(float)
                y = pts[:, 1].astype(float)
                z = pts[:, 2].astype(float)
            # world_enu -> NED: 180-deg rotation around (1,1,0) swaps x and y.
            if 'enu' in self.planner_cloud_frame.lower():
                x, y = y, x
            xyz = np.stack([x, y, z], axis=1)
            now = time.time()
            self.planner.update_cloud(xyz, timestamp=now)
            self.global_route = self.planner.plan(
                (self.pos.x, self.pos.y),
                (self.goal_x, self.goal_y),
            )
            self.planner_t = now
            self.get_logger().info(
                'global planner updated: %d points, %d waypoints' % (
                    len(xyz), len(self.global_route)))
        except Exception as e:
            self.get_logger().warn('octomap planner update failed: %s' % e)

    # ---------- depth metrics ----------
    def depth_metrics(self):
        if self.depth is None:
            return 999.0, 999.0, 999.0
        h, w = self.depth.shape
        y0, y1 = int(h * 0.20), int(h * 0.80)
        a = self.depth[y0:y1]

        def mn(x0, x1):
            v = a[:, x0:x1][np.isfinite(a[:, x0:x1])]
            return float(v.min()) if v.size else 999.0
        dc = mn(int(w * 0.35), int(w * 0.65))
        dl = mn(0, int(w * 0.30))
        dr = mn(int(w * 0.70), w)
        return dc, dl, dr

    # ---------- publishers ----------
    def publish_heartbeat(self):
        m = OffboardControlMode()
        m.position = False
        m.velocity = True
        m.acceleration = False
        m.attitude = False
        m.body_rate = False
        m.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.pub_ocm.publish(m)

    def publish_velocity(self, vx, vy, vz, yaw, yawspeed=0.0):
        m = TrajectorySetpoint()
        m.position = [float('nan'), float('nan'), float('nan')]
        m.velocity = [float(vx), float(vy), float(vz)]
        m.acceleration = [float('nan'), float('nan'), float('nan')]
        if math.isfinite(yaw):
            m.yaw = float(yaw)
        else:
            m.yaw = float('nan')
        m.yawspeed = float(yawspeed)
        m.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.pub_tsp.publish(m)

    def publish_command(self, command, **params):
        m = VehicleCommand()
        m.command = command
        m.param1 = params.get('param1', 0.0)
        m.param2 = params.get('param2', 0.0)
        m.param3 = params.get('param3', 0.0)
        m.param4 = params.get('param4', 0.0)
        m.param5 = params.get('param5', 0.0)
        m.param6 = params.get('param6', 0.0)
        m.param7 = params.get('param7', 0.0)
        m.target_system = 1
        m.target_component = 1
        m.source_system = 1
        m.source_component = 1
        m.from_external = True
        m.timestamp = int(self.get_clock().now().nanoseconds / 1000)
        self.pub_vcmd.publish(m)

    def engage_offboard(self):
        self.publish_command(VehicleCommand.VEHICLE_CMD_DO_SET_MODE, param1=1.0, param2=6.0)

    def arm(self):
        self.publish_command(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=1.0)

    def land(self):
        self.publish_command(VehicleCommand.VEHICLE_CMD_NAV_LAND)

    def disarm(self):
        # Use a normal disarm request.  PX4 will reject this while airborne;
        # never send the force-disarm magic value from autonomous fallback.
        self.publish_command(
            VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, param1=0.0)

    def start_landing(self, now, reason):
        """Enter LAND and reset command/fallback bookkeeping."""
        self.state = 'LAND'
        self.state_t = now
        self.land_cmd_sent = False
        self.land_cmd_t = 0.0
        self.land_cmd_count = 0
        self.disarm_cmd_t = 0.0
        self.disarm_cmd_count = 0
        self.landed_since = None
        self.land_warn_t = 0.0
        self.get_logger().info(reason)

    # ---------- logging ----------
    def log_line(self, now, yaw, yawspeed=0.0):
        self.log_fh.write(
            '%.2f %s %.2f %.2f %.2f %.1f %.1f %.1f %s %.2f %.2f %.2f %.2f %.2f\n' % (
                now - self.t0, self.state,
                self.pos.x, self.pos.y, self.pos.z,
                self.dc, self.dl, self.dr, self.action,
                self.last_vx, self.last_vy, self.last_vz, yaw, yawspeed))
        self.log_fh.flush()

    def capture_depth(self):
        if self.depth is None or not HAS_CV:
            return
        a = self.depth.copy()
        finite = np.isfinite(a)
        if finite.any():
            a[~finite] = self.avoid_front
            a = np.clip(a, 0.0, self.avoid_front)
            img = (a / self.avoid_front * 255.0).astype(np.uint8)
        else:
            img = np.zeros(a.shape, dtype=np.uint8)
        img = cv2.applyColorMap(255 - img, cv2.COLORMAP_TURBO)
        cv2.imwrite(os.path.join(self.cap_dir, 'depth_%06d.png' % self.tick), img)

    # ---------- main control loop ----------
    def on_timer(self):
        now = time.time()
        self.tick += 1
        self.publish_heartbeat()
        self.setpoint_counter += 1

        vx = vy = vz = 0.0
        yaw = self.last_yaw
        yawspeed = 0.0
        self.last_vx = self.last_vy = self.last_vz = 0.0

        depth_ok = (now - self.depth_t) < 1.5
        pos_ok = (now - self.pos_t) < 1.0
        sensor_control_state = self.state in (
            'TAKEOFF', 'NAVIGATE', 'HOVER', 'SCAN')
        if sensor_control_state and not (depth_ok and pos_ok):
            self.action = 'NO_SENSOR'
            self.publish_velocity(0.0, 0.0, 0.0, yaw)
            self.log_line(now, yaw)
            return

        if self.state == 'WAIT':
            self.action = 'wait_sensors'
            if (self.have_st and self.have_pos and self.depth is not None
                    and self.setpoint_counter >= 10 and self.st.pre_flight_checks_pass):
                if self.st.arming_state == VehicleStatus.ARMING_STATE_DISARMED:
                    self.ground_z = float(self.pos.z)
                already_offboard = (
                    self.st.arming_state == VehicleStatus.ARMING_STATE_ARMED
                    and self.st.nav_state
                    == VehicleStatus.NAVIGATION_STATE_OFFBOARD)
                if not already_offboard:
                    self.engage_offboard()
                    self.arm()
                    self.get_logger().info('engaging offboard + arm')
                    self.state = 'TAKEOFF'
                    self.state_t = now
                    self.get_logger().info('takeoff to z=%.1f' % self.flight_z)
                else:
                    self.state = 'NAVIGATE'
                    self.state_t = now
                    self.get_logger().info('already armed+offboard, go navigate')

        if self.state == 'TAKEOFF':
            vz = _clamp(1.2 * (self.flight_z - self.pos.z), -1.5, 1.5)
            self.action = 'takeoff'
            if (self.have_st and self.st.arming_state != VehicleStatus.ARMING_STATE_ARMED
                    and self.st.pre_flight_checks_pass and now - self.rearm_t > 2.0):
                self.rearm_t = now
                self.engage_offboard()
                self.arm()
                self.action = 'rearm'
            if abs(self.pos.z - self.flight_z) < 0.8:
                if self.mode == 'scan':
                    self.state = 'SCAN'
                    self.scan_yaw = 0.0
                    self.scan_step_t = now
                    self.get_logger().info('takeoff done, start 360 deg scan')
                else:
                    self.state = 'NAVIGATE'
                    self.state_t = now
                    self.get_logger().info('takeoff done, navigating to goal')

        if self.state == 'SCAN':
            self.action = 'scan'
            yaw = self.scan_yaw
            self.dc, self.dl, self.dr = self.depth_metrics()
            if now - self.scan_step_t > 0.5:
                self.scan_step_t = now
                self.scan_yaw = self.scan_yaw + 0.25
                if self.scan_yaw > 2 * math.pi:
                    self.start_landing(now, 'scan done, landing')
            vx = vy = vz = 0.0
            yaw = self.scan_yaw

        if self.state == 'NAVIGATE':
            if (now - self.state_t) > self.max_mission:
                self.action = 'TIMEOUT'
                self.start_landing(now, 'mission timeout, landing')
            else:
                vx, vy, vz, yaw, yawspeed = self.compute_avoid(now)

        if self.state == 'HOVER':
            self.action = 'hover'
            if now > self.hover_until:
                self.start_landing(now, 'arrived at goal, landing')

        if self.state == 'LAND':
            self.action = 'land'
            if self.have_st and self.st.arming_state == VehicleStatus.ARMING_STATE_DISARMED:
                self.state = 'DONE'
                self.state_t = now
                self.get_logger().info('DISARMED -> mission done')
            else:
                if (not self.land_cmd_sent
                        or now - self.land_cmd_t >= self.land_command_retry):
                    self.land()
                    self.land_cmd_sent = True
                    self.land_cmd_t = now
                    self.land_cmd_count += 1
                    if self.land_cmd_count == 1:
                        self.get_logger().info('land command sent')
                    else:
                        self.get_logger().warn(
                            'land command retry #%d' % self.land_cmd_count)

                landed_now = pos_ok and is_landed_candidate(
                    z=float(self.pos.z),
                    ground_z=self.ground_z,
                    vx=float(self.pos.vx),
                    vy=float(self.pos.vy),
                    vz=float(self.pos.vz),
                    z_tolerance=self.landed_z_tolerance,
                    xy_speed_tolerance=self.landed_xy_speed_tolerance,
                    z_speed_tolerance=self.landed_z_speed_tolerance,
                )
                if landed_now:
                    if self.landed_since is None:
                        self.landed_since = now
                else:
                    self.landed_since = None

                landed_stable_for = (
                    now - self.landed_since
                    if self.landed_since is not None else 0.0)
                landing_elapsed = now - self.state_t
                if should_request_disarm(
                        landing_elapsed=landing_elapsed,
                        landed_stable_for=landed_stable_for,
                        land_timeout=self.land_timeout,
                        landed_confirm=self.landed_confirm):
                    if now - self.disarm_cmd_t >= self.land_disarm_retry:
                        self.disarm()
                        self.disarm_cmd_t = now
                        self.disarm_cmd_count += 1
                        self.action = 'disarm_fallback'
                        self.get_logger().warn(
                            'landing timeout after %.1fs; grounded for %.1fs, '
                            'normal disarm fallback #%d' % (
                                landing_elapsed,
                                landed_stable_for,
                                self.disarm_cmd_count))
                elif (landing_elapsed >= self.land_timeout
                      and now - self.land_warn_t >= 5.0):
                    self.land_warn_t = now
                    self.get_logger().warn(
                        'landing timeout after %.1fs; disarm withheld until '
                        'ground/velocity checks remain stable' % landing_elapsed)

            if pos_ok:
                vz = _clamp(0.8 * (self.ground_z - self.pos.z), -0.5, 0.8)
            else:
                vz = 0.0

        if self.state == 'DONE':
            self.action = 'done'
            if not hasattr(self, 'done_logged'):
                self.done_logged = True
                self.get_logger().info(
                    ('=== MISSION DONE === goal=({}, {}) pos=({:.1f},{:.1f}) '
                     'elapsed={:.1f}s').format(
                        self.goal_x, self.goal_y, self.pos.x, self.pos.y, now - self.t0))
            if self.exit_on_done:
                # Node/context teardown must be owned by main() (or by the
                # external runner embedding AvoidNode).  Destroying the node
                # and shutting down rclpy from inside a timer callback can
                # deadlock the executor, and the outer runner would then try
                # to destroy/shutdown the same objects a second time.
                self.timer.cancel()
                return

        self.publish_velocity(vx, vy, vz, yaw, yawspeed)
        self.last_yaw = yaw if math.isfinite(yaw) else self.last_yaw
        self.last_vx, self.last_vy, self.last_vz = vx, vy, vz

        if self.tick % 5 == 0:
            self.log_line(now, yaw, yawspeed)
        if self.tick % 10 == 0 and self.state in ('TAKEOFF', 'NAVIGATE', 'HOVER', 'LAND', 'SCAN'):
            self.get_logger().info(
                ('[%s] pos=(%.1f,%.1f,%.1f) goal_dist=%.1f dc=%.1f '
                 'dl=%.1f dr=%.1f act=%s v=(%.2f,%.2f,%.2f) '
                 'yaw=%.2f ys=%.2f') % (
                    self.state, self.pos.x, self.pos.y, self.pos.z,
                    math.hypot(self.goal_x - self.pos.x, self.goal_y - self.pos.y),
                    self.dc, self.dl, self.dr, self.action, vx, vy, vz, yaw, yawspeed))
        if self.state in ('NAVIGATE', 'SCAN') and now - self.cap_t > 4.0:
            self.cap_t = now
            self.capture_depth()

    # ---------- legacy reactive avoidance ----------
    def _legacy_compute_avoid(self, now):
        dx = self.goal_x - self.pos.x
        dy = self.goal_y - self.pos.y
        dist = math.hypot(dx, dy)
        gh = math.atan2(dy, dx)

        if dist < self.arrive_dist:
            if self.goal_idx < len(self.goal_list) - 1:
                self.goal_idx += 1
                self.goal_x, self.goal_y = self.goal_list[self.goal_idx]
                self.best_dist = 1e9
                self.best_dist_t = now
                self.action = 'wp%d' % self.goal_idx
                self.get_logger().info(
                    'WAYPOINT %d/%d reached, next goal=(%.1f,%.1f) pos=(%.1f,%.1f)' % (
                        self.goal_idx, len(self.goal_list) - 1,
                        self.goal_x, self.goal_y, self.pos.x, self.pos.y))
                return 0.0, 0.0, 0.0, self.last_yaw, 0.0
            self.state = 'HOVER'
            self.state_t = now
            self.hover_until = now + 1.5
            self.get_logger().info('reached final goal (dist=%.1f), hover then land' % dist)
            self.action = 'arrived'
            return 0.0, 0.0, 0.0, self.last_yaw, 0.0

        self.dc, self.dl, self.dr = self.depth_metrics()

        if dist < self.best_dist - 0.2:
            self.best_dist = dist
            self.best_dist_t = now
            if now < self.recover_until:
                self.recover_until = 0.0
        elif now - self.best_dist_t > self.stop_prog:
            if now >= self.recover_until:
                self.recover_until = now + 3.0
                self.recover_turn = 0.9 if self.dl >= self.dr else -0.9
                self.get_logger().warn(
                    'STUCK %.0fs (dist=%.1f dc=%.1f dl=%.1f dr=%.1f) -> recovery turn %.1f' % (
                        now - self.best_dist_t, dist, self.dc, self.dl,
                        self.dr, self.recover_turn))

        if self.dc > self.avoid_front:
            fwd = self.cruise
            self.action = 'go'
        elif self.dc > self.avoid_brake:
            fwd = (
                self.cruise * (self.dc - self.avoid_brake)
                / (self.avoid_front - self.avoid_brake))
            self.action = 'slow'
        elif self.dc > self.avoid_near:
            fwd = 0.3
            self.action = 'near'
        else:
            fwd = -1.0
            self.action = 'backup'

        turn = 0.0
        if self.dc < self.avoid_front:
            if now < self.recover_until:
                turn = self.recover_turn
                self.action = 'recover'
            else:
                open_diff = self.dl - self.dr
                if open_diff > 1.0:
                    turn = 0.9
                    self.action = 'avoidL'
                elif open_diff < -1.0:
                    turn = -0.9
                    self.action = 'avoidR'
                else:
                    turn = 0.0
                prox = 1.0 - _clamp(
                    (self.dc - self.avoid_near)
                    / (self.avoid_front - self.avoid_near),
                    0.0,
                    1.0,
                )
                turn *= (0.4 + 0.6 * prox)
        turn *= (0.15 + 0.85 * min(1.0, dist / 12.0))

        heading = gh + turn
        vx = math.cos(heading) * fwd
        vy = math.sin(heading) * fwd

        h = self.pos.heading
        lx, ly = math.sin(h), -math.cos(h)
        if self.dl < 3.0:
            push = (3.0 - self.dl) * 0.7
            vx -= push * lx
            vy -= push * ly
        if self.dr < 3.0:
            push = (3.0 - self.dr) * 0.7
            vx += push * lx
            vy += push * ly

        spd = math.hypot(vx, vy)
        if spd > self.max_spd:
            vx *= self.max_spd / spd
            vy *= self.max_spd / spd
            spd = self.max_spd

        vz = _clamp(1.2 * (self.flight_z - self.pos.z), -1.5, 1.5)
        if spd > 0.25:
            yaw = math.atan2(vy, vx) if fwd >= 0 else heading
        else:
            yaw = self.last_yaw
        return vx, vy, vz, yaw, 0.0

    # ---------- VFH + global planner avoidance ----------
    def compute_avoid(self, now):
        dx = self.goal_x - self.pos.x
        dy = self.goal_y - self.pos.y
        dist = math.hypot(dx, dy)
        gh = math.atan2(dy, dx)

        if dist < self.arrive_dist:
            if self.goal_idx < len(self.goal_list) - 1:
                self.goal_idx += 1
                self.goal_x, self.goal_y = self.goal_list[self.goal_idx]
                self.best_dist = 1e9
                self.best_dist_t = now
                self.last_vfh_theta = 0.0
                self.global_route = []
                self.action = 'wp%d' % self.goal_idx
                self.get_logger().info(
                    'WAYPOINT %d/%d reached, next goal=(%.1f,%.1f) pos=(%.1f,%.1f)' % (
                        self.goal_idx, len(self.goal_list) - 1,
                        self.goal_x, self.goal_y, self.pos.x, self.pos.y))
                return 0.0, 0.0, 0.0, self.last_yaw, 0.0
            self.state = 'HOVER'
            self.state_t = now
            self.hover_until = now + 1.5
            self.get_logger().info('reached final goal (dist=%.1f), hover then land' % dist)
            self.action = 'arrived'
            return 0.0, 0.0, 0.0, self.last_yaw, 0.0

        self.dc, self.dl, self.dr = self.depth_metrics()

        if not self.use_vfh:
            return self._legacy_compute_avoid(now)

        # Choose effective goal: global A* sub-goal or final waypoint.
        goal_x, goal_y = self.goal_x, self.goal_y
        if (self.use_global_planner and self.global_route
                and (now - self.planner_t) < 10.0):
            sub = select_subgoal(
                self.global_route,
                (self.pos.x, self.pos.y),
                (self.goal_x, self.goal_y),
                self.planner_lookahead,
                self.arrive_dist,
            )
            goal_x, goal_y = sub
            if sub != (self.goal_x, self.goal_y):
                self.action = 'follow'

        body_heading = float(self.pos.heading) if self.have_pos else 0.0
        camera_info = None
        if self.camera_info is not None:
            camera_info = {
                'k': list(self.camera_info.k),
                'width': int(self.camera_info.width),
                'height': int(self.camera_info.height),
            }

        # Stuck watchdog.
        if dist < self.best_dist - 0.2:
            self.best_dist = dist
            self.best_dist_t = now
            if now < self.recover_until:
                self.recover_until = 0.0
        elif now - self.best_dist_t > self.stop_prog:
            if now >= self.recover_until:
                self.recover_until = now + 4.0
                try:
                    self.vfh_recovery_theta = best_gap_heading(
                        self.depth, self.vfh_params, camera_info)
                except Exception as e:
                    self.get_logger().warn('VFH gap search failed: %s' % e)
                    self.vfh_recovery_theta = 0.9 if self.dl >= self.dr else -0.9
                self.get_logger().warn(
                    'STUCK %.0fs (dist=%.1f dc=%.1f dl=%.1f dr=%.1f) -> recovery theta %.2f' % (
                        now - self.best_dist_t, dist, self.dc, self.dl, self.dr,
                        self.vfh_recovery_theta))

        recovery_theta = None
        if now < self.recover_until:
            recovery_theta = self.vfh_recovery_theta

        try:
            motion = compute_vfh_motion(
                depth=self.depth,
                params=self.vfh_params,
                body_heading=body_heading,
                goal_x=goal_x,
                goal_y=goal_y,
                pos_x=self.pos.x,
                pos_y=self.pos.y,
                last_theta=self.last_vfh_theta,
                recovery_theta=recovery_theta,
                camera_info=camera_info,
            )
        except Exception as e:
            self.get_logger().error('VFH motion computation failed: %s' % e)
            return self._legacy_compute_avoid(now)

        self.action = motion['action']
        self.last_vfh_theta = motion['theta']
        self.dc = motion['dc']

        # ----- VFH+ behind-goal handling -----
        if motion['action'] == 'turn' and abs(motion['yaw_rate']) > 1e-3:
            # Turn in place using yaw-rate control.
            vx = vy = 0.0
            yawspeed = motion['yaw_rate']
            yaw = float('nan')
            vz = _clamp(1.2 * (self.flight_z - self.pos.z), -1.5, 1.5)
            # Track turn progress to avoid spinning forever.
            if self.turn_target_yaw is None:
                self.turn_target_yaw = _wrap_angle(body_heading + motion['goal_theta'])
                self.turn_start_yaw = body_heading
            else:
                # If we have turned past the target, exit turn mode next cycle.
                turned = _wrap_angle(body_heading - self.turn_start_yaw)
                target_delta = _wrap_angle(self.turn_target_yaw - self.turn_start_yaw)
                if abs(_wrap_angle(turned - target_delta)) < 0.25:
                    self.turn_target_yaw = None
                    self.turn_start_yaw = None
                    self.last_vfh_theta = 0.0
            return vx, vy, vz, yaw, yawspeed
        else:
            self.turn_target_yaw = None
            self.turn_start_yaw = None

        vx, vy = motion['vx'], motion['vy']
        yaw = motion['yaw']
        yawspeed = motion['yaw_rate']

        # Blend selected corridor direction with direct goal direction for
        # smoother convergence when the path is clear.
        goal_blend = 0.15 + 0.85 * min(1.0, dist / 12.0)
        if motion['forward_speed'] >= 0.0 and motion['action'] != 'turn':
            heading_world = blend_corridor_heading(
                body_heading=body_heading,
                goal_heading=gh,
                corridor_theta=motion['theta'],
                corridor_weight=goal_blend,
                max_steer=self.max_steer,
            )
            vx = math.cos(heading_world) * motion['forward_speed']
            vy = math.sin(heading_world) * motion['forward_speed']
            yaw = heading_world

        spd = math.hypot(vx, vy)
        if spd > self.max_spd:
            scale = self.max_spd / spd
            vx *= scale
            vy *= scale

        vz = _clamp(1.2 * (self.flight_z - self.pos.z), -1.5, 1.5)
        return vx, vy, vz, yaw, yawspeed


def main(args=None):
    rclpy.init(args=args)
    node = AvoidNode()
    try:
        if node.exit_on_done:
            while rclpy.ok() and node.state != 'DONE':
                rclpy.spin_once(node, timeout_sec=0.1)
            if rclpy.ok():
                rclpy.spin_once(node, timeout_sec=0.25)
        else:
            rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(node, 'log_fh'):
            node.log_fh.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
