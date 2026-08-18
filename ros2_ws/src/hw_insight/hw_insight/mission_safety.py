"""Pure helpers for conservative autonomous landing fallback decisions."""

import math


def is_landed_candidate(
    z,
    ground_z,
    vx,
    vy,
    vz,
    z_tolerance,
    xy_speed_tolerance,
    z_speed_tolerance,
):
    """Return whether local position and velocity look stably grounded."""
    values = (z, ground_z, vx, vy, vz)
    if not all(math.isfinite(value) for value in values):
        return False
    return (
        abs(z - ground_z) <= z_tolerance
        and math.hypot(vx, vy) <= xy_speed_tolerance
        and abs(vz) <= z_speed_tolerance
    )


def should_request_disarm(
    landing_elapsed,
    landed_stable_for,
    land_timeout,
    landed_confirm,
):
    """Allow normal disarm fallback only after timeout and stable grounding."""
    return (
        landing_elapsed >= land_timeout
        and landed_stable_for >= landed_confirm
    )
