"""QProcess 包装：跑外部进程，不阻塞 UI。"""

from __future__ import annotations

import locale
import os
from pathlib import Path
import sys
from typing import Dict

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from drone_gui.commands import CommandSpec


def _sanitize_search_path(value: str, bundle_root: Path) -> str:
    # PyInstaller 会把 sys._MEIPASS 塞进 PATH，子进程继承后可能从 GUI 的
    # 打包目录里加载 DLL。把 bundle 目录从 PATH 里剔掉。
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
    # 只在 frozen 的 Windows 上有效，其他平台直接 no-op。
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
        # PyInstaller 把 SetDllDirectoryW 指向 sys._MEIPASS，Windows 子进程
        # 会继承这个搜索路径。不清掉的话 UE4 会从 GUI 的打包目录里加载
        # MSVCP140.dll，把包锁住。QProcess 在 start()/waitForStarted() 期间
        # 创建 OS 进程，之后就能把 bundle 路径恢复回去。
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
        # 停下来的 QProcess 继续挂在 controller 下，等下次 start 或 controller
        # 销毁时再删。在自己的 finished 信号里 deleteLater 会和 Qt 事件处理打架。
        process = self._processes.get(task_name)
        if process is not None:
            self._read_output(task_name, process)
        remainder = self._buffers.pop(task_name, "")
        if remainder:
            self.task_output.emit(task_name, remainder.rstrip("\r"))
        self.task_finished.emit(task_name, exit_code)
