#!/usr/bin/env python3
"""CLI wrapper that keeps the repository package importable from any cwd."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from drone_gui.session_archive import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
