"""Tests for drone_gui.theme.APP_STYLESHEET."""

from __future__ import annotations

import re

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from drone_gui.theme import APP_STYLESHEET  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


REQUIRED_SELECTORS = [
    "QWidget",
    "QPushButton",
    "QLineEdit",
    "QLabel",
    "QScrollBar",
    "QToolTip",
    "QComboBox",
    "QSpinBox",
    "QDoubleSpinBox",
    "QTableWidget",
    "QTreeWidget",
    "QPlainTextEdit",
    "QHeaderView",
    "QTabBar",
    "QSplitter",
    "QMainWindow",
    "QFrame",
]


def test_stylesheet_is_nonempty_string():
    assert isinstance(APP_STYLESHEET, str)
    assert APP_STYLESHEET.strip()


def test_stylesheet_parses_without_exception(qapp):
    # setStyleSheet must not raise; Qt silently drops invalid rules.
    qapp.setStyleSheet(APP_STYLESHEET)
    assert qapp.styleSheet() == APP_STYLESHEET


@pytest.mark.parametrize("selector", REQUIRED_SELECTORS)
def test_required_selector_present(selector):
    # Match the selector as a token (word boundary) so QLabel doesn't match QLabel#x only.
    pattern = re.compile(r"(?<![\w#])" + re.escape(selector) + r"(?![\w])")
    assert pattern.search(APP_STYLESHEET), f"missing selector: {selector}"


def test_braces_are_balanced():
    opens = APP_STYLESHEET.count("{")
    closes = APP_STYLESHEET.count("}")
    assert opens == closes, f"unbalanced braces: {opens} '{{' vs {closes} '}}'"
    assert opens > 0


def test_no_stray_closing_brace_before_opening():
    depth = 0
    for ch in APP_STYLESHEET:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            assert depth >= 0, "closing brace without matching opening brace"
    assert depth == 0


HEX_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
HASH_TOKEN_RE = re.compile(r"#[0-9A-Za-z_]+")


def test_all_hex_colors_are_six_digit():
    # Every '#' token that is not a selector id (e.g. #Sidebar) must be a 6-digit hex color.
    for token in HASH_TOKEN_RE.findall(APP_STYLESHEET):
        body = token[1:]
        if re.fullmatch(r"[0-9A-Fa-f]{6}", body):
            continue
        # Selector ids like #Sidebar, #ProductTitle, #StatusBadge, #AppShell
        assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", body), (
            f"invalid hex color or selector id: {token}"
        )


def test_no_three_digit_hex_colors():
    # Find every '#' followed by exactly 3 hex chars and nothing more.
    for match in re.finditer(r"#([0-9A-Fa-f]{3})(?![0-9A-Fa-f])", APP_STYLESHEET):
        token = match.group(0)
        # Skip selector ids that happen to be 3 hex chars (rare, but be safe).
        assert re.fullmatch(r"#[0-9A-Fa-f]{3}", token)


def test_hex_color_count_is_reasonable():
    colors = HEX_COLOR_RE.findall(APP_STYLESHEET)
    assert len(colors) >= 20


def test_known_palette_colors_present():
    for color in ("#11181D", "#0C1216", "#4FB4C1", "#176D78"):
        assert color in APP_STYLESHEET


def test_selector_id_blocks_are_well_formed():
    # Every "Selector {" block must have a non-empty body.
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", APP_STYLESHEET):
        selector = match.group(1).strip()
        body = match.group(2).strip()
        assert selector, "empty selector"
        assert body, f"empty body for selector: {selector}"
