from __future__ import annotations

from datetime import datetime

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QMessageBox

from drone_gui.commands import CommandBuilder
from drone_gui.models import MissionPlan, RuntimeConfig
from drone_gui.protocol import GUI_PROBE_PREFIX, GUI_STATUS_PREFIX, parse_prefixed_json
from drone_gui.runtime import RuntimeController
from drone_gui.widgets.control_shell import ControlShell
from drone_gui.widgets.live_page import LivePage
from drone_gui.widgets.mission_page import MissionPage
from drone_gui.widgets.preflight_page import PreflightPage
from drone_gui.widgets.results_page import ResultsPage


class MainWindow(QMainWindow):
    PAGE_NAMES = ("系统与自检", "航线规划", "实时感知", "地图与成果")

    def __init__(self, config: RuntimeConfig) -> None:
        super().__init__()
        self.config = config
        self.commands = CommandBuilder(config)
        self.runtime = RuntimeController(self)
        self._mission_closed_loop = False
        self._last_probe: dict | None = None
        self.setWindowTitle("Drone Mapbuilding Control Station")
        self.setMinimumSize(1180, 760)
        self.resize(1480, 920)

        self.preflight_page = PreflightPage(config)
        self.mission_page = MissionPage()
        self.live_page = LivePage()
        self.results_page = ResultsPage(config.results_dir)
        self.shell = ControlShell(
            self.PAGE_NAMES,
            (
                self.preflight_page,
                self.mission_page,
                self.live_page,
                self.results_page,
            ),
        )
        self.setCentralWidget(self.shell)
        self._connect_signals()

    def _connect_signals(self) -> None:
        self.shell.page_requested.connect(self._show_page)
        self.preflight_page.launch_ue4_requested.connect(self._launch_ue4)
        self.preflight_page.restart_stack_requested.connect(self._restart_stack)
        self.preflight_page.runtime_probe_requested.connect(self._probe_runtime)
        self.mission_page.start_requested.connect(self._start_mission)
        self.live_page.hold_requested.connect(lambda: self._mission_control("hold"))
        self.live_page.resume_requested.connect(lambda: self._mission_control("resume"))
        self.live_page.land_requested.connect(lambda: self._mission_control("land"))
        self.runtime.task_started.connect(self._task_started)
        self.runtime.task_output.connect(self._task_output)
        self.runtime.task_finished.connect(self._task_finished)
        self.runtime.task_error.connect(self._task_error)

    def _show_page(self, index: int) -> None:
        self.shell.show_page(index)
        if index == 3:
            self.results_page.refresh()

    def _launch_ue4(self) -> None:
        self.runtime.start("ue4", self.commands.launch_ue4())

    def _restart_stack(self) -> None:
        self.runtime.start("stack", self.commands.restart_stack())

    def _probe_runtime(self) -> None:
        self._last_probe = None
        self.preflight_page.set_probe_running(True)
        self.runtime.start("probe", self.commands.probe_stack())

    def _start_mission(self, plan: MissionPlan) -> None:
        if not self.preflight_page.required_ready:
            QMessageBox.warning(
                self, "自检未通过",
                "请先在“系统与自检”页面完成本地与 WSL 动态检查。",
            )
            self._show_page(0)
            return
        if self.runtime.is_running("mission"):
            QMessageBox.information(self, "任务运行中", "当前任务尚未结束，不能重复启动。")
            return
        self.runtime.start("mission", self.commands.run_mission(plan))

    def _mission_control(self, action: str) -> None:
        if not self.runtime.is_running("mission"):
            QMessageBox.information(self, "任务未运行", "当前没有可控制的飞行任务。")
            return
        if action == "land" and QMessageBox.question(
            self,
            "确认安全降落",
            "将调用 PX4 正常 LAND 流程；不会在空中强制解除锁定。是否继续？",
        ) != QMessageBox.Yes:
            return
        if any(self.runtime.is_running(f"control_{name}") for name in ("hold", "resume", "land")):
            QMessageBox.information(self, "控制处理中", "请等待当前飞行控制请求返回。")
            return
        self.live_page.controls.set_busy(True)
        self.runtime.start(f"control_{action}", self.commands.mission_control(action))

    def _task_started(self, name: str, command: str) -> None:
        self._append_log(name, f"START {command}")
        if name == "ue4":
            self.shell.ue_status.set_state("running", "UE4 启动中")
        elif name == "stack":
            self.shell.stack_status.set_state("running", "PX4 / ROS2 启动中")
        elif name == "mission":
            self._mission_closed_loop = False
            self.shell.mission_status.set_state("running", "任务运行中")
            self.live_page.set_process_state("running", "感知运行中")
            self.mission_page.set_running(True)
        elif name == "probe":
            self.preflight_page.set_probe_running(True)

    def _task_output(self, name: str, text: str) -> None:
        self._append_log(name, text)
        if name == "probe":
            payload = parse_prefixed_json(text, GUI_PROBE_PREFIX)
            if payload is not None:
                self._last_probe = payload
            return
        if name != "mission":
            return
        payload = parse_prefixed_json(text, GUI_STATUS_PREFIX)
        if payload is not None:
            self.live_page.update_status(payload)
            if payload.get("state") == "DONE" and payload.get("armed") is False:
                self._mission_closed_loop = True
                self.shell.mission_status.set_state("done", "已降落 / 已解锁")
        self.live_page.consume_log(text)
        if "MISSION DONE" in text.upper():
            self._mission_closed_loop = True
            self.shell.mission_status.set_state("done", "已降落 / 已解锁")

    def _task_finished(self, name: str, exit_code: int) -> None:
        self._append_log(name, f"EXIT code={exit_code}")
        state = "ready" if exit_code == 0 else "error"
        if name == "ue4":
            text = "UE4 就绪" if exit_code == 0 else "UE4 启动失败"
            self.shell.ue_status.set_state(state, text)
        elif name == "stack":
            text = "PX4 / ROS2 就绪" if exit_code == 0 else "堆栈启动失败"
            self.shell.stack_status.set_state(state, text)
            if exit_code == 0:
                self._probe_runtime()
        elif name == "probe":
            if exit_code == 0 and self._last_probe is not None:
                self.preflight_page.apply_runtime_probe(self._last_probe)
                required_keys = (
                    key for key, _label, required
                    in self.preflight_page.RUNTIME_COMPONENTS if required
                )
                healthy = all(self._last_probe.get(key) is True for key in required_keys)
                self.shell.stack_status.set_state(
                    "ready" if healthy else "warning",
                    "PX4 / ROS2 运行正常" if healthy else "运行检查未通过",
                )
            else:
                self.preflight_page.apply_runtime_failure(
                    f"进程退出码 {exit_code}，未收到 GUI_PROBE"
                )
        elif name == "mission":
            self._mission_finished(exit_code)
        elif name.startswith("control_"):
            self.live_page.controls.set_busy(False)

    def _mission_finished(self, exit_code: int) -> None:
        self.mission_page.set_running(False)
        if exit_code != 0:
            self.shell.mission_status.set_state("error", "任务异常结束")
            self.live_page.set_process_state("error", "感知任务异常")
        elif not self._mission_closed_loop:
            self.shell.mission_status.set_state("warning", "进程结束，闭环未确认")
            self.live_page.set_process_state("warning", "未收到 MISSION DONE")
        self.results_page.refresh()

    def _task_error(self, name: str, message: str) -> None:
        self._append_log(name, f"ERROR {message}")
        badges = {
            "ue4": (self.shell.ue_status, "UE4 启动失败"),
            "stack": (self.shell.stack_status, "堆栈启动失败"),
            "mission": (self.shell.mission_status, "任务启动失败"),
        }
        if name in badges:
            badge, text = badges[name]
            badge.set_state("error", text)
        if name == "mission":
            self.mission_page.set_running(False)
        if name == "probe":
            self.preflight_page.apply_runtime_failure(message)
            return
        if name.startswith("control_"):
            self.live_page.controls.set_busy(False)
        QMessageBox.critical(self, f"{name} 启动失败", message)

    def _append_log(self, source: str, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        for line in text.splitlines() or [text]:
            self.shell.log.appendPlainText(f"{stamp}  [{source}]  {line}")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.runtime.is_running("mission"):
            QMessageBox.warning(
                self,
                "任务仍在运行",
                "GUI 不会通过关闭窗口强杀飞行任务。请等待任务安全降落并完成。",
            )
            event.ignore()
            return
        event.accept()
