# Drone Mapbuilding：无人机自主避障、三维建图与视觉感知

这个仓库做的是仿真环境里的无人机自主飞行：PX4 SITL 当飞控，AirSim/UE4 出场景和深度，ROS2 负责节点通信，VFH+ 管局部避障，OctoMap 建三维占用图，YOLO 做语义识别。无人机从安全出生点起飞，按航点走，靠前视深度实时绕障，一边飞一边建图，把识别到的物体连框带距离存下来，最后返航、降落、解除锁定，控制台打出 `MISSION DONE`。

仓库里放的是已经实际跑过的 ROS2 包、Windows/WSL 编排脚本、视觉训练与推理代码、测试和配置示例。UE4 工程、PX4/AirSim 第三方源码、数据集、运行结果和模型权重不在仓库里，需要自己准备。

## 已验证能力

- PX4 Offboard 多航点任务，带完整状态机。
- 前视深度的 VFH+ 局部避障。转向、倒车、阻塞恢复都有，A* 子目标是可选项。
- AirSim 深度图 → PointCloud2 → OctoMap → RViz/PNG 这条链路。
- YOLO 27 类统一语义模型的训练、AirSim 在线推理、每类场景证据归档。
- 框内深度估计，场景图里带类别、置信度和目标距离。
- QGroundControl 航点下载和本地 NED 转换（这条链路是可选的）。
- 降落闭环做得比较保守：稳定触地之后才解除锁定，解除锁定之后才宣布 `MISSION DONE`。

2026-08-17 的 CityPark 大环线任务完整跑通过一次。4 个航点全部到达，最终位置约 `(-0.4, -0.0)`，任务约 756 秒完成。生成的东西包括轨迹、OctoMap、RViz 深度图，另外从 314 帧里保存了 74 张语义场景图，覆盖 tree、fence、shrub、building、playground_equipment 和 pole。详细记录在 [docs/VALIDATION_2026-08-17.md](docs/VALIDATION_2026-08-17.md)。

2026-08-19 又从打包版 Windows EXE 实际跑通一条 60 m 短航线。UE4/AirSim、PX4/ROS2、深度、OctoMap、YOLO、返航、LAND、解除锁定、`MISSION DONE`、Session 回放和地图导出全部通过。逐步操作与排障记录见 [docs/EXE_END_TO_END_2026-08-19.md](docs/EXE_END_TO_END_2026-08-19.md)。

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

坐标用的是 PX4 本地 NED：`x=North`、`y=East`、`z=Down`。所以飞行高度是负的。比如 `flight_z=-15` 表示离起飞参考面约 15 米，别看到负号以为搞错了。

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
drone_gui/                                PySide6 桌面工作站（M5 归档与回放）
tests/                                    VFH 与语义证据测试
```

## 运行环境

下面这套组合是实测过的。其他版本大概率也能跑，但换版本之后建议重新做一遍全链路验收，别直接信。

| 组件 | 已验证版本/配置 |
|---|---|
| Windows / WSL | Windows 11 / Ubuntu-22.04 |
| UE / AirSim | UE4.27 / AirSim 1.8.1 |
| 飞控 | PX4 v1.15.2 SITL，`none_iris` |
| ROS | ROS2 Humble，Python 3.10.12 |
| 桥 | MicroXRCEAgent UDP 8888 |
| 视觉环境 | Python 3.8.20，Ultralytics 8.4.37 |
| GPU 环境 | PyTorch 2.4.1 + CUDA 12.4（本机验证） |

ROS2 工作区还需要有兼容版本的这几个东西：

- `px4_msgs`、`px4_ros_com`；
- `airsim_ros_pkgs`、`airsim_interfaces`；
- 项目原工作区使用的 `hw_interface`；
- 系统包 `depth_image_proc`、`octomap_server`、`rviz2`。

系统包可以这样装：

```bash
sudo apt update
sudo apt install ros-humble-depth-image-proc \
  ros-humble-octomap-server ros-humble-rviz2 \
  python3-numpy python3-opencv python3-matplotlib
