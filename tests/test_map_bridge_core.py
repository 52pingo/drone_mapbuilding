import json

import numpy as np

from scripts.map_bridge_core import (
    MapSnapshotWriter, assign_semantic_ids, finite_downsample,
    frame_to_local_ned, world_enu_to_local_ned, world_enu_to_ned,
    world_ned_to_local_ned, write_pcd, write_ply,
)
from scripts.uav_semantic_schema import CLASS_TO_ID


def _body(path):
    """Return the vertex rows of an exported cloud, header stripped."""
    text = path.read_text(encoding="ascii")
    return [line for line in text.splitlines()
            if line and line[0].isdigit() or line.startswith("-")]


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


def test_world_ned_to_local_ned_only_moves_the_origin():
    """A NED cloud must keep north on x; swapping it transposes the map."""
    points = world_ned_to_local_ned([[10.0, 20.0, -30.0]], [1.0, 2.0, 3.0])
    np.testing.assert_allclose(points, [[9.0, 18.0, -33.0]])


def test_frame_dispatch_picks_the_conversion_from_the_frame_name():
    values = [[1.0, 2.0, -3.0]]
    np.testing.assert_allclose(frame_to_local_ned(values, "world_ned"),
                               [[1.0, 2.0, -3.0]])
    np.testing.assert_allclose(frame_to_local_ned(values, "world_enu"),
                               [[2.0, 1.0, 3.0]])
    np.testing.assert_allclose(frame_to_local_ned(values, "/world_ned"),
                               [[1.0, 2.0, -3.0]])


def test_unknown_frame_raises_instead_of_guessing():
    """Guessing the handedness is how the map ended up transposed."""
    import pytest
    with pytest.raises(ValueError, match="must end in 'enu' or 'ned'"):
        frame_to_local_ned([[1, 2, 3]], "map")


def test_snapshot_of_a_world_ned_cloud_keeps_xy_meaning(tmp_path):
    """Regression: the writer used to swap x/y for every cloud regardless."""
    writer = MapSnapshotWriter(tmp_path, max_points=10)
    writer.publish([[100.0, -50.0, -12.0]], frame_id="world_ned",
                   world_origin_ned=(7.0, 3.0, -1.5))
    metadata = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    points = np.load(tmp_path / metadata["points"], allow_pickle=False)
    np.testing.assert_allclose(points, [[93.0, -53.0, -10.5]])
    assert metadata["source_frame"] == "world_ned"
    assert metadata["coordinate_frame"] == "px4_local_ned"


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
    assert (f"4.0000 5.0000 6.0000 238 180 74 {CLASS_TO_ID['tree']}" in text)


