from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from drone_gui.widgets.map_view_page import MapViewPage
from drone_gui.widgets.results_page import ResultsPage
from drone_gui.sessions import session_payload


class MapResultsPage(QWidget):
    def __init__(self, results_dir, parent=None) -> None:
        super().__init__(parent)
        self.map_view = MapViewPage()
        self.results = ResultsPage(results_dir)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("实时地图和任务成果")
        self.tabs.addTab(self.map_view, "实时 3D 地图")
        self.tabs.addTab(self.results, "成果浏览")
        self.results.session_open_requested.connect(self.open_session)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.tabs)

    def refresh(self) -> None:
        self.results.refresh()

    def set_results_dir(self, results_dir) -> None:
        self.results.results_dir = results_dir
        self.results.refresh()

    def start_session(self, session: dict) -> None:
        self.map_view.start_session(session)

    def open_session(self, root) -> None:
        self.map_view.start_session(session_payload(root, offline=True))
        self.tabs.setCurrentWidget(self.map_view)

    def update_telemetry(self, payload: dict) -> None:
        self.map_view.update_telemetry(payload)

    def update_semantics(self, payload: dict) -> None:
        self.map_view.update_semantics(payload)

    def stop_live_map(self, message: str) -> None:
        self.map_view.stop(message)
