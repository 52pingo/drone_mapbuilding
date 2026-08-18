# Qt GUI M4 真实仿真验收记录（2026-08-18）

## 验收环境

- UE4 4.27 + AirSim 1.8.1，CityPark `Showcase`。
- PX4 v1.15.2 SITL、Micro XRCE-DDS、ROS2 Humble、OctoMap。
- Windows PySide6 6.8.3 + pyqtgraph OpenGL。
- 27 类本地 `best.pt`，置信度阈值 0.25。

## 实际数据链

1. `launch_ue4.ps1` 成功等待 AirSim RPC，运行时移除
   `PostProcessVolumeMAIN`；真实 `CameraDepth` 统计为：最小 1.761 m、
   中位数 61.844 m、最大 16,640 m。
2. `/octomap_point_cloud_centers` 实测约 4.8–5.1 Hz；桥接器按 1 Hz
   连续发布快照，每帧约 29,000 个有限占据点。
3. AirSim ROS TF 给出的 CityPark 出生点为
   `world_ned -> PX4 = (-134.09, 258.15, -1.50) m`。桥接器先把
   `world_enu` 旋转为 world NED，再减去该平移；校准后的真实快照范围为
   N `1.14–24.74 m`、E `-17.60–17.20 m`、D `0.25–0.55 m`，与 PX4
   局部原点一致。
4. YOLO 在线读取同一 AirSim Scene + DepthPerspective 流，18 秒限制测试内处理
   6 帧，确认并保存 3 张 `fence` 场景证据；最终生成 7 个经多帧合并的近似
   三维语义对象。
5. Qt/OpenGL 离线 Session 复开成功，同时显示 29,651 个真实点和 7/7 个语义
   标签；成功导出 1,100,073 字节 PLY、2,059 字节语义 JSON 和 308,583 字节 PNG。

## 现场发现并修复

- 旧 AirSim RPC 的 Tornado 4 会在 Windows 导入时无关地加载系统证书，某些旧
  Python 环境因此抛出 ASN.1 异常。现使用共享兼容导入器，仅在本地非 TLS RPC
  导入阶段隔离该证书初始化，并支持从仓库上级 `.tools/airsim_rpc` 找离线依赖。
- 最初地图桥接只交换 ENU/NED 轴，漏掉 CityPark 出生点平移，导致点云与 PX4
  轨迹相差约百米。现从 TF 自动读取并扣除该平移，且在快照 JSON 中记录
  `world_origin_ned`。
- 桥接器收到 SIGINT 时可能对已关闭的 `rclpy` Context 二次 `shutdown`。现先检查
  `rclpy.ok()`，现场复测可正常退出且无 traceback。

## 验收边界

本记录证明 M4 能消费真实 UE4/AirSim/ROS2/OctoMap/YOLO 数据并完成三维显示与导出。
完整大环线的起飞、VFH、返航、着陆、解除锁定和 `MISSION DONE` 闭环已在
`VALIDATION_2026-08-17.md` 记录，本次没有重复飞行该 756 秒航线。
