"""Perception, QGC, and WSL workflow settings panel."""

from PySide6.QtWidgets import QFormLayout, QLineEdit, QWidget

from drone_gui.models import RuntimeConfig
from drone_gui.widgets.path_field import PathField


class WorkflowSettings(QWidget):
    def __init__(self, config: RuntimeConfig, parent=None) -> None:
        super().__init__(parent)
        self.python = PathField("视觉 Python", file_filter="Python (python.exe);;程序 (*.exe)")
        self.airsim = PathField("AirSim PythonClient", mode="directory")
        self.weights = PathField("YOLO 权重", file_filter="PyTorch 权重 (*.pt)")
        self.results = PathField("成果目录", mode="directory")
        self.qgc = PathField("QGroundControl", file_filter="QGroundControl (QGroundControl.exe);;程序 (*.exe)")
        self.distro = QLineEdit()
        self.user = QLineEdit()
        self.ros = QLineEdit()
        self.px4 = QLineEdit()
        self.xrce = QLineEdit()
        self.logs = QLineEdit()
        form = QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addRow("视觉 Python", self.python)
        form.addRow("AirSim PythonClient", self.airsim)
        form.addRow("YOLO 权重", self.weights)
        form.addRow("成果目录", self.results)
        form.addRow("QGroundControl", self.qgc)
        form.addRow("WSL 发行版", self.distro)
        form.addRow("WSL 用户", self.user)
        form.addRow("ROS2 工作区", self.ros)
        form.addRow("PX4 目录", self.px4)
        form.addRow("Micro XRCE-DDS", self.xrce)
        form.addRow("WSL 日志目录", self.logs)
        self.load(config)

    def load(self, config: RuntimeConfig) -> None:
        self.python.set_value(config.perception_python)
        self.airsim.set_value(config.airsim_client)
        self.weights.set_value(config.weights)
        self.results.set_value(config.results_dir)
        self.qgc.set_value(config.qgc_executable)
        self.distro.setText(config.wsl_distro)
        self.user.setText(config.wsl_user)
        self.ros.setText(config.ros_workspace)
        self.px4.setText(config.px4_dir)
        self.xrce.setText(config.micro_xrce_agent)
        self.logs.setText(config.log_dir)

    def apply(self, config: RuntimeConfig) -> None:
        config.perception_python = self.python.value() or config.perception_python
        config.airsim_client = self.airsim.value() or config.airsim_client
        config.weights = self.weights.value() or config.weights
        config.results_dir = self.results.value() or config.results_dir
        config.qgc_executable = self.qgc.value()
        config.wsl_distro = self.distro.text().strip() or "Ubuntu-22.04"
        config.wsl_user = self.user.text().strip() or "hw"
        config.ros_workspace = self.ros.text().strip()
        config.px4_dir = self.px4.text().strip()
        config.micro_xrce_agent = self.xrce.text().strip()
        config.log_dir = self.logs.text().strip()
