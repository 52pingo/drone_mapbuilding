from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider,
)

from drone_gui.replay import ReplayController
from drone_gui.widgets.status_badge import StatusBadge


class ReplayPanel(QFrame):
    frame_changed = Signal(dict, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self.controller = ReplayController(self)
        self.play_button = QPushButton("播放")
        self.play_button.setAccessibleName("播放或暂停任务遥测回放")
        self.reset_button = QPushButton("回到起点")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setAccessibleName("任务遥测回放时间轴")
        self.speed = QComboBox()
        self.speed.setAccessibleName("任务回放速度")
        for value in (0.5, 1.0, 2.0, 4.0, 8.0):
            self.speed.addItem(f"{value:g}×", value)
        self.speed.setCurrentText("1×")
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setProperty("role", "muted")
        self.status = StatusBadge("等待离线 Session")
        self._build_layout()
        self._connect()

    def _build_layout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        title = QLabel("遥测回放")
        title.setProperty("role", "sectionTitle")
        layout.addWidget(title)
        layout.addWidget(self.play_button)
        layout.addWidget(self.reset_button)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.time_label)
        layout.addWidget(self.speed)
        layout.addWidget(self.status)

    def _connect(self) -> None:
        self.play_button.clicked.connect(self.controller.toggle)
        self.reset_button.clicked.connect(lambda: self.controller.seek(0))
        self.slider.sliderMoved.connect(self.controller.seek)
        self.speed.currentIndexChanged.connect(
            lambda: self.controller.set_speed(float(self.speed.currentData()))
        )
        self.controller.frame_ready.connect(self.frame_changed)
        self.controller.position_changed.connect(self._set_position)
        self.controller.state_changed.connect(self._set_state)

    def load(self, root: Path) -> bool:
        loaded = self.controller.load(root)
        self.play_button.setEnabled(loaded)
        self.reset_button.setEnabled(loaded)
        self.slider.setEnabled(loaded)
        self.speed.setEnabled(loaded)
        return loaded

    def _set_position(
        self, index: int, count: int, elapsed: float, duration: float
    ) -> None:
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, count - 1))
        self.slider.setValue(index)
        self.slider.blockSignals(False)
        self.time_label.setText(
            f"{self._clock(elapsed)} / {self._clock(duration)}"
        )

    def _set_state(self, state: str, message: str) -> None:
        self.status.set_state(state, message)
        self.play_button.setText(
            "暂停" if self.controller.timer.isActive() else "播放"
        )

    @staticmethod
    def _clock(seconds: float) -> str:
        value = max(0, int(seconds))
        return f"{value // 60:02d}:{value % 60:02d}"
