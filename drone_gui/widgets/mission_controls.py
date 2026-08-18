from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class MissionControls(QFrame):
    hold_requested = Signal()
    resume_requested = Signal()
    land_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self._state = "WAIT"
        title = QLabel("飞行控制")
        title.setProperty("role", "sectionTitle")
        self.note = QLabel("任务启动并收到飞控状态后可操作")
        self.note.setProperty("role", "muted")
        self.note.setWordWrap(True)

        self.hold_button = QPushButton("悬停")
        self.hold_button.setAccessibleName("暂停航线并原地悬停")
        self.hold_button.clicked.connect(self.hold_requested)
        self.resume_button = QPushButton("继续航线")
        self.resume_button.setProperty("kind", "primary")
        self.resume_button.clicked.connect(self.resume_requested)
        self.land_button = QPushButton("安全降落")
        self.land_button.setProperty("kind", "danger")
        self.land_button.setAccessibleName("调用 PX4 正常降落闭环")
        self.land_button.clicked.connect(self.land_requested)

        buttons = QHBoxLayout()
        buttons.addWidget(self.hold_button)
        buttons.addWidget(self.resume_button)
        buttons.addWidget(self.land_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(title)
        layout.addWidget(self.note)
        layout.addLayout(buttons)
        self.set_state("WAIT")

    def set_state(self, state: str) -> None:
        state = state.upper()
        self._state = state
        self.hold_button.setEnabled(state in {"NAVIGATE", "SCAN"})
        self.resume_button.setEnabled(state == "HOLD")
        self.land_button.setEnabled(
            state in {"TAKEOFF", "NAVIGATE", "SCAN", "HOVER", "HOLD"}
        )
        notes = {
            "HOLD": "航线已暂停；飞控持续接收零速度设定值。",
            "LAND": "正在执行 PX4 LAND 与落地解锁闭环。",
            "DONE": "已确认降落、解除锁定并完成任务。",
        }
        self.note.setText(notes.get(state, f"当前状态：{state}"))

    def set_busy(self, busy: bool) -> None:
        if busy:
            self.hold_button.setEnabled(False)
            self.resume_button.setEnabled(False)
            self.land_button.setEnabled(False)
        else:
            self.set_state(self._state)
