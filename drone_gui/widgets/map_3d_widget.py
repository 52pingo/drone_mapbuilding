from __future__ import annotations

import numpy as np
import pyqtgraph.opengl as gl
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QVector3D
from PySide6.QtWidgets import QLabel


SEMANTIC_COLORS = (
    (0.93, 0.71, 0.29, 1.0), (0.45, 0.84, 0.71, 1.0),
    (0.36, 0.68, 0.94, 1.0), (0.82, 0.48, 0.91, 1.0),
)

_LUT_SIZE = 256
_HEIGHT_LUT = np.empty((_LUT_SIZE, 4), dtype=np.float32)
_t = np.linspace(0.0, 1.0, _LUT_SIZE, dtype=np.float32)
_HEIGHT_LUT[:, 0] = 0.18 + 0.18 * _t
_HEIGHT_LUT[:, 1] = 0.48 + 0.36 * _t
_HEIGHT_LUT[:, 2] = 0.62 + 0.30 * _t
_HEIGHT_LUT[:, 3] = 0.82
del _t


def render_coordinates(ned_points) -> np.ndarray:
    # NED 的 D 朝下，GL 里 Z 朝上，渲染前把 Z 翻个号
    values = np.asarray(ned_points, dtype=np.float32).reshape((-1, 3))
    if not len(values):
        return values.copy()
    result = values.copy()
    result[:, 2] *= -1.0
    return result


def _finite_rows(values: np.ndarray) -> np.ndarray:
    if not len(values):
        return values
    mask = np.all(np.isfinite(values), axis=1)
    if mask.all():
        return values
    return values[mask]


