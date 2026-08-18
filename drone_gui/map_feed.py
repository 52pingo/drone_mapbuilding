"""Non-blocking reader for WSL OctoMap NPY/JSON snapshots."""

from __future__ import annotations

import json
from pathlib import Path
import time

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal


class MapFeed(QObject):
    snapshot_ready = Signal(object, dict)
    state_changed = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._poll)
        self.directory: Path | None = None
        self._last_sequence = -1
        self._started_at = 0.0
        self._last_received = 0.0
        self._last_state = ""

    def start(self, session: dict) -> bool:
        value = session.get("map_dir")
        if not isinstance(value, str):
            self._emit_state("error", "Session 未提供实时地图目录")
            return False
        self.directory = Path(value)
        self._last_sequence = -1
        self._started_at = time.monotonic()
        self._last_received = 0.0
        self._last_state = ""
        self._emit_state("running", "等待首个 OctoMap 快照")
        self.timer.start()
        return True

    def stop(self, message: str = "地图流已停止") -> None:
        self.timer.stop()
        self._emit_state("ready", message)

    def _emit_state(self, state: str, message: str) -> None:
        marker = f"{state}:{message}"
        if marker == self._last_state:
            return
        self._last_state = marker
        self.state_changed.emit(state, message)

    def _poll(self) -> None:
        if self.directory is None:
            return
        latest = self.directory / "latest.json"
        if not latest.is_file():
            if time.monotonic() - self._started_at > 15.0:
                self._emit_state("warning", "尚未收到地图，请检查 OctoMap 话题")
            return
        try:
            metadata = json.loads(latest.read_text(encoding="utf-8"))
            sequence = int(metadata["sequence"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            self._emit_state("warning", "地图状态文件暂不可读")
            return
        if sequence == self._last_sequence:
            if self._last_received and time.monotonic() - self._last_received > 4.0:
                self._emit_state("warning", "OctoMap 超过 4 秒未更新")
            return
        point_name = Path(str(metadata.get("points", ""))).name
        try:
            points = np.load(self.directory / point_name, allow_pickle=False)
        except (OSError, ValueError):
            self._emit_state("warning", "点云快照暂不可读")
            return
        if points.ndim != 2 or points.shape[1] != 3:
            self._emit_state("error", "点云快照必须是 N×3")
            return
        points = np.asarray(points, dtype=np.float32)
        self._last_sequence = sequence
        self._last_received = time.monotonic()
        self.snapshot_ready.emit(points, metadata)
        self._emit_state("running", f"{len(points):,} 点 · NED 实时地图")
