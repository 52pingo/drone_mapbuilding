"""Tests for conservative autonomous landing safety decisions."""

import math

from hw_insight.mission_safety import is_landed_candidate, should_request_disarm


def test_landed_candidate_requires_ground_proximity_and_low_velocity():
    assert is_landed_candidate(
        z=0.08,
        ground_z=0.0,
        vx=0.05,
        vy=-0.04,
        vz=0.03,
        z_tolerance=0.4,
        xy_speed_tolerance=0.3,
        z_speed_tolerance=0.2,
    )
    assert not is_landed_candidate(
        z=-3.0,
        ground_z=0.0,
        vx=0.0,
        vy=0.0,
        vz=0.0,
        z_tolerance=0.4,
        xy_speed_tolerance=0.3,
        z_speed_tolerance=0.2,
    )
    assert not is_landed_candidate(
        z=0.0,
        ground_z=0.0,
        vx=0.8,
        vy=0.0,
        vz=0.0,
        z_tolerance=0.4,
        xy_speed_tolerance=0.3,
        z_speed_tolerance=0.2,
    )


def test_landed_candidate_rejects_invalid_telemetry():
    assert not is_landed_candidate(
        z=math.nan,
        ground_z=0.0,
        vx=0.0,
        vy=0.0,
        vz=0.0,
        z_tolerance=0.4,
        xy_speed_tolerance=0.3,
        z_speed_tolerance=0.2,
    )


def test_disarm_fallback_requires_both_timeout_and_stable_grounding():
    assert not should_request_disarm(44.9, 3.0, 45.0, 2.0)
    assert not should_request_disarm(45.0, 1.9, 45.0, 2.0)
    assert should_request_disarm(45.0, 2.0, 45.0, 2.0)