class Map3DWidget(gl.GLViewWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAccessibleName("实时三维占用地图，坐标轴为北、东和向上高度")
        self.setBackgroundColor((12, 18, 22, 255))
        self.setCameraPosition(distance=120, elevation=28, azimuth=-55)
        self.point_size = 2.2
        self._points = np.empty((0, 3), dtype=np.float32)
        self._trajectory = np.empty((0, 3), dtype=np.float32)
        self._labels: list[tuple[QLabel, np.ndarray]] = []
        self._semantics_visible = True
        self._build_scene()

    def _build_scene(self) -> None:
        grid = gl.GLGridItem()
        grid.setSize(200, 200, 1)
        grid.setSpacing(10, 10, 1)
        grid.setColor((70, 91, 101, 100))
        self.addItem(grid)
        axis = gl.GLAxisItem()
        axis.setSize(20, 20, 10)
        self.addItem(axis)
        self.map_item = gl.GLScatterPlotItem(
            pos=np.empty((0, 3)), color=(0.3, 0.7, 0.8, 0.8),
            size=self.point_size, pxMode=True,
        )
        self.path_item = gl.GLLinePlotItem(
            pos=np.empty((0, 3)), color=(0.96, 0.78, 0.33, 1.0),
            width=2.5, antialias=True, mode="line_strip",
        )
        self.drone_item = gl.GLScatterPlotItem(
            pos=np.empty((0, 3)), color=(1.0, 0.35, 0.31, 1.0),
            size=11, pxMode=True,
        )
        self.semantic_item = gl.GLScatterPlotItem(
            pos=np.empty((0, 3)), color=np.empty((0, 4)), size=10, pxMode=True,
        )
        for item in (self.map_item, self.path_item, self.drone_item, self.semantic_item):
            self.addItem(item)

    @staticmethod
    def _finite_positions(items):
        """Filter items whose position_ned is a finite length-3 vector.

        Returns (kept_items, positions) where positions is (M, 3) float32.
        """
        kept: list[dict] = []
        coords: list[np.ndarray] = []
        for item in items:
            pos = item.get("position_ned")
            if pos is None:
                continue
            try:
                arr = np.asarray(pos, dtype=np.float32).reshape(-1)
            except (TypeError, ValueError):
                continue
            if arr.shape[0] != 3 or not np.all(np.isfinite(arr)):
                continue
            kept.append(item)
            coords.append(arr)
        if not coords:
            return kept, np.empty((0, 3), dtype=np.float32)
        return kept, np.stack(coords).astype(np.float32, copy=False)

    def set_points(self, points) -> None:
        rendered = render_coordinates(points)
        rendered = _finite_rows(rendered)
        self._points = rendered
        if not len(self._points):
            self.map_item.setData(pos=self._points)
            return
        # 按高度从低到高调色，低处偏蓝、高处偏黄，方便一眼看出层次
        heights = self._points[:, 2]
        low = float(heights.min())
        high = float(heights.max())
        span = high - low
        if not np.isfinite(span) or span < 0.1:
            span = 0.1
        ratio = np.clip((heights - low) / span, 0.0, 1.0)
        indices = (ratio * (_LUT_SIZE - 1)).astype(np.int32)
        colors = _HEIGHT_LUT[indices]
        self.map_item.setData(
            pos=self._points, color=colors, size=self.point_size, pxMode=True
        )

    def set_trajectory(self, ned_positions) -> None:
        rendered = render_coordinates(ned_positions)
        rendered = _finite_rows(rendered)
        self._trajectory = rendered
        self.path_item.setData(pos=self._trajectory)
        self.drone_item.setData(
            pos=self._trajectory[-1:] if len(self._trajectory) else np.empty((0, 3))
        )

    def set_semantics(self, objects: list[dict]) -> None:
        for label, _position in self._labels:
            label.deleteLater()
        self._labels = []
        values, ned_positions = self._finite_positions(objects)
        positions = (
            render_coordinates(ned_positions)
            if len(ned_positions)
            else np.empty((0, 3), dtype=np.float32)
        )
        colors = np.array([
            SEMANTIC_COLORS[index % len(SEMANTIC_COLORS)]
            for index in range(len(values))
        ], dtype=np.float32) if values else np.empty((0, 4), dtype=np.float32)
        self.semantic_item.setData(pos=positions, color=colors, size=10, pxMode=True)
        # GL 里画不了文字，用 QLabel 叠在 viewport 上，每帧投影重定位
        font = QFont("Microsoft YaHei UI", 9, QFont.Bold)
        for index, (item, position) in enumerate(zip(values, positions)):
            red, green, blue, _alpha = SEMANTIC_COLORS[index % len(SEMANTIC_COLORS)]
            color = f"rgb({int(red * 255)}, {int(green * 255)}, {int(blue * 255)})"
            label = QLabel(
                f"{item.get('label', 'object')} · {item.get('id', index + 1)}", self
            )
            label.setFont(font)
            label.setStyleSheet(
                f"color: {color}; background: rgba(10, 16, 20, 220);"
                f"border: 1px solid {color}; border-radius: 4px; padding: 2px 5px;"
            )
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            label.adjustSize()
            label.setVisible(self._semantics_visible)
            self._labels.append((label, position + np.array([0, 0, 1.2], dtype=np.float32)))
        self._position_labels()

    def set_path_visible(self, visible: bool) -> None:
        self.path_item.setVisible(visible)
        self.drone_item.setVisible(visible)

    def set_semantics_visible(self, visible: bool) -> None:
        self._semantics_visible = visible
        self.semantic_item.setVisible(visible)
        for label, _position in self._labels:
            label.setVisible(visible)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        self._position_labels()

    def _position_labels(self) -> None:
        if not self._labels:
            return
        viewport = self.getViewport()
        matrix = self.projectionMatrix(viewport, viewport) * self.viewMatrix()
        for label, position in self._labels:
            projected = matrix.map(QVector3D(*[float(value) for value in position]))
            px, py, pz = projected.x(), projected.y(), projected.z()
            if not (np.isfinite(px) and np.isfinite(py) and np.isfinite(pz)):
                label.setVisible(False)
                continue
            x = int((px + 1.0) * self.width() * 0.5)
            y = int((1.0 - py) * self.height() * 0.5)
            # z 超出 [-1, 1] 说明在相机背后，直接藏掉
            inside = -1.0 <= pz <= 1.0 and (
                -label.width() < x < self.width() and 0 < y < self.height()
            )
            label.setVisible(self._semantics_visible and inside)
            if inside:
                label.move(x + 8, y - label.height() - 8)

    def fit_scene(self) -> None:
        values = self._points if len(self._points) else self._trajectory
        if not len(values):
            self.setCameraPosition(distance=120, elevation=28, azimuth=-55)
            return
        low, high = values.min(axis=0), values.max(axis=0)
        center = (low + high) * 0.5
        if not np.all(np.isfinite(center)):
            self.setCameraPosition(distance=120, elevation=28, azimuth=-55)
            return
        distance = max(30.0, float(np.linalg.norm(high - low)) * 1.15)
        if not np.isfinite(distance):
            distance = 120.0
        self.setCameraPosition(
            pos=QVector3D(*[float(value) for value in center]),
            distance=distance, elevation=28, azimuth=-55,
        )

    def top_view(self) -> None:
        self.setCameraPosition(elevation=90, azimuth=-90)

    def set_point_size(self, size: int) -> None:
        self.point_size = float(size) / 10.0
        self.map_item.setData(size=self.point_size)
