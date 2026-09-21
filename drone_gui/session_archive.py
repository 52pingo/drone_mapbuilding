"""Create, finalize, and recover portable mission Session directories."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import threading
from typing import Callable, Iterable

import numpy as np

from drone_gui.report_export import generate_report
from scripts.map_bridge_core import write_pcd, write_ply


try:
    from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
    _QT_AVAILABLE = True
except ImportError:
    try:
        from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal as Signal
        _QT_AVAILABLE = True
    except ImportError:
        try:
            from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal as Signal
            _QT_AVAILABLE = True
        except ImportError:
            QObject = object
            QRunnable = object
            QThreadPool = None
            Signal = None
            _QT_AVAILABLE = False


STATUS_PREFIX = "GUI_STATUS "
MANIFEST_NAME = "manifest.json"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_dir(path.parent)


def _atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    _atomic_write_bytes(path, text.encode(encoding))


def _atomic_json(path: Path, payload: dict) -> None:
    _atomic_write_text(
        path, json.dumps(payload, ensure_ascii=False, indent=2), "utf-8"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(root: Path) -> dict:
    path = root / MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


if _QT_AVAILABLE:
    class _ScanSignals(QObject):
        finished = Signal(object)
        failed = Signal(str)

    class SessionScanTask(QRunnable):
        """Runnable that scans a results directory off the GUI thread."""

        def __init__(self, scanner: "SessionScanner", results_dir: Path) -> None:
            super().__init__()
            self.signals = _ScanSignals()
            self._scanner = scanner
            self._results_dir = results_dir

        def run(self) -> None:
            try:
                payload = self._scanner.scan_sessions(self._results_dir)
            except Exception as exc:  # noqa: BLE001 - surface to GUI
                self.signals.failed.emit(str(exc))
                return
            self.signals.finished.emit(payload)


class SessionScanner:
    """Scan a results directory for session folders.

    Results are cached keyed by (path, dir mtime/size, manifest mtime/size) so
    unchanged sessions are not re-walked on every scan. The synchronous
    ``scan_sessions`` path is preserved for tests; ``scan_sessions_async``
    dispatches the same work to a QThreadPool and delivers results via signals.
    """

    def __init__(self) -> None:
        self._cache: dict[str, tuple[tuple, dict]] = {}
        self._lock = threading.Lock()
        self._tasks: set = set()

    def _signature(self, session_dir: Path) -> tuple:
        try:
            st = session_dir.stat()
            dir_sig = (st.st_mtime_ns, st.st_size)
        except OSError:
            dir_sig = (-1, -1)
        try:
            mst = (session_dir / MANIFEST_NAME).stat()
            man_sig = (mst.st_mtime_ns, mst.st_size)
        except OSError:
            man_sig = (-1, -1)
        return dir_sig + man_sig

    def _scan_one(self, session_dir: Path) -> dict:
        manifest = load_manifest(session_dir)
        artifact_count = 0
        total_size = 0
        try:
            for item in session_dir.rglob("*"):
                if not item.is_file():
                    continue
                if item.suffix == ".tmp":
                    continue
                artifact_count += 1
                try:
                    total_size += item.stat().st_size
                except OSError:
                    pass
        except OSError:
            pass
        return {
            "path": str(session_dir),
            "session_id": manifest.get("session_id", session_dir.name),
            "status": manifest.get("status", "unknown"),
            "created_at": manifest.get("created_at"),
            "updated_at": manifest.get("updated_at"),
            "completed_at": manifest.get("completed_at"),
            "summary": manifest.get("summary", {}),
            "artifact_count": artifact_count,
            "size_bytes": total_size,
        }

    def scan_sessions(self, results_dir: Path) -> list[dict]:
        results_dir = Path(results_dir)
        if not results_dir.is_dir():
            return []
        try:
            children = sorted(
                (child for child in results_dir.iterdir() if child.is_dir()),
                key=lambda p: p.name,
            )
        except OSError:
            return []
        results: list[dict] = []
        for child in children:
            key = str(child)
            signature = self._signature(child)
            with self._lock:
                cached = self._cache.get(key)
            if cached is not None and cached[0] == signature:
                results.append(cached[1])
                continue
            info = self._scan_one(child)
            with self._lock:
                self._cache[key] = (signature, info)
            results.append(info)
        return results

    def invalidate(self, path: Path | None = None) -> None:
        with self._lock:
            if path is None:
                self._cache.clear()
            else:
                self._cache.pop(str(Path(path)), None)

    def scan_sessions_async(
        self,
        results_dir: Path,
        on_finished: Callable[[list[dict]], None],
        on_failed: Callable[[str], None] | None = None,
    ):
        if not _QT_AVAILABLE:
            try:
                payload = self.scan_sessions(results_dir)
            except Exception as exc:  # noqa: BLE001
                if on_failed is not None:
                    on_failed(str(exc))
                return None
            on_finished(payload)
            return None
        task = SessionScanTask(self, Path(results_dir))
        task.setAutoDelete(False)
        task.signals.finished.connect(on_finished)
        if on_failed is not None:
            task.signals.failed.connect(on_failed)
        with self._lock:
            self._tasks.add(task)
        task.signals.finished.connect(lambda _r, t=task: self._release(t))
        task.signals.failed.connect(lambda _e, t=task: self._release(t))
        QThreadPool.globalInstance().start(task)
        return task

    def _release(self, task) -> None:
        with self._lock:
            self._tasks.discard(task)


_default_scanner: SessionScanner | None = None
_default_scanner_lock = threading.Lock()


def get_scanner() -> SessionScanner:
    global _default_scanner
    with _default_scanner_lock:
        if _default_scanner is None:
            _default_scanner = SessionScanner()
        return _default_scanner


def scan_sessions(results_dir: Path) -> list[dict]:
    return get_scanner().scan_sessions(results_dir)


def scan_sessions_async(
    results_dir: Path,
    on_finished: Callable[[list[dict]], None],
    on_failed: Callable[[str], None] | None = None,
):
    return get_scanner().scan_sessions_async(results_dir, on_finished, on_failed)


def initialize_session(
    root: Path, mission: dict, weights: Path | None = None,
    perception: dict | None = None,
) -> dict:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    previous = load_manifest(root)
    model = {"name": "", "sha256": "", "size": 0}
    if weights is not None and weights.is_file():
        model = {
            "name": weights.name,
            "sha256": _sha256(weights),
            "size": weights.stat().st_size,
        }
    manifest = {
        "schema": 1,
        "session_id": root.name,
        "status": "running",
        "coordinate_frame": "px4_local_ned",
        "created_at": previous.get("created_at", _now()),
        "updated_at": _now(),
        "completed_at": None,
        "mission": mission,
        "perception": perception or {},
        "model": model,
        "summary": {},
        "artifacts": [],
        "error": None,
    }
    _atomic_json(root / "mission.json", mission)
    _atomic_json(root / MANIFEST_NAME, manifest)
    get_scanner().invalidate(root)
    return manifest


def _parse_console(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    frames = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        marker = line.find(STATUS_PREFIX)
        if marker < 0:
            continue
        try:
            payload = json.loads(line[marker + len(STATUS_PREFIX):])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            frames.append(payload)
    return frames


def _parse_legacy_flight(root: Path) -> list[dict]:
    path = root / "avoid_flight.log"
    if not path.is_file():
        return []
    frames = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 14:
            continue
        try:
            elapsed, north, east, down = map(float, (parts[0], *parts[2:5]))
            dc, dl, dr = map(float, parts[5:8])
            vn, ve, vd = map(float, parts[9:12])
        except ValueError:
            continue
        obstacle = min(dc, dl, dr)
        frames.append({
            "elapsed": elapsed,
            "state": parts[1],
            "armed": None,
            "nav_state": None,
            "position": [north, east, down],
            "velocity": [vn, ve, vd],
            "goal": None,
            "goal_index": None,
            "goal_count": None,
            "goal_distance": None,
            "nearest_obstacle": obstacle if obstacle < 900 else None,
            "action": parts[8],
            "resumable": False,
        })
    console_path = root / "mission_console.log"
    console = (
        console_path.read_text(encoding="utf-8", errors="replace")
        if console_path.is_file() else ""
    )
    if frames and "MISSION DONE" in console.upper() and "DISARMED" in console.upper():
        final = dict(frames[-1])
        match = re.search(r"elapsed=([0-9.]+)s", console)
        final.update({
            "elapsed": float(match.group(1)) if match else final["elapsed"],
            "state": "DONE", "armed": False, "action": "mission_done",
        })
        frames.append(final)
    return frames


def load_telemetry(root: Path) -> list[dict]:
    jsonl = root / "telemetry.jsonl"
    if jsonl.is_file():
        frames = []
        for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                frames.append(payload)
        if frames:
            return frames
    frames = _parse_console(root / "mission_console.log")
    return frames if frames else _parse_legacy_flight(root)


def _write_telemetry(root: Path, frames: Iterable[dict]) -> list[dict]:
    values = list(frames)
    _atomic_write_text(
        root / "telemetry.jsonl",
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in values),
        "utf-8",
    )
    columns = [
        "elapsed", "state", "armed", "nav_state", "north", "east", "down",
        "vn", "ve", "vd", "goal_north", "goal_east", "goal_index",
        "goal_count", "goal_distance", "nearest_obstacle", "action", "resumable",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for item in values:
        position = item.get("position") or [None, None, None]
        velocity = item.get("velocity") or [None, None, None]
        goal = item.get("goal") or [None, None]
        writer.writerow({
            "elapsed": item.get("elapsed"), "state": item.get("state"),
            "armed": item.get("armed"), "nav_state": item.get("nav_state"),
            "north": position[0], "east": position[1], "down": position[2],
            "vn": velocity[0], "ve": velocity[1], "vd": velocity[2],
            "goal_north": goal[0], "goal_east": goal[1],
            "goal_index": item.get("goal_index"),
            "goal_count": item.get("goal_count"),
            "goal_distance": item.get("goal_distance"),
            "nearest_obstacle": item.get("nearest_obstacle"),
            "action": item.get("action"), "resumable": item.get("resumable"),
        })
    _atomic_write_text(root / "telemetry.csv", buffer.getvalue(), "utf-8-sig")
    return values


def _semantic_objects(root: Path) -> list[dict]:
    candidates = (
        root / "detected_classes" / "semantic_objects.json",
        root / "semantic_objects.json",
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        values = payload.get("objects", []) if isinstance(payload, dict) else []
        if isinstance(values, list):
            return [item for item in values if isinstance(item, dict)]
    return []


def _export_final_cloud(root: Path, semantics: list[dict]) -> int:
    latest = root / "live_map" / "latest.json"
    if not latest.is_file():
        return 0
    try:
        metadata = json.loads(latest.read_text(encoding="utf-8"))
        point_file = root / "live_map" / Path(str(metadata["points"])).name
        points = np.load(point_file, allow_pickle=False)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return 0
    if points.ndim != 2 or points.shape[1] != 3:
        return 0
    write_ply(root / "semantic_map.ply", points, semantics)
    write_pcd(root / "semantic_map.pcd", points, semantics)
    _fsync_dir(root)
    _atomic_json(root / "semantic_objects.json", {
        "coordinate_frame": "px4_local_ned",
        "render_axes": "north_east_height_up",
        "objects": semantics,
    })
    return int(len(points))


def _artifact_inventory(root: Path) -> list[dict]:
    ignored = {MANIFEST_NAME, "report.html"}
    artifacts = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name in ignored or path.suffix == ".tmp":
            continue
        relative = path.relative_to(root).as_posix()
        suffix = path.suffix.lower().lstrip(".") or "file"
        artifacts.append({
            "path": relative,
            "kind": suffix,
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        })
    return artifacts


def finalize_session(root: Path, requested_status: str, error: str = "") -> dict:
    root = root.resolve()
    manifest = load_manifest(root)
    if not manifest:
        manifest = initialize_session(root, {"name": root.name})
    telemetry = _write_telemetry(root, load_telemetry(root))
    semantics = _semantic_objects(root)
    point_count = _export_final_cloud(root, semantics)
    last = telemetry[-1] if telemetry else {}
    closed_loop = last.get("state") == "DONE" and last.get("armed") is False
    status = requested_status
    if requested_status == "completed" and not closed_loop:
        status = "incomplete"
    manifest.update({
        "status": status,
        "updated_at": _now(),
        "completed_at": _now(),
        "error": error or None,
        "summary": {
            "telemetry_samples": len(telemetry),
            "point_count": point_count,
            "semantic_objects": len(semantics),
            "closed_loop": closed_loop,
            "final_state": last.get("state"),
            "final_armed": last.get("armed"),
        },
    })
    artifacts = _artifact_inventory(root)
    manifest["artifacts"] = artifacts
    _atomic_json(root / MANIFEST_NAME, manifest)
    generate_report(root, manifest, telemetry, artifacts)
    get_scanner().invalidate(root)
    return manifest


def recover_session(root: Path) -> dict:
    """Rebuild a partial/legacy archive without overstating mission safety."""
    telemetry = load_telemetry(root)
    last = telemetry[-1] if telemetry else {}
    requested = (
        "completed"
        if last.get("state") == "DONE" and last.get("armed") is False
        else "interrupted"
    )
    return finalize_session(root, requested)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a portable mission Session")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("init")
    start.add_argument("--root", type=Path, required=True)
    start.add_argument("--name", default="CityPark 大环线")
    start.add_argument("--goals", default="")
    start.add_argument("--flight-z", type=float, default=-15.0)
    start.add_argument("--max-mission-time", type=float, default=1200.0)
    start.add_argument("--weights", type=Path)
    start.add_argument("--confidence", type=float, default=0.25)
    finish = sub.add_parser("finalize")
    finish.add_argument("--root", type=Path, required=True)
    finish.add_argument(
        "--status", choices=("completed", "failed", "interrupted"), required=True
    )
    finish.add_argument("--error", default="")
    recover = sub.add_parser("recover")
    recover.add_argument("--root", type=Path, required=True)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "init":
        manifest = initialize_session(
            args.root,
            {
                "name": args.name, "goals": args.goals,
                "flight_z": args.flight_z,
                "max_mission_time": args.max_mission_time,
            },
            args.weights,
            {"confidence": args.confidence},
        )
    elif args.command == "finalize":
        manifest = finalize_session(args.root, args.status, args.error)
    else:
        manifest = recover_session(args.root)
    print(json.dumps({
        "session": manifest.get("session_id"),
        "status": manifest.get("status"),
        "summary": manifest.get("summary", {}),
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
