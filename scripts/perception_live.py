"""Atomic live-frame protocol for the Qt perception monitor."""

from __future__ import annotations

import datetime as dt
from collections import deque
import itertools
import json
import os
from pathlib import Path
import time
from typing import Sequence

#: How many recent ``frame_*.jpg`` files stay on disk. Must comfortably exceed
#: the reader's "read latest.json -> parse -> read image" window; at 30 Hz this
#: is ~1 s of slack.
DEFAULT_RETAIN = 30

#: Process-wide monotonic counter so concurrent writers never share a temp path.
_TMP_SEQ = itertools.count()

#: Temp files older than this are assumed to be crash leftovers and are reaped.
_TMP_STALE_SECONDS = 5.0


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
        "position_ned": (
            [round(float(value), 3) for value in detection.world_ned]
            if getattr(detection, "world_ned", None) is not None else None
        ),
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
    semantic_objects: Sequence[dict] = (),
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
        "semantic_objects": list(semantic_objects),
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


def read_latest_snapshot(directory: Path, retries: int = 1) -> tuple[dict, bytes]:
    """Read ``latest.json`` plus its frame image, retrying a raced deletion.

    The writer commits the JPEG before the JSON, so a reader that wins the race
    against the retention sweep can still observe a missing image. One retry
    re-reads the (now newer) manifest instead of raising ``FileNotFoundError``.
    """
    directory = Path(directory)
    for attempt in range(retries + 1):
        try:
            snapshot = json.loads((directory / "latest.json").read_text("utf-8"))
            image = (directory / str(snapshot["image"])).read_bytes()
            return snapshot, image
        except FileNotFoundError:
            if attempt >= retries:
                raise
    raise AssertionError("unreachable")


class LiveFrameWriter:
    """Commit JPEG first and JSON last so readers see complete frames."""

    def __init__(self, directory: Path, cv2, retain: int = DEFAULT_RETAIN) -> None:
        if retain < 1:
            raise ValueError("retain must be at least 1")
        self.directory = directory
        self.cv2 = cv2
        self.retain = int(retain)
        self.directory.mkdir(parents=True, exist_ok=True)
        # In-memory mirror of the on-disk frame window: append on publish,
        # popleft + unlink on overflow. No glob()/sorted() in the hot path.
        self._live_frames: deque[str] = deque()
        self._live_names: set[str] = set()
        self._reap_stale_temporaries()
        self._seed_from_disk()

    @staticmethod
    def _replace_bytes(path: Path, payload: bytes) -> None:
        """Atomically swap ``path`` for ``payload`` via a writer-unique temp."""
        temporary = path.with_name(
            f"{path.name}.{os.getpid()}.{next(_TMP_SEQ)}.tmp"
        )
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, path)
        except BaseException:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise

    def _reap_stale_temporaries(self) -> None:
        """Drop ``*.tmp`` left behind by a crashed writer.

        Only files older than ``_TMP_STALE_SECONDS`` are removed so a live
        concurrent writer's in-flight temp is never yanked out from under it.
        """
        cutoff = time.time() - _TMP_STALE_SECONDS
        for stale in self.directory.glob("*.tmp"):
            try:
                if stale.stat().st_mtime < cutoff:
                    stale.unlink()
            except OSError:
                pass

    def _seed_from_disk(self) -> None:
        """Adopt pre-existing frames once at construction, then trim to retain."""
        for name in sorted(path.name for path in self.directory.glob("frame_*.jpg")):
            self._live_frames.append(name)
            self._live_names.add(name)
        self._trim()

    def _trim(self) -> None:
        while len(self._live_frames) > self.retain:
            stale = self._live_frames.popleft()
            self._live_names.discard(stale)
            try:
                (self.directory / stale).unlink()
            except OSError:
                pass

    def _track(self, image_name: str) -> None:
        """Record a freshly written frame and evict the oldest beyond retain."""
        if image_name in self._live_names:
            # Same frame_index republished: move it to the back, keep one entry.
            try:
                self._live_frames.remove(image_name)
            except ValueError:
                pass
        else:
            self._live_names.add(image_name)
        self._live_frames.append(image_name)
        self._trim()

    def publish(self, frame, detections, events, frame_index: int, fps: float,
                semantic_objects=()) -> None:
        canvas = annotate_live(frame, detections, self.cv2, fps, frame_index)
        encoded, buffer = self.cv2.imencode(
            ".jpg", canvas, [self.cv2.IMWRITE_JPEG_QUALITY, 84]
        )
        if not encoded:
            raise RuntimeError("failed to encode GUI live frame")
        image_name = f"frame_{frame_index:06d}.jpg"
        self._replace_bytes(self.directory / image_name, buffer.tobytes())
        snapshot = build_snapshot(
            frame_index, frame.shape, fps, detections, events, image_name,
            semantic_objects,
        )
        self._replace_bytes(
            self.directory / "latest.json",
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )
        self._track(image_name)
