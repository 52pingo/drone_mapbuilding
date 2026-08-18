#!/usr/bin/env python3
"""AirSim RGB obstacle perception with per-class boxed scene capture."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import ssl
import sys
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from scripts.perception_live import FrameRateMeter, LiveFrameWriter
except ImportError:
    from perception_live import FrameRateMeter, LiveFrameWriter


@dataclasses.dataclass(frozen=True)
class Detection:
    class_id: int
    label: str
    confidence: float
    box: Tuple[int, int, int, int]
    depth_m: Optional[float] = None


class FirstSeenTracker:
    """Confirm a label for consecutive frames, then emit it exactly once."""

    def __init__(self, confirm_frames: int = 2) -> None:
        if confirm_frames < 1:
            raise ValueError("confirm_frames must be at least 1")
        self.confirm_frames = confirm_frames
        self.streaks: Dict[str, int] = {}
        self.seen = set()

    def update(self, detections: Iterable[Detection]) -> List[Detection]:
        best: Dict[str, Detection] = {}
        for detection in detections:
            current = best.get(detection.label)
            if current is None or detection.confidence > current.confidence:
                best[detection.label] = detection

        present = set(best)
        for label in list(self.streaks):
            if label not in present:
                self.streaks[label] = 0

        events = []
        for label, detection in best.items():
            self.streaks[label] = self.streaks.get(label, 0) + 1
            if (self.streaks[label] >= self.confirm_frames
                    and label not in self.seen):
                self.seen.add(label)
                events.append(detection)
        return events


class ClassEvidenceTracker:
    """Confirm detections and periodically emit representative class scenes."""

    def __init__(
        self,
        confirm_frames: int = 2,
        capture_interval: float = 4.0,
        max_images_per_class: int = 20,
    ) -> None:
        if confirm_frames < 1:
            raise ValueError("confirm_frames must be at least 1")
        if capture_interval < 0.0:
            raise ValueError("capture_interval cannot be negative")
        if max_images_per_class < 0:
            raise ValueError("max_images_per_class cannot be negative")
        self.confirm_frames = confirm_frames
        self.capture_interval = capture_interval
        self.max_images_per_class = max_images_per_class
        self.streaks: Dict[str, int] = {}
        self.last_capture: Dict[str, float] = {}
        self.counts: Dict[str, int] = {}

    def update(
        self,
        detections: Iterable[Detection],
        now: float,
    ) -> List[Detection]:
        best: Dict[str, Detection] = {}
        for detection in detections:
            current = best.get(detection.label)
            if current is None or detection.confidence > current.confidence:
                best[detection.label] = detection

        present = set(best)
        for label in list(self.streaks):
            if label not in present:
                self.streaks[label] = 0

        events = []
        for label, detection in best.items():
            self.streaks[label] = self.streaks.get(label, 0) + 1
            if self.streaks[label] < self.confirm_frames:
                continue
            count = self.counts.get(label, 0)
            if self.max_images_per_class > 0 and count >= self.max_images_per_class:
                continue
            last_capture = self.last_capture.get(label)
            if (last_capture is not None
                    and now - last_capture < self.capture_interval):
                continue
            self.last_capture[label] = now
            self.counts[label] = count + 1
            events.append(detection)
        return events


def parse_args() -> argparse.Namespace:
    workspace = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Detect AirSim obstacles and save boxed scene images in one "
            "folder per detected class."
        )
    )
    parser.add_argument("--weights", required=True)
    parser.add_argument("--output-dir", default=str(
        workspace / "results" / "semantic_first_seen"
    ))
    parser.add_argument("--camera", default="CameraDepth")
    parser.add_argument("--vehicle", default="PX4")
    parser.add_argument("--confidence", type=float, default=0.45)
    parser.add_argument("--iou", type=float, default=0.55)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--interval", type=float, default=0.35)
    parser.add_argument("--confirm-frames", type=int, default=2)
    parser.add_argument("--capture-interval", type=float, default=4.0)
    parser.add_argument("--max-images-per-class", type=int, default=20)
    parser.add_argument("--max-depth-m", type=float, default=60.0)
    parser.add_argument("--min-box-area-ratio", type=float, default=0.0008)
    parser.add_argument("--max-runtime", type=float, default=0.0)
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--stop-file", default="")
    parser.add_argument("--live-dir", default="")
    parser.add_argument("--source-image", default="")
    parser.add_argument(
        "--airsim-client",
        default=r"D:\PycharmProjects\PythonProject19\AirSim\PythonClient",
    )
    parser.add_argument(
        "--airsim-rpc-vendor",
        default=str(workspace / ".tools" / "airsim_rpc"),
    )
    return parser.parse_args()


def import_airsim(client_path: str, vendor_path: str):
    """Import the old AirSim RPC client in the local Python 3.8 YOLO env."""
    for path in (vendor_path, client_path):
        if path and path not in sys.path:
            sys.path.append(path)

    # The vendored Tornado 4 client asks Windows for root certificates even
    # though AirSim RPC is plain localhost TCP. Some local cert stores contain
    # entries Python 3.8 cannot decode, so avoid certificate loading only while
    # importing this non-TLS client.
    original_context = ssl.create_default_context

    def local_only_context(*_args, **_kwargs):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    ssl.create_default_context = local_only_context
    try:
        import airsim  # type: ignore
    finally:
        ssl.create_default_context = original_context
    return airsim


def decode_scene(response, cv2, np):
    data = np.frombuffer(response.image_data_uint8, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("AirSim returned an empty or invalid Scene image")
    return image


def decode_depth(response, np):
    values = np.asarray(response.image_data_float, dtype=np.float32)
    expected = int(response.width) * int(response.height)
    if expected <= 0 or values.size != expected:
        raise RuntimeError(
            f"invalid AirSim depth payload: {values.size} values for "
            f"{response.width}x{response.height}"
        )
    return values.reshape((int(response.height), int(response.width)))


def box_depth_m(depth, box: Sequence[int], image_shape, np) -> Optional[float]:
    """Return a robust near-depth estimate for a Scene-image detection box."""
    image_h, image_w = image_shape[:2]
    depth_h, depth_w = depth.shape[:2]
    x1, y1, x2, y2 = box
    dx1 = max(0, min(depth_w - 1, int(x1 * depth_w / image_w)))
    dx2 = max(dx1 + 1, min(depth_w, int(math.ceil(x2 * depth_w / image_w))))
    dy1 = max(0, min(depth_h - 1, int(y1 * depth_h / image_h)))
    dy2 = max(dy1 + 1, min(depth_h, int(math.ceil(y2 * depth_h / image_h))))
    crop = depth[dy1:dy2, dx1:dx2]
    valid = crop[np.isfinite(crop) & (crop > 0.1) & (crop < 10000.0)]
    if valid.size == 0:
        return None
    # The lower quartile rejects sky/background behind a sparse obstacle while
    # remaining much less noisy than a raw minimum pixel.
    return float(np.percentile(valid, 25.0))


def collect_detections(result, depth, frame_shape, args, np) -> List[Detection]:
    height, width = frame_shape[:2]
    frame_area = float(height * width)
    detections = []
    if result.boxes is None:
        return detections
    names = result.names
    for item in result.boxes:
        coords = item.xyxy[0].detach().cpu().tolist()
        x1, y1, x2, y2 = (
            max(0, min(width - 1, int(round(coords[0])))),
            max(0, min(height - 1, int(round(coords[1])))),
            max(1, min(width, int(round(coords[2])))),
            max(1, min(height, int(round(coords[3])))),
        )
        if x2 <= x1 or y2 <= y1:
            continue
        if ((x2 - x1) * (y2 - y1)) / frame_area < args.min_box_area_ratio:
            continue
        class_id = int(item.cls[0].detach().cpu().item())
        confidence = float(item.conf[0].detach().cpu().item())
        depth_m = None
        if depth is not None:
            depth_m = box_depth_m(depth, (x1, y1, x2, y2), frame_shape, np)
            if depth_m is not None and depth_m > args.max_depth_m:
                continue
        detections.append(Detection(
            class_id=class_id,
            label=str(names[class_id]),
            confidence=confidence,
            box=(x1, y1, x2, y2),
            depth_m=depth_m,
        ))
    return detections


def safe_label(label: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "_", label).strip("_")
    return clean or "unknown"


def best_detection_per_class(
        detections: Sequence[Detection]) -> List[Detection]:
    """Keep evidence readable when a model emits overlapping same-class boxes."""
    best: Dict[str, Detection] = {}
    for detection in detections:
        current = best.get(detection.label)
        if current is None or detection.confidence > current.confidence:
            best[detection.label] = detection
    return list(best.values())


def annotate(
    frame,
    detections: Sequence[Detection],
    focus: str,
    cv2,
    class_image_index: int,
):
    canvas = frame.copy()
    for detection in detections:
        x1, y1, x2, y2 = detection.box
        is_focus = detection.label == focus
        color = (40, 220, 40) if is_focus else (255, 170, 40)
        thickness = 3 if is_focus else 2
        depth_text = (
            f" {detection.depth_m:.1f}m"
            if detection.depth_m is not None else ""
        )
        text = f"{detection.label} {detection.confidence:.2f}{depth_text}"
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)
        (text_w, text_h), baseline = cv2.getTextSize(
            text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2
        )
        text_x = max(0, min(x1, canvas.shape[1] - text_w - 8))
        top = max(0, y1 - text_h - baseline - 6)
        cv2.rectangle(
            canvas, (text_x, top),
            (min(canvas.shape[1], text_x + text_w + 8), y1),
            color, -1,
        )
        cv2.putText(
            canvas, text,
            (text_x + 4, max(text_h + 1, y1 - baseline - 3)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (15, 15, 15), 2,
            cv2.LINE_AA,
        )
    stamp = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    cv2.putText(
        canvas,
        f"DETECTED: {focus} | CLASS IMAGE {class_image_index:03d} | {stamp}",
        (12, 26),
        cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 255, 255), 2, cv2.LINE_AA,
    )
    return canvas


def append_jsonl(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(value, ensure_ascii=False) + "\n")


def write_summary(path: Path, metadata: dict, events: Sequence[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({**metadata, "events": list(events)}, ensure_ascii=False,
                   indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    args = parse_args()
    if not 0.0 < args.confidence <= 1.0:
        raise SystemExit("--confidence must be in (0, 1]")
    if args.interval < 0.0:
        raise SystemExit("--interval cannot be negative")
    if args.capture_interval < 0.0:
        raise SystemExit("--capture-interval cannot be negative")
    if args.max_images_per_class < 0:
        raise SystemExit("--max-images-per-class cannot be negative")

    import cv2
    import numpy as np
    from ultralytics import YOLO

    weights = Path(args.weights).expanduser().resolve()
    if not weights.is_file():
        raise SystemExit(f"weights not found: {weights}")
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    live_writer = (
        LiveFrameWriter(Path(args.live_dir).expanduser().resolve(), cv2)
        if args.live_dir else None
    )

    model = YOLO(str(weights), task="detect")
    tracker = ClassEvidenceTracker(
        confirm_frames=args.confirm_frames,
        capture_interval=args.capture_interval,
        max_images_per_class=args.max_images_per_class,
    )
    metadata = {
        "started_at": dt.datetime.now().astimezone().isoformat(),
        "weights": str(weights),
        "camera": args.camera,
        "vehicle": args.vehicle,
        "confidence": args.confidence,
        "confirm_frames": args.confirm_frames,
        "capture_interval": args.capture_interval,
        "max_images_per_class": args.max_images_per_class,
        "max_depth_m": args.max_depth_m,
        "classes": {str(k): str(v) for k, v in model.names.items()},
    }
    (output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    client = None
    airsim = None
    if not args.source_image:
        airsim = import_airsim(args.airsim_client, args.airsim_rpc_vendor)
        client = airsim.MultirotorClient()
        client.confirmConnection()

    events: List[dict] = []
    started = time.monotonic()
    frame_index = 0
    fps_meter = FrameRateMeter()
    print(f"semantic perception ready: {weights.name}")
    print(f"classes: {', '.join(str(v) for v in model.names.values())}")
    print(f"evidence -> {output_dir}")
    if live_writer is not None:
        print(f"live feed -> {live_writer.directory}")

    while True:
        if args.stop_file and Path(args.stop_file).exists():
            print("stop file detected")
            break
        if args.max_runtime > 0 and time.monotonic() - started >= args.max_runtime:
            print("max runtime reached")
            break

        if args.source_image:
            frame = cv2.imread(args.source_image)
            if frame is None:
                raise RuntimeError(f"cannot read source image: {args.source_image}")
            depth = None
        else:
            responses = client.simGetImages([
                airsim.ImageRequest(
                    args.camera, airsim.ImageType.Scene, False, True
                ),
                airsim.ImageRequest(
                    args.camera, airsim.ImageType.DepthPerspective, True, False
                ),
            ], vehicle_name=args.vehicle)
            if len(responses) != 2:
                raise RuntimeError("AirSim did not return both Scene and Depth")
            frame = decode_scene(responses[0], cv2, np)
            depth = decode_depth(responses[1], np)

        result = model.predict(
            source=frame,
            conf=args.confidence,
            iou=args.iou,
            imgsz=args.image_size,
            device=args.device,
            verbose=False,
        )[0]
        detections = collect_detections(result, depth, frame.shape, args, np)
        frame_index += 1
        live_fps = fps_meter.tick(time.monotonic())
        new_events = tracker.update(detections, time.monotonic())

        for detection in new_events:
            sequence = len(events) + 1
            class_image_index = tracker.counts[detection.label]
            captured_at = dt.datetime.now().astimezone()
            filename = (
                f"scene_{class_image_index:03d}_frame_{frame_index:06d}_"
                f"{captured_at.strftime('%Y%m%d_%H%M%S_%f')[:-3]}.jpg"
            )
            class_dir = output_dir / safe_label(detection.label)
            class_dir.mkdir(parents=True, exist_ok=True)
            image_path = class_dir / filename
            boxed = annotate(
                frame, best_detection_per_class(detections),
                detection.label, cv2, class_image_index,
            )
            if not cv2.imwrite(str(image_path), boxed):
                raise RuntimeError(f"failed to save evidence image: {image_path}")
            event = {
                "sequence": sequence,
                "captured_at": captured_at.isoformat(),
                "frame_index": frame_index,
                "class_image_index": class_image_index,
                "first_seen": class_image_index == 1,
                "class_id": detection.class_id,
                "label": detection.label,
                "confidence": round(detection.confidence, 6),
                "depth_m": (
                    round(detection.depth_m, 3)
                    if detection.depth_m is not None else None
                ),
                "bbox_xyxy": list(detection.box),
                "image": image_path.relative_to(output_dir).as_posix(),
            }
            events.append(event)
            append_jsonl(output_dir / "events.jsonl", event)
            write_summary(output_dir / "summary.json", metadata, events)
            depth_text = (
                f" depth={detection.depth_m:.1f}m"
                if detection.depth_m is not None else ""
            )
            print(
                f"CAPTURED label={detection.label} "
                f"class_image={class_image_index} "
                f"conf={detection.confidence:.3f}{depth_text} -> {image_path}"
            )

        if live_writer is not None:
            live_writer.publish(
                frame, detections, events, frame_index, live_fps
            )

        if args.source_image:
            break
        if args.max_events > 0 and len(events) >= args.max_events:
            print("max events reached")
            break
        time.sleep(args.interval)

    metadata["finished_at"] = dt.datetime.now().astimezone().isoformat()
    metadata["frames_processed"] = frame_index
    metadata["class_image_counts"] = dict(sorted(tracker.counts.items()))
    write_summary(output_dir / "summary.json", metadata, events)
    print(f"semantic perception stopped: frames={frame_index} events={len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
