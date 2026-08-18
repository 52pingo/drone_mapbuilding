# Drone Mapbuilding：无人机自主避障、三维建图与视觉感知

本项目把 PX4 SITL、AirSim/UE4、ROS2、VFH+、OctoMap 和 YOLO 串成一条可复现的
仿真工作流：无人机从安全出生点起飞，按航点飞行，以深度图实时避障并构建三维
占用地图，同时识别场景物品、保存带框证据，最后返航、降落、解除锁定并输出
`MISSION DONE`。

当前仓库保存已经实际运行的 ROS2 包、Windows/WSL 编排脚本、视觉训练与推理代码、
测试和配置示例。UE4 工程、PX4/AirSim 第三方源码、数据集、运行结果和模型权重不在
仓库内。

## 已验证能力

- PX4 Offboard 多航点任务和完整状态机。
- 基于前视深度的 VFH+ 局部避障，含转向、倒车、阻塞恢复和可选 A* 子目标。
- AirSim 深度图 → PointCloud2 → OctoMap → RViz/PNG。
- YOLO 27 类统一语义模型的训练、AirSim 在线推理和每类场景证据归档。
- 框内深度估计，场景图包含类别、置信度和目标距离。
- QGroundControl 航点下载与本地 NED 转换（可选链路）。
- 保守降落闭环：稳定触地后才解除锁定，随后才宣布 `MISSION DONE`。

2026-08-17 的 CityPark 大环线任务已完整成功：4 个航点全部到达，最终位置约
`(-0.4, -0.0)`，任务约 756 秒完成；生成轨迹、OctoMap、RViz 深度图，并从
314 帧中保存 74 张语义场景图，覆盖 tree、fence、shrub、building、
playground_equipment 和 pole。详细记录见
[docs/VALIDATION_2026-08-17.md](docs/VALIDATION_2026-08-17.md)。

## 系统架构

```text
Windows 11
├─ UE4 4.27 + CityPark + AirSim 1.8.1
│   ├─ RGB Scene (640×480)
│   └─ DepthPerspective (400×300, 32FC1)
├─ YOLO / semantic_perception.py
│   └─ detected_classes/<class>/scene_*.jpg + events.jsonl
└─ PowerShell 总控脚本
              │ AirSim RPC / WSL
WSL2 Ubuntu 22.04 + ROS2 Humble
├─ PX4 v1.15.2 SITL ⇄ MicroXRCEAgent
├─ avoid_node：航点状态机 + VFH+ + Land/Disarm 闭环
└─ depth_clamp → depth_image_proc → cloud_relay → octomap_server
```

坐标使用 PX4 本地 NED：`x=North`、`y=East`、`z=Down`。因此飞行高度为负值，
例如 `flight_z=-15` 表示离起飞参考面约 15 米。

## 仓库结构

```text
config/
  airsim_settings.citypark.example.json  CityPark 安全出生点与相机示例
docs/
  VALIDATION_2026-08-17.md                全链路验收记录
  QT_GUI_PLAN.md                          Qt 桌面封装方案
ros2_ws/src/hw_insight/
  hw_insight/avoid_node.py                任务主节点
  hw_insight/avoid_vfh.py                 ROS 无关的 VFH+ 核心
  hw_insight/avoid_planner.py             可选 2D 栅格 A*
  hw_insight/mission_safety.py             降落/解锁安全判定
  hw_insight/qgc_mission_runner.py         QGC 任务桥
  launch/lesson4.launch.py                深度、点云、OctoMap、RViz 链路
scripts/
  launch_ue4.ps1                          启动 CityPark 并验证公制深度
  restart_stack.sh                        重启 PX4、DDS Agent、ROS2
  run_citypark_semantic_mission.ps1       完整任务总入口
  run_citypark_loop_inner.sh              WSL 内层任务与成果导出
  semantic_perception.py                  在线 YOLO + 每类证据
  build_uav_semantic_dataset.py           合并/映射训练集
  collect_citypark_semantic_dataset.py    AirSim 分割标签采集
  train_uav_semantic.py                   Ultralytics 训练入口
drone_gui/                                PySide6 桌面工作站（M3 实时感知）
tests/                                    VFH 与语义证据测试
```

