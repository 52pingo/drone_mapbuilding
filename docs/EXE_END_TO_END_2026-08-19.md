# Windows EXE 端到端操作与验收记录（2026-08-19）

这份东西是照着发布版 `DroneMapbuilding.exe` 亲手点了一遍留下的。飞行环境 CityPark，飞控 PX4 v1.15.2 SITL，ROS2 Humble。下面写的等待时间、判据、踩到的坑都是真跑出来的，不是照着代码推的。

## 1. 发布物位置

```text
dist/DroneMapbuilding/DroneMapbuilding.exe
dist/DroneMapbuilding-win64.zip
```

EXE 不能单独拎出来跑。`_internal/`、`scripts/`、`config/`、`ros2_ws/`、`.tools/`、`drone_gui/` 的相对位置都得在。视觉权重 `best.pt` 既没进 Git 也没进 ZIP，得在「环境配置」里手动指。

## 2. 首次配置

双击 EXE 进「环境配置」，然后：

1. 仿真启动方式二选一——UE4 编辑器工程（选 `UE4Editor.exe`、`.uproject`、地图资源），或者已经打包好的仿真 `.exe`。
2. 把视觉 Python、AirSim PythonClient、`best.pt`、成果目录、QGC 填上。
3. WSL 发行版/用户、ROS2 工作区、PX4、Micro XRCE-DDS Agent、日志目录。
4. 点「保存并应用」，再点「配置能力体检」。页面显示工作流环境通过才往下走。

本机验收用的路径贴在这，只做格式参考，换台电脑得重新选：

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

进「系统自检」，顺序别乱。

先点「本地 + WSL 动态检查」。这个时候飞控栈还没起，PX4、深度、OctoMap 显示未就绪是正常的——一开始我以为是路径配错了，翻了一圈才发现只是还没启动，跟本地路径没关系。

然后点「1  启动 UE4」。等日志出这几行：

```text
UE4 ready
AirSim RGB/depth are ready
CameraDepth verified: min=... median=... max=...m
```

CityPark 第一次启动实测大概 75 秒。按钮超时设的是 300 秒，加载阶段别手贱反复点。相同工程和地图已经在跑的话会复用实例；要是 41451 端口被别的环境占了，GUI 会直接拒绝启动，不会闷头连错场景。

再点「2  启动 PX4 / ROS2」。这个脚本不是进程起来就返回成功，得等三类真实消息：

```text
ready: PX4 telemetry
ready: metric depth
ready: OctoMap point cloud
```

最后等 GUI 自动动态复检。PX4、XRCE、AirSim ROS、位置遥测、`/depth/clamped`、`/octomap_point_cloud_centers` 全绿，才能开始任务。

## 4. 航线规划与任务启动

进「航线规划」。画布双击能加点，表格里能精确改，也能直接加载 JSON。

坐标是 PX4 Local NED——North 是 x，East 是 y，Down 是 z，所以高度必须是负数。末航点建议 `(0,0)`。

摘要显示「航线参数检查通过」之后，点「开始语义建图任务」。本次验收用的短航线：

```text
(20,0) -> (20,15) -> (0,0)
flight_z=-12 m, cruise=3 m/s, max=4 m/s, timeout=300 s
```

任务期间切到「实时感知」盯着。别关 GUI。要人工干预就只用 Hold、Resume 或安全 Land，空中别硬 disarm。

## 5. 完整闭环成功判据

「看起来落地了」或者「进程退出了」都不算成功。下面这些得同时成立：

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

进「地图与成果」。「实时 3D 地图」应该能看到点数、轨迹、语义目标和 `px4_local_ned` 坐标系。

点「导出 PLY / PCD / JSON / PNG」，确认生成：

```text
semantic_map.ply
semantic_map.pcd
semantic_objects.json
semantic_map_view.png
```

切「成果浏览」，选 Session，点「在三维地图中打开所选任务 Session」。播放按钮、时间轴、0.5x–8x 速度都能用。本次 Session 时间轴 0–172，173 帧。

每次任务还应该带上 `manifest.json`、`telemetry.jsonl/csv`、`report.html`、`octomap.bt`、`octomap_map.png`、`depth_rviz.png`、`flight_trajectory.png`，以及 `detected_classes/<类别>/scene_*.jpg`。

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

最后一条修复之前，这次实飞已经跑完了。所以首次归档被误标成 `failed`——飞行证据明明是 `DONE + disarmed`，感知日志也明确是正常 stop、stderr 为空。后来通过 Session finalize 恢复成 `completed`。修完之后，后续任务会直接判成功，不用再手动恢复。

## 8. 常用排障命令

实时看某次任务日志：

```powershell
Get-Content .\results\<Session>\mission_console.log -Wait
Get-Content .\results\<Session>\detected_classes\perception.log -Wait
Get-Content .\results\<Session>\detected_classes\perception_error.log -Wait
```

WSL 后端日志：

```powershell
wsl -d Ubuntu-22.04 -u hw -- tail -f /home/hw/logs/px4.log
wsl -d Ubuntu-22.04 -u hw -- tail -f /home/hw/logs/lesson4.log
wsl -d Ubuntu-22.04 -u hw -- tail -f /home/hw/logs/agent.log
```

成果已经在、但 manifest 没写完的话，在「成果浏览」选中那个 Session，点「修复未完成归档」。恢复逻辑只在日志证明确实有 `MISSION DONE` 且已解锁时才标 completed，不会瞎编闭环。

## 9. 验证清单

- 完整自动测试：`79 passed, 2 skipped`；
- 发布 EXE `--smoke-test`：exit 0；
- UE4/AirSim RGB/Depth：通过；
- PX4/XRCE/ROS2/深度/OctoMap 动态自检：全部必需项通过；
- 实际短航线、返航、LAND、disarm、MISSION DONE：通过；
- YOLO 带框实时页与分类证据：通过；
- 3D 点云、语义标签、离线回放和四格式导出：通过。
