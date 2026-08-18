# Qt GUI M5 归档、回放与打包验收（2026-08-18）

## Session 归档

- 新任务开始时原子写入 `manifest.json` 和 `mission.json`，记录坐标系、航点、飞行
  高度、感知阈值、模型文件大小与 SHA-256。
- 任务结束后从结构化控制台恢复 `telemetry.jsonl` 与带 UTF-8 BOM 的
  `telemetry.csv`，最终点云导出 PLY + PCD，语义对象导出 JSON。
- WSL 任务脚本调用 `octomap_saver_node` 生成 BT；失败时保留告警，不覆盖其他成果。
- 静态 `report.html` 不依赖网络或 JavaScript，包含任务参数、闭环状态、北东轨迹
  SVG、视觉证据统计、预览图和带 SHA-256 的成果清单。

## 安全状态与异常恢复

- 请求 `completed` 不等于闭环成功。归档器仅在最后遥测同时满足
  `state=DONE` 与 `armed=false` 时写入 `completed`；否则降级为 `incomplete`。
- 成果中心能识别 `running/incomplete/failed/interrupted/legacy`，并在后台线程恢复
  未完成归档，不阻塞 Qt 主线程。
- 2026-08-17 的旧版完整飞行没有 `GUI_STATUS`，恢复器从 `avoid_flight.log` 读取
  1,523 行，并且只在控制台同时发现 `DISARMED` 与 `MISSION DONE` 后补入闭环末帧。
  最终得到 1,524 帧、756 秒的可回放 Session，状态为 `completed`。

## 离线回放

- 结果页可以直接把 Session 切到三维地图，无需 UE4、PX4、ROS2 或 YOLO 环境。
- 时间轴支持播放/暂停、回到起点、任意拖动与 0.5×/1×/2×/4×/8× 调速。
- 回放使用实际 `elapsed` 时间推进，轨迹按 0.25 m 去重并限制为最近 5,000 点。
- 离线快照读取一次后停止轮询；缺少三维地图或视觉末帧时显示明确空状态，不误报
  为实时断流。

## Windows 发布包

- 使用 PyInstaller 6.21.0 构建 `dist/DroneMapbuilding/DroneMapbuilding.exe`。
- 发布目录包含 PowerShell/WSL/Python 任务脚本、配置模板与操作手册；262 MB 的
  `best.pt` 保持外置。
- 打包后 EXE 已通过 `--smoke-test`，并成功离线打开上述 1,524 帧真实飞行 Session，
  Qt、OpenGL、成果页和回放时间轴均正常。

## 自动化结果

- Windows：71 passed，2 skipped。
- WSL/Python：32 passed。
- PowerShell 任务/构建脚本解析通过，Bash 任务脚本 `bash -n` 通过。

BT 自动导出代码已接入，但本次没有重复执行约 756 秒的大环线；它将在下一次完整
GUI 飞行结束时与其他 Session 成果一并进行随飞验收。
