from drone_gui.sessions import scan_sessions


def test_scan_sessions_groups_classes_and_maps(tmp_path):
    session = tmp_path / "citypark_run"
    tree_dir = session / "detected_classes" / "tree"
    tree_dir.mkdir(parents=True)
    (tree_dir / "scene_001.jpg").write_bytes(b"jpg")
    (session / "octomap_map.png").write_bytes(b"png")

    sessions = scan_sessions(tmp_path)
    assert len(sessions) == 1
    assert sessions[0].image_count == 1
    assert list(sessions[0].class_images) == ["tree"]
    assert sessions[0].map_images[0].name == "octomap_map.png"


def test_scan_sessions_handles_missing_directory(tmp_path):
    assert scan_sessions(tmp_path / "missing") == []
