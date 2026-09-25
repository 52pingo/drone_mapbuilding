"""把地面从深度图里摘出去，让避障只在真正的障碍物里找山谷。

为什么需要：VFH 的输入是「每个方向多远有东西」，而地面上的一块回波和一个树干
在它眼里没有区别。俯角固定、离地高度已知时，画面每一行对应的**地面斜距是可以算
出来的**：行 v 的仰角 e(v) = pitch + (H/2 - v) * fov_v / H，地面在那条射线上出现
的距离就是 h / sin(-e)。比这个距离明显更近的东西才可能是障碍。

实测依据（2026-09-25，同航线同 900 秒预算的三次飞行）：

    pitch -40，无滞回        recover 34.8%   go  8.7%   最远 253 m
    pitch -40，有滞回        recover  2.1%   go 79.6%   最远 762 m
    pitch -20，有滞回        recover 73.8%   go 14.0%   最远 391 m   ← 更差

第三行本是「把视线抬起来好看清同高度的树」，结果明显更差。原因是地面落在前方
9.8~20 m、几乎填满整个避障带，极坐标直方图把它读成「各方向都有障碍」，反而找不到
山谷。所以调俯角是两头堵：抬起来撞「地面墙」，压下去对同高度障碍迟钝。

真正的解法是让避障知道地面不是障碍物 —— 那之后再回头看俯角，前向可见性才有意义。

本模块不依赖 ROS，便于单测。坐标约定：图像行 0 在顶部，仰角正表示朝上。
"""

from __future__ import annotations

import math

import numpy as np


# 低于地平线多少度以内的行不参与高度估计：那里地面斜距对高度极其敏感
# （r = h/sin(-e)，e 趋近 0 时 r 发散），一点点噪声就会把 h 估飞。
ALTITUDE_MIN_DEPRESSION_DEG = 25.0

# 高度估计至少要这么多有效像素，否则认为这一帧不足以下结论。
ALTITUDE_MIN_SAMPLES = 200

# 高度估计的合理区间（米）。超出就认为估计失败，本帧不做滤除。
ALTITUDE_MIN_M = 0.5
ALTITUDE_MAX_M = 120.0


def vertical_fov_deg(width: int, height: int, horizontal_fov_deg: float) -> float:
    """由水平 FOV 和图像尺寸推垂直 FOV（方形像素）。"""
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    half = math.tan(math.radians(horizontal_fov_deg) * 0.5) * (float(height) / float(width))
    return 2.0 * math.degrees(math.atan(half))


def row_elevations_deg(height: int, fov_v_deg: float, pitch_deg: float) -> np.ndarray:
    """每行相对水平面的仰角，单位度，正数朝上。行 0 在画面顶部。"""
    rows = np.arange(height, dtype=np.float64)
    return pitch_deg + (height * 0.5 - rows) * (fov_v_deg / float(height))


def estimate_altitude(
    depth: np.ndarray,
    fov_v_deg: float,
    pitch_deg: float,
    min_depression_deg: float = ALTITUDE_MIN_DEPRESSION_DEG,
) -> float | None:
    """从画面下方的地面回波反推离地高度。

    对每个有效像素，它若是地面，则 h = d * sin(-e(row))。对足够靠下的行取中位数，
    地形起伏和个别障碍物都被中位数吸收。返回 None 表示这一帧不足以估计。

    用图像自标定而不是直接取 PX4 的 z：z 是相对起飞参考面的，而这里要的是离地
    高度，两者在地形起伏的园区里能差几十米。
    """
    if depth is None or depth.size == 0:
        return None
    rows = np.arange(depth.shape[0], dtype=np.float64)
    elevations = pitch_deg + (depth.shape[0] * 0.5 - rows) * (
        fov_v_deg / float(depth.shape[0]))
    usable = elevations <= -min_depression_deg
    if not usable.any():
        return None
    band = depth[usable]
    sines = -np.sin(np.radians(elevations[usable]))
    finite = np.isfinite(band)
    if int(finite.sum()) < ALTITUDE_MIN_SAMPLES:
        return None
    # 若该像素是地面，则 h = d * sin(-e)。中位数吸收地形起伏与个别障碍物。
    per_pixel_sine = np.broadcast_to(sines[:, None], band.shape)
    heights = band[finite] * per_pixel_sine[finite]
    altitude = float(np.median(heights))
    if not math.isfinite(altitude) or not (
            ALTITUDE_MIN_M <= altitude <= ALTITUDE_MAX_M):
        return None
    return altitude


def expected_ground_depth(
    height: int,
    fov_v_deg: float,
    pitch_deg: float,
    altitude_m: float,
) -> np.ndarray:
    """每行地面应有的斜距；地平线及其以上的行是 NaN（那条射线上没有地面）。"""
    elevations = row_elevations_deg(height, fov_v_deg, pitch_deg)
    with np.errstate(divide="ignore", invalid="ignore"):
        depth = altitude_m / np.sin(np.radians(-elevations))
    return np.where(elevations < 0.0, depth, np.nan)


def strip_ground(
    depth: np.ndarray,
    fov_v_deg: float,
    pitch_deg: float,
    altitude_m: float | None = None,
    margin_ratio: float = 0.15,
) -> np.ndarray:
    """把判为地面的像素置为 NaN，只留下可能是障碍物的回波。

    判据：一行里深度**明显小于**该行地面应有斜距的像素才保留。
      - 障碍物从地面上立起来，那条射线上它一定比地面更近。
      - 地平线以上的行不可能是地面，全部保留 —— 树冠顶端就在那里。
      - 比地面还远的像素物理上不存在（射线已经打到地面了），按地面丢掉。

    ``altitude_m`` 为 None 时先用图像自标定估一个；估不出来就原样返回，
    宁可不滤也不能把真障碍物当成地面丢掉。
    """
    if depth is None or depth.size == 0:
        return depth
    altitude = altitude_m
    if altitude is None:
        altitude = estimate_altitude(depth, fov_v_deg, pitch_deg)
    if altitude is None:
        return depth

    expected = expected_ground_depth(depth.shape[0], fov_v_deg, pitch_deg, altitude)
    # 判为地面要同时满足两条：这一行确实存在「地面斜距」，且像素不比自己行的地面
    # 更近。写成「先算 is_ground 再置 NaN」而不是「离得近就保留」,是因为后者在
    # 地平线以上的行会踩空：那里 expected 是 NaN，任何比较都是 False，于是树冠
    # 顶端会被当成「不是障碍」删掉 —— 正是最不该删的那一类像素。
    has_ground = np.isfinite(expected)[:, None]
    at_ground_range = depth >= (expected[:, None] * (1.0 - margin_ratio))
    is_ground = has_ground & at_ground_range
    return np.where(is_ground, np.nan, depth)
