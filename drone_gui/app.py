from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from drone_gui.main_window import MainWindow
from drone_gui.models import RuntimeConfig
from drone_gui.theme import APP_STYLESHEET


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Drone Mapbuilding Qt control station")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--screenshot", type=Path, default=None)
    parser.add_argument("--page", type=int, choices=range(4), default=0)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    default_config = repo_root / "config" / "gui_config.json"
    config_path = args.config or (default_config if default_config.is_file() else None)
    config = RuntimeConfig.load(config_path, repo_root)
    config.results_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Drone Mapbuilding Control Station")
    app.setOrganizationName("52pingo")
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(APP_STYLESHEET)
    window = MainWindow(config)
    window.shell.show_page(args.page)
    window.show()
    if args.screenshot:
        def capture_and_quit() -> None:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.screenshot)):
                raise RuntimeError(f"无法保存 GUI 截图：{args.screenshot}")
            app.quit()

        QTimer.singleShot(800, capture_and_quit)
    elif args.smoke_test:
        QTimer.singleShot(500, app.quit)
    return app.exec()
