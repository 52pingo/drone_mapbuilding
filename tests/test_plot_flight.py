#!/usr/bin/env python3
"""pytest for scripts/plot_flight.py — log parsing behavior via subprocess.

The parsing logic is inlined at module level in the script, so we exercise it
by running the script with crafted log files and asserting on stdout/stderr.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")


def _find_script():
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "scripts" / "plot_flight.py"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("scripts/plot_flight.py not found next to tests")


SCRIPT = _find_script()
ROUTE = "0,0;2,2"


def run(log_path, out_path, route=ROUTE):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(log_path), str(out_path), route, "Test"],
        capture_output=True,
        text=True,
    )


def nav(t, x, y, decision="go"):
    # 13 whitespace-separated fields: t action x y z vx vy vz decision + 4 filler
    return f"{t} NAVIGATE {x} {y} 0 0 0 0 {decision} 0 0 0 0"


def write_log(tmp_path, text, name="avoid_flight.log", encoding="utf-8"):
    p = tmp_path / name
    p.write_text(text, encoding=encoding)
    return p


def action_count(stdout, action):
    m = re.search(rf"^\s*{re.escape(action)}\s+(\d+)\s*$", stdout, re.M)
    return int(m.group(1)) if m else None


def test_normal_log_parses(tmp_path):
    log = write_log(
        tmp_path,
        "\n".join(
            [
                "# t action x y z vx vy vz decision ...",
                nav(0.0, 0.0, 0.0, "go"),
                nav(1.0, 1.0, 1.0, "go"),
                nav(2.0, 2.0, 2.0, "slow"),
                nav(3.0, 3.0, 3.0, "arrived"),
            ]
        )
        + "\n",
    )
    out = tmp_path / "out.png"
    r = run(log, out)
    assert r.returncode == 0, r.stderr
    assert "rows=4 navigate=4" in r.stdout
    assert "start  : t=0s pos=(0.0,0.0)" in r.stdout
    assert "final  : t=3s pos=(3.0,3.0)" in r.stdout
    assert "elapsed: 3s" in r.stdout
    assert action_count(r.stdout, "go") == 3
    assert action_count(r.stdout, "slow") == 1
    assert action_count(r.stdout, "arrived") == 1
    assert out.exists()


def test_empty_file(tmp_path):
    log = write_log(tmp_path, "")
    out = tmp_path / "out.png"
    r = run(log, out)
    assert r.returncode == 1
    assert "rows=0 navigate=0" in r.stdout
    assert "No NAVIGATE rows found" in r.stderr
    assert "Traceback" not in r.stderr


def test_header_only_no_hash(tmp_path):
    log = write_log(tmp_path, "t action x y z vx vy vz decision\n")
    out = tmp_path / "out.png"
    r = run(log, out)
    assert "rows=0 navigate=0" in r.stdout
    assert "ValueError" not in r.stderr
    assert "No NAVIGATE rows found" in r.stderr


def test_header_line_skipped_but_data_parsed(tmp_path):
    log = write_log(
        tmp_path,
        "t action x y z vx vy vz decision\n" + nav(0.0, 0.0, 0.0) + "\n",
    )
    out = tmp_path / "out.png"
    r = run(log, out)
    assert r.returncode == 0, r.stderr
    assert "rows=1 navigate=1" in r.stdout


def test_utf8_bom_on_comment_line(tmp_path):
    log = write_log(tmp_path, "\ufeff# comment\n" + nav(0.0, 0.0, 0.0) + "\n")
    out = tmp_path / "out.png"
    r = run(log, out)
    assert r.returncode == 0, r.stderr
    assert "rows=1 navigate=1" in r.stdout


def test_utf8_bom_on_data_line(tmp_path):
    log = write_log(
        tmp_path,
        "\ufeff" + nav(0.0, 0.0, 0.0) + "\n" + nav(1.0, 1.0, 1.0) + "\n",
    )
    out = tmp_path / "out.png"
    r = run(log, out)
    # BOM sticks to the first token → float("\ufeff0.0") raises
    assert r.returncode == 1
    assert "ValueError" in r.stderr


def test_short_line_skipped(tmp_path):
    log = write_log(
        tmp_path,
        "\n".join(
            [
                nav(0.0, 0.0, 0.0),
                "1 NAVIGATE 1 1 0",  # only 5 fields
                nav(2.0, 2.0, 2.0),
            ]
        )
        + "\n",
    )
    out = tmp_path / "out.png"
    r = run(log, out)
    assert r.returncode == 0, r.stderr
    assert "rows=2 navigate=2" in r.stdout


def test_non_numeric_first_column(tmp_path):
    log = write_log(
        tmp_path,
        "\n".join(
            [
                nav(0.0, 0.0, 0.0),
                "abc NAVIGATE 1 1 0 0 0 0 go 0 0 0 0",
                nav(2.0, 2.0, 2.0),
            ]
        )
        + "\n",
    )
    out = tmp_path / "out.png"
    r = run(log, out)
    # current code has no try/except around float(parts[0]) → whole run dies
    assert r.returncode == 1
    assert "ValueError" in r.stderr
    assert "abc" in r.stderr


def test_missing_file(tmp_path):
    log = tmp_path / "does_not_exist.log"
    out = tmp_path / "out.png"
    r = run(log, out)
    assert r.returncode == 1
    assert "FileNotFoundError" in r.stderr
    assert "does_not_exist.log" in r.stderr
