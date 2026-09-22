#!/usr/bin/env python3
"""深度图健康判据的单元测试。

背景：CityPark 里 AirSim 的深度渲染出问题，整幅图恒为常数 1.0。避障逻辑取
每个扇区的最小值，于是前/左/右全等于 1.0，被判成「四面贴脸障碍」，无人机
原地震荡 1446 秒无法移动，最后靠全局任务超时才放弃。

这里钉住两条：
  1. 整幅有效深度近乎常数 == 传感器没产出真实几何
  2. 失效时扇区要报 999（通畅）而不是那个常数（贴脸障碍）

判据本身在 hw_insight.depth_health，是纯函数，不依赖 ROS。
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "ros2_ws"
        / "src"
        / "hw_insight"
    ),
)

from hw_insight.depth_health import (  # noqa: E402
    is_depth_sensor_suspect,
    sector_minima,
)


def _constant(value, h=300, w=400):
    return np.full((h, w), value, dtype=np.float32)


def _realistic(h=300, w=400):
    """透视下的真实地面：下方近、上方远，带一点传感器噪声。"""
    rows = np.arange(h, dtype=np.float32).reshape(-1, 1)
    img = 2.0 + (rows / h) * 20.0
    img = np.repeat(img, w, axis=1)
    rng = np.random.default_rng(0)
    return (img + rng.normal(0, 0.05, img.shape)).astype(np.float32)


def test_constant_depth_is_flagged_as_sensor_failure():
    assert is_depth_sensor_suspect(_constant(1.0)) is True


def test_constant_depth_at_other_values_is_also_flagged():
    """不只针对 1.0 —— 任何整幅常数的深度都说明没有真实几何。"""
    for value in (0.5, 3.0, 12.0):
        assert is_depth_sensor_suspect(_constant(value)) is True, (
            f"常数 {value} 应判为失效"
        )


def test_near_constant_depth_is_flagged():
    """轻微噪声但实质无变化，同样应判失效。"""
    img = _constant(1.0) + np.random.default_rng(1).normal(0, 0.001, (300, 400))
    assert is_depth_sensor_suspect(img.astype(np.float32)) is True


def test_realistic_depth_is_not_flagged():
    assert is_depth_sensor_suspect(_realistic()) is False


def test_no_depth_is_not_flagged_as_suspect():
    """收不到深度是另一条链路的问题（由 depth_ok 管），不该在这里判失效。"""
    assert is_depth_sensor_suspect(None) is False


def test_too_few_valid_pixels_is_not_flagged():
    """样本不足时不下结论，避免误判。"""
    img = _constant(1.0)
    img[:, :] = np.nan
    img[0:5, 0:5] = 1.0          # 只有 25 个有效像素
    assert is_depth_sensor_suspect(img) is False


def test_nan_pixels_do_not_defeat_the_detector():
    """天空像素被 clamp 成 NaN 是常态，不该因此漏判。"""
    img = _constant(1.0)
    img[:150, :] = np.nan        # 上半是天空
    assert is_depth_sensor_suspect(img) is True


def test_sectors_report_clear_when_sensor_failed():
    """失效时报 999（通畅）而非那个常数（贴脸障碍）。

    报常数会让无人机认定被围死、原地不动；报 999 最坏只是盲飞一段。
    """
    assert sector_minima(_constant(1.0)) == (999.0, 999.0, 999.0)


def test_sectors_pass_through_when_sensor_healthy():
    dc, dl, dr = sector_minima(_realistic())
    assert dc < 999.0 and dl < 999.0 and dr < 999.0


def test_sectors_use_the_nearest_obstacle_in_each_band():
    """健康数据下仍应取每个扇区的最小值（即最近障碍）。"""
    img = _constant(8.0)
    img[200:260, 140:260] = 2.5      # 正前方近处放一堵墙
    # 加噪声让它不被判为失效
    img += np.random.default_rng(2).normal(0, 0.3, img.shape).astype(np.float32)
    dc, _dl, _dr = sector_minima(img)
    assert dc < 3.5, f"正前方应测到近障碍，实际 {dc}"


def test_sectors_report_clear_when_no_depth():
    assert sector_minima(None) == (999.0, 999.0, 999.0)
