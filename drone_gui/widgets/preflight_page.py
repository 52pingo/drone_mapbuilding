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
from drone_gui.preflight import has_required_failures, run_local_preflight


class PreflightPage(QWidget):
    launch_ue4_requested = Signal()
    restart_stack_requested = Signal()

    STATUS_TEXT = {"pass": "通过", "warning": "待运行检查", "fail": "失败"}

    def __init__(self, config: RuntimeConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._checks = []

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

        refresh_button = QPushButton("重新检查")
        refresh_button.clicked.connect(self.refresh)
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
        action_layout.addWidget(refresh_button)
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

    def refresh(self) -> None:
        self._checks = run_local_preflight(self.config)
        self.table.setRowCount(len(self._checks))
        passed = 0
        for row, check in enumerate(self._checks):
            status = QTableWidgetItem(self.STATUS_TEXT[check.status])
            status.setData(1001, check.status)
            self.table.setItem(row, 0, QTableWidgetItem(check.name))
            self.table.setItem(row, 1, status)
            self.table.setItem(row, 2, QTableWidgetItem(check.detail))
            passed += check.status == "pass"
        required_ok = not has_required_failures(self._checks)
        self.summary.setText(
            f"{passed}/{len(self._checks)} 项通过 · "
            + ("可以进入启动流程" if required_ok else "存在阻止启动的问题")
        )
        self.summary.setProperty("state", "pass" if required_ok else "fail")
        self.summary.style().unpolish(self.summary)
        self.summary.style().polish(self.summary)

    @property
    def required_ready(self) -> bool:
        return not has_required_failures(self._checks)
