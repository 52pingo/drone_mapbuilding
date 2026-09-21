"""QProcess 包装：跑外部进程，不阻塞 UI。"""

from __future__ import annotations

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
        # 累积原始字节，只在完整行边界上解码，避免多字节字符被分片切断。
        self._buffers: Dict[str, bytes] = {}
        # 已经走过 _finish 的任务名，用于 errorOccurred / finished 双路去重。
        self._finished: set[str] = set()

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
            lambda error, name=task_name, proc=process: self._handle_error(name, proc, error)
        )
        process.finished.connect(
            lambda code, _status, name=task_name: self._finish(name, code)
        )
        self._processes[task_name] = process
        self._buffers[task_name] = b""
        self._finished.discard(task_name)
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

    def _handle_error(self, task_name: str, process: QProcess, error) -> None:
        self.task_error.emit(task_name, process.errorString() or str(error))
        # FailedToStart 时 Qt 只发 errorOccurred、不发 finished，必须在这里
        # 走清理路径；其他错误 finished 也会到，靠 _finished 去重。
        self._finish(task_name, process.exitCode())

    def _read_output(self, task_name: str, process: QProcess) -> None:
        payload = bytes(process.readAllStandardOutput())
        if not payload:
            return
        buffered = self._buffers.get(task_name, b"") + payload
        lines = buffered.split(b"\n")
        # 行尾残字节（可能是不完整的多字节字符）留到下一片再拼。
        self._buffers[task_name] = lines.pop()
        for line in lines:
            self.task_output.emit(
                task_name, line.decode("utf-8", errors="replace").rstrip("\r")
            )

    def _finish(self, task_name: str, exit_code: int) -> None:
        if task_name in self._finished:
            return
        self._finished.add(task_name)
        # 停下来的 QProcess 继续挂在 controller 下，等下次 start 或 controller
        # 销毁时再删。在自己的 finished 信号里 deleteLater 会和 Qt 事件处理打架。
        process = self._processes.get(task_name)
        if process is not None:
            self._read_output(task_name, process)
        remainder = self._buffers.pop(task_name, b"")
        if remainder:
            self.task_output.emit(
                task_name, remainder.decode("utf-8", errors="replace").rstrip("\r")
            )
        self.task_finished.emit(task_name, exit_code)
