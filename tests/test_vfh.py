#!/usr/bin/env python3
"""Unit tests for avoid_vfh.py (no ROS needed)."""

import math
import sys
from pathlib import Path

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

from hw_insight.avoid_vfh import (
    VfhParams,
    apply_recovery_hysteresis,
    binary_histogram,
    blend_corridor_heading,
    build_polar_histogram,
    compute_vfh_motion,
    find_valleys,
    RECOVERY_FLIP_LIMIT,
)


def test_recovery_hysteresis_ignores_noise_between_neighbouring_gaps():
    """The case the flight data actually showed.

    Stuck in a gap that is open both ways, best_gap_heading alternated between
    +0.382 and -0.229 rad -- 0.61 rad apart, i.e. the same side as far as the
    drone is concerned.  Without hysteresis it turned left for 4s, right for 4s,
    and oscillated in place 4314 times.
    """
    held = 0.382
    theta, count = apply_recovery_hysteresis(-0.229, held, 0)
    assert theta == held            # kept the held direction
    assert count == 1

    # ... and keeps holding it as the noise keeps flipping.
    for expected in (2, 3):
        theta, count = apply_recovery_hysteresis(0.382, theta, count)
        assert theta == held
        assert count == expected


def test_recovery_hysteresis_releases_after_the_flip_limit():
    """A direction that never helps must eventually be given up."""
    held = 0.382
    count = 0
    for _ in range(RECOVERY_FLIP_LIMIT - 1):
        held, count = apply_recovery_hysteresis(-0.229, held, count)
    assert count == RECOVERY_FLIP_LIMIT - 1
    theta, count = apply_recovery_hysteresis(-0.229, held, count)
    assert theta == pytest.approx(-0.229)   # released, takes the other side
    assert count == 0


def test_recovery_hysteresis_takes_a_genuinely_new_direction_at_once():
    """An obstacle appearing on the held side is not noise; switch immediately."""
    theta, count = apply_recovery_hysteresis(2.0, -0.5, 1)
    assert theta == pytest.approx(2.0)
    assert count == 0


def test_recovery_hysteresis_first_call_always_takes_the_candidate():
    theta, count = apply_recovery_hysteresis(0.7, None, 0)
    assert theta == pytest.approx(0.7)
    assert count == 0


def test_recovery_hysteresis_wraps_across_pi():
    """-3.0 and +3.0 are 0.28 rad apart, not nearly a full turn."""
    theta, count = apply_recovery_hysteresis(-3.0, 3.0, 0)
    assert theta == pytest.approx(3.0)
    assert count == 1
import numpy as np

PARAMS = VfhParams(
    avoid_front=10.0,
    avoid_brake=5.0,
    avoid_near=2.5,
    cruise_speed=2.5,
    max_speed=3.5,
    creep_speed=0.5,
    backup_speed=0.8,
    fov_deg=90.0,
    bins=72,
    robot_width=1.0,
    safety_radius=1.0,
    threshold_high=0.65,
    threshold_low=0.30,
    w_goal=5.0,
    w_current=1.0,
    w_smooth=2.0,
    w_obstacle=3.0,
)


def make_depth(h=150, w=400, fill=30.0):
    return np.full((h, w), fill, dtype=np.float32)


def test_open_space():
    depth = make_depth()
    r = compute_vfh_motion(
        depth, PARAMS, body_heading=0.0, goal_x=30.0, goal_y=10.0,
        pos_x=0.0, pos_y=0.0, last_theta=0.0,
    )
    assert r["action"] == "go", r
    assert r["forward_speed"] == PARAMS.cruise_speed
    assert abs(r["theta"] - math.atan2(10.0, 30.0)) < 0.05
    print("open_space ok")


def test_wall_left_open_right():
    depth = make_depth()
    # Fill left half with close obstacles -> should steer right (positive theta).
    depth[:, :200] = 3.0
    r = compute_vfh_motion(
        depth, PARAMS, body_heading=0.0, goal_x=30.0, goal_y=0.0,
        pos_x=0.0, pos_y=0.0, last_theta=0.0,
    )
    assert r["theta"] > 0.05, r
    assert r["forward_speed"] == PARAMS.cruise_speed
    print("wall_left_open_right ok")


def test_wall_center_open_left():
    depth = make_depth()
    # Obstacle in the center -> either side is open; expect a distinct offset.
    depth[:, 160:240] = 3.0
    r = compute_vfh_motion(
        depth, PARAMS, body_heading=0.0, goal_x=30.0, goal_y=0.0,
        pos_x=0.0, pos_y=0.0, last_theta=0.0,
    )
    assert abs(r["theta"]) > 0.05, r
    # With a 3 m obstacle ahead the planner must slow down (creep).
    assert r["forward_speed"] > 0.0
    print("wall_center_open_left ok")


