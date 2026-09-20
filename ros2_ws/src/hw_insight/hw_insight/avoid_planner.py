#!/usr/bin/env python3
"""栅格 A* 全局规划，给局部 VFH 提供子目标序列。

把 OctoMap 点云压成一张二维占据栅格，按机器人半径膨胀障碍，
然后跑 A*。坐标系沿用 PX4 本地 NED 的水平分量。
"""

from __future__ import annotations

import heapq
import math

import numpy as np


# 8 邻域，先正交后对角：对角那两个要额外查拐角，见 _corner_ok。
_NEIGHBORS = (
    (1, 0), (0, 1), (-1, 0), (0, -1),
    (1, 1), (-1, 1), (-1, -1), (1, -1),
)


def _dilate_l1(grid: np.ndarray, radius: int) -> np.ndarray:
    """按曼哈顿距离膨胀 radius 圈（等价于 scipy 默认十字结构迭代 radius 次）。

    自己写是为了不引入 scipy —— 之前那句函数内 `from scipy import ndimage`
    在没装 scipy 的环境里必崩，而两个 requirements 文件都没声明它。
    """
    out = grid
    for _ in range(radius):
        grown = out.copy()
        grown[1:, :] |= out[:-1, :]
        grown[:-1, :] |= out[1:, :]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


