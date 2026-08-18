"""Generate a self-contained, offline mission summary report."""

from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path
from typing import Iterable


def _trajectory_svg(frames: Iterable[dict]) -> str:
    positions = [
        item.get("position") for item in frames
        if isinstance(item.get("position"), list)
        and len(item["position"]) == 3
    ]
    if len(positions) < 2:
        return '<div class="empty">没有可回放的轨迹遥测</div>'
    north = [float(point[0]) for point in positions]
    east = [float(point[1]) for point in positions]
    n_min, n_max = min(north), max(north)
    e_min, e_max = min(east), max(east)
    n_span = max(1.0, n_max - n_min)
    e_span = max(1.0, e_max - e_min)
    width, height, pad = 760.0, 300.0, 24.0
    coordinates = []
    for n_value, e_value in zip(north, east):
        x = pad + (e_value - e_min) / e_span * (width - 2 * pad)
        y = height - pad - (n_value - n_min) / n_span * (height - 2 * pad)
        coordinates.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg viewBox="0 0 {int(width)} {int(height)}" role="img" '
        'aria-label="无人机北东坐标飞行轨迹">'
        '<rect width="100%" height="100%" fill="#0f171c" rx="6"/>'
        '<polyline points="' + " ".join(coordinates) + '" fill="none" '
        'stroke="#f2c56d" stroke-width="3"/>'
        f'<circle cx="{coordinates[0].split(",")[0]}" '
        f'cy="{coordinates[0].split(",")[1]}" r="5" fill="#76d6b3"/>'
        f'<circle cx="{coordinates[-1].split(",")[0]}" '
        f'cy="{coordinates[-1].split(",")[1]}" r="5" fill="#ff8d86"/>'
        '</svg>'
    )


def _table_rows(values: Iterable[tuple[str, object]]) -> str:
    return "".join(
        f"<tr><th>{escape(str(name))}</th><td>{escape(str(value))}</td></tr>"
        for name, value in values
    )


def _evidence_counts(root: Path) -> Counter:
    counts: Counter = Counter()
    detected = root / "detected_classes"
    if detected.is_dir():
        for directory in detected.iterdir():
            if directory.is_dir():
                counts[directory.name] = sum(
                    path.suffix.lower() in {".jpg", ".jpeg", ".png"}
                    for path in directory.iterdir() if path.is_file()
                )
    return counts


def generate_report(
    root: Path, manifest: dict, telemetry: list[dict], artifacts: list[dict]
) -> Path:
    """Write report.html with no network or JavaScript dependencies."""
    summary = manifest.get("summary", {})
    mission = manifest.get("mission", {})
    evidence = _evidence_counts(root)
    last = telemetry[-1] if telemetry else {}
    evidence_rows = "".join(
        f"<tr><td>{escape(label)}</td><td>{count}</td></tr>"
        for label, count in sorted(evidence.items())
    ) or '<tr><td colspan="2">无类别证据</td></tr>'
    artifact_rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            escape(str(item.get("path", ""))),
            escape(str(item.get("kind", ""))),
            f"{int(item.get('size', 0)):,}",
        ) for item in artifacts
    )
    image_candidates = [
        "semantic_map_view.png", "octomap_map_citypark_loop.png",
        "flight_trajectory_citypark_loop.png", "depth_rviz_citypark.png",
    ]
    images = "".join(
        f'<figure><img src="{escape(name, quote=True)}" alt="{escape(name)}">'
        f'<figcaption>{escape(name)}</figcaption></figure>'
        for name in image_candidates if (root / name).is_file()
    ) or '<div class="empty">没有静态预览图，可在桌面 GUI 中打开点云。</div>'
    report = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(root.name)} · 无人机任务报告</title>
