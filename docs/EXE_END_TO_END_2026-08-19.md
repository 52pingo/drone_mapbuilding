# Windows EXE 端到端操作与验收记录（2026-08-19）

本文记录实际从发布版 `DroneMapbuilding.exe` 操作一遍完整工作流的步骤、正常等待
时间、成功判据、发现的问题与修复结果。飞行环境为 CityPark，飞控为 PX4 v1.15.2
SITL，ROS2 为 Humble。

## 1. 发布物位置

```text
dist/DroneMapbuilding/DroneMapbuilding.exe
dist/DroneMapbuilding-win64.zip
```

必须保留 EXE、`_internal/`、`scripts/`、`config/`、`ros2_ws/`、`.tools/` 和
`drone_gui/` 的相对位置，不能只复制 EXE。视觉权重 `best.pt` 不在 Git/ZIP 中，需
在“环境配置”中选择本地文件。

## 2. 首次配置

1. 双击 `DroneMapbuilding.exe`，进入“环境配置”。
2. 仿真启动方式选择以下之一：
   - UE4 编辑器工程：选择 `UE4Editor.exe`、`.uproject` 和地图资源；
   - 已打包仿真：选择本地仿真 `.exe`。
3. 配置视觉 Python、AirSim PythonClient、`best.pt`、成果目录和 QGC。
4. 配置 WSL 发行版/用户、ROS2 工作区、PX4、Micro XRCE-DDS Agent 和日志目录。
5. 点击“保存并应用”，再点“配置能力体检”。仅当页面显示工作流环境通过时继续。

本机验收配置的关键路径如下，仅作格式参考，其他电脑应在 GUI 中重新选择：

```text
UE4:        D:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe
Project:    D:\CityParkEnvironmentCollec\CityPark.uproject
Map:        /Game/CityPark/Maps/Showcase?game=/Script/AirSim.AirSimGameMode
Python:     C:\Users\29593\anaconda3\envs\deeplearning\python.exe
AirSim:     D:\PycharmProjects\PythonProject19\AirSim\PythonClient
ROS2:       /home/hw/hw-ros2/ros2
PX4:        /home/hw/px4v1.15.2
XRCE:       /home/hw/Micro-XRCE-DDS-Agent/build/MicroXRCEAgent
```

## 3. 系统自检与启动顺序

进入“系统自检”，严格按以下顺序操作：

1. 点“本地 + WSL 动态检查”。在飞控栈未启动时，PX4、深度或 OctoMap 显示未就绪
   是正常状态，不代表本地路径错误。
2. 点“1  启动 UE4”。等待日志出现：

   ```text
   UE4 ready
   AirSim RGB/depth are ready
   CameraDepth verified: min=... median=... max=...m
   ```

   CityPark 首次启动实际用了约 75 秒，按钮已设置 300 秒超时，不要在加载阶段反复
   点击。相同工程和地图已运行时会复用实例；若 41451 端口属于其他环境，GUI 会
   明确拒绝启动，避免连接到错误场景。
3. 点“2  启动 PX4 / ROS2”。脚本只有在收到三类真实消息后才返回成功：

   ```text
   ready: PX4 telemetry
   ready: metric depth
   ready: OctoMap point cloud
   ```

4. 等待 GUI 自动动态复检。PX4、XRCE、AirSim ROS、位置遥测、`/depth/clamped` 和
   `/octomap_point_cloud_centers` 全部通过后，才允许开始任务。

## 4. 航线规划与任务启动

1. 进入“航线规划”。可在画布双击添加，也可在表格精确编辑或加载 JSON。
2. 坐标为 PX4 Local NED：North 为 x、East 为 y、Down 为 z，因此飞行高度必须为
   负数。末航点建议为 `(0,0)`。
3. 确认摘要显示“航线参数检查通过”，再点“开始语义建图任务”。
4. 本次验收使用的短航线为：

   ```text
   (20,0) -> (20,15) -> (0,0)
   flight_z=-12 m, cruise=3 m/s, max=4 m/s, timeout=300 s
   ```

5. 进入“实时感知”观察状态。任务中不要关闭 GUI；需要人工干预时只使用 Hold、
   Resume 或安全 Land，不要在空中强制 disarm。

## 5. 完整闭环成功判据

不能仅以无人机看起来落地或进程退出作为成功。以下条件必须同时成立：

```text
状态：DONE
飞行状态：已解除锁定
DISARMED -> mission done
=== MISSION DONE ===
GUI_STATUS ... "state":"DONE","armed":false
manifest.summary.closed_loop=true
manifest.summary.final_state="DONE"
manifest.summary.final_armed=false
```

