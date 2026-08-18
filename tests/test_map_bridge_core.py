import json

import numpy as np

from scripts.map_bridge_core import (
    MapSnapshotWriter, finite_downsample, world_enu_to_local_ned,
    world_enu_to_ned, write_pcd, write_ply,
)


def test_world_enu_to_px4_ned_swaps_xy_and_flips_z():
    points = world_enu_to_ned([[1.0, 2.0, 3.0], [-4.0, 5.0, -6.0]])
    np.testing.assert_allclose(points, [[2.0, 1.0, -3.0], [5.0, -4.0, 6.0]])


def test_world_enu_to_local_ned_removes_citypark_spawn_translation():
    points = world_enu_to_local_ned(
        [[258.15, -134.09, 1.5]], [-134.09, 258.15, -1.5]
    )
    np.testing.assert_allclose(points, [[0.0, 0.0, 0.0]], atol=1e-5)


def test_downsample_filters_invalid_and_honors_limit():
    values = np.array([[index, 0, 0] for index in range(10)] + [[np.nan, 0, 0]])
    result = finite_downsample(values, 4)
    assert result.shape == (4, 3)
    assert np.isfinite(result).all()


def test_snapshot_writer_rotates_three_atomic_npy_files(tmp_path):
    writer = MapSnapshotWriter(tmp_path, max_points=5)
    values = np.arange(30, dtype=np.float32).reshape((10, 3))
    for _ in range(5):
        writer.publish(values)
    assert len(list(tmp_path.glob("points_*.npy"))) == 3
    metadata = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    points = np.load(tmp_path / metadata["points"], allow_pickle=False)
    assert metadata["sequence"] == 5
    assert points.shape == (5, 3)


def test_ply_export_includes_occupancy_and_semantic_vertices(tmp_path):
    target = tmp_path / "semantic_map.ply"
    write_ply(target, [[1, 2, -3]], [{
        "label": "tree", "position_ned": [4, 5, -6],
    }])
    text = target.read_text(encoding="ascii")
    assert "element vertex 2" in text
    assert "1.0000 2.0000 3.0000" in text
    assert "4.0000 5.0000 6.0000" in text


def test_pcd_export_includes_semantic_marker(tmp_path):
    target = tmp_path / "semantic_map.pcd"
    write_pcd(target, [[1, 2, -3]], [{
        "label": "tree", "position_ned": [4, 5, -6],
    }])
    text = target.read_text(encoding="ascii")
    assert "FIELDS x y z red green blue semantic_id" in text
    assert "POINTS 2" in text
    assert "4.0000 5.0000 6.0000 238 180 74 0" in text
