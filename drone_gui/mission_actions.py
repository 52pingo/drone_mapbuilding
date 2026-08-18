"""Guard and dispatch operator Hold, Resume, and Land requests."""

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QMessageBox


class MissionActionController(QObject):
    ACTIONS = ("hold", "resume", "land")

    def __init__(self, runtime, commands, live_page, dialog_parent) -> None:
        super().__init__(dialog_parent)
        self.runtime = runtime
        self.commands = commands
        self.live_page = live_page
        self.dialog_parent = dialog_parent

    def request(self, action: str) -> None:
        if not self.runtime.is_running("mission"):
            QMessageBox.information(
                self.dialog_parent, "任务未运行", "当前没有可控制的飞行任务。"
            )
            return
        if action == "land" and QMessageBox.question(
            self.dialog_parent,
            "确认安全降落",
            "将调用 PX4 正常 LAND 流程；不会在空中强制解除锁定。是否继续？",
        ) != QMessageBox.Yes:
            return
        if any(self.runtime.is_running(f"control_{name}") for name in self.ACTIONS):
            QMessageBox.information(
                self.dialog_parent, "控制处理中", "请等待当前飞行控制请求返回。"
            )
            return
        self.live_page.controls.set_busy(True)
        self.runtime.start(
            f"control_{action}", self.commands.mission_control(action)
        )
