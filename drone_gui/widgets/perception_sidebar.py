from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFormLayout, QFrame, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from drone_gui.widgets.mission_controls import MissionControls


PATH_ROLE = Qt.UserRole + 1


class PerceptionSidebar(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self.telemetry = {
            "阶段": QLabel("WAIT"),
            "飞行状态": QLabel("未知"),
            "位置 N/E/Z": QLabel("—"),
            "最近障碍": QLabel("—"),
            "任务耗时": QLabel("—"),
        }
        self.objects = QTreeWidget()
        self.objects.setHeaderLabels(["当前目标", "置信度", "深度"])
        self.objects.setAccessibleName("当前视觉检测目标")
        self.objects.setAlternatingRowColors(True)
        self.objects.setMaximumHeight(150)
        self.catalog = QTreeWidget()
        self.catalog.setHeaderLabels(["已发现类别", "证据", "最高置信度"])
        self.catalog.setAccessibleName("已确认类别与首次发现证据")
        self.catalog.setMaximumHeight(130)
        self.catalog.currentItemChanged.connect(self._show_evidence)
        self.evidence = QLabel("选择类别查看首次发现截图")
        self.evidence.setAlignment(Qt.AlignCenter)
        self.evidence.setProperty("role", "muted")
        self.evidence.setMinimumHeight(90)
        self.evidence.setMaximumHeight(120)
        self.evidence.setAccessibleName("类别首次发现截图")
        self.controls = MissionControls()
        self._evidence_pixmap: QPixmap | None = None
        self._build_layout()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        title = QLabel("任务遥测")
        title.setProperty("role", "sectionTitle")
        layout.addWidget(title)
        form = QFormLayout()
        for name, value in self.telemetry.items():
            value.setProperty("role", "metric" if name == "阶段" else "")
            form.addRow(name, value)
        layout.addLayout(form)
        layout.addWidget(self._title("本帧目标"))
        layout.addWidget(self.objects)
        layout.addWidget(self._title("类别证据"))
        layout.addWidget(self.catalog)
        layout.addWidget(self.evidence)
        layout.addWidget(self.controls)

    @staticmethod
    def _title(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "sectionTitle")
        return label

    def set_status(self, payload: dict) -> None:
        phase = str(payload.get("state", "UNKNOWN")).upper()
        self.telemetry["阶段"].setText(phase)
        armed = payload.get("armed")
        self.telemetry["飞行状态"].setText(
            "已锁定" if armed is True else "已解除锁定" if armed is False else "未知"
        )
        position = payload.get("position")
        if isinstance(position, list) and len(position) == 3:
            self.telemetry["位置 N/E/Z"].setText(
                " / ".join(f"{float(value):.1f}" for value in position)
            )
        obstacle = payload.get("nearest_obstacle")
        self.telemetry["最近障碍"].setText(
            f"{float(obstacle):.1f} m" if obstacle is not None else "无有效近障碍"
        )
        elapsed = float(payload.get("elapsed", 0.0))
        self.telemetry["任务耗时"].setText(
            f"{int(elapsed) // 60:02d}:{int(elapsed) % 60:02d}"
        )
        self.controls.set_state(phase)

    def set_detections(self, detections: list[dict]) -> None:
        self.objects.clear()
        for detection in detections:
            depth = detection.get("depth_m")
            QTreeWidgetItem(self.objects, [
                str(detection.get("label", "unknown")),
                f"{float(detection.get('confidence', 0)):.2f}",
                f"{float(depth):.1f} m" if depth is not None else "—",
            ])

    def set_catalog(self, catalog: list[dict]) -> None:
        selected = self.catalog.currentItem().text(0) if self.catalog.currentItem() else None
        self.catalog.clear()
        for value in catalog:
            item = QTreeWidgetItem([
                str(value.get("label", "unknown")),
                str(int(value.get("saved_count", 0))),
                f"{float(value.get('max_confidence', 0)):.2f}",
            ])
            item.setData(0, PATH_ROLE, value.get("first_image"))
            self.catalog.addTopLevelItem(item)
            if selected and item.text(0) == selected:
                self.catalog.setCurrentItem(item)
        if self.catalog.topLevelItemCount() and self.catalog.currentItem() is None:
            self.catalog.setCurrentItem(self.catalog.topLevelItem(0))

    def reset_perception(self) -> None:
        self.objects.clear()
        self.catalog.clear()
        self._evidence_pixmap = None
        self.evidence.setPixmap(QPixmap())
        self.evidence.setText("等待确认类别与首次发现截图")

    def _show_evidence(self, current, _previous) -> None:
        path = Path(current.data(0, PATH_ROLE)) if current and current.data(0, PATH_ROLE) else None
        self._evidence_pixmap = QPixmap(str(path)) if path and path.is_file() else None
        if self._evidence_pixmap is None or self._evidence_pixmap.isNull():
            self.evidence.setPixmap(QPixmap())
            self.evidence.setText("首次发现截图尚未就绪")
            return
        self.evidence.setText("")
        self.evidence.setPixmap(self._evidence_pixmap.scaled(
            self.evidence.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
