# M6 多仿真环境与一键配置验收（2026-08-19）

## 修复结论

旧发布包的 UE4 窗口实际能够创建，但随后使用视觉 Python 执行 CityPark 深度检查时，
打包目录没有携带 `.tools/airsim_rpc`，该 Python 又未全局安装 `msgpackrpc`，所以脚本
返回非零，GUI 将其笼统显示为“UE4 启动失败”。

M6 将窗口和 AirSim 状态拆开，并把 4.6 MB 的兼容 RPC 依赖随发布目录复制。现场使用
修复后的启动链得到：

- UE4 Editor 进程和主窗口正常创建；
- AirSim RPC `ping` 成功；
- CityPark `PostProcessVolumeMAIN` 在运行时移除；
- `CameraDepth`：min `1.756 m`、median `61.906 m`、max `16640.000 m`；
- 最终协议为 `window_ready=true, airsim_ready=true`。

最终发布目录再次执行同一启动链也通过，深度统计为 min `1.775 m`、median
`61.906 m`、max `16640.000 m`，证明修复不依赖源码目录中的兼容包。

## 新增能力

- 环境页支持 UE4 Editor 工程和已打包仿真程序两种启动方式。
- 操作者可选择任意本地 `.uproject`、地图、AirSim settings、载具和相机；航线不再
  绑定 CityPark 结果命名或环境名称。
- 通用环境会验证 AirSim RPC、Scene RGB 和 `DepthPerspective`；CityPark 保留专用
  深度修复逻辑；也可显式选择只检查窗口。
- 一键体检/配置覆盖 Windows Python/AirSim/QGC 与 WSL ROS2/PX4/XRCE/工作区。
- AirSim settings 覆盖前创建带时间戳的备份；WSL 安装需要重启时会停止并明确提示。

## 本机体检结果

只读 `check` 模式逐项返回 `pass`：

- Python 3.8 视觉环境与 AirSim PythonClient/RPC 兼容依赖；
- CityPark 工程 AirSim 插件；
- QGroundControl；
- Ubuntu 22.04 / ROS2 Humble；
- PX4 v1.15.2 SITL；
- Micro XRCE-DDS Agent；
- `/home/hw/hw-ros2/ros2` 工作区。

## 自动化与交付验证

- Windows：`78 passed, 2 skipped`。
- PowerShell 启动、配置、任务和打包脚本均通过 AST 语法检查。
- WSL shell 脚本通过 `bash -n`。
- Qt 新环境页已做真实渲染截图和可访问名称检查。
- 最终发布目录必须同时包含 `scripts`、`ros2_ws` 和 `.tools/airsim_rpc`，EXE 不能
  脱离整个目录单独复制运行。
- `DroneMapbuilding-win64.zip` 大小 `67,537,948` bytes，SHA-256：
  `384A10B40C4D1BAB26E9B3DB3D19C030E6C83B78C7121D08D9C52142A6AE5B56`。
- 发布版环境页截图：`results/gui_m6_packaged_environment.png`。
