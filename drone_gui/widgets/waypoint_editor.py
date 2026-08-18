from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from drone_gui.models import Waypoint


class WaypointEditor(QWidget):
    waypoints_changed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._updating = False
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "North / m", "East / m"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(185)
        self.table.setAccessibleName("航点坐标表")
        self.table.itemChanged.connect(self._on_item_changed)

        add_button = QPushButton("添加")
        delete_button = QPushButton("删除")
        up_button = QPushButton("上移")
        down_button = QPushButton("下移")
        home_button = QPushButton("追加返航点")
        add_button.setAccessibleName("添加空白航点")
        delete_button.setAccessibleName("删除选中航点")
        home_button.setAccessibleName("追加原点返航航点")
        add_button.clicked.connect(lambda: self.add_waypoint(0.0, 0.0))
        delete_button.clicked.connect(self._delete_selected)
        up_button.clicked.connect(lambda: self._move_selected(-1))
        down_button.clicked.connect(lambda: self._move_selected(1))
        home_button.clicked.connect(lambda: self.add_waypoint(0.0, 0.0))

        row = QHBoxLayout()
        row.setSpacing(6)
        for button in (add_button, delete_button, up_button, down_button):
            row.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.table, 1)
        layout.addLayout(row)
        layout.addWidget(home_button)

    def set_waypoints(self, points: List[Waypoint]) -> None:
        self._updating = True
        self.table.setRowCount(len(points))
        for row, point in enumerate(points):
            index_item = QTableWidgetItem(str(row + 1))
            index_item.setFlags(index_item.flags() & ~Qt.ItemIsEditable)
            index_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, index_item)
            self.table.setItem(row, 1, QTableWidgetItem(f"{point.north_m:.3f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{point.east_m:.3f}"))
        self._updating = False
        self.waypoints_changed.emit(self.waypoints())

    def waypoints(self) -> List[Waypoint]:
        points = []
        for row in range(self.table.rowCount()):
            north_item = self.table.item(row, 1)
            east_item = self.table.item(row, 2)
            points.append(Waypoint(float(north_item.text()), float(east_item.text())))
        return points

    def add_waypoint(self, north_m: float, east_m: float) -> None:
        points = self._safe_waypoints()
        points.append(Waypoint(north_m, east_m))
        self.set_waypoints(points)
        self.table.selectRow(len(points) - 1)

    def _safe_waypoints(self) -> List[Waypoint]:
        try:
            return self.waypoints()
        except (TypeError, ValueError, AttributeError):
            return []

    def _on_item_changed(self, _item: QTableWidgetItem) -> None:
        if self._updating:
            return
        try:
            points = self.waypoints()
        except (TypeError, ValueError, AttributeError):
            return
        self.waypoints_changed.emit(points)

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        points = self._safe_waypoints()
        if row < len(points):
            points.pop(row)
            self.set_waypoints(points)

    def _move_selected(self, offset: int) -> None:
        row = self.table.currentRow()
        target = row + offset
        points = self._safe_waypoints()
        if row < 0 or target < 0 or target >= len(points):
            return
        points[row], points[target] = points[target], points[row]
        self.set_waypoints(points)
        self.table.selectRow(target)
