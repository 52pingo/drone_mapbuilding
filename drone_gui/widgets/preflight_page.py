from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from drone_gui.models import RuntimeConfig
from drone_gui.preflight import CheckResult, has_required_failures, run_local_preflight


class PreflightPage(QWidget):
    launch_ue4_requested = Signal()
    restart_stack_requested = Signal()
    runtime_probe_requested = Signal()

    STATUS_TEXT = {"pass": "通过", "warning": "待运行检查", "fail": "失败"}
    RUNTIME_COMPONENTS = (
        ("ros_workspace", "ROS2 工作区", True),
        ("px4", "PX4 SITL 进程", True),
        ("xrce", "Micro XRCE-DDS", True),
        ("airsim", "AirSim ROS 节点", True),
        ("telemetry", "PX4 位置遥测（实时消息）", True),
        ("depth", "深度 /depth/clamped（实时消息）", True),
        ("octomap", "OctoMap 点云（实时消息）", True),
        ("mission_service", "任务控制服务", False),
    )

    def __init__(self, config: RuntimeConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._checks = []
        self._runtime_payload: dict | None = None
        self._probe_completed = False

        intro = QLabel("在启动飞控前确认本机路径、权重、WSL 和输出目录。ROS 话题与深度统计会在启动阶段继续检查。")
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")
        self.summary = QLabel()
        self.summary.setProperty("role", "metric")

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["组件", "状态", "说明"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAccessibleName("启动前环境检查结果")

        self.refresh_button = QPushButton("本地 + WSL 动态检查")
        self.refresh_button.clicked.connect(self._request_refresh)
        launch_button = QPushButton("1  启动 UE4")
        launch_button.setProperty("kind", "primary")
        launch_button.clicked.connect(self.launch_ue4_requested)
        stack_button = QPushButton("2  启动 PX4 / ROS2")
        stack_button.setProperty("kind", "primary")
        stack_button.clicked.connect(self.restart_stack_requested)

        actions = QFrame()
        actions.setProperty("role", "panel")
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(16, 14, 16, 14)
        action_layout.addWidget(self.refresh_button)
        action_layout.addStretch()
        action_layout.addWidget(launch_button)
        action_layout.addWidget(stack_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(intro)
        layout.addWidget(self.summary)
        layout.addWidget(self.table, 1)
        layout.addWidget(actions)
        self.refresh()

    def _request_refresh(self) -> None:
        self.refresh()
        self.runtime_probe_requested.emit()

    def refresh(self) -> None:
        local_checks = [
            item for item in run_local_preflight(self.config)
            if item.name != "ROS2 工作区"
        ]
        runtime_checks = []
        for key, name, required in self.RUNTIME_COMPONENTS:
            if self._runtime_payload is None:
                runtime_checks.append(CheckResult(
                    name, "warning", "等待 WSL 动态检查", required=required
                ))
                continue
            available = self._runtime_payload.get(key) is True
            runtime_checks.append(CheckResult(
                name,
                "pass" if available else "fail" if required else "warning",
                "运行正常" if available else (
                    "未发现；任务启动后才会出现" if not required else "未发现或未就绪"
                ),
                required=required,
            ))
        self._checks = local_checks + runtime_checks
        self._render_checks()

    def _render_checks(self) -> None:
        self.table.setRowCount(len(self._checks))
        passed = 0
        for row, check in enumerate(self._checks):
            status = QTableWidgetItem(self.STATUS_TEXT[check.status])
            status.setData(1001, check.status)
            self.table.setItem(row, 0, QTableWidgetItem(check.name))
            self.table.setItem(row, 1, status)
            self.table.setItem(row, 2, QTableWidgetItem(check.detail))
            passed += check.status == "pass"
        required_ok = self.required_ready
        self.summary.setText(
            f"{passed}/{len(self._checks)} 项通过 · "
            + (
                "可以进入启动流程" if required_ok else
                "请先完成 WSL 动态检查" if not self._probe_completed else
                "存在阻止启动的问题"
            )
        )
        self.summary.setProperty("state", "pass" if required_ok else "fail")
        self.summary.style().unpolish(self.summary)
        self.summary.style().polish(self.summary)

    def apply_runtime_probe(self, payload: dict) -> None:
        self._runtime_payload = payload
        self._probe_completed = True
        self.set_probe_running(False)
        self.refresh()

    def apply_runtime_failure(self, detail: str) -> None:
        self._runtime_payload = {}
        self._probe_completed = True
        self.set_probe_running(False)
        self.refresh()
        self.summary.setText(f"WSL 动态检查失败：{detail}")

    def set_probe_running(self, running: bool) -> None:
        self.refresh_button.setEnabled(not running)
        self.refresh_button.setText(
            "正在检查 WSL…" if running else "本地 + WSL 动态检查"
        )

    @property
    def required_ready(self) -> bool:
        return self._probe_completed and not has_required_failures(self._checks)
