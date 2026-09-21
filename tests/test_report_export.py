#!/usr/bin/env python3
"""pytest 单测：drone_gui.report_export 的轨迹 SVG 与报告生成。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from drone_gui import report_export
from drone_gui.report_export import _trajectory_svg, generate_report


# ---------- _trajectory_svg ----------

def test_trajectory_svg_normal_three_points():
    frames = [
        {"position": [0.0, 0.0, 0.0]},
        {"position": [1.0, 2.0, 0.0]},
        {"position": [3.0, 4.0, 0.0]},
    ]
    svg = _trajectory_svg(frames)
    assert svg.startswith("<svg")
    assert 'viewBox="0 0 760 300"' in svg
    assert "<polyline" in svg
    assert 'stroke="#f2c56d"' in svg
    assert svg.count("<circle") == 2
    assert 'fill="#76d6b3"' in svg
    assert 'fill="#ff8d86"' in svg
    points = svg.split('points="', 1)[1].split('"', 1)[0]
    assert len(points.split()) == 3
    for pair in points.split():
        x, y = pair.split(",")
        float(x)
        float(y)


def test_trajectory_svg_two_points_boundary():
    svg = _trajectory_svg([
        {"position": [0.0, 0.0, 0.0]},
        {"position": [1.0, 1.0, 0.0]},
    ])
    assert "<polyline" in svg
    assert "没有可回放的轨迹遥测" not in svg


def test_trajectory_svg_empty_frames():
    assert "没有可回放的轨迹遥测" in _trajectory_svg([])


def test_trajectory_svg_single_point_placeholder():
    assert "没有可回放的轨迹遥测" in _trajectory_svg([{"position": [0, 0, 0]}])


def test_trajectory_svg_skips_bad_positions():
    frames = [
        {"position": None},
        {"position": "0,0,0"},
        {"position": [1, 2]},
        {"position": [1, 2, 3, 4]},
        {"position": ["a", "b", "c"]},
        {"position": [0.0, 0.0, 0.0]},
        {"position": [1.0, 1.0, 0.0]},
    ]
    svg = _trajectory_svg(frames)
    assert "<polyline" in svg
    assert "没有可回放的轨迹遥测" not in svg
    points = svg.split('points="', 1)[1].split('"', 1)[0]
    assert len(points.split()) == 2


def test_trajectory_svg_all_bad_positions_placeholder():
    frames = [
        {"position": None},
        {"position": "x"},
        {"position": [1, 2]},
        {"position": ["a", "b", "c"]},
    ]
    assert "没有可回放的轨迹遥测" in _trajectory_svg(frames)


def test_trajectory_svg_non_dict_frames():
    frames = [None, "x", 42, [1, 2, 3], {"position": [0, 0, 0]}, {"position": [1, 1, 0]}]
    svg = _trajectory_svg(frames)
    assert "<polyline" in svg


def test_trajectory_svg_accepts_generator():
    def gen():
        yield {"position": [0.0, 0.0, 0.0]}
        yield {"position": [1.0, 1.0, 0.0]}

    svg = _trajectory_svg(gen())
    assert "<polyline" in svg


def test_trajectory_svg_missing_position_key():
    frames = [{"foo": 1}, {"position": [0, 0, 0]}, {"position": [1, 1, 0]}]
    svg = _trajectory_svg(frames)
    assert "<polyline" in svg


def test_trajectory_svg_flat_trajectory_no_div_by_zero():
    frames = [{"position": [5.0, 5.0, 0.0]}, {"position": [5.0, 5.0, 0.0]}]
    svg = _trajectory_svg(frames)
    assert "<polyline" in svg
    points = svg.split('points="', 1)[1].split('"', 1)[0]
    assert len(points.split()) == 2


# ---------- _table_rows ----------

def test_table_rows_escapes_name_and_value():
    rows = report_export._table_rows([("a<b", "c&d")])
    assert "<th>a&lt;b</th>" in rows
    assert "<td>c&amp;d</td>" in rows


def test_table_rows_coerces_values_to_str():
    rows = report_export._table_rows([("n", 42), ("f", 3.14)])
    assert "<td>42</td>" in rows
    assert "<td>3.14</td>" in rows


# ---------- _evidence_counts ----------

def test_evidence_counts_counts_images_only(tmp_path):
    detected = tmp_path / "detected_classes"
    (detected / "person").mkdir(parents=True)
    (detected / "person" / "a.jpg").write_bytes(b"x")
    (detected / "person" / "b.PNG").write_bytes(b"x")
    (detected / "person" / "c.txt").write_bytes(b"x")
    (detected / "car").mkdir()
    (detected / "car" / "x.jpeg").write_bytes(b"x")
    counts = report_export._evidence_counts(tmp_path)
    assert counts["person"] == 2
    assert counts["car"] == 1


def test_evidence_counts_missing_dir(tmp_path):
    assert report_export._evidence_counts(tmp_path) == {}


# ---------- generate_report ----------

def _make_manifest(**overrides):
    manifest = {
        "status": "completed",
        "mission": {
            "name": "CityPark",
            "goals": 5,
            "flight_z": 10.0,
            "max_mission_time": 300,
        },
        "summary": {
            "telemetry_samples": 100,
            "point_count": 5000,
            "semantic_objects": 3,
            "closed_loop": True,
        },
        "model": {"name": "yolo", "sha256": "deadbeef"},
        "created_at": "2024-01-01T00:00:00",
        "completed_at": "2024-01-01T00:10:00",
    }
    manifest.update(overrides)
    return manifest


def test_generate_report_writes_self_contained_html(tmp_path):
    manifest = _make_manifest()
    telemetry = [
        {"position": [0.0, 0.0, 0.0], "elapsed": 0.0, "state": "init", "armed": False},
        {"position": [1.0, 2.0, 0.0], "elapsed": 5.5, "state": "flying", "armed": True},
    ]
    artifacts = [{"path": "logs/a.txt", "kind": "text", "size": 1234}]
    target = generate_report(tmp_path, manifest, telemetry, artifacts)
    assert target == tmp_path / "report.html"
    assert target.is_file()
    html = target.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "无人机任务报告" in html
    assert "任务配置" in html
    assert "闭环状态" in html
    assert "北东平面遥测轨迹" in html
    assert "视觉类别证据" in html
    assert "成果预览" in html
    assert "交付文件" in html
    assert ">100<" in html
    assert "5,000" in html
    assert "5.5s" in html
    assert "COMPLETED" in html
    assert "logs/a.txt" in html
    assert "1,234" in html
    assert "<polyline" in html
    assert "http://" not in html
    assert "https://" not in html


def test_generate_report_empty_telemetry(tmp_path):
    target = generate_report(tmp_path, _make_manifest(), [], [])
    html = target.read_text(encoding="utf-8")
    assert "没有可回放的轨迹遥测" in html
    assert "0.0s" in html
    assert "无类别证据" in html


def test_generate_report_minimal_manifest(tmp_path):
    target = generate_report(tmp_path, {}, [], [])
    html = target.read_text(encoding="utf-8")
    assert "UNKNOWN" in html
    assert "CityPark" in html


def test_generate_report_escapes_script_in_mission_name(tmp_path):
    manifest = _make_manifest()
    manifest["mission"]["name"] = "<script>alert(1)</script>"
    target = generate_report(tmp_path, manifest, [], [])
    html = target.read_text(encoding="utf-8")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_generate_report_escapes_closing_script_in_json(tmp_path):
    manifest = _make_manifest()
    manifest["mission"]["name"] = "</script><script>alert(1)</script>"
    target = generate_report(tmp_path, manifest, [], [])
    html = target.read_text(encoding="utf-8")
    assert "&lt;/script&gt;" in html


def test_generate_report_escapes_root_name(tmp_path):
    root = tmp_path / "run&1"
    root.mkdir()
    target = generate_report(root, _make_manifest(), [], [])
    html = target.read_text(encoding="utf-8")
    assert "run&amp;1" in html


def test_generate_report_escapes_artifact_path(tmp_path):
    artifacts = [{"path": "<img src=x onerror=alert(1)>", "kind": "img", "size": 10}]
    target = generate_report(tmp_path, _make_manifest(), [], artifacts)
    html = target.read_text(encoding="utf-8")
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_generate_report_artifact_size_coerced_to_int(tmp_path):
    artifacts = [{"path": "a", "kind": "k", "size": "2048"}]
    target = generate_report(tmp_path, _make_manifest(), [], artifacts)
    html = target.read_text(encoding="utf-8")
    assert "2,048" in html


def test_generate_report_artifact_missing_fields(tmp_path):
    artifacts = [{}]
    target = generate_report(tmp_path, _make_manifest(), [], artifacts)
    html = target.read_text(encoding="utf-8")
    assert "<td>0</td>" in html


def test_generate_report_evidence_rows_rendered(tmp_path):
    detected = tmp_path / "detected_classes"
    (detected / "person").mkdir(parents=True)
    (detected / "person" / "a.jpg").write_bytes(b"x")
    target = generate_report(tmp_path, _make_manifest(), [], [])
    html = target.read_text(encoding="utf-8")
    assert "<td>person</td>" in html
    assert "<td>1</td>" in html


def test_generate_report_images_rendered_when_present(tmp_path):
    (tmp_path / "semantic_map_view.png").write_bytes(b"x")
    target = generate_report(tmp_path, _make_manifest(), [], [])
    html = target.read_text(encoding="utf-8")
    assert 'src="semantic_map_view.png"' in html
    assert "没有静态预览图" not in html


def test_generate_report_no_images_placeholder(tmp_path):
    target = generate_report(tmp_path, _make_manifest(), [], [])
    html = target.read_text(encoding="utf-8")
    assert "没有静态预览图" in html
