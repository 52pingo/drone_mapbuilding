"""Tests for ground_filter.py (no ROS needed).

The synthetic scenes are built from the same geometry the filter inverts, so a
sign error or a wrong FOV convention shows up as a wrong altitude or as ground
surviving the strip, rather than as a subtly worse avoidance decision in flight.
"""

import math
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

from hw_insight.ground_filter import (  # noqa: E402
    estimate_altitude,
    expected_ground_depth,
    row_elevations_deg,
    strip_ground,
    vertical_fov_deg,
)

HEIGHT, WIDTH = 240, 320
FOV_H = 90.0
FOV_V = vertical_fov_deg(WIDTH, HEIGHT, FOV_H)
PITCH = -40.0


def flat_ground(altitude=15.0):
    """A depth image of nothing but flat ground under a hovering camera."""
    ground = expected_ground_depth(HEIGHT, FOV_V, PITCH, altitude)
    return np.repeat(ground[:, None], WIDTH, axis=1).astype(np.float32)


def test_vertical_fov_matches_the_4_by_3_aspect():
    # 90 deg horizontal over 4:3 gives the familiar 73.7 deg vertical.
    assert FOV_V == pytest.approx(73.74, abs=0.05)


def test_row_elevations_run_from_the_top_of_frame_downward():
    elevations = row_elevations_deg(HEIGHT, FOV_V, PITCH)
    assert elevations[0] == pytest.approx(PITCH + FOV_V / 2.0)   # -3.13 deg
    assert elevations[-1] < PITCH - FOV_V / 2.0 + 1.0
    assert np.all(np.diff(elevations) < 0)                       # top to bottom


def test_expected_ground_depth_is_nan_above_the_horizon():
    expected = expected_ground_depth(HEIGHT, FOV_V, PITCH, 15.0)
    elevations = row_elevations_deg(HEIGHT, FOV_V, PITCH)
    assert np.isnan(expected[elevations >= 0.0]).all()
    below = expected[elevations < 0.0]
    assert np.isfinite(below).all()
    assert (below > 0).all()


def test_altitude_is_recovered_from_a_flat_ground_image():
    assert estimate_altitude(flat_ground(15.0), FOV_V, PITCH) == pytest.approx(
        15.0, rel=0.02)
    assert estimate_altitude(flat_ground(40.0), FOV_V, PITCH) == pytest.approx(
        40.0, rel=0.02)


def test_altitude_ignores_an_obstacle_in_the_lower_band():
    """A tree occupying part of the band must not drag the median."""
    depth = flat_ground(15.0)
    depth[180:220, 100:160] = 4.0        # something much closer
    assert estimate_altitude(depth, FOV_V, PITCH) == pytest.approx(15.0, rel=0.05)


def test_altitude_is_none_when_there_is_nothing_to_estimate_from():
    assert estimate_altitude(None, FOV_V, PITCH) is None
    assert estimate_altitude(np.full((HEIGHT, WIDTH), np.nan, np.float32),
                             FOV_V, PITCH) is None

    # Nothing below the near-horizon cut-off. Rows 30..65 span elevations
    # -12.3 to -23.0 deg at this pitch, all shallower than the 25 deg cut, so
    # every pixel is discarded before the median is taken.
    near_horizon_only = np.full((HEIGHT, WIDTH), np.nan, np.float32)
    near_horizon_only[30:65, :] = 30.0
    assert estimate_altitude(near_horizon_only, FOV_V, PITCH) is None

    # Below the cut-off but far too few samples to trust.
    too_few = np.full((HEIGHT, WIDTH), np.nan, np.float32)
    too_few[180:200, :20] = 20.0          # 400 px, under the 200*W budget? no:
    assert estimate_altitude(too_few, FOV_V, PITCH) is not None  # 400 >= 200
    tiny = np.full((HEIGHT, WIDTH), np.nan, np.float32)
    tiny[180:200, :5] = 20.0              # 100 px, definitely under
    assert estimate_altitude(tiny, FOV_V, PITCH) is None


