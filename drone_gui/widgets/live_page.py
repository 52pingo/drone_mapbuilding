from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from drone_gui.widgets.status_badge import StatusBadge


class LivePage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.video = QLabel("等待 AirSim RGB / YOLO 数据流")
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setMinimumSize(640, 360)
        self.video.setProperty("role", "muted")
        self.video.setAccessibleName("实时相机与识别框画面")
        self.state = StatusBadge("尚未连接")
        self.telemetry = {
            "阶段": QLabel("WAIT"),
            "飞行状态": QLabel("未知"),
            "位置 N/E/Z": QLabel("—"),
            "最近障碍": QLabel("—"),
            "任务耗时": QLabel("—"),
        }
        self.objects = QTreeWidget()
        self.objects.setHeaderLabels(["类别", "置信度", "深度"])
        self.objects.setAccessibleName("当前视觉检测目标")
        self.objects.setAlternatingRowColors(True)
        self._build_layout()

    def _build_layout(self) -> None:
        camera_panel = QFrame()
        camera_panel.setProperty("role", "panel")
        camera_layout = QVBoxLayout(camera_panel)
        camera_layout.setContentsMargins(14, 14, 14, 14)
        header = QHBoxLayout()
        title = QLabel("实时感知")
        title.setProperty("role", "sectionTitle")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.state)
        camera_layout.addLayout(header)
        camera_layout.addWidget(self.video, 1)
        note = QLabel("M1 已建立展示接口；M3 将接入连续 RGB 帧、检测框和跟踪 ID。")
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        camera_layout.addWidget(note)

        telemetry_panel = QFrame()
        telemetry_panel.setProperty("role", "panel")
        telemetry_layout = QVBoxLayout(telemetry_panel)
        telemetry_layout.setContentsMargins(14, 14, 14, 14)
        telemetry_title = QLabel("任务遥测")
        telemetry_title.setProperty("role", "sectionTitle")
        telemetry_layout.addWidget(telemetry_title)
        form = QFormLayout()
        for name, value in self.telemetry.items():
            value.setProperty("role", "metric" if name == "阶段" else "")
            form.addRow(name, value)
        telemetry_layout.addLayout(form)
        object_title = QLabel("本帧目标")
        object_title.setProperty("role", "sectionTitle")
        telemetry_layout.addWidget(object_title)
        telemetry_layout.addWidget(self.objects, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(camera_panel, 3)
        layout.addWidget(telemetry_panel, 2)

    def consume_log(self, text: str) -> None:
        upper = text.upper()
        if "TAKEOFF" in upper:
            self.telemetry["阶段"].setText("TAKEOFF")
        if "NAVIGATE" in upper:
            self.telemetry["阶段"].setText("NAVIGATE")
        if "LAND" in upper:
            self.telemetry["阶段"].setText("LAND")
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

    def set_process_state(self, state: str, text: str) -> None:
        self.state.set_state(state, text)

    def set_detections(self, detections: list[dict]) -> None:
        self.objects.clear()
        for detection in detections:
            QTreeWidgetItem(self.objects, [
                str(detection.get("label", "unknown")),
                f"{float(detection.get('confidence', 0)):.2f}",
                f"{float(detection['depth_m']):.1f} m" if detection.get("depth_m") else "—",
            ])
