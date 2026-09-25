"""Project 2D detections into PX4 local NED and merge observations."""

from __future__ import annotations

import math

import numpy as np

try:  # imported as ``scripts.semantic_geometry``
    from scripts.uav_semantic_schema import max_half_extent_m
except ImportError:  # run with ``scripts/`` on sys.path
    from uav_semantic_schema import max_half_extent_m


def rotate_by_quaternion(vector, quaternion):
    """Rotate xyz by an AirSim quaternion supplied as (w, x, y, z)."""
    vx, vy, vz = (float(value) for value in vector)
    w, x, y, z = (float(value) for value in quaternion)
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if norm <= 1e-9:
        return vx, vy, vz
    w, x, y, z = w / norm, x / norm, y / norm, z / norm
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def project_box_extent_ned(box, depth_m: float | None, image_shape,
                           horizontal_fov_deg: float):
    """框在世界系下的半宽、半高（米）。

    小孔成像：世界尺寸 = 深度 × 像素尺寸 / 焦距。框的横向边大致对应水平宽度、
    纵向边大致对应竖直高度（相机滚转≈0 时成立）。深度方向的厚度单目不可观测，
    不在这里给 —— 调用方用一个下限兜底即可。

    为什么需要：只给一个中心点时，语义标注只能撒一个球，标出来的是团块而不是
    物体本身的形状。实测上这会同时压垮两条验收判据 —— 建筑的立面方差（球给不出
    竖直墙面）和围栏的直线拟合残差（残差被球半径撑大）。给出宽高之后，落在物体
    自己盒子里的点才谈得上「是这个物体」。
    """
    depth = float(depth_m) if depth_m is not None else 0.0
    if not math.isfinite(depth) or depth <= 0.0:
        return None
    height, width = image_shape[:2]
    if width <= 0 or height <= 0 or not 1.0 < horizontal_fov_deg < 179.0:
        return None
    focal = width / (2.0 * math.tan(math.radians(horizontal_fov_deg) * 0.5))
    half_width = depth * abs(float(box[2]) - float(box[0])) * 0.5 / focal
    half_height = depth * abs(float(box[3]) - float(box[1])) * 0.5 / focal
    if not (math.isfinite(half_width) and math.isfinite(half_height)):
        return None
    return half_width, half_height


def project_box_center_ned(
    box, depth_m: float | None, image_shape, horizontal_fov_deg: float,
    camera_position, camera_quaternion,
):
    """Estimate a box centroid in world NED using perspective-ray depth."""
    depth = float(depth_m) if depth_m is not None else 0.0
    if not math.isfinite(depth) or depth <= 0.0:
        return None
    height, width = image_shape[:2]
    if width <= 0 or height <= 0 or not 1.0 < horizontal_fov_deg < 179.0:
        return None
    pose = tuple(float(value) for value in (*camera_position, *camera_quaternion))
    if len(pose) != 7 or not all(math.isfinite(value) for value in pose):
        return None
    center_x = (float(box[0]) + float(box[2])) * 0.5
    center_y = (float(box[1]) + float(box[3])) * 0.5
    focal = width / (2.0 * math.tan(math.radians(horizontal_fov_deg) * 0.5))
    ray = (1.0, (center_x - width * 0.5) / focal,
           (center_y - height * 0.5) / focal)
    ray_norm = math.sqrt(sum(value * value for value in ray))
    camera_point = tuple(depth * value / ray_norm for value in ray)
    world_delta = rotate_by_quaternion(camera_point, pose[3:])
    return tuple(
        round(pose[index] + world_delta[index], 3)
        for index in range(3)
    )


