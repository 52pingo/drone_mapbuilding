"""Non-blocking external process orchestration based on QProcess."""

from __future__ import annotations

import locale
from typing import Dict

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from drone_gui.commands import CommandSpec


class RuntimeController(QObject):
    task_started = Signal(str, str)
    task_output = Signal(str, str)
    task_finished = Signal(str, int)
    task_error = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._processes: Dict[str, QProcess] = {}
        self._buffers: Dict[str, str] = {}

    def is_running(self, task_name: str) -> bool:
        process = self._processes.get(task_name)
        return process is not None and process.state() != QProcess.NotRunning

    def start(self, task_name: str, spec: CommandSpec) -> bool:
        if self.is_running(task_name):
            self.task_error.emit(task_name, "任务已经在运行，已拒绝重复启动")
            return False
        previous = self._processes.get(task_name)
        if previous is not None:
            previous.deleteLater()
        process = QProcess(self)
        process.setWorkingDirectory(str(spec.working_directory))
        process.setProcessChannelMode(QProcess.MergedChannels)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUTF8", "1")
        environment.insert("PYTHONIOENCODING", "utf-8")
        process.setProcessEnvironment(environment)
        process.readyReadStandardOutput.connect(
            lambda name=task_name, proc=process: self._read_output(name, proc)
        )
        process.started.connect(
            lambda name=task_name, command=spec.display(): self.task_started.emit(name, command)
        )
        process.errorOccurred.connect(
            lambda error, name=task_name, proc=process: self.task_error.emit(
                name, proc.errorString() or str(error)
            )
        )
        process.finished.connect(
            lambda code, _status, name=task_name: self._finish(name, code)
        )
        self._processes[task_name] = process
        self._buffers[task_name] = ""
        process.start(spec.program, list(spec.arguments))
        return True

    def _read_output(self, task_name: str, process: QProcess) -> None:
        payload = bytes(process.readAllStandardOutput())
        if not payload:
            return
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            text = payload.decode(locale.getpreferredencoding(False), errors="replace")
        buffered = self._buffers.get(task_name, "") + text
        lines = buffered.split("\n")
        self._buffers[task_name] = lines.pop()
        for line in lines:
            self.task_output.emit(task_name, line.rstrip("\r"))

    def _finish(self, task_name: str, exit_code: int) -> None:
        # Keep the stopped QProcess parented to the controller until either the
        # task is started again or the controller is destroyed. Deleting it
        # from inside its own finished signal can race Qt event processing.
        process = self._processes.get(task_name)
        if process is not None:
            self._read_output(task_name, process)
        remainder = self._buffers.pop(task_name, "")
        if remainder:
            self.task_output.emit(task_name, remainder.rstrip("\r"))
        self.task_finished.emit(task_name, exit_code)
