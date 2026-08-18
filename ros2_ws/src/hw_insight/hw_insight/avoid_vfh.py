#!/usr/bin/env python3
"""Advanced Vector Field Histogram (VFH+) local planner for drone avoidance.

This module implements a VFH+-style local planner inspired by:

* Borenstein & Koren, "The Vector Field Histogram -- Fast Obstacle Avoidance for
  Mobile Robots" (1991).
* Ulrich & Borenstein, "VFH+: Reliable Obstacle Avoidance for Fast Mobile
  Robots" (1998).
* PX4/PX4-Avoidance local_planner, which extends the ideas above to a 3DVFH+
  histogram for drones.

The helper is kept ROS-free so it can be unit-tested with synthetic NumPy
arrays.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class VfhParams:
    """Tunable parameters for the VFH+ planner."""

    # ----- sensor / histogram -----
    fov_deg: float = 90.0
    bins: int = 72                       # finer angular resolution
    depth_min_range: float = 0.1
    depth_max_range: float = 25.0

    # ----- VFH+ binary thresholds -----
    threshold_high: float = 0.65         # sector blocked if density >= this
    threshold_low: float = 0.30          # hysteresis low threshold
    smooth_window: int = 1               # circular smoothing window radius

    # ----- robot geometry / safety -----
    robot_width: float = 1.0             # metres, determines wide vs narrow valley
    safety_radius: float = 1.0           # extra clearance around vehicle
    avoid_front: float = 10.0            # distance at which we start slowing
    avoid_brake: float = 5.0             # distance at which we brake hard
    avoid_near: float = 2.5              # distance at which we creep / back up

    # ----- cost weights (VFH+ style) -----
    w_goal: float = 5.0                  # penalty for deviation from target dir
    w_current: float = 1.0               # penalty for deviation from current heading
    w_smooth: float = 2.0                # penalty for direction changes
    w_obstacle: float = 3.0              # penalty for obstacle density

    # ----- speeds -----
    cruise_speed: float = 2.5
    max_speed: float = 3.5
    creep_speed: float = 0.5
    backup_speed: float = 0.8
    turn_speed: float = 0.6              # forward speed used during behind-goal arcs

    # ----- behind-goal / deadlock -----
    behind_fov_extra_deg: float = 15.0   # treat goal as "behind" when outside FOV+extra
    behind_turn_gain: float = 1.0        # >1 favours turning more aggressively


def _wrap_angle(angle: float) -> float:
    """Wrap angle to [-pi, pi]."""
    while angle > math.pi:
        angle -= 2.0 * math.pi
    while angle < -math.pi:
        angle += 2.0 * math.pi
    return angle


def blend_corridor_heading(
    body_heading: float,
    goal_heading: float,
    corridor_theta: float,
    corridor_weight: float,
    max_steer: float,
) -> float:
    """Blend a body-relative VFH corridor with a world-frame goal heading.

    ``corridor_theta`` is expressed in the vehicle body frame.  Convert it to
    the world frame before blending, and interpolate over the shortest angular
    distance so headings near ``-pi``/``pi`` remain continuous.
    """
    theta = max(-max_steer, min(max_steer, corridor_theta))
    selected_world = _wrap_angle(body_heading + theta)
    weight = max(0.0, min(1.0, corridor_weight))
    selected_from_goal = _wrap_angle(selected_world - goal_heading)
    return _wrap_angle(goal_heading + selected_from_goal * weight)


def _angular_diff(a: float, b: float) -> float:
    """Unsigned angular difference in [0, pi]."""
    return abs(_wrap_angle(a - b))


def _bin_centers_and_edges(bins: int, fov_rad: float) -> Tuple[np.ndarray, np.ndarray]:
    """Return centers and edges for a polar histogram spanning [-fov/2, fov/2]."""
    edges = np.linspace(-fov_rad / 2.0, fov_rad / 2.0, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    return centers, edges


def _camera_angles(width: int, fx: float, cx: float) -> np.ndarray:
    """Ray angle for every image column (radians, 0 = optical axis)."""
    cols = np.arange(width, dtype=float)
    return np.arctan2(cols - cx, fx)


def _intrinsics_from_camera_info(
    camera_info: Optional[Dict], width: int, fov_deg: float
) -> Tuple[float, float]:
    """Return (fx, cx)."""
    if camera_info is not None:
        k = camera_info.get("k", camera_info.get("K", []))
        if len(k) >= 4:
            fx = float(k[0])
            cx = float(k[2])
            return fx, cx
    fx = (width / 2.0) / math.tan(math.radians(fov_deg) / 2.0)
    cx = width / 2.0
    return fx, cx


def _column_min_distances(depth: np.ndarray, params: VfhParams) -> np.ndarray:
    """Return a 1-D array with the closest valid distance per image column."""
    h, w = depth.shape
    if h < 2 or w < 2:
        raise ValueError("depth image too small")

    # Use a central horizontal strip (robust to ground/sky noise).
    y0, y1 = int(h * 0.25), int(h * 0.75)
    strip = depth[y0:y1, :]
    valid = (
        np.isfinite(strip)
        & (strip > params.depth_min_range)
        & (strip < params.depth_max_range)
    )
    masked = np.where(valid, strip, np.inf)
    col_min = np.min(masked, axis=0)
    return col_min


def build_polar_histogram(
    depth: np.ndarray,
    params: VfhParams,
    camera_info: Optional[Dict] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build a polar obstacle density (POD) histogram from a depth image.

    Returns
    -------
    centers : np.ndarray, shape (bins,)
        Histogram bin centre angles in radians.
    hist : np.ndarray, shape (bins,)
        Normalised obstacle density per bin, in [0, 1].
    thetas : np.ndarray, shape (w,)
        Ray angle for every image column.
    col_min : np.ndarray, shape (w,)
        Closest valid distance per column (inf if none).
    """
    if depth is None:
        raise ValueError("depth image is None")
    h, w = depth.shape

    col_min = _column_min_distances(depth, params)
    fx, cx = _intrinsics_from_camera_info(camera_info, w, params.fov_deg)
    thetas = _camera_angles(w, fx, cx)

    # If nothing is valid, assume open space with a low uniform density so
    # the drone keeps moving instead of freezing.
    if not np.isfinite(col_min).any():
        fov_rad = math.radians(params.fov_deg)
        centers, _ = _bin_centers_and_edges(params.bins, fov_rad)
        return (
            centers,
            np.full(params.bins, 0.1, dtype=float),
            thetas,
            np.full(w, np.inf, dtype=float),
        )

    # Per-column obstacle cost: closer obstacles dominate the sector.
    denom = max(params.avoid_front - params.avoid_near, 0.5)
    finite = np.isfinite(col_min)
    cost = np.zeros(w, dtype=float)
    cost[finite] = np.clip(
        (params.avoid_front - col_min[finite]) / denom, 0.0, 1.0
    ) ** 2

    fov_rad = math.radians(params.fov_deg)
    centers, edges = _bin_centers_and_edges(params.bins, fov_rad)
    idx = np.digitize(thetas, edges) - 1
    idx = np.clip(idx, 0, params.bins - 1)

    hist = np.zeros(params.bins, dtype=float)
    np.maximum.at(hist, idx, cost)

    # Normalise to [0, 1].
    mx = hist.max()
    if mx > 0.0:
        hist /= mx

    # Light circular smoothing to suppress single-bin noise.
    if params.smooth_window > 0:
        pad = params.smooth_window
        extended = np.concatenate([hist[-pad:], hist, hist[:pad]])
        kernel = np.ones(2 * pad + 1, dtype=float) / (2 * pad + 1)
        smoothed = np.convolve(extended, kernel, mode="valid")
        if smoothed.max() > 0.0:
            smoothed /= smoothed.max()
        hist = smoothed

    return centers, hist, thetas, col_min


