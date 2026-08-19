"""Simulation-environment settings panel."""

from PySide6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QWidget

from drone_gui.models import RuntimeConfig
from drone_gui.widgets.path_field import PathField


class SimulationSettings(QWidget):
    MODES = (("UE4 编辑器工程（.uproject）", "editor"), ("已打包仿真程序（.exe）", "standalone"))

    def __init__(self, config: RuntimeConfig, parent=None) -> None:
        super().__init__(parent)
        self.name = QLineEdit()
        self.name.setAccessibleName("仿真环境名称")
        self.mode = QComboBox()
        for label, value in self.MODES:
            self.mode.addItem(label, value)
        self.editor = PathField("UE4 Editor 路径", file_filter="UE4 Editor (UE4Editor.exe);;程序 (*.exe)")
        self.project = PathField("UE4 工程路径", file_filter="Unreal 工程 (*.uproject)")
        self.executable = PathField("已打包仿真程序路径", file_filter="仿真程序 (*.exe)")
        self.map_name = QLineEdit()
        self.map_name.setAccessibleName("UE4 地图资源路径")
        self.settings = PathField("AirSim settings.json", file_filter="JSON (*.json)")
        self.vehicle = QLineEdit()
        self.camera = QLineEdit()
        self.validation = QComboBox()
        self.validation.addItem("自动（CityPark 专用修复，其余通用深度检查）", "auto")
        self.validation.addItem("通用 AirSim RGB/深度检查", "generic")
        self.validation.addItem("只确认窗口，不检查 AirSim", "none")
        form = QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.addRow("环境名称", self.name)
        form.addRow("启动方式", self.mode)
        form.addRow("UE4 Editor", self.editor)
        form.addRow("UE4 工程", self.project)
        form.addRow("仿真程序", self.executable)
        form.addRow("地图（可留空）", self.map_name)
        form.addRow("AirSim 配置", self.settings)
        form.addRow("载具 / 深度相机", self._vehicle_camera_row())
        form.addRow("启动验证", self.validation)
        self.mode.currentIndexChanged.connect(self._update_mode)
        self.load(config)

    def _vehicle_camera_row(self):
        row = QWidget()
        layout = QFormLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow("载具", self.vehicle)
        layout.addRow("相机", self.camera)
        return row

    def _update_mode(self) -> None:
        editor_mode = self.mode.currentData() == "editor"
        self.editor.setEnabled(editor_mode)
        self.project.setEnabled(editor_mode)
        self.map_name.setEnabled(editor_mode)
        self.executable.setEnabled(not editor_mode)

    def load(self, config: RuntimeConfig) -> None:
        self.name.setText(config.environment_name)
        index = self.mode.findData(config.ue4_launch_mode)
        self.mode.setCurrentIndex(max(0, index))
        self.editor.set_value(config.ue4_editor)
        self.project.set_value(config.ue4_project)
        self.executable.set_value(config.ue4_executable)
        self.map_name.setText(config.ue4_map)
        self.settings.set_value(config.airsim_settings)
        self.vehicle.setText(config.airsim_vehicle)
        self.camera.setText(config.airsim_camera)
        self.validation.setCurrentIndex(max(0, self.validation.findData(config.ue4_validation)))
        self._update_mode()

    def apply(self, config: RuntimeConfig) -> None:
        config.environment_name = self.name.text().strip() or "未命名环境"
        config.ue4_launch_mode = str(self.mode.currentData())
        config.ue4_editor = self.editor.value() or config.ue4_editor
        config.ue4_project = self.project.value() or config.ue4_project
        config.ue4_executable = self.executable.value()
        config.ue4_map = self.map_name.text().strip()
        config.airsim_settings = self.settings.value()
        config.airsim_vehicle = self.vehicle.text().strip() or "PX4"
        config.airsim_camera = self.camera.text().strip() or "CameraDepth"
        config.ue4_validation = str(self.validation.currentData())
