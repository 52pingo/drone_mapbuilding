from __future__ import annotations

import math
from typing import List

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from drone_gui.models import Waypoint


class WaypointCanvas(QGraphicsView):
    waypoint_added = Signal(float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAccessibleName("NED 航点规划画布")
        self.setToolTip("双击添加航点；滚轮缩放；拖动空白区域平移")
        self._waypoints: List[Waypoint] = []
        self.scene().setSceneRect(-750, -750, 1500, 1500)

    @staticmethod
    def world_to_scene(point: Waypoint) -> QPointF:
        return QPointF(point.east_m, -point.north_m)

    @staticmethod
    def scene_to_world(point: QPointF) -> Waypoint:
        return Waypoint(-point.y(), point.x())

    def set_waypoints(self, points: List[Waypoint]) -> None:
        self._waypoints = list(points)
        self._redraw()

    def _redraw(self) -> None:
        scene = self.scene()
        scene.clear()
        route = [Waypoint(0, 0), *self._waypoints]
        path = QPainterPath(self.world_to_scene(route[0]))
        for point in route[1:]:
            path.lineTo(self.world_to_scene(point))
        scene.addPath(path, QPen(QColor("#4FB4C1"), 2.2))
        self._add_marker(Waypoint(0, 0), "H", QColor("#F2C56D"))
        for index, point in enumerate(self._waypoints, 1):
            self._add_marker(point, str(index), QColor("#76D6B3"))

    def _add_marker(self, point: Waypoint, label: str, color: QColor) -> None:
        position = self.world_to_scene(point)
        marker = self.scene().addEllipse(
            QRectF(position.x() - 6, position.y() - 6, 12, 12),
            QPen(color, 2),
            QBrush(color),
        )
        marker.setToolTip(
            f"{label}: North {point.north_m:.2f} m, East {point.east_m:.2f} m"
        )
        text = self.scene().addText(label)
        text.setDefaultTextColor(QColor("#F4F8FA"))
        text.setPos(position.x() + 8, position.y() - 13)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor("#0E171C"))
        step = 50
        left = math.floor(rect.left() / step) * step
        top = math.floor(rect.top() / step) * step
        painter.setPen(QPen(QColor("#1F3038"), 0))
        x = left
        while x < rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
        y = top
        while y < rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step
        painter.setPen(QPen(QColor("#4A606B"), 0))
        painter.drawLine(QPointF(0, rect.top()), QPointF(0, rect.bottom()))
        painter.drawLine(QPointF(rect.left(), 0), QPointF(rect.right(), 0))

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            point = self.scene_to_world(self.mapToScene(event.position().toPoint()))
            self.waypoint_added.emit(point.north_m, point.east_m)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def fit_route(self) -> None:
        points = [self.world_to_scene(Waypoint(0, 0))]
        points.extend(self.world_to_scene(point) for point in self._waypoints)
        if not points:
            return
        min_x = min(point.x() for point in points) - 60
        max_x = max(point.x() for point in points) + 60
        min_y = min(point.y() for point in points) - 60
        max_y = max(point.y() for point in points) + 60
        self.fitInView(QRectF(min_x, min_y, max_x - min_x, max_y - min_y), Qt.KeepAspectRatio)
