#!/usr/bin/env python3
"""Unit tests for mission_control.py — 操作员 保持/恢复/降落 的状态迁移表。

着重点是「哪些状态允许被打断」和「恢复时回到哪里」，
这两件事判错会让飞机在错误的状态下接受指令。
"""

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

from hw_insight.mission_control import (  # noqa: E402
    HOLDABLE_STATES,
    LANDABLE_STATES,
    decide_control,
)


def test_hold_and_resume_restore_navigation_state():
    hold = decide_control('hold', 'NAVIGATE')
    assert hold.accepted
    assert (hold.next_state, hold.resume_state) == ('HOLD', 'NAVIGATE')

    resume = decide_control('resume', hold.next_state, hold.resume_state)
    assert resume.accepted
    assert (resume.next_state, resume.resume_state) == ('NAVIGATE', None)


def test_hold_is_rejected_during_takeoff_and_landing():
    assert not decide_control('hold', 'TAKEOFF').accepted
    assert not decide_control('hold', 'LAND').accepted


def test_land_enters_existing_land_state_from_hold():
    result = decide_control('land', 'HOLD', 'NAVIGATE')
    assert result.accepted
    assert result.next_state == 'LAND'
    assert result.resume_state is None


def test_land_is_rejected_before_takeoff_or_after_done():
    assert not decide_control('land', 'WAIT').accepted
    assert not decide_control('land', 'DONE').accepted


def test_unknown_action_is_rejected():
    result = decide_control('自爆', 'NAVIGATE')
    assert not result.accepted
    assert result.next_state == 'NAVIGATE'


def test_action_and_state_are_normalised():
    """UI 传来的大小写和空格不该影响判定。"""
    assert decide_control('  HOLD  ', ' navigate ').accepted
    assert decide_control('LAND', 'hold').accepted


def test_resume_without_a_hold_target_is_rejected():
    assert not decide_control('resume', 'HOLD', None).accepted
    assert not decide_control('resume', 'NAVIGATE').accepted


def test_landable_covers_every_airborne_state_avoid_node_publishes():
    """avoid_node 实际只发这几个状态，降落判定必须覆盖其中所有空中态。"""
    airborne = {'TAKEOFF', 'NAVIGATE', 'SCAN', 'HOVER'}
    assert airborne <= LANDABLE_STATES
    # 地面/终态不该接受降落指令
    assert not ({'WAIT', 'LAND', 'DONE'} & LANDABLE_STATES)


def test_holdable_is_a_subset_of_landable():
    """能停的状态一定也能降落，否则操作员会撞上「能停不能降」的死角。"""
    assert HOLDABLE_STATES <= LANDABLE_STATES
