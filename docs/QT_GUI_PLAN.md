# Qt 无人机避障建图工作站：功能与实施方案

> 实施状态（2026-08-18）：M1–M4 已实现，完成 PySide6 主窗口、本地/WSL 动态
> 自检、NED 航点编辑、结构化飞行遥测、Hold/Resume/Safe Land，以及 AirSim RGB、
> YOLO 框、类别证据和首次发现截图的实时共享文件协议。已用 `best.pt` 做真实图片
> 端到端验证；M4 已加入 OctoMap 原子快照、三维点云/轨迹、语义反投影与稳定标签、
> PLY/JSON/PNG 导出和离线 Session。GUI 大环线与真实连续点云仍是现场验收项。

## 1. 产品目标

把现有 PowerShell、WSL/ROS2、AirSim、PX4、VFH、OctoMap 和 YOLO
链路封装成一个 Windows 桌面工作站。操作者可以在同一软件内完成环境自检、
航点规划、任务执行、实时监控、视觉目标查看、三维语义地图导出和任务回放。

首版建议采用 **PySide6**。当前算法、训练和 AirSim 工具已经是 Python，
PySide6 能直接复用数据模型与测试，开发成本低于 C++ Qt；飞控与建图仍运行在
WSL/ROS2，GUI 不把 ROS2 和 CUDA 推理阻塞在界面线程中。

## 2. 建议总体架构

```text
PySide6 GUI（Windows）
  ├─ 航点编辑器 / 任务控制 / 健康检查 / 日志
  ├─ RGB + YOLO 框视图 / 类别图库
  ├─ 2D 轨迹与 3D 语义点云视图
  └─ Session 数据与导出管理
              │ 原子 JSON + JPEG/NPY（后期可升级 WebSocket）
WSL Backend（ROS2 节点或独立服务）
  ├─ Mission Manager：PX4 状态机、航点、Land/Disarm 闭环
  ├─ Map Bridge：PointCloud2 / OctoMap 降采样与分块
  ├─ Semantic Fusion：检测框 + 深度 + 相机位姿 → 世界坐标目标
  └─ Recorder/Exporter：日志、点云、语义对象、回放索引
              │
PX4 SITL ⇄ AirSim/UE4 ⇄ 深度/RGB ⇄ VFH/OctoMap/YOLO
```

关键决定：GUI 通过一个稳定的后端协议访问 ROS2，不在 Windows GUI 进程中
直接加载 `rclpy`。这样 WSL 断开、ROS 图重启或 YOLO 推理异常时，界面仍能响应，
并能明确显示哪个组件失效。

## 3. 界面信息架构

### 3.1 主工作区

- 顶部：项目/场景/模型选择，连接状态，启动仿真、启动堆栈、开始任务。
- 左侧“任务规划”：本地 NED 坐标底图、点选航点、拖动、排序、删除；设置高度、
  巡航速度、到达半径和返航点；显示总距离、预计耗时、越界和危险航段。
- 中央可切换视图：
  - 实时 RGB 视频，叠加类别、置信度、目标深度、跟踪 ID；
  - 2D 实时轨迹和 VFH 当前选向；
  - 3D 点云/OctoMap，叠加语义目标标签和无人机位姿。
- 右侧“感知与任务”：当前阶段、航点进度、PX4 armed/nav 状态、最小障碍距离、
  检出类别列表、类别筛选和首次发现缩略图。
- 底部：分级日志、告警、任务计时，以及 Hold、继续、返航/降落按钮。

### 3.2 独立页面

- 启动与自检：UE4 RPC、深度统计、PX4、DDS Agent、ROS 话题、OctoMap、GPU、
  权重哈希逐项绿/黄/红。
- 模型与感知：选择权重，调整置信度/IoU，查看类别表和离线图片测试结果。
- 成果中心：按任务和类别浏览带框图片，导出地图、报告、日志，加载历史 Session。
- 设置：路径配置、WSL 发行版/用户、ROS 工作区、UE4 项目、AirSim 配置和安全阈值。

## 4. 必须补充的后端能力

### 4.1 任务服务化

把当前脚本编排整理成 `MissionService`，对 GUI 提供明确命令：
`preflight/start/hold/resume/land/abort/status`。每个命令包含任务 ID 和幂等语义，
避免双击“开始”启动两个控制器。只有检测到稳定着陆后才允许解除锁定并宣布
`MISSION DONE`；空中禁止普通强制 disarm。

### 4.2 实时地图桥接

M4 已订阅 `/octomap_point_cloud_centers`，使用可靠、Transient Local QoS 接收 OctoMap
占用点中心；后端把 `world_enu` 转为 `px4_local_ned`，过滤非有限值，确定性限制到
80,000 点，并以 NPY 先写、JSON 后提交的方式每秒发布快照。GUI 每 500 ms 非阻塞轮询，
保留断流和无数据状态。首版使用 `pyqtgraph.opengl.GLViewWidget`；点数和交互需求提高后
再增加体素/范围裁剪或切换 PyVista/VTK。

### 4.3 三维语义融合

M4 首版已经打通以下数据链：

