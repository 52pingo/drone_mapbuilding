from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from drone_gui.models import MissionPlan
from drone_gui.widgets.waypoint_canvas import WaypointCanvas
from drone_gui.widgets.waypoint_editor import WaypointEditor


class MissionPage(QWidget):
    start_requested = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.canvas = WaypointCanvas()
        self.editor = WaypointEditor()
        self.flight_z = self._spin(-120.0, -1.0, -15.0, " m")
        self.cruise_speed = self._spin(0.2, 15.0, 3.0, " m/s")
        self.max_speed = self._spin(0.2, 20.0, 4.0, " m/s")
        self.arrive_dist = self._spin(0.2, 20.0, 3.0, " m")
        self.timeout = self._spin(30.0, 7200.0, 1200.0, " s", 0)
        self.summary = QLabel()
        self.summary.setProperty("role", "metric")
        self.issue_text = QLabel()
        self.issue_text.setWordWrap(True)
        self.issue_text.setProperty("role", "muted")
        self.start_button = QPushButton("开始语义建图任务")
        self.start_button.setProperty("kind", "primary")
        self.start_button.setAccessibleName("验证航线并开始任务")

        self._build_layout()
        self.editor.waypoints_changed.connect(self._route_changed)
        self.canvas.waypoint_added.connect(self.editor.add_waypoint)
        for spin in (
            self.flight_z, self.cruise_speed, self.max_speed,
            self.arrive_dist, self.timeout,
        ):
            spin.valueChanged.connect(self._refresh_summary)
        self.start_button.clicked.connect(self._request_start)
        self.set_plan(MissionPlan.citypark_default())

    @staticmethod
    def _spin(minimum, maximum, value, suffix, decimals=2) -> QDoubleSpinBox:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setDecimals(decimals)
        widget.setSuffix(suffix)
        return widget

    def _build_layout(self) -> None:
        right = QFrame()
        right.setProperty("role", "panel")
        right.setMinimumWidth(390)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 16, 16, 16)
        title = QLabel("航点与任务参数")
        title.setProperty("role", "sectionTitle")
        hint = QLabel("双击左侧画布添加航点；表格支持精确编辑和顺序调整。")
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        right_layout.addWidget(title)
        right_layout.addWidget(hint)
        right_layout.addWidget(self.editor, 1)
        form = QFormLayout()
        form.addRow("飞行高度（NED）", self.flight_z)
        form.addRow("巡航速度", self.cruise_speed)
        form.addRow("最大速度", self.max_speed)
        form.addRow("到达半径", self.arrive_dist)
        form.addRow("任务超时", self.timeout)
        right_layout.addLayout(form)
        right_layout.addWidget(self.summary)
        right_layout.addWidget(self.issue_text)

        save_button = QPushButton("保存航线")
        load_button = QPushButton("加载航线")
        default_button = QPushButton("恢复 CityPark 大环线")
        save_button.clicked.connect(self._save_plan)
        load_button.clicked.connect(self._load_plan)
        default_button.clicked.connect(lambda: self.set_plan(MissionPlan.citypark_default()))
        tools = QHBoxLayout()
        tools.addWidget(save_button)
        tools.addWidget(load_button)
        right_layout.addLayout(tools)
        right_layout.addWidget(default_button)
        right_layout.addWidget(self.start_button)

        canvas_panel = QFrame()
        canvas_panel.setProperty("role", "panel")
        canvas_layout = QVBoxLayout(canvas_panel)
        canvas_layout.setContentsMargins(12, 12, 12, 12)
        canvas_title = QLabel("本地 NED 航线 · North 向上 / East 向右")
        canvas_title.setProperty("role", "sectionTitle")
        fit_button = QPushButton("适配航线")
        fit_button.clicked.connect(self.canvas.fit_route)
        canvas_header = QHBoxLayout()
        canvas_header.addWidget(canvas_title)
        canvas_header.addStretch()
        canvas_header.addWidget(fit_button)
        canvas_layout.addLayout(canvas_header)
        canvas_layout.addWidget(self.canvas, 1)

        splitter = QSplitter()
        splitter.addWidget(canvas_panel)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(splitter)

    def current_plan(self) -> MissionPlan:
        return MissionPlan(
            waypoints=self.editor.waypoints(),
            flight_z=self.flight_z.value(),
            cruise_speed=self.cruise_speed.value(),
            max_speed=self.max_speed.value(),
            arrive_dist=self.arrive_dist.value(),
            max_mission_time=self.timeout.value(),
        )

    def set_plan(self, plan: MissionPlan) -> None:
        self.flight_z.setValue(plan.flight_z)
        self.cruise_speed.setValue(plan.cruise_speed)
        self.max_speed.setValue(plan.max_speed)
        self.arrive_dist.setValue(plan.arrive_dist)
        self.timeout.setValue(plan.max_mission_time)
        self.editor.set_waypoints(plan.waypoints)
        self.canvas.fit_route()

    def _route_changed(self, points) -> None:
        self.canvas.set_waypoints(points)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        try:
            plan = self.current_plan()
        except (TypeError, ValueError, AttributeError):
            self.summary.setText("航点坐标格式无效")
            self.issue_text.setText("请使用有效数字")
            return
        issues = plan.validate()
        self.summary.setText(
            f"{len(plan.waypoints)} 航点 · {plan.route_distance():.0f} m · "
            f"预计 {plan.estimated_seconds() / 60:.1f} min"
        )
        self.issue_text.setText("；".join(issue.message for issue in issues) or "航线参数检查通过")

    def _request_start(self) -> None:
        try:
            plan = self.current_plan()
        except (TypeError, ValueError, AttributeError):
            QMessageBox.warning(self, "航线无效", "航点表中包含无法解析的坐标。")
            return
        errors = [issue.message for issue in plan.validate() if issue.level == "error"]
        if errors:
            QMessageBox.warning(self, "航线无效", "\n".join(errors))
            return
        self.start_requested.emit(plan)

    def _save_plan(self) -> None:
        name, _ = QFileDialog.getSaveFileName(self, "保存航线", "mission.json", "JSON (*.json)")
        if name:
            self.current_plan().save(Path(name))

    def _load_plan(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "加载航线", "", "JSON (*.json)")
        if not name:
            return
        try:
            self.set_plan(MissionPlan.load(Path(name)))
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.critical(self, "加载失败", str(error))

    def set_running(self, running: bool) -> None:
        self.start_button.setDisabled(running)
        self.start_button.setText("任务运行中…" if running else "开始语义建图任务")
