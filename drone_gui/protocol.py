"""Line-oriented JSON protocol shared by WSL helpers and the Qt GUI."""

from __future__ import annotations

import json
from typing import Any


GUI_PROBE_PREFIX = "GUI_PROBE "
GUI_STATUS_PREFIX = "GUI_STATUS "


def parse_prefixed_json(text: str, prefix: str) -> dict[str, Any] | None:
    """Parse the last valid JSON object carried by a prefixed output line."""
    result = None
    for line in text.splitlines():
        if not line.startswith(prefix):
            continue
        try:
            payload = json.loads(line[len(prefix):])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict):
            result = payload
    return result
