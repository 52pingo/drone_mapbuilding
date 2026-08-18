"""Tests for operator mission-control transition rules."""

from hw_insight.mission_control import decide_control


def test_hold_and_resume_restore_navigation_state():
    """A valid hold remembers and restores the interrupted state."""
    hold = decide_control('hold', 'NAVIGATE')
    assert hold.accepted
    assert (hold.next_state, hold.resume_state) == ('HOLD', 'NAVIGATE')

    resume = decide_control('resume', hold.next_state, hold.resume_state)
    assert resume.accepted
    assert (resume.next_state, resume.resume_state) == ('NAVIGATE', None)


def test_hold_is_rejected_during_takeoff_and_landing():
    """Hold never interrupts takeoff or an active landing sequence."""
    assert not decide_control('hold', 'TAKEOFF').accepted
    assert not decide_control('hold', 'LAND').accepted


def test_land_enters_existing_land_state_from_hold():
    """Landing from hold joins the normal LAND state machine."""
    result = decide_control('land', 'HOLD', 'NAVIGATE')
    assert result.accepted
    assert result.next_state == 'LAND'
    assert result.resume_state is None


def test_land_is_rejected_before_takeoff_or_after_done():
    """Landing commands have no effect outside an airborne mission."""
    assert not decide_control('land', 'WAIT').accepted
    assert not decide_control('land', 'DONE').accepted
