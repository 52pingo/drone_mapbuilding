"""Reusable labelled path editor with a native picker."""

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QPushButton, QWidget


class PathField(QWidget):
    def __init__(self, accessible_name: str, mode: str = "file", file_filter: str = "所有文件 (*)", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.file_filter = file_filter
        self.edit = QLineEdit()
        self.edit.setAccessibleName(accessible_name)
        self.button = QPushButton("选择…")
        self.button.setAccessibleName(f"选择{accessible_name}")
        self.button.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def _browse(self) -> None:
        current = self.edit.text().strip()
        start = str(Path(current).parent if current else Path.home())
        if self.mode == "directory":
            value = QFileDialog.getExistingDirectory(self, "选择目录", current or start)
        else:
            value, _selected = QFileDialog.getOpenFileName(
                self, "选择文件", current or start, self.file_filter
            )
        if value:
            self.edit.setText(value)

    def value(self) -> Path | None:
        text = self.edit.text().strip()
        return Path(text) if text else None

    def set_value(self, value: Path | None) -> None:
        self.edit.setText(str(value) if value else "")
