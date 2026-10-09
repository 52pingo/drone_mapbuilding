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
        self._local_checks = []
        self._runtime_payload: dict | None = None
        self._probe_completed = False
        self._ue4_ready = False

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
        self.launch_button = QPushButton("1  启动 UE4")
        self.launch_button.setProperty("kind", "primary")
        self.launch_button.clicked.connect(self.launch_ue4_requested)
        self.stack_button = QPushButton("2  启动 PX4 / ROS2")
        self.stack_button.setProperty("kind", "primary")
        self.stack_button.clicked.connect(self.restart_stack_requested)

        self.gate_hint = QLabel()
        self.gate_hint.setWordWrap(True)

        actions = QFrame()
        actions.setProperty("role", "panel")
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(16, 14, 16, 14)
        action_layout.addWidget(self.refresh_button)
        action_layout.addStretch()
        action_layout.addWidget(self.launch_button)
        action_layout.addWidget(self.stack_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(intro)
        layout.addWidget(self.summary)
        layout.addWidget(self.table, 1)
        layout.addWidget(actions)
        layout.addWidget(self.gate_hint)
        self.apply_ue4_state(False, "尚未启动 UE4")
        self.refresh()

    def apply_ue4_state(self, ready: bool, detail: str) -> None:
        """就绪门禁：UE4 没起来就不让放 PX4 / ROS2 出去。

        先起 PX4 再起仿真是这个按钮最容易犯的错，而且失败得很安静：
        airsim_node 照样能起，只是连不上 RPC，深度链路先报“就绪”再彻底哑掉，
        用户看到的是任务飞到一半卡死。第 1 步用的是 reuse 策略
        （launch_ue4.ps1 检测到已在运行的仿真会直接复用），所以锁住第 2 步
        不等于死路——即使 UE4 是手工开的，点一下第 1 步就能补上就绪状态。
        """
        self._ue4_ready = ready
        self.stack_button.setEnabled(ready)
        self.stack_button.setToolTip(
            "" if ready else f"UE4 未就绪（{detail}），请先完成第 1 步"
        )
        self.stack_button.setAccessibleDescription(
            "UE4 已就绪" if ready else f"已禁用：UE4 未就绪，{detail}"
        )
        self.gate_hint.setText(
            "UE4 已就绪，可以启动 PX4 / ROS2。"
            if ready
            else f"第 2 步已锁定 —— {detail}。请先完成第 1 步；"
                 "若仿真已在运行，第 1 步会直接复用它并刷新就绪状态。"
        )
        state = "pass" if ready else "warning"
        self.gate_hint.setProperty("state", state)
        self.gate_hint.style().unpolish(self.gate_hint)
        self.gate_hint.style().polish(self.gate_hint)

    def _request_refresh(self) -> None:
        self.refresh()
        self.runtime_probe_requested.emit()

    def refresh(self) -> None:
        local_checks = [
            item for item in run_local_preflight(self.config)
            if item.name != "ROS2 工作区"
        ]
        self._local_checks = local_checks
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
        local_blocked = has_required_failures(self._local_checks)
        if required_ok:
            summary_text = "可以进入任务流程"
            summary_state = "pass"
        elif local_blocked:
            summary_text = "存在阻止启动的本地配置问题"
            summary_state = "fail"
        elif not self._probe_completed:
            summary_text = "请先完成 WSL 动态检查"
            summary_state = "warning"
        else:
            summary_text = "运行栈尚未就绪，请按 1 → 2 启动并等待自动复检"
            summary_state = "warning"
        self.summary.setText(
            f"{passed}/{len(self._checks)} 项通过 · {summary_text}"
        )
        self.summary.setProperty("state", summary_state)
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

    @property
    def ue4_ready(self) -> bool:
        return self._ue4_ready