class OccupancyGridPlanner:
    def __init__(
        self,
        resolution: float = 0.5,
        inflation_radius: float = 1.0,
        robot_radius: float = 0.6,
        height_min: float = -2.0,
        height_max: float = 6.0,
        margin: float = 5.0,
    ):
        if resolution <= 0:
            raise ValueError(f'resolution must be > 0, got {resolution}')
        if inflation_radius < 0:
            raise ValueError(f'inflation_radius must be >= 0, got {inflation_radius}')
        if height_max <= height_min:
            raise ValueError(f'height_max ({height_max}) must exceed height_min ({height_min})')

        self.resolution = resolution
        self.inflation_radius = inflation_radius
        self.robot_radius = robot_radius
        self.height_min = height_min
        self.height_max = height_max
        self.margin = margin

        self.origin_x = 0.0
        self.origin_y = 0.0
        self.grid: np.ndarray | None = None
        self.width = 0
        self.height = 0
        self.updated_at = 0.0

    def update_cloud(self, points: np.ndarray, timestamp: float = 0.0) -> None:
        """用一帧点云重建栅格。points 是 Nx3 的 NED 世界坐标。"""
        if points.size == 0:
            self.grid = None
            return

        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        mask = (z >= self.height_min) & (z <= self.height_max)
        # NaN 参与比较恒为 False，会被这条掩码一并滤掉
        if not mask.any():
            self.grid = None
            return
        xm, ym = x[mask], y[mask]

        min_x = float(xm.min()) - self.margin
        max_x = float(xm.max()) + self.margin
        min_y = float(ym.min()) - self.margin
        max_y = float(ym.max()) + self.margin

        self.origin_x = min_x
        self.origin_y = min_y
        self.width = max(1, int(math.ceil((max_x - min_x) / self.resolution)))
        self.height = max(1, int(math.ceil((max_y - min_y) / self.resolution)))

        grid = np.zeros((self.height, self.width), dtype=bool)
        ix = np.clip(((xm - self.origin_x) / self.resolution).astype(int), 0, self.width - 1)
        iy = np.clip(((ym - self.origin_y) / self.resolution).astype(int), 0, self.height - 1)
        grid[iy, ix] = True

        cells = int(math.ceil(self.inflation_radius / self.resolution))
        if cells > 0:
            grid = _dilate_l1(grid, cells)

        self.grid = grid
        self.updated_at = timestamp

    def _world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        return (
            int((x - self.origin_x) / self.resolution),
            int((y - self.origin_y) / self.resolution),
        )

    def _grid_to_world(self, ix: int, iy: int) -> tuple[float, float]:
        return (
            self.origin_x + (ix + 0.5) * self.resolution,
            self.origin_y + (iy + 0.5) * self.resolution,
        )

    def _is_free(self, ix: int, iy: int) -> bool:
        if self.grid is None:
            return True
        if ix < 0 or ix >= self.width or iy < 0 or iy >= self.height:
            return False
        return not self.grid[iy, ix]

    def _corner_ok(self, cx: int, cy: int, dx: int, dy: int) -> bool:
        """对角移动时，两侧正交邻格都得空着，否则会从障碍的角上蹭过去。"""
        if dx == 0 or dy == 0:
            return True
        return self._is_free(cx + dx, cy) and self._is_free(cx, cy + dy)

    def _grow_to_cover(self, *points: tuple[float, float]) -> None:
        """把栅格扩到至少覆盖这些世界点，新增格按空闲处理。

        栅格本来只覆盖点云包围盒。起点或目标一旦落在盒子外，
        A* 会走到边界就到头，最后一段变成横穿未知区域的直线 —— 而且不报错。
        """
        if self.grid is None:
            return
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        right_edge = self.origin_x + self.width * self.resolution
        top_edge = self.origin_y + self.height * self.resolution

        new_min_x = min(self.origin_x, min(xs) - self.margin)
        new_min_y = min(self.origin_y, min(ys) - self.margin)
        new_max_x = max(right_edge, max(xs) + self.margin)
        new_max_y = max(top_edge, max(ys) + self.margin)

        left = int(math.ceil((self.origin_x - new_min_x) / self.resolution))
        bottom = int(math.ceil((self.origin_y - new_min_y) / self.resolution))
        right = int(math.ceil((new_max_x - right_edge) / self.resolution))
        top = int(math.ceil((new_max_y - top_edge) / self.resolution))
        if not (left or bottom or right or top):
            return

        self.grid = np.pad(self.grid, ((bottom, top), (left, right)), constant_values=False)
        self.origin_x -= left * self.resolution
        self.origin_y -= bottom * self.resolution
        self.width += left + right
        self.height += bottom + top

    def _nearest_free(self, ix: int, iy: int) -> tuple[int, int]:
        if self._is_free(ix, iy):
            return ix, iy
        # 一圈一圈往外找。上限取栅格对角线，再远就没意义了。
        for r in range(1, max(self.width, self.height) + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if abs(dx) != r and abs(dy) != r:
                        continue
                    if self._is_free(ix + dx, iy + dy):
                        return ix + dx, iy + dy
        return ix, iy

    def plan(
        self,
        start: tuple[float, float],
        goal: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """返回 start→goal 的航点序列；无路可走时返回空列表。"""
        if self.grid is None:
            return [goal]

        self._grow_to_cover(start, goal)

        raw_gx, raw_gy = self._world_to_grid(*goal)
        exact_goal = self._is_free(raw_gx, raw_gy)
        sx, sy = self._nearest_free(*self._world_to_grid(*start))
        gx, gy = self._nearest_free(raw_gx, raw_gy)

        def heuristic(ix: int, iy: int) -> float:
            return math.hypot(gx - ix, gy - iy) * self.resolution

        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score = {(sx, sy): 0.0}
        open_set = [(heuristic(sx, sy), 0, (sx, sy))]
        counter = 0
        goal_node = (gx, gy)

        while open_set:
            _, _, current = heapq.heappop(open_set)
            if current == goal_node:
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return self._finalize(
                    [self._grid_to_world(ix, iy) for ix, iy in path],
                    start, goal, exact_goal)

            cx, cy = current
            for dx, dy in _NEIGHBORS:
                nx, ny = cx + dx, cy + dy
                if not self._is_free(nx, ny) or not self._corner_ok(cx, cy, dx, dy):
                    continue
                tentative = g_score[current] + math.hypot(dx, dy) * self.resolution
                nxt = (nx, ny)
                if tentative < g_score.get(nxt, float('inf')):
                    came_from[nxt] = current
                    g_score[nxt] = tentative
                    counter += 1
                    heapq.heappush(open_set, (tentative + heuristic(nx, ny), counter, nxt))

        return []

    @staticmethod
    def _finalize(
        waypoints: list[tuple[float, float]],
        start: tuple[float, float],
        goal: tuple[float, float],
        exact_goal: bool,
    ) -> list[tuple[float, float]]:
        """简化折线，并把首尾换成真实起点/终点。

        A* 只知道栅格中心，直接用会让控制器先朝一个偏了半格的目标飞。
        目标格本身被占时不能用真实目标收尾 —— 那等于把终点设进障碍里，
        此时保留 _nearest_free 找到的空闲格。
        """
        if not waypoints:
            return waypoints
        simplified = _simplify_waypoints(waypoints)
        simplified[0] = (float(start[0]), float(start[1]))
        if exact_goal:
            simplified[-1] = (float(goal[0]), float(goal[1]))
        return simplified


def _simplify_waypoints(
    waypoints: list[tuple[float, float]],
    angle_threshold: float = 0.15,
) -> list[tuple[float, float]]:
    """丢掉落在直线上的中间点。"""
    if len(waypoints) <= 2:
        return waypoints
    simplified = [waypoints[0]]
    for i in range(1, len(waypoints) - 1):
        prev = simplified[-1]
        curr = waypoints[i]
        nxt = waypoints[i + 1]
        a1 = math.atan2(curr[1] - prev[1], curr[0] - prev[0])
        a2 = math.atan2(nxt[1] - curr[1], nxt[0] - curr[0])
        if abs(math.atan2(math.sin(a2 - a1), math.cos(a2 - a1))) > angle_threshold:
            simplified.append(curr)
    simplified.append(waypoints[-1])
    return simplified


def select_subgoal(
    route: list[tuple[float, float]],
    pos: tuple[float, float],
    final_goal: tuple[float, float],
    lookahead: float,
    arrived_dist: float,
) -> tuple[float, float]:
    """在 route 上取离 pos 最近的点，再往前够到 lookahead 以内的最远点。"""
    if not route:
        return final_goal

    best_i = min(
        range(len(route)),
        key=lambda i: math.hypot(route[i][0] - pos[0], route[i][1] - pos[1]),
    )

    chosen = route[best_i]
    for i in range(best_i, len(route)):
        if math.hypot(route[i][0] - pos[0], route[i][1] - pos[1]) <= lookahead:
            chosen = route[i]
        else:
            break

    if math.hypot(chosen[0] - final_goal[0], chosen[1] - final_goal[1]) < arrived_dist:
        return final_goal
    return chosen
