"""Time-based offline playback for structured mission telemetry."""

from __future__ import annotations

from bisect import bisect_right
from pathlib import Path
import time

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from drone_gui.session_archive import load_telemetry


def trajectory_until(frames: list[dict], index: int) -> list[list[float]]:
    """Build a bounded, distance-filtered NED path through a replay frame."""
    result: list[list[float]] = []
    for frame in frames[:index + 1]:
        value = frame.get("position")
        if not isinstance(value, list) or len(value) != 3:
            continue
        point = [float(item) for item in value]
        if result and np.linalg.norm(np.asarray(point) - np.asarray(result[-1])) < 0.25:
            continue
        result.append(point)
    return result[-5000:]


class ReplayController(QObject):
    frame_ready = Signal(dict, object)
    state_changed = Signal(str, str)
    position_changed = Signal(int, int, float, float)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self._tick)
        self.frames: list[dict] = []
        self.elapsed: list[float] = []
        self.index = 0
        self.playhead = 0.0
        self.speed = 1.0
        self._last_tick = 0.0

    def load(self, root: Path) -> bool:
        self.pause()
        values = load_telemetry(root)
        self.frames = [item for item in values if isinstance(item, dict)]
        self.elapsed = [max(0.0, float(item.get("elapsed", 0.0))) for item in self.frames]
        self.index = 0
        self.playhead = self.elapsed[0] if self.elapsed else 0.0
        if not self.frames:
            self.state_changed.emit("warning", "该 Session 没有可回放遥测")
            self.position_changed.emit(0, 0, 0.0, 0.0)
            return False
        self.state_changed.emit("ready", "遥测已载入，按播放开始回放")
        self._emit_frame()
        return True

    def play(self) -> None:
        if not self.frames:
            return
        if self.index >= len(self.frames) - 1:
            self.seek(0)
        self._last_tick = time.monotonic()
        self.timer.start()
        self.state_changed.emit("running", f"正在以 {self.speed:g}× 回放")

    def pause(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.state_changed.emit("ready", "回放已暂停")

    def toggle(self) -> None:
        self.pause() if self.timer.isActive() else self.play()

    def set_speed(self, speed: float) -> None:
        self.speed = max(0.25, min(8.0, float(speed)))
        if self.timer.isActive():
            self.state_changed.emit("running", f"正在以 {self.speed:g}× 回放")

    def seek(self, index: int) -> None:
        if not self.frames:
            return
        self.index = max(0, min(len(self.frames) - 1, int(index)))
        self.playhead = self.elapsed[self.index]
        self._last_tick = time.monotonic()
        self._emit_frame()

    def _tick(self) -> None:
        now = time.monotonic()
        self.playhead += max(0.0, now - self._last_tick) * self.speed
        self._last_tick = now
        index = bisect_right(self.elapsed, self.playhead) - 1
        index = max(self.index, min(len(self.frames) - 1, index))
        if index != self.index:
            self.index = index
            self._emit_frame()
        if self.index >= len(self.frames) - 1:
            self.timer.stop()
            self.state_changed.emit("ready", "回放完成")

    def _emit_frame(self) -> None:
        frame = self.frames[self.index]
        history = trajectory_until(self.frames, self.index)
        self.frame_ready.emit(frame, history)
        self.position_changed.emit(
            self.index, len(self.frames), self.elapsed[self.index], self.elapsed[-1]
        )
