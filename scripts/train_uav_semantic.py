#!/usr/bin/env python3
"""Train the unified UAV semantic detector with reproducible defaults."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    workspace = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", default=str(workspace / "yolov8l.pt"))
    parser.add_argument("--data", default=str(workspace / "datasets" / "uav_semantic_v1" / "data.yaml"))
    parser.add_argument("--project", default=str(workspace / "results" / "training"))
    parser.add_argument("--name", required=True)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--no-val", action="store_true")
    parser.add_argument(
        "--skip-amp-check",
        action="store_true",
        help="Keep AMP enabled but skip Ultralytics' network-dependent calibration download.",
    )
    parser.add_argument("--save-period", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available; refusing to start the requested GPU training")
    print(json.dumps({
        "gpu": torch.cuda.get_device_name(0),
        "vram_gb": round(torch.cuda.get_device_properties(0).total_memory / 2**30, 2),
        "weights": str(Path(args.weights).resolve()),
        "data": str(Path(args.data).resolve()),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "fraction": args.fraction,
        "validation": not args.no_val,
        "skip_amp_check": args.skip_amp_check,
    }, ensure_ascii=False, indent=2), flush=True)

    if args.skip_amp_check:
        import ultralytics.engine.trainer as trainer_module

        trainer_module.check_amp = lambda model: True
        print("AMP calibration download skipped; mixed precision remains enabled.", flush=True)

    model = YOLO(args.weights)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=0,
        amp=True,
        cos_lr=True,
        close_mosaic=10,
        patience=25,
        optimizer="auto",
        seed=42,
        deterministic=True,
        cache=False,
        plots=True,
        save=True,
        save_period=args.save_period,
        project=args.project,
        name=args.name,
        exist_ok=False,
        fraction=args.fraction,
        val=not args.no_val,
        verbose=True,
    )


if __name__ == "__main__":
    main()
