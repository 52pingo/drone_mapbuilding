"""Pure transition rules for operator mission controls."""

from dataclasses import dataclass


HOLDABLE_STATES = frozenset({'NAVIGATE', 'SCAN'})
LANDABLE_STATES = frozenset({'TAKEOFF', 'NAVIGATE', 'SCAN', 'HOVER', 'HOLD'})


@dataclass(frozen=True)
class ControlDecision:
    """Describe whether an operator command may change mission state."""

    accepted: bool
    next_state: str
    resume_state: str | None
    message: str


def decide_control(
        action: str, state: str, resume_state: str | None = None
) -> ControlDecision:
    """Return a deterministic and side-effect-free mission transition."""
    action = action.lower().strip()
    state = state.upper().strip()
    if action == 'hold':
        if state not in HOLDABLE_STATES:
            return ControlDecision(
                False, state, resume_state,
                'hold is only available while navigating or scanning')
        return ControlDecision(True, 'HOLD', state, 'operator hold accepted')
    if action == 'resume':
        if state != 'HOLD' or resume_state not in HOLDABLE_STATES:
            return ControlDecision(
                False, state, resume_state,
                'resume is only available after an operator hold')
        return ControlDecision(
            True, resume_state, None, 'operator resume accepted')
    if action == 'land':
        if state == 'LAND':
            return ControlDecision(False, state, resume_state, 'already landing')
        if state == 'DONE':
            return ControlDecision(False, state, resume_state, 'mission already done')
        if state not in LANDABLE_STATES:
            return ControlDecision(
                False, state, resume_state,
                'safe landing is unavailable before takeoff')
        return ControlDecision(True, 'LAND', None, 'operator landing accepted')
    return ControlDecision(False, state, resume_state, 'unknown control action')
