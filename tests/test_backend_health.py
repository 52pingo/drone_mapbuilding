from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from drone_gui.backend_health import BackendHealthController
from drone_gui.protocol import GUI_PROBE_PREFIX


class FakePage:
    RUNTIME_COMPONENTS = (
        ("px4", "PX4", True),
        ("ros2", "ROS2", True),
        ("mavros", "MAVROS", False),
    )

    def __init__(self):
        self.probe_running = []
        self.applied_probe = None
        self.applied_failure = None

    def set_probe_running(self, value):
        self.probe_running.append(value)

    def apply_runtime_probe(self, payload):
        self.applied_probe = payload

    def apply_runtime_failure(self, message):
        self.applied_failure = message


class FakeRuntime:
    def __init__(self):
        self.started = []

    def start(self, name, command):
        self.started.append((name, command))


class FakeCommands:
    def probe_stack(self):
        return ["probe", "cmd"]


class FakeBadge:
    def __init__(self):
        self.states = []

    def set_state(self, state, text):
        self.states.append((state, text))


@pytest.fixture
def controller():
    page = FakePage()
    badge = FakeBadge()
    runtime = FakeRuntime()
    commands = FakeCommands()
    ctrl = BackendHealthController(runtime, commands, page, badge)
    return ctrl, runtime, page, badge


def test_probe_resets_last_probe_and_starts(controller):
    ctrl, runtime, page, badge = controller
    ctrl.last_probe = {"stale": True}
    ctrl.probe()
    assert ctrl.last_probe is None
    assert page.probe_running == [True]
    assert runtime.started == [("probe", ["probe", "cmd"])]


def test_started_sets_probe_running(controller):
    ctrl, runtime, page, badge = controller
    ctrl.started()
    assert page.probe_running == [True]


def test_consume_valid_payload(controller):
    ctrl, runtime, page, badge = controller
    text = GUI_PROBE_PREFIX + '{"px4": true, "ros2": false}'
    ctrl.consume(text)
    assert ctrl.last_probe == {"px4": True, "ros2": False}


def test_consume_ignores_unrelated_text(controller):
    ctrl, runtime, page, badge = controller
    ctrl.consume("some random log line")
    assert ctrl.last_probe is None


def test_consume_overwrites_previous_payload(controller):
    ctrl, runtime, page, badge = controller
    ctrl.consume(GUI_PROBE_PREFIX + '{"px4": false}')
    ctrl.consume(GUI_PROBE_PREFIX + '{"px4": true}')
    assert ctrl.last_probe == {"px4": True}


def test_finished_success_all_required_ready(controller):
    ctrl, runtime, page, badge = controller
    ctrl.last_probe = {"px4": True, "ros2": True, "mavros": False}
    ctrl.finished(0)
    assert page.applied_probe == {"px4": True, "ros2": True, "mavros": False}
    assert badge.states[-1] == ("ready", "PX4 / ROS2 运行正常")


def test_finished_success_missing_required_warning(controller):
    ctrl, runtime, page, badge = controller
    ctrl.last_probe = {"px4": True, "ros2": False}
    ctrl.finished(0)
    assert badge.states[-1] == ("warning", "运行检查未通过")


def test_finished_success_missing_key_treated_as_unhealthy(controller):
    ctrl, runtime, page, badge = controller
    ctrl.last_probe = {"px4": True}
    ctrl.finished(0)
    assert badge.states[-1] == ("warning", "运行检查未通过")


def test_finished_nonzero_exit_fails(controller):
    ctrl, runtime, page, badge = controller
    ctrl.last_probe = {"px4": True, "ros2": True}
    ctrl.finished(1)
    assert page.applied_failure == "进程退出码 1，未收到 GUI_PROBE"
    assert badge.states[-1] == ("error", "运行检查失败")


def test_finished_no_probe_fails(controller):
    ctrl, runtime, page, badge = controller
    ctrl.finished(0)
    assert page.applied_failure == "进程退出码 0，未收到 GUI_PROBE"
    assert badge.states[-1] == ("error", "运行检查失败")


def test_stack_finished_success_triggers_probe(controller):
    ctrl, runtime, page, badge = controller
    ctrl.stack_finished(0)
    assert badge.states[-1] == ("ready", "PX4 / ROS2 就绪")
    assert runtime.started == [("probe", ["probe", "cmd"])]


def test_stack_finished_failure_no_probe(controller):
    ctrl, runtime, page, badge = controller
    ctrl.stack_finished(1)
    assert badge.states[-1] == ("error", "堆栈启动失败")
    assert runtime.started == []


def test_fail_sets_error_state(controller):
    ctrl, runtime, page, badge = controller
    ctrl.fail("boom")
    assert page.applied_failure == "boom"
    assert badge.states[-1] == ("error", "运行检查失败")
