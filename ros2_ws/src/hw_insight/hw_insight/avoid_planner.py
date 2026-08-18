#!/usr/bin/env python3
"""2-D global planner on OctoMap point-cloud occupancy.

Builds a coarse occupancy grid from the latched OctoMap point cloud, inflates
obstacles by a safety radius, and runs A* to produce a sequence of sub-goals
for the local VFH controller.
"""

from __future__ import annotations

import heapq
import math
from typing import List, Optional, Tuple

import numpy as np


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
        self.resolution = resolution
        self.inflation_radius = inflation_radius
        self.robot_radius = robot_radius
        self.height_min = height_min
        self.height_max = height_max
        self.margin = margin

        self.origin_x = 0.0
        self.origin_y = 0.0
        self.grid: Optional[np.ndarray] = None
        self.width = 0
        self.height = 0
        self.updated_at = 0.0

    def update_cloud(self, points: np.ndarray, timestamp: float = 0.0) -> None:
        """points: Nx3 array in world/NED frame."""
        if points.size == 0:
            self.grid = None
            return
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        mask = (z >= self.height_min) & (z <= self.height_max)
        if not mask.any():
            self.grid = None
            return
        xm, ym = x[mask], y[mask]

        min_x, max_x = float(xm.min()) - self.margin, float(xm.max()) + self.margin
        min_y, max_y = float(ym.min()) - self.margin, float(ym.max()) + self.margin

        self.origin_x = min_x
        self.origin_y = min_y
        self.width = max(1, int(math.ceil((max_x - min_x) / self.resolution)))
        self.height = max(1, int(math.ceil((max_y - min_y) / self.resolution)))

        grid = np.zeros((self.height, self.width), dtype=np.uint8)
        ix = np.clip(((xm - self.origin_x) / self.resolution).astype(int), 0, self.width - 1)
        iy = np.clip(((ym - self.origin_y) / self.resolution).astype(int), 0, self.height - 1)
        grid[iy, ix] = 1

        # Inflate obstacles.
        cells = int(math.ceil(self.inflation_radius / self.resolution))
        if cells > 0:
            from scipy import ndimage
            grid = ndimage.binary_dilation(grid, iterations=cells).astype(np.uint8)

        self.grid = grid
        self.updated_at = timestamp

    def _world_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        ix = int((x - self.origin_x) / self.resolution)
        iy = int((y - self.origin_y) / self.resolution)
        return ix, iy

    def _grid_to_world(self, ix: int, iy: int) -> Tuple[float, float]:
        x = self.origin_x + (ix + 0.5) * self.resolution
        y = self.origin_y + (iy + 0.5) * self.resolution
        return x, y

    def _is_free(self, ix: int, iy: int) -> bool:
        if self.grid is None:
            return True
        if ix < 0 or ix >= self.width or iy < 0 or iy >= self.height:
            return False
        return self.grid[iy, ix] == 0

    def _nearest_free(self, ix: int, iy: int) -> Tuple[int, int]:
        if self._is_free(ix, iy):
            return ix, iy
        # Spiral search.
        for r in range(1, max(self.width, self.height)):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if abs(dx) != r and abs(dy) != r:
                        continue
                    nx, ny = ix + dx, iy + dy
                    if self._is_free(nx, ny):
                        return nx, ny
        return ix, iy

    def plan(
        self,
        start: Tuple[float, float],
        goal: Tuple[float, float],
    ) -> List[Tuple[float, float]]:
        """Return a list of waypoints from start to goal, or empty if no path."""
        if self.grid is None:
            return [goal]

        sx, sy = self._world_to_grid(*start)
        gx, gy = self._world_to_grid(*goal)
        sx, sy = self._nearest_free(sx, sy)
        gx, gy = self._nearest_free(gx, gy)

        open_set = [(0.0, 0, (sx, sy))]
        came_from: dict = {}
        g_score = {(sx, sy): 0.0}
        f_score = {(sx, sy): math.hypot(gx - sx, gy - sy)}
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
                waypoints = [self._grid_to_world(ix, iy) for ix, iy in path]
                return _simplify_waypoints(waypoints)

            cx, cy = current
            for dx, dy in _NEIGHBORS:
                nx, ny = cx + dx, cy + dy
                if not self._is_free(nx, ny):
                    continue
                step = math.hypot(dx, dy) * self.resolution
                tentative = g_score[current] + step
                nxt = (nx, ny)
                if tentative < g_score.get(nxt, float('inf')):
                    came_from[nxt] = current
                    g_score[nxt] = tentative
                    f = tentative + math.hypot(gx - nx, gy - ny) * self.resolution
                    counter += 1
                    heapq.heappush(open_set, (f, counter, nxt))

        return []


_NEIGHBORS = [
    (1, 0), (1, 1), (0, 1), (-1, 1),
    (-1, 0), (-1, -1), (0, -1), (1, -1),
]


def _simplify_waypoints(
    waypoints: List[Tuple[float, float]],
    angle_threshold: float = 0.15,
) -> List[Tuple[float, float]]:
    """Drop intermediate waypoints that lie roughly on a straight line."""
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
    route: List[Tuple[float, float]],
    pos: Tuple[float, float],
    final_goal: Tuple[float, float],
    lookahead: float,
    arrived_dist: float,
) -> Tuple[float, float]:
    """Pick the furthest waypoint on the route within lookahead of pos."""
    if not route:
        return final_goal
    # Find closest waypoint index.
    best_i = min(range(len(route)), key=lambda i: math.hypot(route[i][0] - pos[0], route[i][1] - pos[1]))
    chosen = route[best_i]
    for i in range(best_i, len(route)):
        if math.hypot(route[i][0] - pos[0], route[i][1] - pos[1]) <= lookahead:
            chosen = route[i]
        else:
            break
    if math.hypot(chosen[0] - final_goal[0], chosen[1] - final_goal[1]) < arrived_dist:
        return final_goal
    return chosen
