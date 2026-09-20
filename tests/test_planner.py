#!/usr/bin/env python3
"""Unit tests for avoid_planner.py (no ROS needed)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "ros2_ws"
        / "src"
        / "hw_insight"
    ),
)

from hw_insight.avoid_planner import (  # noqa: E402
    OccupancyGridPlanner,
    _dilate_l1,
    select_subgoal,
)


def _wall_with_gap(x=5.0, half=4, gap=0, z=0.5):
    """一堵在 x 处的墙，只在 y=gap 留一个缺口。"""
    ys = [y for y in range(-half, half + 1) if y != gap]
    return np.array([[x, float(y), z] for y in ys], dtype=float)


def _path_is_clear(planner, route, step=0.2):
    """沿航段采样，确认没有踩进占据格。"""
    for (x1, y1), (x2, y2) in zip(route, route[1:]):
        dist = float(np.hypot(x2 - x1, y2 - y1))
        n = max(2, int(dist / step))
        for t in np.linspace(0.0, 1.0, n):
            xx = x1 + (x2 - x1) * t
            yy = y1 + (y2 - y1) * t
            ix, iy = planner._world_to_grid(xx, yy)
            if not planner._is_free(ix, iy):
                return False, (round(xx, 2), round(yy, 2))
    return True, None


def test_no_grid_returns_goal_directly():
    """还没收到点云时不该假装能规划，直接给终点。"""
    planner = OccupancyGridPlanner()
    assert planner.plan((0.0, 0.0), (10.0, 5.0)) == [(10.0, 5.0)]


def test_empty_cloud_clears_grid():
    planner = OccupancyGridPlanner()
    planner.update_cloud(_wall_with_gap())
    assert planner.grid is not None
    planner.update_cloud(np.empty((0, 3)))
    assert planner.grid is None


def test_cloud_outside_height_band_is_ignored():
    """高于 height_max 的点（屋顶、树冠）不该进占据栅格。"""
    planner = OccupancyGridPlanner(height_min=-2.0, height_max=6.0)
    planner.update_cloud(np.array([[3.0, 0.0, 20.0], [3.0, 1.0, -9.0]]))
    assert planner.grid is None


def test_route_endpoints_are_the_exact_inputs():
    """首尾必须是调用方给的真实坐标，不能是栅格中心。"""
    planner = OccupancyGridPlanner(resolution=0.5, inflation_radius=0.3, margin=1.0)
    planner.update_cloud(_wall_with_gap())
    route = planner.plan((0.0, 0.0), (10.0, 0.0))
    assert route[0] == (0.0, 0.0)
    assert route[-1] == (10.0, 0.0)


def test_route_never_enters_an_occupied_cell():
    planner = OccupancyGridPlanner(resolution=0.5, inflation_radius=0.3, margin=1.0)
    planner.update_cloud(_wall_with_gap())
    route = planner.plan((0.0, 0.0), (10.0, 0.0))
    assert len(route) >= 2
    clear, bad = _path_is_clear(planner, route)
    assert clear, f"航段踩进占据格 @{bad}"


def test_goal_far_outside_the_cloud_bounding_box_is_still_reached():
    """点云只覆盖墙附近时，栅格要能扩到起点/终点，否则路径会被截在边界。"""
    planner = OccupancyGridPlanner(resolution=0.5, inflation_radius=0.3, margin=1.0)
    planner.update_cloud(_wall_with_gap())          # 包围盒仅 x∈[4,6]
    route = planner.plan((0.0, 0.0), (20.0, 0.0))   # 终点远在盒外
    assert route[-1] == (20.0, 0.0)


def test_goal_inside_an_obstacle_is_not_used_as_endpoint():
    """目标格被占时，末点应停在最近空闲格，而不是硬塞进障碍里。"""
    planner = OccupancyGridPlanner(resolution=0.5, inflation_radius=0.3, margin=1.0)
    planner.update_cloud(_wall_with_gap(gap=99))    # 无缺口，整堵墙
    route = planner.plan((0.0, 0.0), (5.0, 0.0))    # 目标正落在墙上
    if route:
        ix, iy = planner._world_to_grid(*route[-1])
        assert planner._is_free(ix, iy), "末点落在障碍里"


def test_fully_enclosed_goal_has_no_path():
    planner = OccupancyGridPlanner(resolution=0.5, inflation_radius=0.2, margin=1.0)
    ring = np.array(
        [[float(x), float(y), 0.5] for x in range(4, 9) for y in range(4, 9)
         if x in (4, 8) or y in (4, 8)],
        dtype=float,
    )
    planner.update_cloud(ring)
    assert planner.plan((0.0, 0.0), (6.0, 6.0)) == []


def test_diagonal_move_is_refused_when_both_flanks_are_blocked():
    """对角贴着两个障碍的角走会擦碰，必须拒绝。"""
    planner = OccupancyGridPlanner(resolution=1.0, inflation_radius=0.0)
    planner.origin_x = 0.0
    planner.origin_y = 0.0
    planner.width = 3
    planner.height = 3
    grid = np.zeros((3, 3), dtype=bool)
    grid[0, 1] = True   # (ix=1, iy=0) 即右邻
    grid[1, 0] = True   # (ix=0, iy=1) 即上邻
    planner.grid = grid
    # 从左下角 (0,0) 往右上角 (1,1) 对角走，两个正交邻格都被占
    assert planner._corner_ok(0, 0, 1, 1) is False
    # 正交移动不受影响
    assert planner._corner_ok(0, 0, 1, 0) is True


def test_dilate_l1_needs_no_scipy_and_grows_symmetric():
    grid = np.zeros((7, 7), dtype=bool)
    grid[3, 3] = True
    grown = _dilate_l1(grid, 2)
    # 曼哈顿半径 2 的菱形
    assert grown[3, 3] and grown[1, 3] and grown[5, 3] and grown[3, 1] and grown[3, 5]
    # 切比雪夫半径 2 的角上不该被填
    assert not grown[1, 1]
    assert grown.sum() == 13


def test_invalid_construction_params_are_rejected():
    with pytest.raises(ValueError):
        OccupancyGridPlanner(resolution=0.0)
    with pytest.raises(ValueError):
        OccupancyGridPlanner(inflation_radius=-1.0)
    with pytest.raises(ValueError):
        OccupancyGridPlanner(height_min=6.0, height_max=-2.0)


def test_select_subgoal_empty_route_falls_back_to_final_goal():
    assert select_subgoal([], (0.0, 0.0), (5.0, 5.0), 8.0, 2.0) == (5.0, 5.0)


def test_select_subgoal_takes_furthest_point_within_lookahead():
    route = [(0.0, 0.0), (2.0, 0.0), (4.0, 0.0), (20.0, 0.0)]
    # lookahead 5 只能覆盖到 (4,0)
    assert select_subgoal(route, (0.0, 0.0), (20.0, 0.0), 5.0, 1.0) == (4.0, 0.0)
    # 目标足够近时直接返回最终目标
    assert select_subgoal(route, (0.0, 0.0), (4.5, 0.0), 5.0, 1.0) == (4.5, 0.0)
