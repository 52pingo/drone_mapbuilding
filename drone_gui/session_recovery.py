"""Run potentially expensive Session repair outside the Qt GUI thread."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from drone_gui.session_archive import recover_session


class _RecoveryWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    @Slot()
    def run(self) -> None:
        try:
            self.completed.emit(recover_session(self.root))
        except Exception as error:  # surfaced verbatim in the results page
            self.failed.emit(str(error))


class SessionRecoveryController(QObject):
    state_changed = Signal(str, str)
    recovered = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.thread: QThread | None = None
        self.worker: _RecoveryWorker | None = None

    def recover(self, root: Path) -> bool:
        if self.thread is not None and self.thread.isRunning():
            return False
        self.thread = QThread(self)
        self.worker = _RecoveryWorker(root)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.completed.connect(self._completed)
        self.worker.failed.connect(self._failed)
        self.worker.completed.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.completed.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._cleanup)
        self.thread.finished.connect(self.thread.deleteLater)
        self.state_changed.emit("running", "正在校验并修复 Session 归档…")
        self.thread.start()
        return True

    @Slot(object)
    def _completed(self, manifest: dict) -> None:
        self.state_changed.emit(
            "ready", f"归档已恢复：{manifest.get('status', 'unknown')}"
        )
        self.recovered.emit(manifest)

    @Slot(str)
    def _failed(self, message: str) -> None:
        self.state_changed.emit("error", f"归档恢复失败：{message}")

    @Slot()
    def _cleanup(self) -> None:
        self.worker = None
        self.thread = None