```

## 首次安装

### 1. 克隆并安装 ROS2 包

ROS2 源码建议放在 WSL 的 ext4 文件系统里，别直接在 `/mnt/<drive>` 上编译——慢，而且 colcon 有时候会出奇怪的问题。

```bash
git clone https://github.com/52pingo/drone_mapbuilding.git
mkdir -p ~/hw-ros2/ros2/src
cp -a drone_mapbuilding/ros2_ws/src/hw_insight ~/hw-ros2/ros2/src/
cd ~/hw-ros2/ros2
source /opt/ros/humble/setup.bash
colcon build --packages-select hw_insight
```

### 2. 配置 AirSim

把 `config/airsim_settings.citypark.example.json` 复制成 Windows 的 `Documents/AirSim/settings.json`，然后按自己的端口和路径改。示例里的出生点 `X=-134.09, Y=258.15, Z=-1.50` 是特意挑的，避开了湖面；相机 `CameraDepth` 同时提供 RGB Scene 和 DepthPerspective。

`launch_ue4.ps1` 在运行时会删掉 CityPark 的 `PostProcessVolumeMAIN`。这个后处理体会把浮点深度截断到 `[0,1]`，不删的话深度全是 0 到 1 之间的数，点云直接废掉。删的是当前运行实例，不动 `.umap`。脚本会在启动 ROS 之前验证公制深度，通不过就不往下走。

### 3. 建立视觉环境

先按显卡和 CUDA 装对应的 PyTorch，再装剩下的：

```powershell
conda create -n deeplearning python=3.8 -y
conda activate deeplearning
# 先安装与你的 CUDA 匹配的 torch/torchvision
pip install -r requirements-perception.txt
```

这个环境还得能 import AirSim PythonClient。要么去 AirSim 的 `PythonClient` 目录跑 `pip install -e .`，要么启动参数里传 `-AirSimClientPath`。AirSim 1.8.1 的 `msgpack-rpc-python`/Tornado 4 是旧依赖，仓库里的兼容导入器会在非 TLS 本地 RPC 导入阶段绕开 Windows 的异常证书，并依次找仓库内和仓库上级的 `.tools/airsim_rpc`。所以正常装 PythonClient 也行，把离线依赖丢到那个目录也行。

### 4. 放置视觉权重

训练出来的权重放仓库根目录，命名 `best.pt`，或者运行时用 `-Weights` 指过去。当前验证过的权重是 262,366,363 字节，SHA-256：

```text
2f3259e64d92d96411d24287e8e77c23957ce0ca39d9697d9ee5e261d8ad7094
```

权重超过 GitHub 普通 Git 的 100 MiB 限制，所以没提交；`.gitignore` 也会拦住误传。

## 完整 CityPark 任务操作手册

下面命令都在仓库根目录的 Windows PowerShell 里跑。

### 步骤 1：启动 UE4 并验证深度

```powershell
.\scripts\launch_ue4.ps1 `
  -TimeoutSeconds 300 `
  -Ue4EditorPath 'D:\UE_4.27\Engine\Binaries\Win64\UE4Editor.exe' `
  -ProjectPath 'D:\CityParkEnvironmentCollec\CityPark.uproject' `
  -Python 'C:\Users\YOUR_NAME\anaconda3\envs\deeplearning\python.exe' `
  -AirSimClientPath 'D:\path\to\AirSim\PythonClient'
```

成功的标志是出现 `UE4 ready`，以及类似这样的深度统计：

```text
CameraDepth verified: min=...m median=...m max=...m
```

如果中位数接近 1.0，或者最大值不超过 5 m，脚本会拒绝继续。这种情况一般是后处理体没删干净。

### 步骤 2：启动 PX4、DDS 与建图链路

先确认 `PX4_DIR`、`MICRO_XRCE_AGENT`、`ROS_WORKSPACE` 指向本机目录。仓库在 Windows 盘上的话，先把 Windows 路径转成 WSL 路径：

```powershell
$repo = (Resolve-Path .).Path
$repoWsl = (wsl -d Ubuntu-22.04 -- wslpath -a $repo).Trim()
wsl -d Ubuntu-22.04 -u hw -- bash -lc `
  "ROS_WORKSPACE=/home/hw/hw-ros2/ros2 bash '$repoWsl/scripts/restart_stack.sh'"
