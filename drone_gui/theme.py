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
QPushButton[kind="primary"]:disabled {
    color: #61727B; background: #151E23; border-color: #26343B;
}
QPushButton[kind="quiet"] { background: transparent; border-color: transparent; }
QPushButton[kind="danger"] { background: #5B2927; border-color: #8A4440; }
QPushButton[kind="danger"]:disabled {
    color: #61727B; background: #151E23; border-color: #26343B;
}
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
/* 上面这些变体规则和 QPushButton:focus 特异性相同（元素+属性 vs 元素+伪类），
   又排在它后面，会把 focus 的描边整个盖掉 —— 键盘用户看不到焦点在哪。
   这里显式给每个变体补 focus：多一个伪类，特异性更高，必然生效。 */
QPushButton[kind="primary"]:focus,
QPushButton[kind="quiet"]:focus,
QPushButton[kind="danger"]:focus,
QPushButton[nav="true"]:focus {
    border: 2px solid #4FB4C1;
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
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {
    border-color: #4A626E;
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    color: #61727B; background: #151E23; border-color: #26343B;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border-left: 1px solid #344650;
    background: transparent;
}
QComboBox::drop-down:hover { background: #17242B; }
QComboBox::drop-down:disabled { border-left-color: #26343B; }
QComboBox::down-arrow {
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8FA0A9;
    margin-right: 6px;
}
QComboBox::down-arrow:hover { border-top-color: #8FE0E7; }
QComboBox::down-arrow:disabled { border-top-color: #61727B; }
QComboBox QAbstractItemView {
    background: #0F171C;
    border: 1px solid #2A3942;
    border-radius: 4px;
    padding: 4px;
    outline: 0;
    selection-background-color: #1B515B;
    selection-color: #FFFFFF;
}
QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 0 8px;
    border-radius: 3px;
}
QComboBox QAbstractItemView::item:hover { background: #17242B; }
QComboBox QAbstractItemView::item:selected { background: #1B515B; color: #FFFFFF; }
QTableWidget, QTreeWidget, QPlainTextEdit {
    background: #0F171C;
    alternate-background-color: #131E24;
    border: 1px solid #2A3942;
    border-radius: 4px;
    gridline-color: #26353D;
    selection-background-color: #1B515B;
    selection-color: #FFFFFF;
}
QTableWidget:focus, QTreeWidget:focus, QPlainTextEdit:focus {
    border: 1px solid #4FB4C1;
}
QTableWidget:disabled, QTreeWidget:disabled, QPlainTextEdit:disabled {
    color: #61727B; background: #151E23; border-color: #26343B;
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
QHeaderView::section:hover { background: #1D2C34; }
QTreeWidget::branch { background: transparent; }
QTreeWidget::branch:hover { background: #17242B; }
QTreeWidget::branch:selected { background: #1B515B; }
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings {
    border-image: none;
    background: transparent;
}
QTreeWidget::branch:open:has-children:!has-siblings,
QTreeWidget::branch:open:has-children:has-siblings {
    border-image: none;
    background: transparent;
}
QTabWidget::pane {
    background: #141E24;
    border: 1px solid #2A3942;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background: #141E24; color: #8FA0A9; padding: 8px 14px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover { color: #D8E2E8; background: #17242B; }
QTabBar::tab:selected { color: #8FE0E7; border-bottom-color: #4FB4C1; }
QTabBar::tab:focus { border: 1px solid #4FB4C1; }
QTabBar::tab:disabled { color: #61727B; background: #151E23; }
QSplitter::handle { background: #26343C; width: 1px; height: 1px; }
QSplitter::handle:hover { background: #4FB4C1; }
QSplitter::handle:pressed { background: #258D99; }
QScrollBar:vertical { width: 10px; background: #0F171C; margin: 0; }
QScrollBar::handle:vertical {
    background: #354852; border-radius: 4px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #4A626E; }
QScrollBar::handle:vertical:pressed { background: #258D99; }
QScrollBar::handle:vertical:disabled { background: #26343B; }
QScrollBar:horizontal { height: 10px; background: #0F171C; margin: 0; }
QScrollBar::handle:horizontal {
    background: #354852; border-radius: 4px; min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #4A626E; }
QScrollBar::handle:horizontal:pressed { background: #258D99; }
QScrollBar::handle:horizontal:disabled { background: #26343B; }
QScrollBar::add-line, QScrollBar::sub-line {
    background: transparent; border: 0; width: 0; height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSlider { min-height: 24px; }
QSlider::groove:horizontal {
    height: 4px; background: #26343C; border-radius: 2px;
}
QSlider::sub-page:horizontal { background: #258D99; border-radius: 2px; }
QSlider::add-page:horizontal { background: #26343C; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #4FB4C1;
    border: 1px solid #258D99;
    width: 14px; height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover { background: #8FE0E7; border-color: #4FB4C1; }
QSlider::handle:horizontal:focus { border: 2px solid #4FB4C1; }
QSlider::handle:horizontal:disabled {
    background: #61727B; border-color: #26343B;
}
QSlider::groove:vertical {
    width: 4px; background: #26343C; border-radius: 2px;
}
QSlider::sub-page:vertical { background: #26343C; border-radius: 2px; }
QSlider::add-page:vertical { background: #258D99; border-radius: 2px; }
QSlider::handle:vertical {
    background: #4FB4C1;
    border: 1px solid #258D99;
    width: 14px; height: 14px;
    margin: 0 -6px;
    border-radius: 7px;
}
QSlider::handle:vertical:hover { background: #8FE0E7; border-color: #4FB4C1; }
QSlider::handle:vertical:focus { border: 2px solid #4FB4C1; }
QSlider::handle:vertical:disabled {
    background: #61727B; border-color: #26343B;
}
QSlider::sub-page:horizontal:disabled { background: #3A4A52; }
QSlider::add-page:horizontal:disabled { background: #26343B; }
QSlider::sub-page:vertical:disabled { background: #26343B; }
QSlider::add-page:vertical:disabled { background: #3A4A52; }
QCheckBox, QRadioButton {
    spacing: 8px;
    min-height: 24px;
    color: #D8E2E8;
    background: transparent;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px; height: 16px;
    border: 1px solid #344650;
    background: #0F171C;
}
QCheckBox::indicator { border-radius: 3px; }
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #4FB4C1;
}
QCheckBox::indicator:focus, QRadioButton::indicator:focus {
    border: 2px solid #4FB4C1;
}
QCheckBox::indicator:checked {
    background: #176D78;
    border-color: #258D99;
}
QRadioButton::indicator:checked {
    background: #176D78;
    border: 4px solid #0F171C;
    outline: 1px solid #258D99;
}
QCheckBox::indicator:checked:hover, QRadioButton::indicator:checked:hover {
    background: #1B7E8A; border-color: #4FB4C1;
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    background: #151E23; border-color: #26343B;
}
QCheckBox:disabled, QRadioButton:disabled { color: #61727B; }
QProgressBar {
    min-height: 8px;
    max-height: 8px;
    border: 1px solid #2A3942;
    border-radius: 4px;
    background: #0F171C;
    text-align: center;
    color: #D8E2E8;
}
QProgressBar::chunk {
    background: #258D99;
    border-radius: 3px;
}
QProgressBar:hover { border-color: #4A626E; }
QProgressBar:focus { border: 1px solid #4FB4C1; }
QProgressBar:disabled { color: #61727B; background: #151E23; border-color: #26343B; }
QProgressBar::chunk:disabled { background: #3A4A52; }
QGroupBox {
    background: #141E24;
    border: 1px solid #2A3942;
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 10px 10px 10px;
    font-weight: 650;
    color: #F0F5F7;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: #AFC0C8;
    background: #141E24;
}
QGroupBox:hover { border-color: #344650; }
QGroupBox:focus { border: 1px solid #4FB4C1; }
QGroupBox:disabled {
    color: #61727B; background: #151E23; border-color: #26343B;
}
QGroupBox::title:disabled { color: #61727B; background: #151E23; }
QMenuBar {
    background: #0F171C;
    color: #D8E2E8;
    border-bottom: 1px solid #26343C;
    padding: 2px 4px;
}
QMenuBar::item {
    padding: 5px 10px;
    background: transparent;
    border-radius: 4px;
}
QMenuBar::item:selected { background: #17242B; color: #E5EDF1; }
QMenuBar::item:pressed { background: #183139; color: #8FE0E7; }
QMenuBar::item:disabled { color: #61727B; }
QMenu {
    background: #141E24;
    border: 1px solid #2A3942;
    border-radius: 6px;
    padding: 4px;
    color: #D8E2E8;
}
QMenu::item {
    padding: 6px 22px 6px 22px;
    border-radius: 4px;
    background: transparent;
}
QMenu::item:selected { background: #183139; color: #8FE0E7; }
QMenu::item:pressed { background: #1B515B; color: #FFFFFF; }
QMenu::item:disabled { color: #61727B; }
QMenu::separator {
    height: 1px;
    background: #26343C;
    margin: 4px 8px;
}
QMenu::indicator { width: 14px; height: 14px; }
QStatusBar {
    background: #0F171C;
    color: #83959F;
    border-top: 1px solid #26343C;
    min-height: 22px;
}
QStatusBar::item { border: 0; }
QStatusBar QLabel { color: #83959F; background: transparent; }
QStatusBar QLabel:disabled { color: #61727B; }
QDialog {
    background: #11181D;
    color: #D8E2E8;
}
QDialog QLabel { background: transparent; }
QMessageBox {
    background: #141E24;
    color: #D8E2E8;
}
QMessageBox QLabel { color: #D8E2E8; background: transparent; }
QMessageBox QPushButton { min-width: 76px; }
QToolBar {
    background: #0F171C;
    border-bottom: 1px solid #26343C;
    spacing: 4px;
    padding: 3px 6px;
}
QToolBar::separator {
    width: 1px;
    background: #26343C;
    margin: 4px 6px;
}
QToolBar QToolButton {
    min-height: 28px;
    padding: 0 10px;
    border-radius: 4px;
    border: 1px solid transparent;
    background: transparent;
    color: #D9E4E9;
}
QToolBar QToolButton:hover { background: #17242B; border-color: #354852; }
QToolBar QToolButton:focus { border: 2px solid #4FB4C1; }
QToolBar QToolButton:checked {
    background: #183139; border-color: #28515B; color: #8FE0E7;
}
QToolBar QToolButton:disabled {
    color: #61727B; background: #151E23; border-color: #26343B;
}
QToolTip { background: #24323A; color: #F3F7F9; border: 1px solid #526872; }
"""