def test_markers_carry_their_class_id_not_their_index():
    """An index id would collide with a real class id and inflate its count."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "m.ply"
        write_ply(target, [], [
            {"label": "fence", "position_ned": [1, 1, 1]},
            {"label": "tree", "position_ned": [2, 2, 2]},
        ])
        rows = _body(target)
    assert rows[0].endswith(str(CLASS_TO_ID["fence"]))
    assert rows[1].endswith(str(CLASS_TO_ID["tree"]))
    assert rows[1].endswith("0") is False


def test_object_extents_label_a_facade_instead_of_a_ball():
    """What "a building is a vertical face" needs.

    A sphere around the centre can only ever produce a lump: measured on a real
    run the biggest building blob was 3.9m tall with a facade variance of 0.28,
    against thresholds of 4m and 1m^2.  A box of the object's own size captures
    the wall.
    """
    rng = np.random.default_rng(0)
    wall = np.column_stack((
        rng.uniform(-9.0, 9.0, 4000),      # 18m wide
        rng.uniform(-0.2, 0.2, 4000),      # thin
        rng.uniform(-4.0, 4.0, 4000),      # 8m tall
    ))
    boxed = [{"label": "building", "position_ned": [0.0, 0.0, 0.0],
              "half_width": 9.5, "half_height": 4.2}]
    sphere = [{"label": "building", "position_ned": [0.0, 0.0, 0.0]}]

    with_extent = assign_semantic_ids(wall, boxed)
    with_sphere = assign_semantic_ids(wall, sphere)

    assert (with_extent >= 0).mean() > 0.95          # the wall is labelled
    assert (with_sphere >= 0).mean() < 0.25          # only a ball of it is
    assert np.ptp(wall[with_extent >= 0, 2]) > 7.5   # near the full 8m height
    assert np.ptp(wall[with_sphere >= 0, 2]) < 6.0


def test_object_extents_follow_a_fence_line_instead_of_a_chain_of_balls():
    """A fence is a line of posts; the label must not be rounder than the post."""
    rng = np.random.default_rng(1)
    along = np.linspace(0.0, 40.0, 2000)
    posts = np.column_stack((along, rng.normal(0.0, 0.05, 2000),
                             rng.uniform(-0.9, 0.9, 2000)))
    objects = [{"label": "fence",
                "position_ned": [float(x), 0.0, 0.0],
                "half_width": 1.2, "half_height": 1.0}
               for x in np.linspace(0.0, 40.0, 20)]

    tagged = assign_semantic_ids(posts, objects)
    assert (tagged >= 0).mean() > 0.9
    centre = posts[tagged >= 0, :2].mean(axis=0)
    _, _, vt = np.linalg.svd(posts[tagged >= 0, :2] - centre, full_matrices=False)
    residual = float(np.sqrt(np.mean((posts[tagged >= 0, :2] @ vt[1]) ** 2)))
    assert residual < 0.5


def test_extents_beat_the_sphere_when_objects_overlap():
    """A fence post in front of a building must not be swallowed by it."""
    objects = [
        {"label": "building", "position_ned": [0.0, 0.0, 0.0],
         "half_width": 20.0, "half_height": 10.0},
        {"label": "fence", "position_ned": [12.0, 0.0, -5.0],
         "half_width": 1.0, "half_height": 1.0},
    ]
    ids = assign_semantic_ids([[12.0, 0.0, -5.0], [1.0, 0.0, -9.0]], objects)
    assert ids.tolist() == [CLASS_TO_ID["fence"], CLASS_TO_ID["building"]]


def test_assign_semantic_ids_labels_only_points_inside_the_radius():
    points = [
        [0.0, 0.0, 0.0],      # 0 m from the tree centre
        [2.0, 0.0, 0.0],      # 2 m -> inside the 3 m default
        [4.0, 0.0, 0.0],      # 4 m -> outside
    ]
    objects = [{"label": "tree", "position_ned": [0.0, 0.0, 0.0]}]
    ids = assign_semantic_ids(points, objects)
    assert ids.tolist() == [CLASS_TO_ID["tree"], CLASS_TO_ID["tree"], -1]


def test_assign_semantic_ids_prefers_the_nearest_object():
    points = [[10.0, 0.0, 0.0]]
    objects = [
        {"label": "tree", "position_ned": [0.0, 0.0, 0.0]},
        {"label": "fence", "position_ned": [10.5, 0.0, 0.0]},
    ]
    assert assign_semantic_ids(points, objects).tolist() == [CLASS_TO_ID["fence"]]


def test_assign_semantic_ids_ignores_unplaceable_and_unknown_objects():
    points = [[0.0, 0.0, 0.0]]
    objects = [
        {"label": "tree"},                              # no position
        {"label": "tree", "position_ned": None},        # null position
        {"label": "unicorn", "position_ned": [0, 0, 0]},  # not in the schema
    ]
    assert assign_semantic_ids(points, objects).tolist() == [-1]


def test_assign_semantic_ids_rejects_a_nonpositive_radius():
    import pytest
    with pytest.raises(ValueError):
        assign_semantic_ids([[0, 0, 0]],
                            [{"label": "tree", "position_ned": [0, 0, 0]}], 0.0)


def test_ply_tags_nearby_occupancy_points_with_the_class_colour(tmp_path):
    target = tmp_path / "semantic_map.ply"
    write_ply(target, [[0.0, 0.0, 0.0], [50.0, 50.0, 0.0]],
              [{"label": "tree", "position_ned": [0.0, 0.0, 0.0]}])
    rows = _body(target)
    near, far = rows[0], rows[1]

    def semantic_id(row):
        return int(row.rsplit(" ", 1)[1])

    assert semantic_id(near) == CLASS_TO_ID["tree"]
    assert semantic_id(far) == -1
    # The tagged point is painted in the class colour, not the height ramp.
    assert near.split()[3:6] == ["58", "138", "62"]
