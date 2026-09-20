# Qt GUI M5 归档、回放与打包验收（2026-08-18）

## Session 归档

新任务一开始就原子写入 `manifest.json` 和 `mission.json`，记录坐标系、航点、
飞行高度、感知阈值、模型文件大小与 SHA-256。

任务结束后从结构化控制台恢复 `telemetry.jsonl` 和带 UTF-8 BOM 的
`telemetry.csv`，最终点云导出 PLY + PCD，语义对象导出 JSON。WSL 任务脚本调
`octomap_saver_node` 生成 BT；失败时保留告警，不覆盖其他成果。

静态 `report.html` 不依赖网络也不依赖 JavaScript，里面放任务参数、闭环状态、
北东轨迹 SVG、视觉证据统计、预览图和带 SHA-256 的成果清单。

## 安全状态与异常恢复

请求 `completed` 不等于闭环成功。归档器只在最后遥测同时满足 `state=DONE` 与
`armed=false` 时才写 `completed`；否则降级为 `incomplete`。

成果中心能识别 `running/incomplete/failed/interrupted/legacy`，并在后台线程恢复
未完成归档，不阻塞 Qt 主线程。

2026-08-17 那次旧版完整飞行没有 `GUI_STATUS`，恢复器从 `avoid_flight.log` 读
1,523 行，并且只在控制台同时发现 `DISARMED` 与 `MISSION DONE` 之后才补入闭环
末帧。最终得到 1,524 帧、756 秒的可回放 Session，状态 `completed`。

## 离线回放

结果页可以直接把 Session 切到三维地图，不需要 UE4、PX4、ROS2 或 YOLO 环境。

时间轴支持播放/暂停、回到起点、任意拖动，以及 0.5×/1×/2×/4×/8× 调速。回放按
实际 `elapsed` 时间推进，轨迹按 0.25 m 去重并限制为最近 5,000 点。离线快照读
一次后就停止轮询；缺三维地图或视觉末帧时显示明确空状态，不会误报成实时断流。

## Windows 发布包

用 PyInstaller 6.21.0 构建 `dist/DroneMapbuilding/DroneMapbuilding.exe`。

发布目录里带 PowerShell/WSL/Python 任务脚本、配置模板和操作手册；262 MB 的
`best.pt` 保持外置。打包后的 EXE 已经过 `--smoke-test`，并成功离线打开上面那个
1,524 帧真实飞行 Session，Qt、OpenGL、成果页和回放时间轴都正常。

## 自动化结果

- Windows：71 passed，2 skipped。
- WSL/Python：32 passed。
- PowerShell 任务/构建脚本解析通过，Bash 任务脚本 `bash -n` 通过。

BT 自动导出代码已经接进去了，但这次没有重复跑约 756 秒的大环线；等下一次完整
GUI 飞行结束时，再和其他 Session 成果一起做随飞验收。
