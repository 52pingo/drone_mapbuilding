"""Operator page for selecting a simulator and configuring the workflow."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
)

from drone_gui.config_store import save_config
from drone_gui.environment_discovery import discover_runtime
from drone_gui.models import RuntimeConfig
from drone_gui.widgets.simulation_settings import SimulationSettings
from drone_gui.widgets.workflow_settings import WorkflowSettings


class EnvironmentPage(QWidget):
    config_saved = Signal(object, object)
    setup_requested = Signal(str)
    qgc_requested = Signal()

    def __init__(self, config: RuntimeConfig, config_path=None, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.config_path = config_path
        self.simulation = SimulationSettings(config)
        self.workflow = WorkflowSettings(config)
        intro = QLabel(
            "选择任意已接入 AirSim 的 UE4 工程或已打包仿真程序。保存后，启动、自检、"
            "航线和语义任务都会使用当前环境；不再固定为 CityPark。"
        )
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")
        tabs = QTabWidget()
        tabs.addTab(self.simulation, "本地仿真环境")
        tabs.addTab(self.workflow, "工作流路径")
        self.status = QLabel("尚未修改配置")
        self.status.setWordWrap(True)
        self.status.setProperty("role", "muted")
        actions = self._build_actions()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(intro)
        layout.addWidget(tabs, 1)
        layout.addWidget(self.status)
        layout.addWidget(actions)

    def _build_actions(self) -> QFrame:
        panel = QFrame()
        panel.setProperty("role", "panel")
        layout = QHBoxLayout(panel)
        discover = QPushButton("自动发现本机路径")
        discover.clicked.connect(self._discover)
        save = QPushButton("保存并应用")
        save.setProperty("kind", "primary")
        save.clicked.connect(self._save)
        check = QPushButton("配置能力体检")
        check.clicked.connect(lambda: self.setup_requested.emit("check"))
        install = QPushButton("一键配置 / 修复")
        install.setProperty("kind", "primary")
        install.clicked.connect(self._request_install)
        qgc = QPushButton("打开 QGC")
        qgc.clicked.connect(self.qgc_requested)
        layout.addWidget(discover)
        layout.addWidget(save)
        layout.addStretch()
        layout.addWidget(check)
        layout.addWidget(install)
        layout.addWidget(qgc)
        return panel

    def _apply_fields(self) -> None:
        self.simulation.apply(self.config)
        self.workflow.apply(self.config)

    def _save(self) -> None:
        self._apply_fields()
        try:
            self.config.results_dir.mkdir(parents=True, exist_ok=True)
            path = save_config(self.config, self.config_path)
        except OSError as exc:
            QMessageBox.critical(self, "配置保存失败", str(exc))
            return
        self.config_path = path
        self.status.setText(f"已保存并应用：{path}")
        self.status.setProperty("state", "pass")
        self.config_saved.emit(self.config, path)

    def _discover(self) -> None:
        self._apply_fields()
        changes = discover_runtime(self.config)
        self.simulation.load(self.config)
        self.workflow.load(self.config)
        self.status.setText("\n".join(changes) if changes else "现有路径均有效，未替换任何配置。")

    def _request_install(self) -> None:
        self._apply_fields()
        answer = QMessageBox.question(
            self,
            "确认一键配置",
            "将联网安装或修复 ROS2 Humble、PX4 v1.15.2、Micro XRCE-DDS、"
            "AirSim 客户端和 QGroundControl。首次执行可能需要 30–90 分钟；"
            "若 WSL 尚未安装，Windows 可能要求重启。是否继续？",
        )
        if answer == QMessageBox.Yes:
            self.setup_requested.emit("install")

    def set_setup_state(self, state: str, message: str) -> None:
        self.status.setText(message)
        self.status.setProperty("state", state)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
