from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from drone_gui.sessions import scan_sessions
from drone_gui.session_recovery import SessionRecoveryController
from drone_gui.widgets.results_tree import (
    PATH_ROLE, SESSION_ROLE, STATUS_ROLE, populate_session_tree,
)


class ResultsPage(QWidget):
    session_open_requested = Signal(object)

    def __init__(self, results_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.results_dir = results_dir
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Session / 类别 / 文件", "状态", "数量"])
        self.tree.setAccessibleName("任务成果目录")
        self.tree.currentItemChanged.connect(self._selection_changed)
        self.preview = QLabel("选择带框图片、深度图、轨迹图或地图进行预览")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setProperty("role", "muted")
        self.preview.setMinimumSize(520, 360)
        self.preview.setAccessibleName("成果图片预览")
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setProperty("role", "muted")
        self._pixmap: QPixmap | None = None
        self._selected_session: Path | None = None
        self._selected_status = ""
        self.recovery = SessionRecoveryController(self)
        self._build_layout()
        self.refresh()

    def _build_layout(self) -> None:
        browser_panel = QFrame()
        browser_panel.setProperty("role", "panel")
        browser_layout = QVBoxLayout(browser_panel)
        browser_layout.setContentsMargins(14, 14, 14, 14)
        title = QLabel("任务成果")
        title.setProperty("role", "sectionTitle")
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.refresh)
        open_button = QPushButton("打开成果目录")
        open_button.clicked.connect(self._open_results)
        self.replay_button = QPushButton("在三维回放中打开")
        self.replay_button.setProperty("kind", "primary")
        self.replay_button.setAccessibleName("在三维地图中打开所选任务 Session")
        self.replay_button.setEnabled(False)
        self.replay_button.clicked.connect(self._open_selected_session)
        self.recover_button = QPushButton("修复未完成归档")
        self.recover_button.setAccessibleName("恢复所选任务的清单、遥测和报告")
        self.recover_button.setEnabled(False)
        self.recover_button.clicked.connect(self._recover_selected_session)
        self.recovery.state_changed.connect(self._recovery_state)
        self.recovery.recovered.connect(lambda _manifest: self.refresh())
        actions = QHBoxLayout()
        actions.addWidget(refresh_button)
        actions.addWidget(open_button)
        actions.addWidget(self.replay_button)
        actions.addWidget(self.recover_button)
        browser_layout.addWidget(title)
        browser_layout.addWidget(self.tree, 1)
        browser_layout.addLayout(actions)

        preview_panel = QFrame()
        preview_panel.setProperty("role", "panel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_title = QLabel("预览与导出准备")
        preview_title.setProperty("role", "sectionTitle")
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.preview, 1)
        preview_layout.addWidget(self.detail)

        splitter = QSplitter()
        splitter.addWidget(browser_panel)
        splitter.addWidget(preview_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(splitter)

    def refresh(self) -> None:
        self.tree.clear()
        self._selected_session = None
        self.replay_button.setEnabled(False)
        self.recover_button.setEnabled(False)
        sessions = scan_sessions(self.results_dir)
        if not sessions:
            empty = QTreeWidgetItem(["暂无可预览成果", "0"])
            empty.setDisabled(True)
            self.tree.addTopLevelItem(empty)
            self.detail.setText(f"扫描目录：{self.results_dir}")
            return
        populate_session_tree(self.tree, sessions)
        self.tree.expandToDepth(0)
        self.detail.setText(f"已载入 {len(sessions)} 个 Session · {self.results_dir}")

    def _selection_changed(self, current, _previous) -> None:
        if current is None:
            return
        session_value = current.data(0, SESSION_ROLE)
        self._selected_session = Path(session_value) if session_value else None
        root_item = current
        while root_item.parent() is not None:
            root_item = root_item.parent()
        status_value = root_item.data(0, STATUS_ROLE)
        self._selected_status = str(status_value or "")
        self.replay_button.setEnabled(self._selected_session is not None)
        self.recover_button.setEnabled(
            self._selected_session is not None
            and self._selected_status not in {"completed", "running"}
        )
        value = current.data(0, PATH_ROLE)
        if not value:
            return
        path = Path(value)
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            self.detail.setText(
                f"{path}\n选择“在三维回放中打开”可载入最终点云和遥测时间轴。"
            )
            return
        self._pixmap = QPixmap(str(path))
        self._update_preview()
        self.detail.setText(f"{path.name} · {self._pixmap.width()}×{self._pixmap.height()} · {path.parent}")

    def _update_preview(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            self.preview.setText("图片无法读取")
            return
        self.preview.setPixmap(self._pixmap.scaled(
            self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_preview()

    def _open_results(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.results_dir)))

    def _open_selected_session(self) -> None:
        if self._selected_session is not None:
            self.session_open_requested.emit(self._selected_session)

    def _recover_selected_session(self) -> None:
        if self._selected_session is None:
            return
        if self.recovery.recover(self._selected_session):
            self.recover_button.setEnabled(False)

    def _recovery_state(self, state: str, message: str) -> None:
        self.detail.setText(message)
        if state != "running":
            self.recover_button.setEnabled(self._selected_session is not None)