## 运行环境

已验证组合如下。其他版本可能可用，但应重新执行全链路验收。

| 组件 | 已验证版本/配置 |
|---|---|
| Windows / WSL | Windows 11 / Ubuntu-22.04 |
| UE / AirSim | UE4.27 / AirSim 1.8.1 |
| 飞控 | PX4 v1.15.2 SITL，`none_iris` |
| ROS | ROS2 Humble，Python 3.10.12 |
| 桥 | MicroXRCEAgent UDP 8888 |
| 视觉环境 | Python 3.8.20，Ultralytics 8.4.37 |
| GPU 环境 | PyTorch 2.4.1 + CUDA 12.4（本机验证） |

ROS2 工作区还需包含兼容版本的：

- `px4_msgs`、`px4_ros_com`；
- `airsim_ros_pkgs`、`airsim_interfaces`；
- 项目原工作区使用的 `hw_interface`；
- 系统包 `depth_image_proc`、`octomap_server`、`rviz2`。

示例安装系统包：

```bash
sudo apt update
sudo apt install ros-humble-depth-image-proc \
  ros-humble-octomap-server ros-humble-rviz2 \
  python3-numpy python3-opencv python3-matplotlib
```

## 首次安装

### 1. 克隆并安装 ROS2 包

建议把 ROS2 源码放在 WSL 的 ext4 文件系统中，不直接在 `/mnt/<drive>` 上编译。

```bash
git clone https://github.com/52pingo/drone_mapbuilding.git
mkdir -p ~/hw-ros2/ros2/src
cp -a drone_mapbuilding/ros2_ws/src/hw_insight ~/hw-ros2/ros2/src/
cd ~/hw-ros2/ros2
source /opt/ros/humble/setup.bash
colcon build --packages-select hw_insight
```

### 2. 配置 AirSim

把 `config/airsim_settings.citypark.example.json` 复制为 Windows 的
`Documents/AirSim/settings.json`，再按自己的端口和路径调整。示例中的出生点
`X=-134.09, Y=258.15, Z=-1.50` 已避开湖面；相机 `CameraDepth` 同时提供 RGB
Scene 和 DepthPerspective。

`launch_ue4.ps1` 会在运行时删除 CityPark 的 `PostProcessVolumeMAIN`，因为该
后处理体会把浮点深度截断到 `[0,1]`。此操作只影响当前运行实例，不修改 `.umap`，
并且脚本会在启动 ROS 前验证公制深度。

### 3. 建立视觉环境

先按显卡和 CUDA 安装对应的 PyTorch，再安装其余依赖：

```powershell
conda create -n deeplearning python=3.8 -y
conda activate deeplearning
# 先安装与你的 CUDA 匹配的 torch/torchvision
pip install -r requirements-perception.txt
```

还需让该环境能导入 AirSim PythonClient。可以在 AirSim `PythonClient` 目录执行
`pip install -e .`，也可以在启动参数中传入 `-AirSimClientPath`。

### 4. 放置视觉权重

把训练得到的权重放在仓库根目录并命名为 `best.pt`，或运行任务时通过
`-Weights` 指定。当前已验证权重为 262,366,363 字节，SHA-256：

```text
2f3259e64d92d96411d24287e8e77c23957ce0ca39d9697d9ee5e261d8ad7094
```

权重超过 GitHub 普通 Git 的 100 MiB 限制，故未提交；`.gitignore` 也会阻止误传。

## 完整 CityPark 任务操作手册

以下命令在仓库根目录的 Windows PowerShell 中执行。

### 步骤 1：启动 UE4 并验证深度

