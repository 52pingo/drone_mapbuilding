"""Application-wide visual tokens and Qt stylesheet."""

APP_STYLESHEET = """
QWidget {
    color: #D8E2E8;
    background: #11181D;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}
QMainWindow, QWidget#AppShell { background: #0C1216; }
QFrame#Sidebar {
    background: #101A20;
    border-right: 1px solid #26343C;
}
QFrame#Header {
    background: #0F171C;
    border-bottom: 1px solid #26343C;
}
QFrame[role="panel"] {
    background: #141E24;
    border: 1px solid #2A3942;
    border-radius: 6px;
}
QLabel#ProductTitle {
    color: #F2F7F9;
    font-size: 18px;
    font-weight: 700;
}
QLabel#ProductCaption, QLabel[role="muted"] { color: #83959F; }
QLabel#PageTitle {
    color: #F4F8FA;
    font-size: 20px;
    font-weight: 700;
}
QLabel[role="sectionTitle"] {
    color: #F0F5F7;
    font-size: 15px;
    font-weight: 650;
}
QLabel[role="metric"] {
    color: #F0F5F7;
    font-size: 16px;
    font-weight: 700;
}
QLabel[state="pass"] { color: #76D6B3; }
QLabel[state="warning"] { color: #F2C56D; }
QLabel[state="fail"] { color: #FF8D86; }
QLabel#StatusBadge {
    border: 1px solid #40515B;
    border-radius: 10px;
    padding: 3px 9px;
    background: #18242B;
    color: #AEBCC4;
}
QLabel#StatusBadge[state="ready"] {
    border-color: #28735E; background: #12372E; color: #8BE0C0;
}
QLabel#StatusBadge[state="running"] {
    border-color: #2B7182; background: #12343D; color: #8DD8E9;
}
QLabel#StatusBadge[state="warning"] {
    border-color: #80632D; background: #3A2C12; color: #F4CC79;
}
QLabel#StatusBadge[state="error"] {
    border-color: #87413E; background: #3D1D1C; color: #FFA19B;
}
QPushButton {
    min-height: 30px;
    padding: 0 12px;
    border-radius: 4px;
    border: 1px solid #354852;
    background: #19262D;
    color: #D9E4E9;
}
QPushButton:hover { background: #21323A; border-color: #4A626E; }
QPushButton:focus { border: 2px solid #4FB4C1; }
QPushButton:disabled { color: #61727B; background: #151E23; border-color: #26343B; }
QPushButton[kind="primary"] {
    background: #176D78; border-color: #258D99; color: #FFFFFF; font-weight: 650;
}
QPushButton[kind="primary"]:hover { background: #1B7E8A; }
QPushButton[kind="quiet"] { background: transparent; border-color: transparent; }
QPushButton[kind="danger"] { background: #5B2927; border-color: #8A4440; }
QPushButton[nav="true"] {
    min-height: 38px;
    text-align: left;
    padding-left: 16px;
    background: transparent;
    border: 1px solid transparent;
    color: #9FAFB7;
}
QPushButton[nav="true"]:hover { background: #17242B; color: #E5EDF1; }
QPushButton[nav="true"]:checked {
    background: #183139;
    border-color: #28515B;
    color: #8FE0E7;
    font-weight: 650;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    min-height: 29px;
    border: 1px solid #344650;
    border-radius: 4px;
    background: #0F171C;
    padding: 0 8px;
    selection-background-color: #176D78;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #4FB4C1;
}
QTableWidget, QTreeWidget, QPlainTextEdit {
    background: #0F171C;
    alternate-background-color: #131E24;
    border: 1px solid #2A3942;
    border-radius: 4px;
    gridline-color: #26353D;
    selection-background-color: #1B515B;
    selection-color: #FFFFFF;
}
QHeaderView::section {
    background: #172229;
    color: #AFC0C8;
    border: 0;
    border-right: 1px solid #2B3B43;
    border-bottom: 1px solid #2B3B43;
    padding: 7px;
    font-weight: 650;
}
QTabBar::tab {
    background: #141E24; color: #8FA0A9; padding: 8px 14px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: #8FE0E7; border-bottom-color: #4FB4C1; }
QSplitter::handle { background: #26343C; width: 1px; height: 1px; }
QScrollBar:vertical { width: 10px; background: #0F171C; }
QScrollBar::handle:vertical { background: #354852; border-radius: 4px; min-height: 24px; }
QToolTip { background: #24323A; color: #F3F7F9; border: 1px solid #526872; }
"""
