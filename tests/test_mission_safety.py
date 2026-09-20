#!/usr/bin/env python3
"""Unit tests for mission_safety.py — 触地判定与解锁兜底。

这套逻辑决定「什么时候允许解锁」，判错就是飞机在地上不停车或空中被解锁，
所以除了正常路径，脏遥测（None / NaN / inf）也逐个钉住。
"""

import math
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "ros2_ws"
        / "src"
        / "hw_insight"
    ),
)

from hw_insight.mission_safety import (  # noqa: E402
    is_landed_candidate,
    should_request_disarm,
)

TOL = dict(z_tolerance=0.4, xy_speed_tolerance=0.3, z_speed_tolerance=0.2)


def test_landed_candidate_requires_ground_proximity_and_low_velocity():
    assert is_landed_candidate(z=0.08, ground_z=0.0, vx=0.05, vy=-0.04, vz=0.03, **TOL)
    assert not is_landed_candidate(z=-3.0, ground_z=0.0, vx=0.0, vy=0.0, vz=0.0, **TOL)
    assert not is_landed_candidate(z=0.0, ground_z=0.0, vx=0.8, vy=0.0, vz=0.0, **TOL)


def test_landed_candidate_rejects_nan():
    assert not is_landed_candidate(
        z=math.nan, ground_z=0.0, vx=0.0, vy=0.0, vz=0.0, **TOL)


def test_landed_candidate_rejects_none_telemetry():
    """位置话题还没上来时字段是 None，不能抛 TypeError。"""
    assert not is_landed_candidate(
        z=None, ground_z=0.0, vx=0.0, vy=0.0, vz=0.0, **TOL)
    assert not is_landed_candidate(
        z=0.0, ground_z=None, vx=None, vy=None, vz=None, **TOL)


def test_landed_candidate_rejects_infinity():
    assert not is_landed_candidate(
        z=math.inf, ground_z=0.0, vx=0.0, vy=0.0, vz=0.0, **TOL)


def test_landed_candidate_rejects_non_numeric():
    assert not is_landed_candidate(
        z="0.1", ground_z=0.0, vx=0.0, vy=0.0, vz=0.0, **TOL)
    assert not is_landed_candidate(
        z=True, ground_z=0.0, vx=0.0, vy=0.0, vz=0.0, **TOL)


def test_disarm_fallback_requires_both_timeout_and_stable_grounding():
    assert not should_request_disarm(44.9, 3.0, 45.0, 2.0)
    assert not should_request_disarm(45.0, 1.9, 45.0, 2.0)
    assert should_request_disarm(45.0, 2.0, 45.0, 2.0)


def test_disarm_fallback_rejects_nan_timers():
    """NaN 跟任何数比较都是 False；不挡住的话兜底永不触发，飞机停在地上不解锁。"""
    assert not should_request_disarm(math.nan, 3.0, 45.0, 2.0)
    assert not should_request_disarm(60.0, math.nan, 45.0, 2.0)


def test_disarm_fallback_rejects_none_timers():
    assert not should_request_disarm(None, 3.0, 45.0, 2.0)
    assert not should_request_disarm(60.0, None, 45.0, 2.0)
