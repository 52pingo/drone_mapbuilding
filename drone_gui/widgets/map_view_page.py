from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QSlider, QVBoxLayout, QWidget,
)

from drone_gui.map_export import export_map
from drone_gui.map_feed import MapFeed
from drone_gui.widgets.map_3d_widget import Map3DWidget
from drone_gui.widgets.status_badge import StatusBadge


class MapViewPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.feed = MapFeed(self)
        self.view = Map3DWidget()
        self.status = StatusBadge("等待地图 Session")
        self.metrics = {
            "points": QLabel("0 点"),
            "path": QLabel("0 轨迹点"),
            "objects": QLabel("0 语义目标"),
            "frame": QLabel("PX4 Local NED"),
        }
        self.points = np.empty((0, 3), dtype=np.float32)
        self.trajectory: list[list[float]] = []
        self.semantic_objects: list[dict] = []
        self.session_root: Path | None = None
        self._auto_fitted = False
        self._build_layout()
        self.feed.snapshot_ready.connect(self._update_map)
        self.feed.state_changed.connect(self.status.set_state)

    def _build_layout(self) -> None:
        header = QFrame()
        header.setProperty("role", "panel")
        row = QHBoxLayout(header)
        row.setContentsMargins(14, 10, 14, 10)
        title = QLabel("实时三维占用与语义地图")
        title.setProperty("role", "sectionTitle")
        row.addWidget(title)
        for label in self.metrics.values():
            label.setProperty("role", "muted")
            row.addWidget(label)
        row.addStretch()
        row.addWidget(self.status)

        controls = QFrame()
        controls.setProperty("role", "panel")
        actions = QHBoxLayout(controls)
        actions.setContentsMargins(14, 8, 14, 8)
        fit_button = QPushButton("适配地图")
        fit_button.clicked.connect(self.view.fit_scene)
        top_button = QPushButton("俯视")
        top_button.clicked.connect(self.view.top_view)
        self.map_toggle = self._toggle("占用点云", self.view.map_item.setVisible)
        self.path_toggle = self._toggle("飞行轨迹", self.view.set_path_visible)
        self.semantic_toggle = self._toggle("语义目标", self.view.set_semantics_visible)
        self.class_filter = QComboBox()
        self.class_filter.setAccessibleName("三维语义目标类别筛选")
        self.class_filter.addItem("全部类别")
        self.class_filter.currentTextChanged.connect(self._render_semantics)
        point_size = QSlider(Qt.Horizontal)
        point_size.setRange(8, 50)
        point_size.setValue(22)
        point_size.setMaximumWidth(120)
        point_size.setAccessibleName("三维点云点大小")
        point_size.valueChanged.connect(self.view.set_point_size)
        export_button = QPushButton("导出 PLY / JSON / PNG")
        export_button.setProperty("kind", "primary")
        export_button.clicked.connect(self.export_current)
        for widget in (
            fit_button, top_button, self.map_toggle, self.path_toggle,
            self.semantic_toggle, self.class_filter,
        ):
            actions.addWidget(widget)
        actions.addWidget(QLabel("点大小"))
        actions.addWidget(point_size)
        actions.addStretch()
        actions.addWidget(export_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(header)
        layout.addWidget(self.view, 1)
        layout.addWidget(controls)

    @staticmethod
    def _toggle(text: str, callback) -> QCheckBox:
        toggle = QCheckBox(text)
        toggle.setChecked(True)
        toggle.toggled.connect(callback)
        return toggle

    def start_session(self, session: dict) -> None:
        root = session.get("result_root")
        self.session_root = Path(root) if isinstance(root, str) else None
        self.points = np.empty((0, 3), dtype=np.float32)
        self.trajectory = []
        self.semantic_objects = []
        self._auto_fitted = False
        self.view.set_points(self.points)
        self.view.set_trajectory([])
        self.view.set_semantics([])
        self.class_filter.clear()
        self.class_filter.addItem("全部类别")
        self._refresh_metrics()
        self.feed.start(session)

    def stop(self, message: str = "任务结束，保留最终地图") -> None:
        self.feed.stop(message)
        if self.session_root is not None and len(self.points):
            export_map(
                self.session_root, self.points, self.semantic_objects, image=None
            )

    def _update_map(self, points, metadata: dict) -> None:
        self.points = points
        self.view.set_points(points)
        self.metrics["frame"].setText(str(metadata.get("coordinate_frame", "NED")))
        self._refresh_metrics()
        if not self._auto_fitted:
            self._auto_fitted = True
            self.view.fit_scene()

    def update_telemetry(self, payload: dict) -> None:
        position = payload.get("position")
        if not isinstance(position, list) or len(position) != 3:
            return
        point = [float(value) for value in position]
        if self.trajectory and np.linalg.norm(
                np.asarray(point) - np.asarray(self.trajectory[-1])) < 0.25:
            return
        self.trajectory.append(point)
        self.trajectory = self.trajectory[-5000:]
        self.view.set_trajectory(self.trajectory)
        self._refresh_metrics()

    def update_semantics(self, payload: dict) -> None:
        values = payload.get("semantic_objects")
        self.semantic_objects = [
            item for item in values if isinstance(item, dict)
        ] if isinstance(values, list) else []
        selected = self.class_filter.currentText()
        labels = sorted({
            str(item.get("label", "object")) for item in self.semantic_objects
            if isinstance(item, dict)
        })
        self.class_filter.blockSignals(True)
        self.class_filter.clear()
        self.class_filter.addItems(["全部类别", *labels])
        self.class_filter.setCurrentText(
            selected if selected in labels else "全部类别"
        )
        self.class_filter.blockSignals(False)
        self._render_semantics()
        self._refresh_metrics()

    def _render_semantics(self, _text: str = "") -> None:
        selected = self.class_filter.currentText()
        visible = self.semantic_objects if selected == "全部类别" else [
            item for item in self.semantic_objects if item.get("label") == selected
        ]
        self.view.set_semantics(visible)
        self.metrics["objects"].setText(
            f"{len(visible)} / {len(self.semantic_objects)} 语义目标"
        )

    def _refresh_metrics(self) -> None:
        self.metrics["points"].setText(f"{len(self.points):,} 点")
        self.metrics["path"].setText(f"{len(self.trajectory):,} 轨迹点")
        if not self.semantic_objects:
            self.metrics["objects"].setText("0 语义目标")

    def export_current(self) -> None:
        if not len(self.points) or self.session_root is None:
            QMessageBox.information(self, "暂无地图", "收到点云 Session 后才能导出。")
            return
        outputs = export_map(
            self.session_root, self.points, self.semantic_objects,
            self.view.grab(),
        )
        QMessageBox.information(
            self, "地图已导出", "\n".join(str(path) for path in outputs)
        )
