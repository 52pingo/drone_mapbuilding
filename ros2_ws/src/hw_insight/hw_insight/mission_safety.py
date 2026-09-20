"""触地判定，以及超时后的解锁兜底。"""

import math


def _all_finite(*values) -> bool:
    """所有值都是有限实数才算数。

    None 要单独挡掉 —— math.isfinite(None) 会抛 TypeError，
    而调用方在位置话题还没上来时传的就是 None。
    """
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        if not math.isfinite(v):
            return False
    return True


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
    """位置贴近地面、且三个方向速度都足够小，才算停稳了。"""
    if not _all_finite(z, ground_z, vx, vy, vz):
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
    """超时且停稳都满足，才走解锁兜底。

    这里也要挡 NaN：NaN 跟任何数比较都是 False，
    一旦计时器算出 NaN，兜底会永远不触发，飞机就停在原地不解锁了。
    """
    if not _all_finite(landing_elapsed, landed_stable_for):
        return False
    return (
        landing_elapsed >= land_timeout
        and landed_stable_for >= landed_confirm
    )