1. 取检测框中心的有效 `DepthPerspective`，结合相机水平 FOV 构造投影射线。
2. 使用 AirSim 同帧返回的相机位置和四元数转换到 PX4 本地 NED。
3. 按类别与 4 m 空间距离合并重复观察，生成稳定对象 ID 和观测次数。
4. 为每个语义对象保存 `label/max_confidence/position_ned/id/observations`，并明确标记
   当前中心点估计为近似值。
5. 渲染时用类别颜色、三维锚点和随相机移动的 Qt 标签叠加到占用点云。

后续精度升级项是框内多像素鲁棒质心、三维包围盒和更严格的数据关联；它们不阻塞
当前 M4 演示和结果导出。

安全避障仍使用深度/VFH；YOLO 语义只用于解释、筛选和成果标注，不能替代几何
避障。这样即使视觉漏检，飞行安全链路仍然工作。

### 4.4 Session 与导出

每次任务采用不可覆盖的 Session 目录：

```text
sessions/<timestamp>_<mission>/
  manifest.json
  mission.json
  telemetry.csv
  detections.jsonl
  semantic_objects.json
  map.bt
  map.pcd
  semantic_map.ply
  screenshots/<class>/*.jpg
  report.html
```

导出至少支持：OctoMap `.bt/.ot`、点云 `.pcd/.ply`、语义对象 `.json`、
俯视图/三维截图 `.png`、任务报告 `.html`。导出前写入坐标系、单位、起飞原点、
模型哈希和参数，保证成果可复现。

## 5. 安全与交互约束

- “开始任务”前必须通过深度有效性、遥测、GPS/本地位置、模型和输出目录检查。
- `Land` 始终可见；紧急停止采用长按或二次确认，且与普通 abort 分开。
- UI 所有长任务使用 `QProcess/QThreadPool` 或异步 I/O，主线程只绘制。
- 后端心跳超时后界面进入失联态，不把“未知”显示为“已停止”。
- 航点规划提供高度、最大距离、地理围栏、返航点和预计电量/时长校验。
- 任务状态和 PX4 armed 状态以遥测为准，不能仅根据子进程退出码推断。

## 6. 技术选型

| 层 | 首选 | 说明 |
|---|---|---|
| 桌面 GUI | PySide6 + Qt Designer | Python 复用度高，许可证和部署友好 |
| 2D 规划/轨迹 | QGraphicsView + pyqtgraph | 本地 NED 坐标比在线地图更适合当前仿真 |
| 3D 点云 | pyqtgraph.opengl；后期 PyVistaQt/VTK | 先快速实现，再按点量升级 |
| 视频与框 | QGraphicsView/QImage | GUI 端可选择类别并查看框元数据 |
| GUI↔WSL | 原子 JSON + JPEG/NPY；后期 WebSocket | 当前链路易调试、跨 Windows/WSL、可离线重开 |
| 配置 | Pydantic + YAML/JSON | 路径、场景、任务和安全参数可校验 |
| 打包 | PyInstaller | 首版生成 Windows 可执行目录 |
| 测试 | pytest + pytest-qt | 覆盖状态机、协议、导出和界面响应 |

## 7. 实施阶段与验收点

### M1：项目骨架与自检（3–4 天）

状态：已完成。

- PySide6 主窗口、配置持久化、进程管理、后端心跳。
- 一键启动 UE4/WSL 堆栈，逐项显示自检结果。
- 验收：任何依赖缺失都有明确诊断，GUI 不冻结、不重复启动控制器。

### M2：航点规划与任务控制（4–6 天）

状态：控制面、ROS2 服务和自动化测试已完成；等待完整仿真实飞验收。

- 2D 点选/拖动/排序，参数校验，保存/加载任务。
- Start/Hold/Resume/Land 与实时任务状态、轨迹。
- 验收：从 GUI 完成大环线，并以 landed + disarmed 作为完成条件。

### M3：实时视觉与类别成果（4–6 天）

状态：实时协议、Qt 画面、类别统计、首次证据和断流提示已完成；等待完整仿真持续流
与飞行验收。

- RGB 流、YOLO 框、深度、类别筛选、首次发现和类别图库。
- 验收：视频目标 5–10 FPS，界面无阻塞；结果目录与界面计数一致。

### M4：实时 3D 语义地图（7–10 天）

状态：功能实现与自动化验证完成；已在 Windows OpenGL 下验证 24,300 点、5 个三维
语义标签和 PLY/JSON 导出，等待完整 UE4/PX4 大环线现场验收。

- 点云增量显示、无人机位姿、语义反投影/聚类、3D 标签。
- 验收：关闭/开启类别可筛选点云标签；同一静态物体不会随每帧无限复制。

### M5：导出、回放与交付（4–6 天）

- 状态：M4 已提前完成 PLY/JSON/PNG 和当前快照离线打开；PCD/BT/HTML、完整遥测回放、
  异常恢复和 PyInstaller 打包仍待实现。
- PCD/PLY/BT/JSON/PNG/HTML 导出、Session 回放、异常恢复、打包。
- 验收：导出的 Session 可在无 UE4/ROS 环境中重新打开并查看。

单人开发预计 4–6 周得到可演示且可持续迭代的首版。建议优先完成 M1–M3，
先交付“能规划、能飞、能看框、能安全结束”的版本，再加入三维语义融合；
M4 是技术风险和价值最高的部分，应单独做数据正确性验收。