```powershell
.\scripts\launch_ue4.ps1 `
  -TimeoutSeconds 300 `
  -Ue4EditorPath 'D:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe' `
  -ProjectPath 'D:\CityParkEnvironmentCollec\CityPark.uproject' `
  -Python 'C:\Users\YOUR_NAME\anaconda3\envs\deeplearning\python.exe' `
  -AirSimClientPath 'D:\path\to\AirSim\PythonClient'
```

成功标志包括 `UE4 ready` 和类似以下深度统计：

```text
CameraDepth verified: min=...m median=...m max=...m
```

若中位数接近 1.0 或最大值不超过 5 m，脚本会拒绝继续。

### 步骤 2：启动 PX4、DDS 与建图链路

先确保 `PX4_DIR`、`MICRO_XRCE_AGENT`、`ROS_WORKSPACE` 指向本机目录。仓库位于
Windows 盘时，可先把 Windows 路径转换为 WSL 路径：

```powershell
$repo = (Resolve-Path .).Path
$repoWsl = (wsl -d Ubuntu-22.04 -- wslpath -a $repo).Trim()
wsl -d Ubuntu-22.04 -u hw -- bash -lc `
  "ROS_WORKSPACE=/home/hw/hw-ros2/ros2 bash '$repoWsl/scripts/restart_stack.sh'"
```

默认值为：

```text
PX4_DIR=$HOME/px4v1.15.2
MICRO_XRCE_AGENT=$HOME/Micro-XRCE-DDS-Agent/build/MicroXRCEAgent
ROS_WORKSPACE=$HOME/hw-ros2/ros2
LOG_DIR=$HOME/logs
```

该脚本会清理旧节点，启动 PX4、MicroXRCEAgent 和 `lesson4.launch.py`。RViz 会随
launch 打开，并显示深度点云/OctoMap。

### 步骤 3：启动语义感知与大环线任务

```powershell
.\scripts\run_citypark_semantic_mission.ps1 `
  -Weights '.\best.pt' `
  -Python 'C:\Users\YOUR_NAME\anaconda3\envs\deeplearning\python.exe' `
  -WslDistro 'Ubuntu-22.04' `
  -WslUser 'hw' `
  -Confidence 0.25 `
  -ConfirmFrames 2 `
  -CaptureInterval 4.0 `
  -MaxImagesPerClass 20 `
  -FlightZ -15 `
  -MaxMissionTime 1200
```

默认航路是一次大范围绕行，没有复杂来回折线：

```text
181.55,-583.34 → -395.53,-409.16 → -159.49,25.13 → 0,0
```

可用 `-Goals 'x1,y1;x2,y2;...;0,0'` 替换。航点以当前安全出生点为本地原点；
换地图或换出生点后必须重新勘测，不能直接复用 CityPark 坐标。

### 步骤 4：检查完整闭环

不要仅根据进程结束判断成功。`mission_console.log` 应同时包含：

```text
DISARMED -> mission done
=== MISSION DONE ===
```

并确认最终遥测为落地、未解锁。脚本在任务结束后向视觉进程写停止信号，等待输出
流和 JSON 元数据落盘，再退出。

### 步骤 5：检查成果

默认目录：`results/citypark_semantic_<timestamp>/`。

```text
avoid_flight.log
mission_console.log
flight_trajectory_citypark_loop.png
octomap_map_citypark_loop.png
depth_rviz_citypark.png
detected_classes/
  summary.json
  events.jsonl
  perception.log
  tree/scene_*.jpg
  building/scene_*.jpg
  ...
```

类别目录保存完整场景的带框图片：当前重点类别为绿色框，画面中的其他类别使用
另一颜色，框文字包含置信度和可用的深度估计。

## 单独运行视觉感知

在线 AirSim：

