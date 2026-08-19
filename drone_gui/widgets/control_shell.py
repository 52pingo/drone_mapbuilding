from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from drone_gui.widgets.status_badge import StatusBadge


class ControlShell(QWidget):
    PAGE_NAMES = ("环境配置", "系统自检", "航线规划", "实时感知", "地图与成果")

    page_requested = Signal(int)

    def __init__(self, page_names: Sequence[str], pages: Sequence[QWidget], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("AppShell")
        self.page_names = tuple(page_names)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_header())
        self.pages = QStackedWidget()
        for page in pages:
            self.pages.addWidget(page)
        content_layout.addWidget(self.pages, 1)
        content_layout.addWidget(self._build_log_panel())
        outer.addWidget(content, 1)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(205)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 20, 14, 16)
        title = QLabel("DRONE OPS")
        title.setObjectName("ProductTitle")
        caption = QLabel("避障 · 建图 · 语义")
        caption.setObjectName("ProductCaption")
        layout.addWidget(title)
        layout.addWidget(caption)
        layout.addSpacing(24)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        for index, name in enumerate(self.page_names):
            button = QPushButton(f"{index + 1:02d}   {name}")
            button.setCheckable(True)
            button.setProperty("nav", True)
            button.setAccessibleName(f"打开{name}页面")
            button.clicked.connect(
                lambda _checked=False, page=index: self.page_requested.emit(page)
            )
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        layout.addStretch()
        version = QLabel("GUI M6 · v0.6.0\n坐标系：PX4 Local NED")
        version.setProperty("role", "muted")
        layout.addWidget(version)
        return sidebar

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 12, 20, 12)
        self.page_title = QLabel(self.page_names[0])
        self.page_title.setObjectName("PageTitle")
        self.ue_status = StatusBadge("UE4 未启动")
        self.stack_status = StatusBadge("PX4 / ROS2 未启动")
        self.mission_status = StatusBadge("任务未启动")
        layout.addWidget(self.page_title)
        layout.addStretch()
        layout.addWidget(self.ue_status)
        layout.addWidget(self.stack_status)
        layout.addWidget(self.mission_status)
        return header

    def _build_log_panel(self) -> QFrame:
        panel = QFrame()
        panel.setProperty("role", "panel")
        panel.setMaximumHeight(190)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 9, 12, 10)
        row = QHBoxLayout()
        title = QLabel("运行日志")
        title.setProperty("role", "sectionTitle")
        clear_button = QPushButton("清空")
        clear_button.setProperty("kind", "quiet")
        row.addWidget(title)
        row.addStretch()
        row.addWidget(clear_button)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setAccessibleName("外部任务实时日志")
        clear_button.clicked.connect(self.log.clear)
        layout.addLayout(row)
        layout.addWidget(self.log)
        return panel

    def show_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.page_title.setText(self.page_names[index])
        self.nav_buttons[index].setChecked(True)
