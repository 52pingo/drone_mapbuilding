"""Tests for scripts/check_acceptance.py.

Each criterion is exercised with a cloud whose verdict is known by
construction, so a harness bug shows up as a wrong verdict rather than as a
quiet pass on a broken map.
"""

import numpy as np
import pytest

from scripts.check_acceptance import (
    _drift_from_history, _facade_variance, _line_residual, evaluate,
    read_ascii_ply,
)
from scripts.uav_semantic_schema import CLASS_TO_ID

GROUND = -1


def write_ply(path, points, ids):
    body = "".join(
        f"{x:.4f} {y:.4f} {z:.4f} 10 20 30 {int(i)}\n"
        for (x, y, z), i in zip(points, ids)
    )
    path.write_text(
        "ply\nformat ascii 1.0\n"
        f"element vertex {len(points)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property int semantic_id\nend_header\n" + body,
        encoding="ascii",
    )


def good_map():
    """A cloud that satisfies every criterion, built from known geometry."""
    ground = np.column_stack((
        np.linspace(0, 60, 600), np.linspace(0, 60, 600), np.zeros(600)))
    ground_ids = np.full(len(ground), GROUND)

    # A tree: 4m tall, 4m wide, centred 4m above the ground.
    tree = np.column_stack((
        np.random.default_rng(0).uniform(8, 12, 300),
        np.random.default_rng(1).uniform(8, 12, 300),
        np.random.default_rng(2).uniform(2, 6, 300),
    ))
    tree_ids = np.full(len(tree), CLASS_TO_ID["tree"])

    # A building: 8m tall with a dense vertical wall.
    building = np.column_stack((
        np.random.default_rng(3).uniform(29, 31, 300),
        np.random.default_rng(4).uniform(29, 31, 300),
        np.linspace(0, 8, 300),
    ))
    building_ids = np.full(len(building), CLASS_TO_ID["building"])

    # A fence: straight run of posts 1.5m tall.
    fence = np.column_stack((
        np.linspace(0, 20, 120),
        np.full(120, 5.0),
        np.linspace(0, 1.5, 120),
    ))
    fence_ids = np.full(len(fence), CLASS_TO_ID["fence"])

    points = np.vstack((ground, tree, building, fence))
    ids = np.concatenate((ground_ids, tree_ids, building_ids, fence_ids))
    return points, ids


def verdicts(checks):
    return {item["criterion"]: item["passed"] for item in checks}


def test_good_map_passes_every_evaluable_criterion(tmp_path):
    path = tmp_path / "semantic_map.ply"
    write_ply(path, *good_map())
    checks = evaluate(path, None)
    result = verdicts(checks)
    assert result["z-span >= 5m and not a single spike"] is True
    assert result["tree: span/count/height"] is True
    assert result["building: span + vertical facade"] is True
    assert result["fence: straight line + height"] is True
    assert result["ground flat / thin surface"] is None  # retired, not a pass
    assert _share_verdict(evaluate(path, None)) is True


def test_flat_ground_only_map_fails_the_span_criterion(tmp_path):
    path = tmp_path / "flat.ply"
    points = np.column_stack((
        np.linspace(0, 60, 900), np.linspace(0, 60, 900), np.zeros(900)))
    write_ply(path, points, np.full(900, GROUND))
    result = verdicts(evaluate(path, None))
    assert result["z-span >= 5m and not a single spike"] is False
    assert _share_verdict(evaluate(path, None)) is False


def test_the_retired_ground_criterion_is_skipped_not_passed(tmp_path):
    """A criterion that cannot discriminate must never read as a pass.

    A flat sheet is the smoothest surface there is, so every form of this
    check scored the failed 2026-08-19 map *better* than a good one.
    """
    path = tmp_path / "flat.ply"
    points = np.column_stack((
        np.linspace(0, 60, 900), np.linspace(0, 60, 900), np.zeros(900)))
    write_ply(path, points, np.full(900, GROUND))
    checks = evaluate(path, None)
    retired = [item for item in checks
               if item["criterion"] == "ground flat / thin surface"]
    assert len(retired) == 1
    assert retired[0]["passed"] is None
    assert retired[0]["detail"].startswith("RETIRED")


def _share_verdict(checks):
    return next(item for item in checks
                if item["criterion"].startswith("tagged "))["passed"]


