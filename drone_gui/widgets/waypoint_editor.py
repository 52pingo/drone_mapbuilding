from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from drone_gui.models import Waypoint


class WaypointEditor(QWidget):
    waypoints_changed = Signal(object)

    _BAD_CELL_COLOR = QColor("#ffd6d6")

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

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("航点表状态提示")

        row = QHBoxLayout()
        row.setSpacing(6)
        for button in (add_button, delete_button, up_button, down_button):
            row.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status_label)
        layout.addLayout(row)
        layout.addWidget(home_button)

    def set_waypoints(self, points: List[Waypoint]) -> None:
        # setRowCount 和 setItem 都会触发 itemChanged，先立个旗子挡住
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
        self._clear_bad_cells()
        self._set_status("")
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
        if points is None:
            # 基底不可解析：不要用只含新点的列表整体重写，否则会抹掉其余航点
            self._report_parse_failure("添加")
            return
        points.append(Waypoint(north_m, east_m))
        self.set_waypoints(points)
        self.table.selectRow(len(points) - 1)

    def _safe_waypoints(self) -> Optional[List[Waypoint]]:
        # 用户正在单元格里打字时 text() 可能是空串或半截数字，float() 会炸。
        # 返回 None 表示解析失败，返回 [] 表示确实没有航点。
        try:
            return self.waypoints()
        except (TypeError, ValueError, AttributeError):
            return None

    def _on_item_changed(self, _item: QTableWidgetItem) -> None:
        if self._updating:
            return
        try:
            points = self.waypoints()
        except (TypeError, ValueError, AttributeError):
            self._report_parse_failure("编辑")
            return
        self._clear_bad_cells()
        self._set_status("")
        self.waypoints_changed.emit(points)

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        points = self._safe_waypoints()
        if points is None:
            self._report_parse_failure("删除")
            return
        if row < len(points):
            points.pop(row)
            self.set_waypoints(points)

    def _move_selected(self, offset: int) -> None:
        row = self.table.currentRow()
        target = row + offset
        points = self._safe_waypoints()
        if points is None:
            self._report_parse_failure("移动")
            return
        if row < 0 or target < 0 or target >= len(points):
            return
        points[row], points[target] = points[target], points[row]
        self.set_waypoints(points)
        self.table.selectRow(target)

    # ---- 内部辅助 ----

    def _first_bad_cell(self) -> Optional[Tuple[int, int, str]]:
        for row in range(self.table.rowCount()):
            for col in (1, 2):
                item = self.table.item(row, col)
                text = "" if item is None else item.text().strip()
                try:
                    float(text)
                except ValueError:
                    return row, col, text
        return None

    def _report_parse_failure(self, action: str) -> None:
        was_updating = self._updating
        self._updating = True
        try:
            bad = self._first_bad_cell()
            self._clear_bad_cells()
            if bad is None:
                self._set_status(f"航点表存在无法解析的单元格，已中止{action}")
                return
            row, col, text = bad
            col_name = "North / m" if col == 1 else "East / m"
            item = self.table.item(row, col)
            if item is not None:
                item.setBackground(self._BAD_CELL_COLOR)
            shown = text if text else "(空)"
            self._set_status(
                f"第 {row + 1} 行「{col_name}」的值 {shown} 不是合法数字，已中止{action}"
            )
        finally:
            self._updating = was_updating

    def _clear_bad_cells(self) -> None:
        was_updating = self._updating
        self._updating = True
        try:
            for row in range(self.table.rowCount()):
                for col in (1, 2):
                    item = self.table.item(row, col)
                    if item is not None:
                        item.setData(Qt.BackgroundRole, None)
        finally:
            self._updating = was_updating

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