```

默认值是：

```text
PX4_DIR=$HOME/px4v1.15.2
MICRO_XRCE_AGENT=$HOME/Micro-XRCE-DDS-Agent/build/MicroXRCEAgent
ROS_WORKSPACE=$HOME/hw-ros2/ros2
LOG_DIR=$HOME/logs
```

脚本会先清掉旧节点，再启动 PX4、MicroXRCEAgent 和 `lesson4.launch.py`。RViz 会跟着 launch 打开，显示深度点云/OctoMap。

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

默认航路是一次大范围绕行，没有复杂的来回折线：

```text
181.55,-583.34 → -395.53,-409.16 → -159.49,25.13 → 0,0
```

想换航点用 `-Goals 'x1,y1;x2,y2;...;0,0'`。航点是以当前安全出生点为本地原点的，换地图或者换出生点之后必须重新勘测，不能直接把 CityPark 坐标搬过去用。

### 步骤 4：检查完整闭环

别只看进程退没退出。`mission_console.log` 里得同时有：

```text
DISARMED -> mission done
=== MISSION DONE ===
```

再确认最终遥测是落地、未解锁。任务结束后脚本会给视觉进程写停止信号，等输出流和 JSON 元数据落盘，然后才退出。

### 步骤 5：检查成果

默认目录：`results/citypark_semantic_<timestamp>/`。

```text
avoid_flight.log
mission_console.log
flight_trajectory_citypark_loop.png
octomap_map_citypark_loop.png
depth_rviz_citypark.png
live_map/
  latest.json
  points_*.npy
live_feed/
  latest.json
  frame_*.jpg
detected_classes/
  summary.json
  events.jsonl
  semantic_objects.json
  perception.log
  tree/scene_*.jpg
  building/scene_*.jpg
  ...