本次实飞结果：

| 项目 | 结果 |
|---|---|
| Session | `gui_CityPark_20260819_220756` |
| 航线距离 | 60 m |
| 飞行闭环耗时 | 86.8 s |
| 最终 N/E/Z | 约 `0.42 / 0.24 / -0.07 m` |
| 最终返航误差 | 约 0.49 m |
| 着陆/解锁 | LAND 后稳定触地，安全 fallback #3，`armed=false` |
| 遥测 | 173 帧 |
| 三维地图 | 80,000 点；最终 OctoMap 原始渲染 171,513 点 |
| OctoMap BT | 2,473,211 nodes，0.1 m 分辨率 |
| 语义对象 | 32 个 |
| 类别证据 | fence 8 张、tree 2 张；均为带框场景图 |

## 6. 成果浏览、回放和导出

1. 进入“地图与成果”。“实时 3D 地图”应显示点数、轨迹、语义目标和
   `px4_local_ned` 坐标系。
2. 点“导出 PLY / PCD / JSON / PNG”，确认生成：

   ```text
   semantic_map.ply
   semantic_map.pcd
   semantic_objects.json
   semantic_map_view.png
   ```

3. 切到“成果浏览”，选择 Session，点“在三维地图中打开所选任务 Session”。
4. 使用播放按钮、时间轴和 0.5x–8x 速度进行离线遥测回放。本次 Session 的时间轴
   范围为 0–172，共 173 帧。
5. 每次任务还应包含 `manifest.json`、`telemetry.jsonl/csv`、`report.html`、
   `octomap.bt`、`octomap_map.png`、`depth_rviz.png`、`flight_trajectory.png` 和
   `detected_classes/<类别>/scene_*.jpg`。

## 7. 本次发现并修复的问题

| 问题 | 修复 |
|---|---|
| 已有 UE4 时重复启动并可能连接旧场景 | 按工程+地图检测，复用相同实例；异环境占用 41451 时拒绝 |
| PX4 已运行但自检为 false | 改为匹配实际 `px4` SITL 进程 |
| ROS launch 存活但深度/OctoMap 尚未出数据 | 启动脚本等待三条真实消息后才返回成功 |
| ROS setup 在 `set -u` 下提前退出 | source 时临时关闭 nounset，完成后恢复 |
| UE4 继承 PyInstaller DLL 搜索路径并锁定发布包 | 启动外部进程前清理 `SetDllDirectoryW` 与 bundle PATH；UE4 已验证加载系统 DLL |
| 发布包的外部 Python 无法导入 Session 模块 | 随包发布必要的 `drone_gui` 纯 Python 模块 |
| 正常 stop-file 退出却得到空 ExitCode | 结合 finished_at、语义对象文件和空 stderr 做严格正常退出判定 |

本次实飞发生在最后一项修复前，因此首次归档被误标为 `failed`；飞行证据已明确
`DONE + disarmed`，感知日志也明确正常 stop 且 stderr 为空，随后通过 Session
finalize 恢复为 `completed`。修复后的脚本会在后续任务中直接判定为成功，无需恢复。

## 8. 常用排障命令

实时查看某次任务日志：

```powershell
Get-Content .\results\<Session>\mission_console.log -Wait
Get-Content .\results\<Session>\detected_classes\perception.log -Wait
Get-Content .\results\<Session>\detected_classes\perception_error.log -Wait
```

检查 WSL 后端日志：

```powershell
wsl -d Ubuntu-22.04 -u hw -- tail -f /home/hw/logs/px4.log
wsl -d Ubuntu-22.04 -u hw -- tail -f /home/hw/logs/lesson4.log
wsl -d Ubuntu-22.04 -u hw -- tail -f /home/hw/logs/agent.log
```

如果成果已存在但 manifest 未完成，可在“成果浏览”选择该 Session 后点“修复未完成
归档”。恢复逻辑只在日志证明确有 `MISSION DONE` 且已解除锁定时标记 completed，
不会伪造闭环。

## 9. 验证清单

- 完整自动测试：`79 passed, 2 skipped`；
- 发布 EXE `--smoke-test`：exit 0；
- UE4/AirSim RGB/Depth：通过；
- PX4/XRCE/ROS2/深度/OctoMap 动态自检：全部必需项通过；
- 实际短航线、返航、LAND、disarm、MISSION DONE：通过；
- YOLO 带框实时页与分类证据：通过；
- 3D 点云、语义标签、离线回放和四格式导出：通过。
