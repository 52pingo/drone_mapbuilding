from __future__ import annotations
from datetime import datetime
from pathlib import Path
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QMessageBox

from drone_gui.backend_health import BackendHealthController
from drone_gui.commands import CommandBuilder
from drone_gui.mission_actions import MissionActionController
from drone_gui.models import MissionPlan, RuntimeConfig
from drone_gui.perception_feed import PerceptionFeed
from drone_gui.protocol import (
    GUI_SESSION_PREFIX, GUI_SETUP_PREFIX, GUI_STATUS_PREFIX, GUI_UE4_PREFIX,
    parse_prefixed_json,
)
from drone_gui.runtime import RuntimeController
from drone_gui.widgets.control_shell import ControlShell
from drone_gui.widgets.live_page import LivePage
from drone_gui.widgets.mission_page import MissionPage
from drone_gui.widgets.preflight_page import PreflightPage
from drone_gui.widgets.map_results_page import MapResultsPage
from drone_gui.widgets.environment_page import EnvironmentPage


class MainWindow(QMainWindow):
    ENVIRONMENT_PAGE = 0
    PREFLIGHT_PAGE = 1
    MISSION_PAGE = 2
    LIVE_PAGE = 3
    RESULTS_PAGE = 4

    def __init__(self, config: RuntimeConfig, config_path=None) -> None:
        super().__init__()
        self.config = config
        self.commands = CommandBuilder(config)
        self.runtime = RuntimeController(self)
        self.perception = PerceptionFeed(self)
        self._mission_closed_loop = False
        self._ue_window_ready = False
        self._ue_airsim_ready = None
        self._setup_components: dict[str, dict] = {}
        self.setWindowTitle("Drone Mapbuilding Control Station")
        self.setMinimumSize(1180, 760)
        self.resize(1480, 920)
        self.environment_page = EnvironmentPage(config, config_path)
        self.preflight_page = PreflightPage(config)
        self.mission_page = MissionPage()
        self.live_page = LivePage()
        self.results_page = MapResultsPage(config.results_dir)
        self.shell = ControlShell(
            ControlShell.PAGE_NAMES,
            (
                self.environment_page,
                self.preflight_page,
                self.mission_page,
                self.live_page,
                self.results_page,
            ),
        )
        self.setCentralWidget(self.shell)
        self.health = BackendHealthController(
            self.runtime, self.commands, self.preflight_page,
            self.shell.stack_status, self,
        )
        self.mission_actions = MissionActionController(
            self.runtime, self.commands, self.live_page, self
        )
        self._connect_signals()

    def _connect_signals(self) -> None:
        self.shell.page_requested.connect(self._show_page)
        self.environment_page.config_saved.connect(self._apply_config)
        self.environment_page.setup_requested.connect(self._setup_environment)
        self.environment_page.qgc_requested.connect(self._launch_qgc)
        self.preflight_page.launch_ue4_requested.connect(self._launch_ue4)
        self.preflight_page.restart_stack_requested.connect(self._restart_stack)
        self.preflight_page.runtime_probe_requested.connect(self.health.probe)
        self.mission_page.start_requested.connect(self._start_mission)
        self.live_page.hold_requested.connect(
            lambda: self.mission_actions.request("hold"))
        self.live_page.resume_requested.connect(
            lambda: self.mission_actions.request("resume"))
        self.live_page.land_requested.connect(
            lambda: self.mission_actions.request("land"))
        self.runtime.task_started.connect(self._task_started)
        self.runtime.task_output.connect(self._task_output)
        self.runtime.task_finished.connect(self._task_finished)
        self.runtime.task_error.connect(self._task_error)
        self.perception.frame_ready.connect(self.live_page.set_frame)
        self.perception.snapshot_ready.connect(self.live_page.update_perception)
        self.perception.snapshot_ready.connect(self.results_page.update_semantics)
        self.perception.state_changed.connect(self.live_page.set_feed_state)

    def _show_page(self, index: int) -> None:
        self.shell.show_page(index)
        if index == self.RESULTS_PAGE:
            self.results_page.refresh()

    def _launch_ue4(self) -> None:
        if self.config.ue4_launch_mode == "editor" and not self.config.ue4_project.is_file():
            QMessageBox.warning(self, "未选择 UE4 工程", "请先在“环境配置”中选择有效的 .uproject 文件。")
            self._show_page(self.ENVIRONMENT_PAGE)
            return
        if self.config.ue4_launch_mode == "standalone" and (
            self.config.ue4_executable is None or not self.config.ue4_executable.is_file()
        ):
            QMessageBox.warning(self, "未选择仿真程序", "请先选择有效的已打包 UE4 仿真 .exe。")
            self._show_page(self.ENVIRONMENT_PAGE)
            return
        self.runtime.start("ue4", self.commands.launch_ue4())

    def _setup_environment(self, mode: str) -> None:
        self._setup_components = {}
        self.runtime.start("setup", self.commands.setup_environment(mode))

    def _launch_qgc(self) -> None:
        try:
            command = self.commands.launch_qgc()
        except ValueError as exc:
            QMessageBox.warning(self, "QGC 未配置", str(exc))
            return
        if not Path(command.program).is_file():
            QMessageBox.warning(self, "QGC 未找到", f"程序不存在：{command.program}")
            return
        self.runtime.start("qgc", command)

    def _apply_config(self, config: RuntimeConfig, _path) -> None:
        self.config = config
        self.commands = CommandBuilder(config)
        self.health.commands = self.commands
        self.mission_actions.commands = self.commands
        self.preflight_page.config = config
        self.preflight_page.refresh()
        self.results_page.set_results_dir(config.results_dir)
        self.shell.ue_status.set_state("warning", f"待启动：{config.environment_name}")

    def _restart_stack(self) -> None:
        self.runtime.start("stack", self.commands.restart_stack())

    def _start_mission(self, plan: MissionPlan) -> None:
        if not self.preflight_page.required_ready:
            QMessageBox.warning(
                self, "自检未通过",
                "请先在“系统与自检”页面完成本地与 WSL 动态检查。",
            )
            self._show_page(self.PREFLIGHT_PAGE)
            return
        if self.runtime.is_running("mission"):
            QMessageBox.information(self, "任务运行中", "当前任务尚未结束，不能重复启动。")
            return
        self.runtime.start("mission", self.commands.run_mission(plan))

    def _task_started(self, name: str, command: str) -> None:
        self._append_log(name, f"START {command}")
        if name == "ue4":
            self._ue_window_ready = False
            self._ue_airsim_ready = None
            self.shell.ue_status.set_state("running", "UE4 启动中")
        elif name == "stack":
            self.shell.stack_status.set_state("running", "PX4 / ROS2 启动中")
        elif name == "mission":
            self._mission_closed_loop = False
            self.perception.stop("准备新的视觉 Session")
            self.live_page.reset_perception()
            self.shell.mission_status.set_state("running", "任务运行中")
            self.live_page.set_process_state("running", "感知运行中")
            self.mission_page.set_running(True)
        elif name == "probe":
            self.health.started()
        elif name == "setup":
            self.environment_page.set_setup_state("warning", "正在检查或配置环境，请查看下方运行日志…")

    def _task_output(self, name: str, text: str) -> None:
        self._append_log(name, text)
        if name == "ue4":
            payload = parse_prefixed_json(text, GUI_UE4_PREFIX)
            if payload is not None:
                self._ue_window_ready = payload.get("window_ready") is True
                self._ue_airsim_ready = payload.get("airsim_ready")
                if self._ue_window_ready and self._ue_airsim_ready is True:
                    self.shell.ue_status.set_state("ready", "UE4 / AirSim 就绪")
                elif self._ue_window_ready:
                    self.shell.ue_status.set_state("warning", "UE4 已打开 · AirSim 检查中")
            return
        if name == "setup":
            payload = parse_prefixed_json(text, GUI_SETUP_PREFIX)
            if payload is not None and payload.get("component"):
                self._setup_components[str(payload["component"])] = payload
                suggested = payload.get("suggested_path")
                if suggested and payload["component"] == "qgc":
                    self.config.qgc_executable = Path(suggested)
                elif suggested and payload["component"] == "airsim_download":
                    self.config.airsim_client = Path(suggested)
                lines = [
                    f"{item.get('component')}：{item.get('status')} · {item.get('detail')}"
                    for item in self._setup_components.values()
                ]
                self.environment_page.set_setup_state("warning", "\n".join(lines[-8:]))
            return
        if name == "probe":
            self.health.consume(text)
            return
        if name != "mission":
            return
        session = parse_prefixed_json(text, GUI_SESSION_PREFIX)
        if session is not None:
            self.perception.start(session)
            self.results_page.start_session(session)
        payload = parse_prefixed_json(text, GUI_STATUS_PREFIX)
        if payload is not None:
            self.live_page.update_status(payload)
            self.results_page.update_telemetry(payload)
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
            if self._ue_window_ready and self._ue_airsim_ready is not True:
                self.shell.ue_status.set_state("warning", "UE4 已打开 · AirSim 未就绪")
            else:
                text = "UE4 / AirSim 就绪" if exit_code == 0 else "UE4 启动失败"
                self.shell.ue_status.set_state(state, text)
        elif name == "stack":
            self.health.stack_finished(exit_code)
        elif name == "probe":
            self.health.finished(exit_code)
        elif name == "mission":
            self._mission_finished(exit_code)
        elif name.startswith("control_"):
            self.live_page.controls.set_busy(False)
        elif name == "setup":
            failed = [item for item in self._setup_components.values() if item.get("status") == "fail"]
            state_name = "warning" if failed or exit_code else "pass"
            message = (
                f"配置完成，但仍有 {len(failed)} 项未就绪；请查看日志并再次体检。"
                if failed or exit_code else "工作流环境已配置并通过体检。"
            )
            self.environment_page.set_setup_state(state_name, message)
            self.environment_page.workflow.load(self.config)

    def _mission_finished(self, exit_code: int) -> None:
        self.mission_page.set_running(False)
        self.perception.stop("任务结束，保留最后一帧")
        self.results_page.stop_live_map("任务结束，保留最终地图")
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
            "setup": (self.shell.stack_status, "环境配置失败"),
        }
        if name in badges:
            badge, text = badges[name]
            badge.set_state("error", text)
        if name == "mission":
            self.mission_page.set_running(False)
            self.perception.stop("任务异常，视觉流已停止")
            self.results_page.stop_live_map("任务异常，地图流已停止")
        if name == "probe":
            self.health.fail(message)
            return
        if name == "setup":
            self.environment_page.set_setup_state("fail", f"环境配置失败：{message}")
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
