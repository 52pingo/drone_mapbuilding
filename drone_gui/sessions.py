"""Read-only discovery of mission results and semantic evidence."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from drone_gui.session_archive import load_manifest

try:
    from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without Qt
    _QT_AVAILABLE = False


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
DELIVERABLE_SUFFIXES = {".ply", ".pcd", ".bt", ".ot", ".json", ".csv", ".html"}


@dataclass
class SessionSummary:
    path: Path
    class_images: Dict[str, List[Path]] = field(default_factory=dict)
    map_images: List[Path] = field(default_factory=list)
    deliverables: List[Path] = field(default_factory=list)
    status: str = "legacy"
    telemetry_samples: int = 0
    point_count: int = 0
    semantic_objects: int = 0

    @property
    def image_count(self) -> int:
        return sum(len(images) for images in self.class_images.values())


# ---------------------------------------------------------------------------
# Cache: keyed by session folder path, value = ((mtime_ns, size), summary).
# Guarded by a lock because scan_sessions runs on QThreadPool worker threads.
# ---------------------------------------------------------------------------
_CACHE_LOCK = threading.Lock()
_SESSION_CACHE: Dict[Path, Tuple[Tuple[int, int], SessionSummary]] = {}


def _dir_fingerprint(path: Path) -> Tuple[int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (0, 0)
    return (stat.st_mtime_ns, stat.st_size)


def _scan_session_folder(folder: Path) -> Optional[SessionSummary]:
    detected = folder / "detected_classes"
    class_images: Dict[str, List[Path]] = {}
    if detected.is_dir():
        for class_dir in sorted(path for path in detected.iterdir() if path.is_dir()):
            images = sorted(
                path for path in class_dir.iterdir()
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
            )
            if images:
                class_images[class_dir.name] = images
    map_images = sorted(
        path for path in folder.iterdir()
        if path.is_file()
        and path.suffix.lower() == ".png"
        and any(token in path.name.lower() for token in ("map", "depth", "trajectory"))
    )
    manifest = load_manifest(folder)
    deliverables = sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in DELIVERABLE_SUFFIXES
    )
    if not (class_images or map_images or deliverables or manifest):
        return None
    summary = manifest.get("summary", {})
    return SessionSummary(
        path=folder,
        class_images=class_images,
        map_images=map_images,
        deliverables=deliverables,
        status=str(manifest.get("status", "legacy")),
        telemetry_samples=int(summary.get("telemetry_samples", 0)),
        point_count=int(summary.get("point_count", 0)),
        semantic_objects=int(summary.get("semantic_objects", 0)),
    )


def scan_sessions(results_dir: Path) -> List[SessionSummary]:
    if not results_dir.is_dir():
        return []
    sessions: List[SessionSummary] = []
    for folder in results_dir.iterdir():
        if not folder.is_dir():
            continue
        fingerprint = _dir_fingerprint(folder)
        with _CACHE_LOCK:
            cached = _SESSION_CACHE.get(folder)
        if cached is not None and cached[0] == fingerprint:
            summary = cached[1]
        else:
            summary = _scan_session_folder(folder)
            with _CACHE_LOCK:
                if summary is None:
                    _SESSION_CACHE.pop(folder, None)
                else:
                    _SESSION_CACHE[folder] = (fingerprint, summary)
        if summary is not None:
            sessions.append(summary)
    return sorted(sessions, key=lambda item: item.path.stat().st_mtime, reverse=True)


# ---------------------------------------------------------------------------
# Async entry point: runs scan_sessions on the global QThreadPool and delivers
# the result back on the caller's thread via Qt signals. Falls back to a
# synchronous call when Qt is unavailable.
# ---------------------------------------------------------------------------
if _QT_AVAILABLE:
    class _ScanSignals(QObject):
        finished = Signal(object)
        failed = Signal(object)

    class _ScanTask(QRunnable):
        def __init__(self, results_dir: Path, signals: "_ScanSignals") -> None:
            super().__init__()
            self._results_dir = results_dir
            self._signals = signals

        @Slot()
        def run(self) -> None:
            try:
                result = scan_sessions(self._results_dir)
            except Exception as exc:  # noqa: BLE001 - surfaced to on_failed
                self._signals.failed.emit(exc)
            else:
                self._signals.finished.emit(result)


# Keeps the per-call signals object alive until its callback fires.
_ACTIVE_SCANS: set = set()


def scan_sessions_async(
    results_dir: Path,
    on_finished: Callable[[List[SessionSummary]], None],
    on_failed: Optional[Callable[[BaseException], None]] = None,
) -> None:
    if not _QT_AVAILABLE:
        try:
            result = scan_sessions(results_dir)
        except Exception as exc:  # noqa: BLE001
            if on_failed is not None:
                on_failed(exc)
            else:
                raise
        else:
            on_finished(result)
        return

    signals = _ScanSignals()
    task = _ScanTask(results_dir, signals)
    _ACTIVE_SCANS.add(signals)

    def _cleanup() -> None:
        _ACTIVE_SCANS.discard(signals)

    def _handle_finished(result) -> None:
        _cleanup()
        on_finished(result)

    def _handle_failed(exc) -> None:
        _cleanup()
        if on_failed is not None:
            on_failed(exc)

    signals.finished.connect(_handle_finished)
    signals.failed.connect(_handle_failed)
    QThreadPool.globalInstance().start(task)


def session_payload(root: Path, offline: bool = True) -> dict:
    root = root.resolve()
    return {
        "result_root": str(root),
        "semantic_dir": str(root / "detected_classes"),
        "live_dir": str(root / "live_feed"),
        "map_dir": str(root / "live_map"),
        "offline": offline,
    }