<style>
:root{{--bg:#0c1216;--panel:#141e24;--line:#2a3942;--text:#d8e2e8;
--muted:#83959f;--cyan:#8fe0e7;--green:#76d6b3;--amber:#f2c56d}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);
font:14px/1.55 "Microsoft YaHei UI","Segoe UI",sans-serif}}
main{{max-width:1120px;margin:auto;padding:32px 24px 64px}}h1{{font-size:26px;margin:0}}
h2{{font-size:17px;margin:0 0 14px}}.eyebrow{{color:var(--cyan);letter-spacing:.08em}}
.header{{display:flex;justify-content:space-between;gap:24px;align-items:end;margin-bottom:22px}}
.badge{{border:1px solid #28735e;background:#12372e;color:#8be0c0;padding:5px 12px;
border-radius:16px}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}
.metric,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:6px}}
.metric{{padding:14px}}.metric b{{display:block;font-size:20px;color:#f4f8fa}}
.metric span,.muted{{color:var(--muted)}}.panel{{padding:18px;margin-top:12px}}
.columns{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}table{{width:100%;border-collapse:collapse}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--muted);font-weight:500;width:42%}}.artifacts th{{width:auto;color:var(--text)}}
.gallery{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}figure{{margin:0}}
img{{display:block;width:100%;max-height:440px;object-fit:contain;background:#0f171c;border-radius:4px}}
figcaption{{color:var(--muted);padding-top:6px}}.empty{{color:var(--muted);padding:28px;text-align:center}}
svg{{display:block;width:100%;height:auto}}@media(max-width:760px){{.grid{{grid-template-columns:1fr 1fr}}
.columns,.gallery{{grid-template-columns:1fr}}.header{{display:block}}.badge{{display:inline-block;margin-top:12px}}}}
</style></head><body><main>
<header class="header"><div><div class="eyebrow">DRONE OPS / SESSION REPORT</div>
<h1>{escape(root.name)}</h1><div class="muted">坐标系 PX4 Local NED · 离线可读</div></div>
<div class="badge">{escape(str(manifest.get('status', 'unknown')).upper())}</div></header>
<section class="grid">
<div class="metric"><b>{int(summary.get('telemetry_samples', 0)):,}</b><span>遥测样本</span></div>
<div class="metric"><b>{int(summary.get('point_count', 0)):,}</b><span>占据点</span></div>
<div class="metric"><b>{int(summary.get('semantic_objects', 0))}</b><span>语义对象</span></div>
<div class="metric"><b>{float(last.get('elapsed', 0.0)):.1f}s</b><span>任务时间</span></div>
</section>
<section class="columns"><div class="panel"><h2>任务配置</h2><table>{_table_rows([
('任务名', mission.get('name', 'CityPark')), ('航点', mission.get('goals', '')),
('高度', mission.get('flight_z', '')), ('最大时长', mission.get('max_mission_time', '')),
('模型', manifest.get('model', {}).get('name', '')), ('模型 SHA-256', manifest.get('model', {}).get('sha256', '')),
])}</table></div><div class="panel"><h2>闭环状态</h2><table>{_table_rows([
('最终阶段', last.get('state', 'unknown')), ('已锁定', last.get('armed', 'unknown')),
('闭环确认', summary.get('closed_loop', False)), ('创建时间', manifest.get('created_at', '')),
('完成时间', manifest.get('completed_at', '')), ('异常信息', manifest.get('error', '') or '无'),
])}</table></div></section>
<section class="panel"><h2>北东平面遥测轨迹</h2>{_trajectory_svg(telemetry)}</section>
<section class="columns"><div class="panel"><h2>视觉类别证据</h2><table><tr><th>类别</th><th>图片数</th></tr>{evidence_rows}</table></div>
<div class="panel"><h2>成果预览</h2><div class="gallery">{images}</div></div></section>
<section class="panel"><h2>交付文件</h2><table class="artifacts"><tr><th>相对路径</th><th>类型</th><th>字节</th></tr>{artifact_rows}</table></section>
<script type="application/json" id="manifest">{escape(json.dumps(manifest, ensure_ascii=False))}</script>
</main></body></html>"""
    target = root / "report.html"
    target.write_text(report, encoding="utf-8")
    return target