def test_close_obstacle_avoid():
    depth = make_depth()
    # Close obstacle in the centre front -> steer around it while still moving.
    depth[:, 160:240] = 3.0
    r = compute_vfh_motion(
        depth, PARAMS, body_heading=0.0, goal_x=30.0, goal_y=0.0,
        pos_x=0.0, pos_y=0.0, last_theta=0.0,
    )
    assert abs(r["theta"]) > 0.1, r
    assert r["forward_speed"] > 0.0
    print("close_obstacle_avoid ok")


def test_fully_blocked_backup():
    depth = make_depth()
    # Entire field of view blocked at close range -> back up.
    depth[:, :] = 1.5
    r = compute_vfh_motion(
        depth, PARAMS, body_heading=0.0, goal_x=30.0, goal_y=0.0,
        pos_x=0.0, pos_y=0.0, last_theta=0.0,
    )
    assert r["forward_speed"] < 0.0, r
    print("fully_blocked_backup ok")


def test_goal_behind_turn_in_place():
    depth = make_depth()
    r = compute_vfh_motion(
        depth, PARAMS, body_heading=0.0, goal_x=-10.0, goal_y=0.0,
        pos_x=0.0, pos_y=0.0, last_theta=0.0,
    )
    assert r["action"] == "turn", r
    assert abs(r["vx"]) < 0.01 and abs(r["vy"]) < 0.01
    assert abs(r["goal_theta"] - math.pi) < 0.1
    assert abs(r["yaw_rate"]) > 0.1
    print("goal_behind_turn_in_place ok")


def test_recovery_toward_gap():
    depth = make_depth()
    # Block everything except a gap on the left.
    depth[:, :] = 2.0
    depth[:, 20:80] = np.inf
    r = compute_vfh_motion(
        depth, PARAMS, body_heading=0.0, goal_x=30.0, goal_y=0.0,
        pos_x=0.0, pos_y=0.0, last_theta=0.0,
        recovery_theta=0.6,
    )
    assert r["action"] == "recover"
    assert abs(r["theta"] - 0.6) < 0.05
    print("recovery_toward_gap ok")


def test_valley_detection():
    depth = make_depth()
    depth[:, :150] = 1.5
    depth[:, 250:] = 1.5
    centers, hist, _, _ = build_polar_histogram(depth, PARAMS)
    binary = binary_histogram(hist, PARAMS)
    valleys = find_valleys(binary, centers, PARAMS)
    assert len(valleys) >= 1
    # The free valley should be roughly in the centre (around 0 rad).
    assert any(abs(v["centre"]) < 0.3 for v in valleys)
    print("valley_detection ok")


def test_goal_behind_uses_clear_side():
    # Goal behind, obstacle on the left -> should pick right turn (positive theta).
    depth = make_depth()
    depth[:, :200] = 2.0
    r = compute_vfh_motion(
        depth, PARAMS, body_heading=0.0, goal_x=-10.0, goal_y=0.0,
        pos_x=0.0, pos_y=0.0, last_theta=0.0,
    )
    assert r["action"] == "turn"
    assert r["theta"] > 0.1, r
    assert r["forward_speed"] == 0.0
    assert abs(r["yaw_rate"]) > 0.0
    print("goal_behind_uses_clear_side ok")


def test_corridor_heading_uses_body_frame():
    # A zero corridor angle points along the body, not along the world-frame
    # goal.  The old node implementation incorrectly added theta to the goal.
    heading = blend_corridor_heading(
        body_heading=math.pi / 2.0,
        goal_heading=0.0,
        corridor_theta=0.0,
        corridor_weight=1.0,
        max_steer=2.5,
    )
    assert abs(heading - math.pi / 2.0) < 1e-6

    goal_only = blend_corridor_heading(
        body_heading=math.pi / 2.0,
        goal_heading=0.0,
        corridor_theta=0.5,
        corridor_weight=0.0,
        max_steer=2.5,
    )
    assert abs(goal_only) < 1e-6
    print("corridor_heading_uses_body_frame ok")


if __name__ == "__main__":
    test_open_space()
    test_wall_left_open_right()
    test_wall_center_open_left()
    test_close_obstacle_avoid()
    test_fully_blocked_backup()
    test_goal_behind_turn_in_place()
    test_recovery_toward_gap()
    test_valley_detection()
    test_goal_behind_uses_clear_side()
    test_corridor_heading_uses_body_frame()
    print("all vfh tests passed")
