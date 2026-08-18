from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider,
)


class MapControls(QFrame):
    fit_requested = Signal()
    top_view_requested = Signal()
    map_visibility_changed = Signal(bool)
    path_visibility_changed = Signal(bool)
    semantic_visibility_changed = Signal(bool)
    point_size_changed = Signal(int)
    export_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("role", "panel")
        self.class_filter = QComboBox()
        self.class_filter.setAccessibleName("三维语义目标类别筛选")
        self.class_filter.addItem("全部类别")
        self._build_layout()

    def _build_layout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        fit_button = QPushButton("适配地图")
        fit_button.clicked.connect(self.fit_requested)
        top_button = QPushButton("俯视")
        top_button.clicked.connect(self.top_view_requested)
        self.map_toggle = self._toggle("占用点云", self.map_visibility_changed)
        self.path_toggle = self._toggle("飞行轨迹", self.path_visibility_changed)
        self.semantic_toggle = self._toggle(
            "语义目标", self.semantic_visibility_changed
        )
        point_size = QSlider(Qt.Horizontal)
        point_size.setRange(8, 50)
        point_size.setValue(22)
        point_size.setMaximumWidth(120)
        point_size.setAccessibleName("三维点云点大小")
        point_size.valueChanged.connect(self.point_size_changed)
        export_button = QPushButton("导出 PLY / PCD / JSON / PNG")
        export_button.setProperty("kind", "primary")
        export_button.clicked.connect(self.export_requested)
        for widget in (
            fit_button, top_button, self.map_toggle, self.path_toggle,
            self.semantic_toggle, self.class_filter,
        ):
            layout.addWidget(widget)
        layout.addWidget(QLabel("点大小"))
        layout.addWidget(point_size)
        layout.addStretch()
        layout.addWidget(export_button)

    @staticmethod
    def _toggle(text: str, signal) -> QCheckBox:
        toggle = QCheckBox(text)
        toggle.setChecked(True)
        toggle.toggled.connect(signal)
        return toggle
