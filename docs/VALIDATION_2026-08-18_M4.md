# Qt GUI M4 真实仿真验收记录（2026-08-18）

## 验收环境

UE4 4.27 + AirSim 1.8.1，CityPark `Showcase`。PX4 v1.15.2 SITL、Micro XRCE-DDS、
ROS2 Humble、OctoMap。Windows 侧是 PySide6 6.8.3 + pyqtgraph OpenGL。模型为
27 类本地 `best.pt`，置信度阈值 0.25。

## 实际数据链

1. `launch_ue4.ps1` 成功等到了 AirSim RPC，运行时把 `PostProcessVolumeMAIN` 移掉。
   真实 `CameraDepth` 统计：最小 1.761 m、中位数 61.844 m、最大 16,640 m。

2. `/octomap_point_cloud_centers` 实测约 4.8–5.1 Hz；桥接器按 1 Hz 连续发快照，
   每帧约 29,000 个有限占据点。

3. AirSim ROS TF 给出的 CityPark 出生点是
   `world_ned -> PX4 = (-134.09, 258.15, -1.50) m`。桥接器先把 `world_enu` 旋成
   world NED，再减掉这个平移；校准后的真实快照范围是 N `1.14–24.74 m`、
   E `-17.60–17.20 m`、D `0.25–0.55 m`，和 PX4 局部原点对上了。

4. YOLO 在线读的是同一路 AirSim Scene + DepthPerspective 流，18 秒限制测试里
   处理 6 帧，确认并保存 3 张 `fence` 场景证据；最终生成 7 个经多帧合并的近似
   三维语义对象。

5. Qt/OpenGL 离线 Session 复开成功，同时显示 29,651 个真实点和 7/7 个语义标签；
   导出 1,100,073 字节 PLY、2,059 字节语义 JSON 和 308,583 字节 PNG。

## 现场发现并修复

- 旧 AirSim RPC 的 Tornado 4 会在 Windows 导入时顺带加载系统证书，某些旧 Python
  环境因此抛 ASN.1 异常。现在的做法是用共享兼容导入器，只在本地非 TLS RPC 导入
  阶段把证书初始化隔离掉，并支持从仓库上级 `.tools/airsim_rpc` 找离线依赖。

- 地图桥接最早只交换 ENU/NED 轴，漏掉了 CityPark 出生点平移，点云和 PX4 轨迹
  差了大约百米。后来改成从 TF 自动读取并扣除该平移，同时在快照 JSON 里记录
  `world_origin_ned`。

- 桥接器收到 SIGINT 时可能对已经关掉的 `rclpy` Context 二次 `shutdown`。改成先
  检查 `rclpy.ok()`，现场复测能正常退出，没有 traceback。

## 验收边界

本记录证明 M4 能消费真实 UE4/AirSim/ROS2/OctoMap/YOLO 数据并完成三维显示与导出。
完整大环线的起飞、VFH、返航、着陆、解除锁定和 `MISSION DONE` 闭环已经在
`VALIDATION_2026-08-17.md` 里，这次没有重复飞那 756 秒航线。
