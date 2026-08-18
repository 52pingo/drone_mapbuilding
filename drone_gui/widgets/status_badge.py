from PySide6.QtWidgets import QLabel


class StatusBadge(QLabel):
    LABELS = {
        "idle": "未启动",
        "ready": "就绪",
        "running": "运行中",
        "warning": "需检查",
        "error": "异常",
        "done": "已完成",
    }

    def __init__(self, text: str = "未启动", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("StatusBadge")
        self.setAccessibleName("运行状态")
        self.set_state("idle", text)

    def set_state(self, state: str, text: str | None = None) -> None:
        self.setProperty("state", "ready" if state == "done" else state)
        self.setText(text or self.LABELS.get(state, state))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