def binary_histogram(
    hist: np.ndarray,
    params: VfhParams,
    prev_binary: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Convert POD histogram to a binary blocked/free map with hysteresis."""
    binary = (hist >= params.threshold_high).astype(int)
    if prev_binary is not None and prev_binary.size == hist.size:
        # Hysteresis: previously free cells stay free until threshold_low.
        free_now = hist < params.threshold_low
        binary = np.where(prev_binary == 0, np.where(free_now, 0, 1), binary)
    return binary


def find_valleys(
    binary: np.ndarray,
    centers: np.ndarray,
    params: VfhParams,
) -> List[Dict]:
    """Return contiguous free sectors (valleys) in the binary histogram.

    Each valley is a dict with:
        start_idx, end_idx, centre_idx, centre, width_bins, wide.
    Wide valleys are wide enough for the robot to pass through.
    """
    bins = len(binary)
    free = binary == 0
    if free.all():
        return [{
            "start_idx": 0,
            "end_idx": bins - 1,
            "centre_idx": bins // 2,
            "centre": float(centers[bins // 2]),
            "width_bins": bins,
            "wide": True,
        }]

    # Required bins to fit the robot width at the centre of the histogram.
    # Use the angular resolution at the centre as a conservative estimate.
    if bins > 1:
        angular_res = abs(centers[1] - centers[0])
    else:
        angular_res = math.radians(90.0)
    required_width = max(1, int(math.ceil(
        2.0 * math.asin(min(1.0, params.robot_width / (2.0 * max(params.safety_radius, 0.5))))
        / angular_res
    )))

    # Walk around the histogram circularly to group free sectors.
    valleys = []
    in_valley = False
    start = 0
    # Duplicate the free array to handle wrap-around seamlessly.
    free2 = np.concatenate([free, free])
    for i in range(2 * bins):
        if free2[i] and not in_valley:
            in_valley = True
            start = i
        elif not free2[i] and in_valley:
            end = i - 1
            if end - start + 1 >= required_width or end >= bins:
                # Normalise to primary [0, bins-1] range.
                s = start % bins
                e = end % bins
                if s <= e:
                    centre_idx = (s + e) // 2
                    width = e - s + 1
                else:
                    # wraps around 0
                    centre_idx = ((s + e + bins) // 2) % bins
                    width = (bins - s) + e + 1
                valleys.append({
                    "start_idx": s,
                    "end_idx": e,
                    "centre_idx": centre_idx,
                    "centre": float(centers[centre_idx]),
                    "width_bins": width,
                    "wide": width >= required_width,
                })
            in_valley = False
    if in_valley:
        end = 2 * bins - 1
        if end - start + 1 >= required_width or end >= bins:
            s = start % bins
            e = end % bins
            if s <= e:
                centre_idx = (s + e) // 2
                width = e - s + 1
            else:
                centre_idx = ((s + e + bins) // 2) % bins
                width = (bins - s) + e + 1
            valleys.append({
                "start_idx": s,
                "end_idx": e,
                "centre_idx": centre_idx,
                "centre": float(centers[centre_idx]),
                "width_bins": width,
                "wide": width >= required_width,
            })

    # De-duplicate by centre index.
    seen = set()
    unique = []
    for v in valleys:
        key = (v["start_idx"], v["end_idx"], v["centre_idx"])
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


def _wrap_angle_vec(angles: np.ndarray) -> np.ndarray:
    """Vectorised wrap to [-pi, pi]."""
    return (angles + np.pi) % (2.0 * np.pi) - np.pi


def corridor_clearance(
    theta: float,
    thetas: np.ndarray,
    col_min: np.ndarray,
    half_width: float,
) -> float:
    """Minimum finite distance in an angular corridor around theta."""
    mask = np.abs(_wrap_angle_vec(thetas - theta)) <= half_width
    vals = col_min[mask & np.isfinite(col_min)]
    if vals.size == 0:
        return 999.0
    return float(np.min(vals))


def _candidate_directions(
    valleys: List[Dict],
    centers: np.ndarray,
    params: VfhParams,
) -> List[float]:
    """Generate candidate steering directions from valleys.

    Wide valleys yield three candidates (left, right, centre); narrow valleys
    yield the centre only.  This matches classic VFH+.
    """
    candidates = []
    if not valleys:
        return candidates

    if len(centers) > 1:
        bin_res = abs(centers[1] - centers[0])
    else:
        bin_res = math.radians(90.0)
    margin_bins = max(1, int(round(
        math.asin(min(1.0, params.safety_radius / max(params.avoid_near, 0.5))) / bin_res
    )))

    for v in valleys:
        s, e, cidx = v["start_idx"], v["end_idx"], v["centre_idx"]
        if v["wide"]:
            # Candidate near the right border (inside the valley by safety margin).
            ridx = min(s + margin_bins, e)
            lidx = max(e - margin_bins, s)
            for idx in (ridx, lidx, cidx):
                candidates.append(float(centers[idx]))
        else:
            candidates.append(float(centers[cidx]))

    # Preserve order but remove duplicates caused by small valleys.
    uniq = []
    seen = set()
    for c in candidates:
        key = round(c, 5)
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


def _obstacle_density_at(
    theta: float,
    centers: np.ndarray,
    hist: np.ndarray,
    half_width_bins: int = 1,
) -> float:
    """Average obstacle density around theta."""
    bins = len(centers)
    if bins == 0:
        return 1.0
    idx = int(np.argmin(np.abs(_wrap_angle_vec(centers - theta))))
    total = 0.0
    count = 0
    for d in range(-half_width_bins, half_width_bins + 1):
        i = (idx + d) % bins
        total += hist[i]
        count += 1
    return total / max(count, 1)


def speed_from_clearance(clearance: float, params: VfhParams) -> float:
    """Forward speed given the clearance in the chosen corridor."""
    if clearance >= params.avoid_front:
        return params.cruise_speed
    if clearance >= params.avoid_brake:
        t = (clearance - params.avoid_brake) / max(
            params.avoid_front - params.avoid_brake, 0.1
        )
        return params.cruise_speed * t
    if clearance > params.avoid_near:
        return params.creep_speed
    return -params.backup_speed


def best_gap_heading(
    depth: np.ndarray,
    params: VfhParams,
    camera_info: Optional[Dict] = None,
) -> float:
    """Return the heading offset (rad) of the largest open corridor."""
    centers, hist, thetas, col_min = build_polar_histogram(depth, params, camera_info)
    binary = binary_histogram(hist, params)
    valleys = find_valleys(binary, centers, params)
    if not valleys:
        # Everything blocked: pick direction with lowest density.
        return float(centers[int(np.argmin(hist))])

    half_width = math.radians(params.fov_deg / params.bins * 2.0)
    best_c = valleys[0]["centre"]
    best_clear = 0.0
    for v in valleys:
        c = corridor_clearance(v["centre"], thetas, col_min, half_width)
        if c > best_clear:
            best_clear = c
            best_c = v["centre"]
    return float(best_c)


def _build_output(
    chosen_theta: float,
    fwd: float,
    clearance: float,
    body_heading: float,
    goal_heading: float,
    theta_goal: float,
    action: str,
    blocked: bool,
    thetas: np.ndarray,
    col_min: np.ndarray,
    candidates: np.ndarray,
    valleys: List[Dict],
) -> Dict:
    """Pack the planner output."""
    heading_world = _wrap_angle(body_heading + chosen_theta)

    # For a turn-in-place, do not issue a translational velocity; just command
    # a yaw rate.  Otherwise move along the chosen corridor.
    if action == "turn":
        vx = vy = 0.0
        fwd = 0.0
        yaw_rate = _wrap_angle(goal_heading - heading_world)
        # Cap yaw rate to a reasonable value.
        max_rate = 1.0
        yaw_rate = max(-max_rate, min(max_rate, yaw_rate))
        yaw = float("nan")  # signal yaw-rate control
    else:
        vx = math.cos(heading_world) * fwd
        vy = math.sin(heading_world) * fwd
        yaw_rate = 0.0
        yaw = heading_world if fwd >= 0.0 else _wrap_angle(heading_world + math.pi)

    dc = corridor_clearance(0.0, thetas, col_min, math.radians(5.0))

    return {
        "vx": vx,
        "vy": vy,
        "yaw": yaw,
        "yaw_rate": yaw_rate,
        "forward_speed": fwd,
        "theta": chosen_theta,
        "clearance": clearance,
        "action": action,
        "blocked": blocked,
        "dc": dc,
        "candidate_thetas": [float(c) for c in candidates],
        "valley_info": [
            {
                "centre": v["centre"],
                "width_bins": v["width_bins"],
                "wide": v["wide"],
            }
            for v in valleys
        ],
        "goal_theta": theta_goal,
    }


def compute_vfh_motion(
    depth: np.ndarray,
    params: VfhParams,
    body_heading: float,
    goal_x: float,
    goal_y: float,
    pos_x: float,
    pos_y: float,
    last_theta: float,
    recovery_theta: Optional[float] = None,
    camera_info: Optional[Dict] = None,
) -> Dict:
    """Plan one avoidance step using VFH+.

    Returns a dict with keys:
      vx, vy, yaw, forward_speed, theta, clearance, action, blocked, dc,
      candidate_thetas, valley_info, goal_theta, yaw_rate.
    """
    centers, hist, thetas, col_min = build_polar_histogram(depth, params, camera_info)
    binary = binary_histogram(hist, params)
    valleys = find_valleys(binary, centers, params)

    gh = math.atan2(goal_y - pos_y, goal_x - pos_x)
    theta_goal = _wrap_angle(gh - body_heading)

    fov_half = max(abs(centers[0]), abs(centers[-1]))
    behind_extra = math.radians(params.behind_fov_extra_deg)
    goal_is_behind = abs(theta_goal) > fov_half + behind_extra

    # Default: choose the goal direction (clamped to FOV).
    goal_clamped = float(np.clip(theta_goal, centers[0], centers[-1]))

    # Build candidate set.
    candidates = _candidate_directions(valleys, centers, params)

    # If goal direction is relatively free, add it as a candidate.
    goal_bin = int(np.argmin(np.abs(centers - goal_clamped)))
    if binary[goal_bin] == 0:
        candidates.insert(0, goal_clamped)

    # Special handling when the goal is behind the sensor FOV.
    if goal_is_behind:
        # Add lateral arc candidates; the cost function will pick the side
        # that both turns toward the goal and has better clearance.
        arc_mag = min(fov_half, math.radians(60.0))
        candidates.insert(0, arc_mag)
        candidates.insert(0, -arc_mag)

    if recovery_theta is not None:
        # Recovery mode: temporarily ignore the goal and head for the safest gap.
        chosen_theta = _wrap_angle(recovery_theta)
        action = "recover"
        clearance = corridor_clearance(chosen_theta, thetas, col_min, math.radians(5.0))
        fwd = speed_from_clearance(clearance, params)
        return _build_output(
            chosen_theta, fwd, clearance, body_heading, gh, theta_goal,
            action, True, thetas, col_min, np.array([chosen_theta]), valleys
        )

    if not candidates:
        # Completely blocked in the front FOV.
        chosen_theta = 0.0
        action = "blocked"
        clearance = corridor_clearance(0.0, thetas, col_min, math.radians(5.0))
        fwd = -params.backup_speed
        return _build_output(
            chosen_theta, fwd, clearance, body_heading, gh, theta_goal,
            action, True, thetas, col_min, np.array([]), valleys
        )

    # VFH+ cost function.
    candidates = np.array(candidates, dtype=float)
    obstacle_densities = np.array([
        _obstacle_density_at(c, centers, hist) for c in candidates
    ])

    J = (
        params.w_goal * np.array([_angular_diff(c, theta_goal) for c in candidates])
        + params.w_current * np.array([_angular_diff(c, 0.0) for c in candidates])
        + params.w_smooth * np.array([_angular_diff(c, last_theta) for c in candidates])
        + params.w_obstacle * obstacle_densities
    )

    # If goal is behind, increase the weight of turning toward it.
    if goal_is_behind:
        J += (
            params.behind_turn_gain
            * params.w_goal
            * np.array([
                _angular_diff(c, np.sign(theta_goal) * math.pi / 2.0)
                for c in candidates
            ])
        )

    best_idx = int(np.argmin(J))
    chosen_theta = float(candidates[best_idx])
    chosen_density = float(obstacle_densities[best_idx])

    half_width = math.radians(params.fov_deg / params.bins * 3.0)
    clearance = corridor_clearance(chosen_theta, thetas, col_min, half_width)
    fwd = speed_from_clearance(clearance, params)

    blocked = chosen_density >= params.threshold_high or clearance <= params.avoid_near
    if blocked and fwd >= 0.0:
        fwd = -params.backup_speed

    if goal_is_behind:
        action = "turn"
        if fwd >= 0.0:
            fwd = min(fwd, params.turn_speed)
    elif blocked:
        action = "backup"
    elif chosen_density < 0.25 and abs(chosen_theta - theta_goal) < 0.2:
        action = "go"
    elif chosen_theta > 0.15:
        action = "avoidL"
    elif chosen_theta < -0.15:
        action = "avoidR"
    else:
        action = "go"

    return _build_output(
        chosen_theta, fwd, clearance, body_heading, gh, theta_goal,
        action, blocked, thetas, col_min, candidates, valleys
    )
