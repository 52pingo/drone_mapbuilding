from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QMessageBox

from drone_gui.mission_actions import MissionActionController


class FakeRuntime:
    def __init__(self, running=()):
        self.running = set(running)
        self.started = []

    def is_running(self, name):
        return name in self.running

    def start(self, name, command):
        self.started.append((name, command))


class FakeCommands:
    def mission_control(self, action):
        return ["mission_control", action]


class FakeControls:
    def __init__(self):
        self.busy = []

    def set_busy(self, value):
        self.busy.append(value)


class FakeLivePage:
    def __init__(self):
        self.controls = FakeControls()


@pytest.fixture
def make_controller():
    def _make(running=()):
        runtime = FakeRuntime(running)
        commands = FakeCommands()
        page = FakeLivePage()
        ctrl = MissionActionController(runtime, commands, page, None)
        return ctrl, runtime, commands, page

    return _make


@pytest.fixture
def info_calls(monkeypatch):
    calls = []

    def fake_information(*args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr(QMessageBox, "information", fake_information)
    return calls


@pytest.fixture
def question_answer(monkeypatch):
    state = {"answer": QMessageBox.Yes}

    def fake_question(*args, **kwargs):
        return state["answer"]

    monkeypatch.setattr(QMessageBox, "question", fake_question)
    return state


def test_hold_when_mission_not_running(make_controller, info_calls):
    ctrl, runtime, commands, page = make_controller(running=())
    ctrl.request("hold")
    assert len(info_calls) == 1
    assert runtime.started == []
    assert page.controls.busy == []


def test_hold_when_mission_running(make_controller, info_calls):
    ctrl, runtime, commands, page = make_controller(running=("mission",))
    ctrl.request("hold")
    assert info_calls == []
    assert runtime.started == [("control_hold", ["mission_control", "hold"])]
    assert page.controls.busy == [True]


def test_resume_dispatches_correct_command(make_controller, info_calls):
    ctrl, runtime, commands, page = make_controller(running=("mission",))
    ctrl.request("resume")
    assert runtime.started == [("control_resume", ["mission_control", "resume"])]
    assert page.controls.busy == [True]


def test_land_confirmed(make_controller, info_calls, question_answer):
    question_answer["answer"] = QMessageBox.Yes
    ctrl, runtime, commands, page = make_controller(running=("mission",))
    ctrl.request("land")
    assert runtime.started == [("control_land", ["mission_control", "land"])]
    assert page.controls.busy == [True]


def test_land_cancelled(make_controller, info_calls, question_answer):
    question_answer["answer"] = QMessageBox.No
    ctrl, runtime, commands, page = make_controller(running=("mission",))
    ctrl.request("land")
    assert runtime.started == []
    assert page.controls.busy == []


def test_control_in_progress_blocks_resume(make_controller, info_calls):
    ctrl, runtime, commands, page = make_controller(
        running=("mission", "control_hold")
    )
    ctrl.request("resume")
    assert len(info_calls) == 1
    assert runtime.started == []
    assert page.controls.busy == []


def test_control_in_progress_blocks_hold(make_controller, info_calls):
    ctrl, runtime, commands, page = make_controller(
        running=("mission", "control_land")
    )
    ctrl.request("hold")
    assert len(info_calls) == 1
    assert runtime.started == []


def test_control_in_progress_land_after_confirmation(
    make_controller, info_calls, question_answer
):
    question_answer["answer"] = QMessageBox.Yes
    ctrl, runtime, commands, page = make_controller(
        running=("mission", "control_resume")
    )
    ctrl.request("land")
    assert len(info_calls) == 1
    assert runtime.started == []


def test_mission_not_running_takes_precedence(make_controller, info_calls):
    ctrl, runtime, commands, page = make_controller(running=("control_hold",))
    ctrl.request("hold")
    assert len(info_calls) == 1
    assert runtime.started == []


def test_land_question_not_asked_when_mission_not_running(
    make_controller, info_calls, monkeypatch
):
    asked = []

    def fake_question(*args, **kwargs):
        asked.append(args)
        return QMessageBox.Yes

    monkeypatch.setattr(QMessageBox, "question", fake_question)
    ctrl, runtime, commands, page = make_controller(running=())
    ctrl.request("land")
    assert asked == []
    assert runtime.started == []


def test_actions_tuple_contains_expected(make_controller):
    assert MissionActionController.ACTIONS == ("hold", "resume", "land")