semantic_map.ply              # GUI 结束任务或手动导出后生成
semantic_objects.json         # GUI 导出的三维语义对象
semantic_map_view.png         # 手动导出当前三维视角时生成
```

类别目录里存的是完整场景的带框图片：当前重点类别用绿框，画面里其他类别用另一种颜色，框上的文字包含置信度和可用的深度估计。

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

统一类别表在 `scripts/uav_semantic_schema.py`，一共 27 类。构建脚本会合并 Road20、VisDrone YOLO 和 CityPark 仿真分割数据，写出可复现的 `stats.json`。

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

当前的 `best.pt` 够支撑已验证的 CityPark 演示，但别据此说 27 类都到生产级精度了。车辆、行人和稀有类别还得按类统计独立测试集的 precision、recall 和 AP，再用包含这些物体的航路做在线验收。几何避障这一层必须继续以深度/VFH 为安全主链，YOLO 只负责语义解释和成果标注。

## 测试

纯算法和视觉证据测试可以在仓库根目录跑：

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

改过任务状态机、降落逻辑、深度话题、VFH 参数或者坐标系之后，建议重跑一遍完整 CityPark 闭环，别只跑单元测试就完事。

## 常见问题

### RViz 没有深度/点云

按顺序查：

1. AirSim `CameraDepth` 是不是同时配了 ImageType 2 和正确分辨率；
2. `prepare_citypark_runtime.py` 的深度统计正不正常；
3. `/depth/clamped` 里有没有 `32FC1` 数据；
4. `depth_image_proc` 的 `camera_info` remap 对不对；
5. `/depth/points` 是 BEST_EFFORT，OctoMap 默认 RELIABLE，必须过 `cloud_relay`；
6. 读已发布的 OctoMap 点云得用 TRANSIENT_LOCAL QoS。

足球场这类平地区域深度图信息少，是场景本身没障碍物，不等于传感器坏了。结合深度统计和不同视角一起判断。

### 无法起飞或出生在湖中

确认加载的是本仓库 CityPark 示例里的出生点，然后重启 UE4 和整套 WSL 栈。AirSim 的 reset 服务在当前组合里不太可靠，重启能顺便清掉 EKF 原点和 OctoMap。

### 任务结束但未看到 MISSION DONE

去看 `mission_console.log` 里的 LAND 阶段、地面高度、垂直速度和 armed 状态。安全逻辑不会在空中强制 disarm；要是没稳定触地，就修降落/地面检测，别绕过条件。

### 视觉有框但没有保存图片

检查 `confidence`、`confirm_frames`、`capture_interval` 和 `max_images_per_class`。类别得连续出现指定帧数，同类保存还受时间间隔和数量上限控制。错误详情在 `detected_classes/perception_error.log`。

## Qt GUI（M6 多仿真环境与一键配置已接入）

当前已实现可运行的 M1–M6 桌面工作站：

- 深色工业控制风格主窗口、键盘可达的五页导航和统一状态栏；
- “环境配置”能选任意接入 AirSim 的 `.uproject`，也能选已打包 UE4 仿真 `.exe`；环境名称、地图资源、载具和深度相机都能独立配置并持久化；
- UE4、工程、视觉 Python、AirSim Client、QGC、权重、WSL 和成果目录本地自检；
- UE4 窗口状态和 AirSim RPC/RGB/深度状态分开呈现，不再把 Python 依赖错误误报成“UE4 没有打开”；非 CityPark 环境用通用 RGB/DepthPerspective 验证；
- “配置能力体检”和“一键配置 / 修复”可以幂等检查或补齐 AirSim Python 依赖、AirSim ROS2 源码、ROS2 Humble、PX4 v1.15.2、Micro XRCE-DDS Agent 和 QGC；
- 用 `QProcess` 异步启动 UE4、PX4/ROS2 堆栈和完整语义任务，实时汇总日志；
- WSL 动态检查 PX4、Micro XRCE-DDS、AirSim ROS、位置遥测、深度和 OctoMap 话题；
- NED 航点画布：双击添加、滚轮缩放、拖动画布、表格精确编辑、排序和返航点；
- 航线距离、预计用时和安全参数校验，航线 JSON 保存/加载；
- `GUI_STATUS` 结构化飞行状态、位置、armed 状态、最近障碍和任务耗时；
- 感知进程以原子 JPEG + JSON 快照发布 AirSim RGB、YOLO 检测框、置信度、目标深度、滚动 FPS 和当前分辨率，不会用大体积图像阻塞控制台或 Qt 主线程；
- 实时页显示完整带框画面、本帧目标、累计确认类别、证据数量和每类首次发现截图；
- 视觉流超过 3 秒没更新会明确显示断流告警，任务结束后保留最后一帧供复核；
- WSL 地图桥接订阅 `/octomap_point_cloud_centers`，先转换 `world_enu` 轴，再从 TF 自动读 `world_ned -> PX4` 出生点平移并转成 PX4 本地 NED；按 1 Hz 限流、最多 80,000 点降采样并原子发布 NPY + JSON 快照；
- 三维页实时显示占用点云、无人机轨迹和当前位置，支持鼠标旋转/缩放、适配地图、俯视、图层开关和点大小控制；
- YOLO 框中心结合 `DepthPerspective`、相机 FOV、同步相机位置和姿态反投影到 NED，同类近邻观测合并成稳定对象 ID，并以彩色三维标签叠加到地图；
- 一键导出 `semantic_map.ply`、`semantic_map.pcd`、`semantic_objects.json` 和当前三维视图 PNG；任务结束时自动归档，也能用 `--session-dir` 在没有 UE4/ROS 的情况下打开已有快照；
- 每次任务写入 `manifest.json`、`mission.json`、模型 SHA-256、遥测 JSONL/CSV、成果哈希清单和无需网络的 `report.html`；OctoMap 同时保存 BT；
- 成果中心能直接把任意 Session 打开到三维页，播放/暂停、拖动时间轴并以 0.5×–8× 回放完整遥测轨迹；旧版 `avoid_flight.log` 也能恢复；
- 未完成或旧版归档可在后台线程修复，界面不会冻结；只有 `DONE + disarmed` 才会标记为 `completed`，否则保留为 `incomplete/interrupted/failed`；
- Hold、Resume 和二次确认的安全 Land；Hold 只在导航/扫描阶段可用，Land 复用原有接地稳定判定与普通 disarm 闭环，不提供空中强制解除锁定；
- 实时感知页面的数据接口，以及已有类别图片、深度图、轨迹图、OctoMap 浏览；
- 只有日志明确出现 `MISSION DONE` 才把任务标记为闭环完成；关闭 GUI 不会强杀飞行任务。

M4 的真实 CityPark 点云、坐标校准、YOLO 语义叠加和 PLY/JSON/PNG 导出验收见 [`docs/VALIDATION_2026-08-18_M4.md`](docs/VALIDATION_2026-08-18_M4.md)。M5 的 Session 恢复、遥测回放、PCD/HTML 和 Windows EXE 验收见 [`docs/VALIDATION_2026-08-18_M5.md`](docs/VALIDATION_2026-08-18_M5.md)。M6 的多环境选择、打包依赖修复和一键配置体检见 [`docs/VALIDATION_2026-08-19_M6.md`](docs/VALIDATION_2026-08-19_M6.md)。打包 EXE 的完整点击顺序、正常等待时间、成功判据和 2026-08-19 实飞验收见 [`docs/EXE_END_TO_END_2026-08-19.md`](docs/EXE_END_TO_END_2026-08-19.md)。

### 发布版首次使用（M6）

1. 解压 `DroneMapbuilding-win64.zip`，保持 `DroneMapbuilding.exe`、`_internal`、`scripts`、`config`、`ros2_ws` 和 `.tools` 的相对位置，别只复制 EXE。
2. 把 `best.pt` 放到 EXE 同目录，启动 EXE，进“环境配置”。
3. “启动方式”选 UE4 编辑器工程或已打包仿真程序；选本地工程、地图和 `AirSim/settings.json`，再检查工作流路径并点“保存并应用”。
4. 先点“配置能力体检”。缺组件就点“一键配置 / 修复”；首次装 ROS2/PX4 可能要 30–90 分钟，WSL 首次安装要求重启的话，重启后再次点击就能继续。
5. 进“系统自检”，依次启动 UE4、PX4/ROS2 并做动态检查，全部必需项通过后再进航线规划。

一键配置不会自动下载需要 Epic 账号和许可证确认的 UE4 Editor；它用的是操作者选的本地 UE4 工程，然后配置本工作流需要的 PX4、AirSim、ROS2、DDS 和 QGC。应用新的 `AirSim settings.json` 之前，脚本会把原文件存成带时间戳的备份。

建立并启动独立环境：

```powershell
py -3.11 -m venv .venv-gui
.\.venv-gui\Scripts\python.exe -m pip install `
  --index-url https://pypi.org/simple -r requirements-gui.txt
Copy-Item .\config\gui_config.example.json .\config\gui_config.json
# 按本机实际路径修改 gui_config.json
.\scripts\start_gui.bat
```

