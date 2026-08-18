"""Presentation controller for WSL/ROS runtime health checks."""

from __future__ import annotations

from PySide6.QtCore import QObject

from drone_gui.commands import CommandBuilder
from drone_gui.protocol import GUI_PROBE_PREFIX, parse_prefixed_json
from drone_gui.runtime import RuntimeController


class BackendHealthController(QObject):
    def __init__(self, runtime: RuntimeController, commands: CommandBuilder,
                 page, status_badge, parent=None) -> None:
        super().__init__(parent)
        self.runtime = runtime
        self.commands = commands
        self.page = page
        self.status_badge = status_badge
        self.last_probe: dict | None = None

    def probe(self) -> None:
        self.last_probe = None
        self.page.set_probe_running(True)
        self.runtime.start("probe", self.commands.probe_stack())

    def started(self) -> None:
        self.page.set_probe_running(True)

    def consume(self, text: str) -> None:
        payload = parse_prefixed_json(text, GUI_PROBE_PREFIX)
        if payload is not None:
            self.last_probe = payload

    def stack_finished(self, exit_code: int) -> None:
        state = "ready" if exit_code == 0 else "error"
        text = "PX4 / ROS2 就绪" if exit_code == 0 else "堆栈启动失败"
        self.status_badge.set_state(state, text)
        if exit_code == 0:
            self.probe()

    def finished(self, exit_code: int) -> None:
        if exit_code != 0 or self.last_probe is None:
            self.fail(f"进程退出码 {exit_code}，未收到 GUI_PROBE")
            return
        self.page.apply_runtime_probe(self.last_probe)
        required_keys = (
            key for key, _label, required
            in self.page.RUNTIME_COMPONENTS if required
        )
        healthy = all(self.last_probe.get(key) is True for key in required_keys)
        self.status_badge.set_state(
            "ready" if healthy else "warning",
            "PX4 / ROS2 运行正常" if healthy else "运行检查未通过",
        )

    def fail(self, message: str) -> None:
        self.page.apply_runtime_failure(message)
        self.status_badge.set_state("error", "运行检查失败")
