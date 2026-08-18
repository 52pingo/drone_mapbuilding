"""Non-blocking reader for semantic perception JPEG/JSON snapshots."""

from __future__ import annotations

import json
from pathlib import Path
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage


class PerceptionFeed(QObject):
    frame_ready = Signal(QImage)
    snapshot_ready = Signal(dict)
    state_changed = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._poll)
        self.live_dir: Path | None = None
        self.semantic_dir: Path | None = None
        self._last_frame_index = -1
        self._started_at = 0.0
        self._last_received = 0.0
        self._last_state = ""

    def start(self, session: dict) -> bool:
        live_dir = session.get("live_dir")
        semantic_dir = session.get("semantic_dir")
        if not isinstance(live_dir, str) or not isinstance(semantic_dir, str):
            self.state_changed.emit("error", "Session 未提供视觉数据目录")
            return False
        self.live_dir = Path(live_dir)
        self.semantic_dir = Path(semantic_dir)
        self._last_frame_index = -1
        self._started_at = time.monotonic()
        self._last_received = 0.0
        self._last_state = ""
        self._emit_state("running", "等待 YOLO 首帧")
        self.timer.start()
        return True

    def stop(self, message: str = "视觉流已停止") -> None:
        self.timer.stop()
        self._emit_state("ready", message)

    def _emit_state(self, state: str, message: str) -> None:
        marker = f"{state}:{message}"
        if marker == self._last_state:
            return
        self._last_state = marker
        self.state_changed.emit(state, message)

    def _poll(self) -> None:
        if self.live_dir is None or self.semantic_dir is None:
            return
        latest = self.live_dir / "latest.json"
        if not latest.is_file():
            if time.monotonic() - self._started_at > 12.0:
                self._emit_state("warning", "尚未收到视觉帧，请检查 AirSim RGB")
            return
        try:
            snapshot = json.loads(latest.read_text(encoding="utf-8"))
            frame_index = int(snapshot["frame_index"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            self._emit_state("warning", "视觉状态文件暂不可读")
            return
        if frame_index == self._last_frame_index:
            if self._last_received and time.monotonic() - self._last_received > 3.0:
                self._emit_state("warning", "视觉流超过 3 秒未更新")
            return
        image_name = Path(str(snapshot.get("image", "frame.jpg"))).name
        try:
            image = QImage.fromData((self.live_dir / image_name).read_bytes(), "JPG")
        except OSError:
            self._emit_state("warning", "带框图像暂不可读")
            return
        if image.isNull():
            self._emit_state("warning", "带框图像解码失败")
            return

        detections = snapshot.get("detections")
        snapshot["detections"] = detections if isinstance(detections, list) else []
        objects = snapshot.get("semantic_objects")
        snapshot["semantic_objects"] = objects if isinstance(objects, list) else []
        size = snapshot.get("size")
        snapshot["size"] = size if isinstance(size, list) and len(size) == 2 else [0, 0]
        try:
            snapshot["fps"] = float(snapshot.get("fps", 0.0))
        except (TypeError, ValueError):
            snapshot["fps"] = 0.0
        snapshot["catalog"] = self._resolve_catalog(snapshot.get("catalog", []))
        self._last_frame_index = frame_index
        self._last_received = time.monotonic()
        self.frame_ready.emit(image)
        self.snapshot_ready.emit(snapshot)
        fps = float(snapshot.get("fps", 0.0))
        count = len(snapshot.get("detections", []))
        self._emit_state("running", f"{fps:.1f} FPS · {count} 个目标")

    def _resolve_catalog(self, values) -> list[dict]:
        catalog = []
        for value in values if isinstance(values, list) else []:
            if not isinstance(value, dict):
                continue
            item = dict(value)
            for key in ("first_image", "last_image"):
                relative = item.get(key)
                if isinstance(relative, str):
                    relative_path = Path(relative)
                    if relative_path.is_absolute() or ".." in relative_path.parts:
                        item[key] = None
                    else:
                        item[key] = str(self.semantic_dir / relative_path)
            catalog.append(item)
        return catalog
