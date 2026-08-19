"""Portable configuration discovery and atomic persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from drone_gui.models import RuntimeConfig


def portable_config_path(application_root: Path) -> Path:
    return application_root / "config" / "gui_config.json"


def user_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "52pingo" / "DroneMapbuilding" / "gui_config.json"


def config_candidates(application_root: Path) -> Iterable[Path]:
    yield portable_config_path(application_root)
    yield user_config_path()


def find_config(application_root: Path) -> Path | None:
    return next((path for path in config_candidates(application_root) if path.is_file()), None)


def save_config(config: RuntimeConfig, preferred: Path | None = None) -> Path:
    """Save atomically, falling back to the per-user directory if needed."""
    targets = [preferred] if preferred is not None else []
    targets.extend(path for path in config_candidates(config.repo_root) if path not in targets)
    payload = json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n"
    errors = []
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(payload, encoding="utf-8")
            os.replace(temporary, target)
            return target
        except OSError as exc:
            errors.append(f"{target}: {exc}")
    raise OSError("无法保存 GUI 配置：" + "；".join(errors))