```powershell
python .\scripts\semantic_perception.py `
  --weights .\best.pt `
  --output-dir .\results\semantic_manual `
  --confidence 0.25 `
  --confirm-frames 2 `
  --capture-interval 4 `
  --max-images-per-class 20 `
  --airsim-client 'D:\path\to\AirSim\PythonClient'
```

离线图片冒烟测试：

```powershell
python .\scripts\semantic_perception.py `
  --weights .\best.pt `
  --source-image .\sample.jpg `
  --output-dir .\results\semantic_smoke `
  --confidence 0.25 `
  --confirm-frames 1
```

## 数据集与训练

统一类别表在 `scripts/uav_semantic_schema.py`，共 27 类。构建脚本合并 Road20、
VisDrone YOLO 和 CityPark 仿真分割数据，并写出可复现的 `stats.json`。

```powershell
python .\scripts\build_uav_semantic_dataset.py `
  --road20-root 'E:\path\to\Road20' `
  --visdrone-root 'E:\path\to\visdrone_yolo' `
  --citypark-root '.\datasets\raw\citypark_semantic_v1' `
  --output-dir '.\datasets\uav_semantic_v1'

python .\scripts\train_uav_semantic.py `
  --weights .\yolov8l.pt `
  --data .\datasets\uav_semantic_v1\data.yaml `
  --name uav_semantic_v1 `
  --epochs 80 `
  --batch 16 `
  --imgsz 640 `
  --workers 8 `
  --skip-amp-check
```

当前 `best.pt` 足以支持已验证的 CityPark 演示，但不能据此宣称 27 类都达到生产级
精度。车辆、行人和稀有类别仍需按类统计独立测试集的 precision、recall 和 AP，
并用包含这些物体的航路做在线验收。几何避障必须继续以深度/VFH 为安全主链，
YOLO 用于语义解释和成果标注。

## 测试

纯算法与视觉证据测试可在仓库根目录运行：

```powershell
python -m pytest tests\test_vfh.py tests\test_semantic_perception.py -q
```

ROS2 包测试：

```bash
cd ~/hw-ros2/ros2
source /opt/ros/humble/setup.bash
source install/setup.bash
colcon test --packages-select hw_insight
colcon test-result --verbose
```

建议在修改任务状态机、降落逻辑、深度话题、VFH 参数或坐标系后重新跑一次完整
CityPark 闭环，而不仅是单元测试。

## 常见问题

### RViz 没有深度/点云

依次检查：

1. AirSim `CameraDepth` 是否同时配置 ImageType 2 和正确分辨率；
2. `prepare_citypark_runtime.py` 的深度统计是否正常；
3. `/depth/clamped` 是否有 `32FC1` 数据；
4. `depth_image_proc` 的 `camera_info` remap 是否正确；
5. `/depth/points` 为 BEST_EFFORT，而 OctoMap 默认 RELIABLE，必须经过
   `cloud_relay`；
6. 读取已发布的 OctoMap 点云需使用 TRANSIENT_LOCAL QoS。

足球场等平地区域深度图信息少是场景本身缺少障碍物，不等于传感器失效；应结合
深度统计和不同视角判断。

### 无法起飞或出生在湖中

确认加载的是本仓库 CityPark 示例中的出生点，并重启 UE4 与整套 WSL 栈。AirSim
reset 服务在当前组合中并不可靠，重启能同时清理 EKF 原点和 OctoMap。

### 任务结束但未看到 MISSION DONE

查看 `mission_console.log` 中的 LAND 阶段、地面高度、垂直速度和 armed 状态。
安全逻辑不会在空中强制 disarm；若未稳定触地，应修复降落/地面检测，不要绕过条件。

### 视觉有框但没有保存图片

检查 `confidence`、`confirm_frames`、`capture_interval` 和
`max_images_per_class`。类别必须连续出现指定帧数，且同类保存受时间间隔和数量上限
控制。错误详情在 `detected_classes/perception_error.log`。

## Qt GUI（M3 实时感知已接入）

当前已实现可运行的 M1–M3 桌面工作站：

