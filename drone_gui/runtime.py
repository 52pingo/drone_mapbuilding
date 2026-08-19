"""Non-blocking external process orchestration based on QProcess."""

from __future__ import annotations

import locale
import os
from pathlib import Path
import sys
from typing import Dict

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from drone_gui.commands import CommandSpec


def _sanitize_search_path(value: str, bundle_root: Path) -> str:
    """Remove PyInstaller bundle directories before launching system tools."""
    root = bundle_root.resolve()
    clean = []
    for item in value.split(os.pathsep):
        if not item:
            continue
        try:
            candidate = Path(item.strip('"')).resolve()
            if candidate == root or candidate.is_relative_to(root):
                continue
        except (OSError, RuntimeError, ValueError):
            pass
        clean.append(item)
    return os.pathsep.join(clean)


def _external_process_environment() -> QProcessEnvironment:
    environment = QProcessEnvironment.systemEnvironment()
    bundle_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle_root:
        path_value = environment.value("PATH")
        environment.insert(
            "PATH", _sanitize_search_path(path_value, Path(bundle_root))
        )
        environment.remove("_MEIPASS2")
    environment.insert("PYTHONUTF8", "1")
    environment.insert("PYTHONIOENCODING", "utf-8")
    return environment


def _set_frozen_dll_directory(path: str | None) -> None:
    """Control the Windows loader path inherited by external child processes."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    import ctypes
    if not ctypes.windll.kernel32.SetDllDirectoryW(path):
        raise OSError("SetDllDirectoryW failed")


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
        process.setProcessEnvironment(_external_process_environment())
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
        # PyInstaller points SetDllDirectoryW at ``sys._MEIPASS``. Windows
        # child processes inherit that search path; without temporarily
        # clearing it, UE4 can load MSVCP140.dll from this GUI package and
        # keep the package locked.  QProcess creates the OS process during
        # start()/waitForStarted(), after which the GUI's bundle path is safe
        # to restore.
        bundle_root = getattr(sys, "_MEIPASS", None)
        try:
            _set_frozen_dll_directory(None)
            process.start(spec.program, list(spec.arguments))
            process.waitForStarted(3000)
        finally:
            if bundle_root:
                _set_frozen_dll_directory(str(bundle_root))
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
