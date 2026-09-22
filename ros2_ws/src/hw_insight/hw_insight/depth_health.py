"""深度图健康判据。纯函数，不依赖 ROS，便于单测。

存在的理由：CityPark 里 AirSim 的深度渲染出问题，整幅图恒为常数 1.0。
避障逻辑取每个扇区的最小值，于是前/左/右全等于 1.0，被判成「四面贴脸障碍」，
无人机原地震荡 1446 秒无法移动，最后靠全局任务超时才放弃。

真实深度图不可能整幅常数：透视下不同像素对应不同距离，而且真实传感器有噪声。
所以「整幅有效深度近乎常数」是传感器没有产出真实几何的可靠信号。
"""

from __future__ import annotations

import numpy as np


# 有效深度的标准差低于这个值就认为整幅图没有变化（单位：米）。
# 真实场景下这个量级是米级的，常数图会是 0。
CONSTANT_STD_THRESHOLD = 0.01

# 有效像素太少时不做判断，避免样本不足导致误判
MIN_VALID_PIXELS = 200

# 只看画面中间这一段。上下边缘常有天空/地面极值，会掩盖「整幅常数」这一特征。
ROI_TOP_FRACTION = 0.20
ROI_BOTTOM_FRACTION = 0.80


def valid_region(depth: np.ndarray) -> np.ndarray:
    """取画面中间带的有限值像素。"""
    h = depth.shape[0]
    band = depth[int(h * ROI_TOP_FRACTION):int(h * ROI_BOTTOM_FRACTION)]
    return band[np.isfinite(band)]


def is_depth_sensor_suspect(depth: np.ndarray | None) -> bool:
    """整幅有效深度近乎常数则判为传感器失效。

    注意这不是「前方有一堵平墙」——真有一堵平墙时，透视仍会让不同像素
    对应略微不同的距离，且会有传感器噪声。整幅完全一致只可能出在渲染
    或传输环节。

    收不到深度（depth 为 None）不算失效，那是另一条链路的问题，
    由调用方的 depth_ok 判断。
    """
    if depth is None:
        return False
    valid = valid_region(depth)
    if valid.size < MIN_VALID_PIXELS:
        return False
    return bool(float(valid.std()) < CONSTANT_STD_THRESHOLD)


def sector_minima(
    depth: np.ndarray | None,
) -> tuple[float, float, float]:
    """按前/左/右三个扇区取最小深度。无有效像素时报 999（视为通畅）。

    传感器失效时同样报 999：把「常数距离」当成贴脸障碍会让无人机原地卡死，
    当成通畅最坏只是盲飞一段 —— 后者代价明显更小。
    """
    if depth is None or is_depth_sensor_suspect(depth):
        return 999.0, 999.0, 999.0

    h, w = depth.shape
    band = depth[int(h * ROI_TOP_FRACTION):int(h * ROI_BOTTOM_FRACTION)]

    def mn(x0: int, x1: int) -> float:
        col = band[:, x0:x1]
        v = col[np.isfinite(col)]
        return float(v.min()) if v.size else 999.0

    return (
        mn(int(w * 0.35), int(w * 0.65)),
        mn(0, int(w * 0.30)),
        mn(int(w * 0.70), w),
    )