def test_strip_ground_removes_flat_ground_and_keeps_an_obstacle():
    depth = flat_ground(15.0)
    # A vertical obstacle standing on the ground across three columns: at every
    # row it sits at half the distance the ground would be.
    expected = expected_ground_depth(HEIGHT, FOV_V, PITCH, 15.0)
    rows = np.where(np.isfinite(expected))[0]
    obstacle_rows = rows[len(rows) // 2:]
    depth[np.ix_(obstacle_rows, [150, 151, 152])] = (
        expected[obstacle_rows, None] * 0.5)

    stripped = strip_ground(depth, FOV_V, PITCH)

    assert np.isfinite(stripped[obstacle_rows, 150]).all()   # obstacle survives
    assert np.isfinite(stripped[obstacle_rows, 151]).all()
    # Ground elsewhere on those rows is gone.
    elsewhere = np.setdiff1d(np.arange(WIDTH), [150, 151, 152])
    assert not np.isfinite(stripped[obstacle_rows[-1], elsewhere]).any()


@pytest.mark.parametrize("pitch", [-40.0, -30.0, -20.0])
def test_strip_ground_keeps_everything_above_the_horizon(pitch):
    """Tree canopy at flight level lives there; it cannot be ground.

    Regression: the first version compared ``depth < expected`` and kept the
    true branch, which meant NaN in ``expected`` (every row at or above the
    horizon) fell through to *discard*.  It deleted exactly the canopy pixels
    the filter exists to protect, and the original test skipped whenever the
    geometry happened to have no such rows -- which it does at pitch -40.
    """
    elevations = row_elevations_deg(HEIGHT, FOV_V, pitch)
    above = np.where(elevations >= 0.0)[0]
    if above.size == 0:
        pytest.skip(f"pitch {pitch} puts no row at or above the horizon")

    depth = flat_ground(15.0)
    depth[above, :] = 12.0                       # something at flight level
    stripped = strip_ground(depth, FOV_V, pitch)
    assert np.isfinite(stripped[above, :]).all()


def test_strip_ground_keeps_rows_that_cannot_be_ground():
    """Rows at or above the horizon are sky and treetops, whatever the range.

    (A level camera still sees ground in its lower rows -- at 15m altitude the
    rows below -22 deg look at ground inside 40m -- so only the rows above the
    optical axis are unconditionally safe.)
    """
    depth = np.full((HEIGHT, WIDTH), 40.0, np.float32)
    stripped = strip_ground(depth, FOV_V, 0.0, altitude_m=15.0)
    above = row_elevations_deg(HEIGHT, FOV_V, 0.0) >= 0.0
    assert above.any()
    assert np.isfinite(stripped[above]).all()


def test_strip_ground_returns_the_input_when_altitude_is_unknown():
    """Never trade a real obstacle for a guess."""
    unusable = np.full((HEIGHT, WIDTH), np.nan, np.float32)
    assert strip_ground(unusable, FOV_V, PITCH) is unusable
    everything_nan = np.full((HEIGHT, WIDTH), np.nan, np.float32)
    assert strip_ground(everything_nan, FOV_V, PITCH) is everything_nan


def test_margin_ratio_controls_how_much_counts_as_ground():
    depth = flat_ground(15.0)
    expected = expected_ground_depth(HEIGHT, FOV_V, PITCH, 15.0)
    rows = np.where(np.isfinite(expected))[0]
    row = rows[-1]
    # Something 8% closer than the ground: within the default 15% margin.
    depth[row, :] = expected[row] * 0.92
    assert not np.isfinite(strip_ground(depth, FOV_V, PITCH, margin_ratio=0.15)[row]).any()
    # With a tighter margin the same returns count as an obstacle.
    assert np.isfinite(strip_ground(depth, FOV_V, PITCH, margin_ratio=0.05)[row]).all()