- 深色工业控制风格主窗口、键盘可达的四页导航和统一状态栏；
- UE4、工程、视觉 Python、AirSim Client、权重、WSL 和成果目录本地自检；
- 使用 `QProcess` 异步启动 UE4、PX4/ROS2 堆栈和完整语义任务，实时汇总日志；
- WSL 动态检查 PX4、Micro XRCE-DDS、AirSim ROS、位置遥测、深度和 OctoMap 话题；
- NED 航点画布：双击添加、滚轮缩放、拖动画布、表格精确编辑、排序和返航点；
- 航线距离、预计用时和安全参数校验，航线 JSON 保存/加载；
- `GUI_STATUS` 结构化飞行状态、位置、armed 状态、最近障碍和任务耗时；
- 感知进程以原子 JPEG + JSON 快照发布 AirSim RGB、YOLO 检测框、置信度、目标
  深度、滚动 FPS 和当前分辨率，不会用大体积图像阻塞控制台或 Qt 主线程；
- 实时页显示完整带框画面、本帧目标、累计确认类别、证据数量和每类首次发现截图；
- 视觉流超过 3 秒未更新时明确显示断流告警，任务结束后保留最后一帧供复核；
- Hold、Resume 和二次确认的安全 Land；Hold 仅在导航/扫描阶段可用，Land 复用原有
  接地稳定判定与普通 disarm 闭环，不提供空中强制解除锁定；
- 实时感知页面的数据接口，以及已有类别图片、深度图、轨迹图、OctoMap 浏览；
- 只有日志明确出现 `MISSION DONE` 才把任务标记为闭环完成；关闭 GUI 不会强杀飞行任务。

建立并启动独立环境：

```powershell
py -3.11 -m venv .venv-gui
.\.venv-gui\Scripts\python.exe -m pip install `
  --index-url https://pypi.org/simple -r requirements-gui.txt
Copy-Item .\config\gui_config.example.json .\config\gui_config.json
# 按本机实际路径修改 gui_config.json
.\scripts\start_gui.bat
```

也可以直接执行：

```powershell
.\.venv-gui\Scripts\python.exe -m drone_gui
```

GUI 测试和无界面启动检查：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$guiTests = Get-ChildItem .\tests\test_gui_*.py | Select-Object -Expand FullName
.\.venv-gui\Scripts\python.exe -m pytest $guiTests -q
.\scripts\start_gui.bat -SmokeTest
```

“系统与自检”中的“本地 + WSL 动态检查”必须完成且所有必需组件通过，GUI 才允许
开始任务。任务运行时，ROS2 提供以下 `std_srvs/Trigger` 服务：

```text
/hw_insight/mission/hold
/hw_insight/mission/resume
/hw_insight/mission/land
```

每个任务的实时交换文件位于 `live_feed/`。带框 JPEG 使用轮转文件名并只保留最近
三帧，`latest.json` 最后原子提交，因此 GUI 不会读到半写入图片；正式的类别证据仍
完整保存在 `detected_classes/<class>/` 下。可通过 `gui_config.json` 中的
`perception_interval` 调整采样间隔，默认 `0.20 s`。

M3 已使用本地 `best.pt` 完成真实图片推理、带框帧、类别 JSON 和首次证据界面验证。
三维页面尚未实现实时点云渲染，属于 M4；M2/M3 仍需在 UE4/PX4 全链路运行时完成
一次 GUI 大环线飞行与持续 RGB 流现场验收。

### 后续规划

桌面封装的功能架构、三维语义融合、页面规划、技术选型、阶段划分和验收指标见
[docs/QT_GUI_PLAN.md](docs/QT_GUI_PLAN.md)。核心原则是让 GUI 负责规划、可视化和
编排，让 WSL 后端继续负责 ROS2/飞控与地图数据；语义标签通过深度反投影进入三维
世界坐标，但飞行安全仍由深度/VFH 保证。