def test_tagged_share_threshold_is_configurable_and_counts_are_per_class(tmp_path):
    """Only the share moves here; the per-class counts stay satisfied.

    good_map() is 720 of 1320 points tagged, i.e. 54.5%.
    """
    path = tmp_path / "mixed.ply"
    write_ply(path, *good_map())

    assert _share_verdict(evaluate(path, None, min_tagged_share=0.50)) is True
    assert _share_verdict(evaluate(path, None, min_tagged_share=0.99)) is False


def test_a_map_that_labels_almost_everything_fails(tmp_path):
    """The guard against painting the map, which is how 97.2% got through.

    Objects inflated to cover the whole park passed every shape criterion --
    the big blob is trivially tall and wide.  The share is what separates a
    labelled map from a painted one.
    """
    path = tmp_path / "painted.ply"
    points, ids = good_map()
    write_ply(path, points, np.where(ids == GROUND, CLASS_TO_ID["tree"], ids))
    checks = evaluate(path, None)
    assert _share_verdict(checks) is False
    assert "cap 60%" in next(item for item in checks
                             if item["criterion"].startswith("tagged "))["detail"]


def test_a_class_below_the_count_floor_fails_even_when_the_share_is_fine(tmp_path):
    path = tmp_path / "few_fence.ply"
    points, ids = good_map()
    fence = CLASS_TO_ID["fence"]
    # Thin the fence out to well under the 100-point floor.
    keep = ~((ids == fence) & (np.arange(len(ids)) % 5 != 0))
    write_ply(path, points[keep], ids[keep])

    result = verdicts(evaluate(path, None))
    assert _share_verdict(evaluate(path, None)) is False


def test_missing_class_fails_rather_than_passing_vacuously(tmp_path):
    path = tmp_path / "no_fence.ply"
    points, ids = good_map()
    keep = ids != CLASS_TO_ID["fence"]
    write_ply(path, points[keep], ids[keep])
    result = verdicts(evaluate(path, None))
    assert result["fence: straight line + height"] is False


def test_untagged_trail_reports_skip_not_pass(tmp_path):
    path = tmp_path / "semantic_map.ply"
    write_ply(path, *good_map())
    checks = evaluate(path, None)
    drift = [item for item in checks if item["criterion"] == "object drift < 1.0m"]
    assert len(drift) == 1
    assert drift[0]["passed"] is None
    assert drift[0]["detail"].startswith("SKIP")


def test_drift_is_measured_from_the_trail():
    objects = [{"trail": [
        {"position_ned": [0.0, 0.0, 0.0]},
        {"position_ned": [0.4, 0.0, 0.0]},
        {"position_ned": [1.9, 0.0, 0.0]},
    ]}]
    assert _drift_from_history(objects) == pytest.approx(1.5)


def test_drift_needs_at_least_three_observations():
    assert _drift_from_history([{"trail": [{"position_ned": [0, 0, 0]}]}]) is None
    assert _drift_from_history([{}]) is None


def test_line_residual_is_zero_on_a_perfect_line_and_grows_with_scatter():
    straight = np.column_stack((np.linspace(0, 10, 50), np.zeros(50)))
    assert _line_residual(straight) == pytest.approx(0.0, abs=1e-9)
    # Off-line by up to ~1m, alternating sides: RMS should be around 0.5m.
    # (Scaling y with x would still be perfectly collinear and score zero.)
    jitter = np.tile([0.0, 1.0, -1.0, 0.5, -0.5], 10)
    scattered = np.column_stack((np.linspace(0, 10, 50), jitter))
    assert _line_residual(scattered) > 0.4


def test_facade_variance_separates_a_wall_from_a_flat_slab():
    wall = np.column_stack((
        np.full(200, 5.0), np.full(200, 5.0), np.linspace(0, 8, 200)))
    slab = np.column_stack((
        np.linspace(0, 8, 200), np.zeros(200), np.zeros(200)))
    assert _facade_variance(wall) > 1.0
    assert _facade_variance(slab) == pytest.approx(0.0)


def test_read_ascii_ply_rejects_a_truncated_body(tmp_path):
    path = tmp_path / "short.ply"
    path.write_text(
        "ply\nformat ascii 1.0\nelement vertex 3\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "property int semantic_id\nend_header\n1 2 3 0 0 0 -1\n",
        encoding="ascii",
    )
    with pytest.raises(ValueError, match="promises 3 vertices"):
        read_ascii_ply(path)