class SemanticObjectTracker:
    """Merge repeated same-class 3D observations into stable map objects."""

    # How many past observations to keep per object.  The acceptance criteria
    # ask for centroid drift across consecutive observations, which is not
    # recoverable from a running average, so the trail is kept explicitly.
    TRAIL_LIMIT = 32

    DEFAULT_MERGE_DISTANCE = 2.0

    # 半宽/半高的下限（米）。远处物体框很小，换算出来的尺寸会趋近 0，
    # 那样一个点都标不到。给个下限保证每个对象至少有自己的小块。
    MIN_HALF_WIDTH_M = 1.0
    MIN_HALF_HEIGHT_M = 1.0

    # 参与中位数的近期样本数。太小则压不住离群，太大则跟不上物体真实的
    # 视角变化（走近时框会变大，那是真信息）。
    EXTENT_SAMPLES = 6

    # How far a detection may sit from an object's centre and still be merged
    # into it.  4.0m was loose enough that one bad box could drag a sparsely
    # observed object: measured on the 2026-09-24 run a building seen 5 times
    # moved 6.2m in a single step, which at weight 1/5 still shifts the centre
    # by 1.2m -- past the 1.0m drift the map is held to.  Halving the gate
    # halves that worst case, at the cost of splitting genuinely close
    # objects; re-tune it against the per-class counts if that shows up.
    def __init__(self, merge_distance: float = DEFAULT_MERGE_DISTANCE) -> None:
        if merge_distance <= 0.0:
            raise ValueError("merge distance must be positive")
        self.merge_distance = float(merge_distance)
        self.objects: list[dict] = []
        self.sequence = 0

    @staticmethod
    def _append_trail(item: dict, seen_at: float) -> None:
        """Record the *tracked* centroid, not the raw detection.

        The acceptance criterion is about how far an object's centroid wanders
        between observations.  Storing the raw per-frame estimate instead made
        the figure meaningless: one bad box projecting 6m off dragged the
        recorded position with it, and the criterion then measured the
        detector's noise rather than the tracker's stability -- which is what
        it is supposed to bound.
        """
        trail = item.setdefault("trail", [])
        trail.append({
            "seen_at": float(seen_at),
            "position_ned": [float(value) for value in item["position_ned"]],
        })
        if len(trail) > SemanticObjectTracker.TRAIL_LIMIT:
            del trail[:-SemanticObjectTracker.TRAIL_LIMIT]

    def update(self, detections, seen_at: float) -> None:
        for detection in detections:
            position = getattr(detection, "world_ned", None)
            if position is None:
                continue
            half_width, half_height = self._observed_extent(detection)
            matched = self._nearest(detection.label, position)
            if matched is None:
                self.sequence += 1
                self.objects.append({
                    "id": f"{detection.label}-{self.sequence:03d}",
                    "label": detection.label,
                    "position_ned": [float(value) for value in position],
                    "half_width": half_width,
                    "half_height": half_height,
                    "extent_samples": [[half_width, half_height]],
                    "observations": 1,
                    "max_confidence": float(detection.confidence),
                    "last_seen": float(seen_at),
                    "approximate": True,
                    "trail": [],
                })
                self._append_trail(self.objects[-1], seen_at)
                continue
            count = int(matched["observations"]) + 1
            weight = 1.0 / min(count, 12)
            matched["position_ned"] = [
                (1.0 - weight) * old + weight * float(new)
                for old, new in zip(matched["position_ned"], position)
            ]
            self._fold_extent(matched, half_width, half_height)
            matched["observations"] = count
            matched["max_confidence"] = max(
                float(matched["max_confidence"]), float(detection.confidence)
            )
            matched["last_seen"] = float(seen_at)
            self._append_trail(matched, seen_at)

    @classmethod
    def _fold_extent(cls, item, half_width, half_height) -> None:
        """把一次观测的尺寸并进物体，取近期样本的**中位数**并压到类别上限内。

        原来取的是见过的最大值，理由是「框被画面边缘裁掉时会显得更小」。但反过来
        的错更贵：远处或框偏大的单次观测会把物体永久撑大。2026-09-25 实测，取最大值
        时 tree 的半宽中位数 13.6m、最大 58.5m，551 个树盒子盖满整张图、标注率
        99.2% —— 判据全过，但那不是地图。
        中位数对这两种误差都稳健；上限则挡住数量级错误（见 uav_semantic_schema）。
        """
        samples = item.setdefault("extent_samples", [])
        samples.append([float(half_width), float(half_height)])
        if len(samples) > cls.EXTENT_SAMPLES:
            del samples[:-cls.EXTENT_SAMPLES]
        cap = max_half_extent_m(item.get("label"))
        item["half_width"] = min(
            float(np.median([s[0] for s in samples])), cap)
        item["half_height"] = min(
            float(np.median([s[1] for s in samples])), cap)

    @classmethod
    def _observed_extent(cls, detection):
        """观测到的半宽/半高，压到 [下限, 类别上限] 区间内。

        **上限必须在这里也生效**，不能只放在合并路径里。实测（2026-09-25 第三轮）
        每个对象的观测次数中位数是 1 —— 大多数检测是单次观测，永远走不到合并分支。
        当时上限只写在 _fold_extent 里，于是 tree 的半宽中位数是 13.3m（上限 7m 形同
        虚设），630 个树盒子铺出 84 万平方米，标注率 97.2%，判据再次被"涂满"骗过。
        """
        label = getattr(detection, "label", None)
        cap = max_half_extent_m(label) if isinstance(label, str) else None
        extent = getattr(detection, "extent_ned", None)
        if not extent:
            return cls.MIN_HALF_WIDTH_M, cls.MIN_HALF_HEIGHT_M
        half_width, half_height = (float(value) for value in extent)
        half_width = max(half_width, cls.MIN_HALF_WIDTH_M)
        half_height = max(half_height, cls.MIN_HALF_HEIGHT_M)
        if cap is not None:
            half_width = min(half_width, cap)
            half_height = min(half_height, cap)
        return half_width, half_height

    def _nearest(self, label: str, position):
        candidates = []
        for item in self.objects:
            if item["label"] != label:
                continue
            distance = math.dist(item["position_ned"], position)
            if distance <= self.merge_distance:
                candidates.append((distance, item))
        return min(candidates, key=lambda value: value[0])[1] if candidates else None

    def snapshot(self) -> list[dict]:
        result = []
        for item in self.objects:
            value = dict(item)
            value["position_ned"] = [
                round(float(position), 3) for position in item["position_ned"]
            ]
            value["max_confidence"] = round(float(item["max_confidence"]), 6)
            result.append(value)
        return result