也可以直接：

```powershell
.\.venv-gui\Scripts\python.exe -m drone_gui

# 离线打开某次任务的三维地图和最后一帧感知结果
.\.venv-gui\Scripts\python.exe -m drone_gui `
  --session-dir .\results\citypark_semantic_YYYYMMDD_HHMMSS
```

GUI 测试和无界面启动检查：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$guiTests = Get-ChildItem .\tests\test_gui_*.py | Select-Object -Expand FullName
.\.venv-gui\Scripts\python.exe -m pytest $guiTests -q
.\scripts\start_gui.bat -SmokeTest
```

构建免 Python GUI 发布目录：

```powershell
.\.venv-gui\Scripts\python.exe -m pip install `
  --index-url https://pypi.org/simple -r requirements-build.txt
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_gui.ps1

# 输出：dist\DroneMapbuilding\ 和 dist\DroneMapbuilding-win64.zip
# 把 best.pt 放到 EXE 同目录；其余路径可直接在“环境配置”页选择并保存。
```

异常退出或旧版本任务可以从命令行重建 Session；这操作不会伪造闭环状态：

```powershell
.\.venv-gui\Scripts\python.exe .\scripts\session_archive.py recover `
  --root .\results\citypark_semantic_YYYYMMDD_HHMMSS
```

“系统自检”里的“本地 + WSL 动态检查”必须完成且所有必需组件通过，GUI 才允许开始任务。任务运行时，ROS2 提供这几个 `std_srvs/Trigger` 服务：

```text
/hw_insight/mission/hold
/hw_insight/mission/resume
/hw_insight/mission/land
```

每个任务的视觉交换文件在 `live_feed/`。带框 JPEG 用轮转文件名，只保留最近三帧，`latest.json` 最后原子提交，所以 GUI 不会读到半写入的图片；正式的类别证据还是完整存在 `detected_classes/<class>/` 下。采样间隔可以通过 `gui_config.json` 里的 `perception_interval` 调，默认 `0.20 s`。

地图交换文件在 `live_map/`：桥接器保留最近三个 `points_*.npy`，最后更新 `latest.json`，GUI 每 500 ms 非阻塞检查一次；超过 4 秒没有新快照会显示明确告警。坐标元数据始终声明 `px4_local_ned`，渲染和 PLY 导出时只把 Down 取反为向上高度。

M4 已完成真实 CityPark 深度、约 5 Hz OctoMap、29,651 点和 7 个三维语义标签验收。M5 用 756 秒历史完整飞行恢复了 1,524 帧回放，并实际构建、启动 Windows EXE。M6 修了发布包依赖、外部进程 DLL 隔离、重复 UE4、PX4 假阴性、启动数据等待和 Session 外部 Python 依赖问题。2026-08-19 已从打包 EXE 实际完成短航线飞行，BT、全套 Session 自动归档、173 帧回放以及 PLY/PCD/JSON/PNG 导出均已验证。

### 后续规划

桌面封装的功能架构、三维语义融合、页面规划、技术选型、阶段划分和验收指标见 [docs/QT_GUI_PLAN.md](docs/QT_GUI_PLAN.md)。核心原则是让 GUI 负责规划、可视化和编排，让 WSL 后端继续负责 ROS2/飞控与地图数据；语义标签通过深度反投影进入三维世界坐标，但飞行安全还是得靠深度/VFH 兜底。
