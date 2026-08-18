"""Atomic live-frame protocol for the Qt perception monitor."""

from __future__ import annotations

import datetime as dt
from collections import deque
import json
import os
from pathlib import Path
from typing import Sequence


class FrameRateMeter:
    """Estimate recent throughput without including model warm-up time."""

    def __init__(self, window: int = 20) -> None:
        if window < 2:
            raise ValueError("FPS window must be at least 2")
        self.samples = deque(maxlen=window)

    def tick(self, now: float) -> float:
        self.samples.append(float(now))
        if len(self.samples) < 2:
            return 0.0
        elapsed = self.samples[-1] - self.samples[0]
        return (len(self.samples) - 1) / elapsed if elapsed > 0.0 else 0.0


def detection_payload(detection) -> dict:
    """Convert a Detection-like object to the stable GUI wire schema."""
    return {
        "class_id": int(detection.class_id),
        "label": str(detection.label),
        "confidence": round(float(detection.confidence), 6),
        "depth_m": (
            round(float(detection.depth_m), 3)
            if detection.depth_m is not None else None
        ),
        "bbox_xyxy": [int(value) for value in detection.box],
    }


def evidence_catalog(events: Sequence[dict]) -> list[dict]:
    """Summarize the first and latest saved evidence for every class."""
    catalog = {}
    for event in events:
        label = str(event["label"])
        item = catalog.setdefault(label, {
            "label": label,
            "saved_count": 0,
            "first_image": event.get("image"),
            "last_image": event.get("image"),
            "max_confidence": 0.0,
            "last_depth_m": None,
        })
        item["saved_count"] = max(
            int(item["saved_count"]), int(event.get("class_image_index", 0))
        )
        item["last_image"] = event.get("image")
        item["max_confidence"] = max(
            float(item["max_confidence"]), float(event.get("confidence", 0.0))
        )
        item["last_depth_m"] = event.get("depth_m")
    return [catalog[label] for label in sorted(catalog)]


def build_snapshot(
    frame_index: int,
    frame_shape,
    fps: float,
    detections: Sequence,
    events: Sequence[dict],
    image_name: str = "frame.jpg",
) -> dict:
    """Build one JSON-serializable live perception snapshot."""
    height, width = frame_shape[:2]
    return {
        "schema": 1,
        "frame_index": int(frame_index),
        "captured_at": dt.datetime.now().astimezone().isoformat(),
        "fps": round(float(fps), 2),
        "size": [int(width), int(height)],
        "detections": [detection_payload(item) for item in detections],
        "catalog": evidence_catalog(events),
        "image": image_name,
    }


def annotate_live(frame, detections: Sequence, cv2, fps: float, frame_index: int):
    """Render the complete current detection set for the operator view."""
    canvas = frame.copy()
    palette = (
        (74, 201, 176), (89, 169, 244), (238, 180, 74),
        (207, 120, 232), (105, 215, 239), (103, 143, 238),
    )
    for detection in detections:
        x1, y1, x2, y2 = detection.box
        color = palette[int(detection.class_id) % len(palette)]
        depth = f" {detection.depth_m:.1f}m" if detection.depth_m is not None else ""
        label = f"{detection.label} {detection.confidence:.2f}{depth}"
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        (text_w, text_h), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2
        )
        top = max(0, y1 - text_h - baseline - 6)
        cv2.rectangle(canvas, (x1, top), (x1 + text_w + 8, y1), color, -1)
        cv2.putText(
            canvas, label, (x1 + 4, max(text_h + 1, y1 - baseline - 3)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.52, (12, 16, 18), 2, cv2.LINE_AA,
        )
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 30), (12, 18, 22), -1)
    cv2.putText(
        canvas,
        f"LIVE  frame {frame_index:06d}  {fps:.1f} FPS  objects {len(detections)}",
        (12, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
        (115, 222, 225), 2, cv2.LINE_AA,
    )
    return canvas


class LiveFrameWriter:
    """Commit JPEG first and JSON last so readers see complete frames."""

    def __init__(self, directory: Path, cv2) -> None:
        self.directory = directory
        self.cv2 = cv2
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _replace_bytes(path: Path, payload: bytes) -> None:
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, path)

    def publish(self, frame, detections, events, frame_index: int, fps: float) -> None:
        canvas = annotate_live(frame, detections, self.cv2, fps, frame_index)
        encoded, buffer = self.cv2.imencode(
            ".jpg", canvas, [self.cv2.IMWRITE_JPEG_QUALITY, 84]
        )
        if not encoded:
            raise RuntimeError("failed to encode GUI live frame")
        image_name = f"frame_{frame_index:06d}.jpg"
        self._replace_bytes(self.directory / image_name, buffer.tobytes())
        snapshot = build_snapshot(
            frame_index, frame.shape, fps, detections, events, image_name
        )
        self._replace_bytes(
            self.directory / "latest.json",
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )
        for old_frame in sorted(self.directory.glob("frame_*.jpg"))[:-3]:
            try:
                old_frame.unlink()
            except OSError:
                pass
