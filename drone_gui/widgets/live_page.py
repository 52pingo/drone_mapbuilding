from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from drone_gui.widgets.perception_sidebar import PerceptionSidebar
from drone_gui.widgets.status_badge import StatusBadge


class LivePage(QWidget):
    hold_requested = Signal()
    resume_requested = Signal()
    land_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.video = QLabel("等待任务启动与 AirSim RGB 数据流")
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setMinimumSize(640, 360)
        self.video.setProperty("role", "muted")
        self.video.setAccessibleName("AirSim 实时相机与 YOLO 检测框")
        self.state = StatusBadge("尚未连接")
        self.feed_note = QLabel("M3 实时协议已就绪；启动任务后显示带框画面。")
        self.feed_note.setProperty("role", "muted")
        self.feed_note.setWordWrap(True)
        self.sidebar = PerceptionSidebar()
        self.telemetry = self.sidebar.telemetry
        self.objects = self.sidebar.objects
        self.controls = self.sidebar.controls
        self.controls.hold_requested.connect(self.hold_requested)
        self.controls.resume_requested.connect(self.resume_requested)
        self.controls.land_requested.connect(self.land_requested)
        self._frame: QImage | None = None
        self._build_layout()

    def _build_layout(self) -> None:
        camera_panel = QFrame()
        camera_panel.setProperty("role", "panel")
        camera_layout = QVBoxLayout(camera_panel)
        camera_layout.setContentsMargins(14, 14, 14, 14)
        header = QHBoxLayout()
        title = QLabel("AirSim RGB · YOLO 语义感知")
        title.setProperty("role", "sectionTitle")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.state)
        camera_layout.addLayout(header)
        camera_layout.addWidget(self.video, 1)
        camera_layout.addWidget(self.feed_note)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(camera_panel, 3)
        layout.addWidget(self.sidebar, 2)

    def consume_log(self, text: str) -> None:
        upper = text.upper()
        for phase in ("TAKEOFF", "NAVIGATE", "HOLD", "LAND"):
            if phase in upper:
                self.telemetry["阶段"].setText(phase)
        if "DISARMED" in upper:
            self.telemetry["飞行状态"].setText("已解除锁定")
        if "MISSION DONE" in upper:
            self.telemetry["阶段"].setText("DONE")
            self.state.set_state("done", "任务完成")
        position = re.search(r"pos=\(([-\d.]+),\s*([-\d.]+)\)", text)
        if position:
            self.telemetry["位置 N/E/Z"].setText(
                f"{position.group(1)} / {position.group(2)} / —"
            )

    def update_status(self, payload: dict) -> None:
        self.sidebar.set_status(payload)
        if str(payload.get("state", "")).upper() == "DONE":
            self.state.set_state("done", "任务完成")

    def update_perception(self, payload: dict) -> None:
        self.sidebar.set_detections(payload.get("detections", []))
        self.sidebar.set_catalog(payload.get("catalog", []))
        size = payload.get("size", [0, 0])
        self.feed_note.setText(
            f"帧 {int(payload.get('frame_index', 0)):,} · "
            f"{float(payload.get('fps', 0)):.1f} FPS · "
            f"{int(size[0]) if len(size) > 1 else 0}×{int(size[1]) if len(size) > 1 else 0}"
        )

    def set_frame(self, image: QImage) -> None:
        self._frame = image
        self._render_frame()

    def set_feed_state(self, state: str, text: str) -> None:
        self.state.set_state(state, text)
        if state in {"warning", "error"}:
            self.feed_note.setText(text)

    def reset_perception(self) -> None:
        self._frame = None
        self.video.setPixmap(QPixmap())
        self.video.setText("等待 YOLO 首帧")
        self.sidebar.reset_perception()
        self.feed_note.setText("正在初始化模型与 AirSim 图像连接…")

    def set_process_state(self, state: str, text: str) -> None:
        self.state.set_state(state, text)

    def set_detections(self, detections: list[dict]) -> None:
        self.sidebar.set_detections(detections)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_frame()

    def _render_frame(self) -> None:
        if self._frame is None or self._frame.isNull():
            return
        pixmap = QPixmap.fromImage(self._frame)
        self.video.setText("")
        self.video.setPixmap(pixmap.scaled(
            self.video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
