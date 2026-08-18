"""Project 2D detections into PX4 local NED and merge observations."""

from __future__ import annotations

import math


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

    def __init__(self, merge_distance: float = 4.0) -> None:
        if merge_distance <= 0.0:
            raise ValueError("merge distance must be positive")
        self.merge_distance = float(merge_distance)
        self.objects: list[dict] = []
        self.sequence = 0

    def update(self, detections, seen_at: float) -> None:
        for detection in detections:
            position = getattr(detection, "world_ned", None)
            if position is None:
                continue
            matched = self._nearest(detection.label, position)
            if matched is None:
                self.sequence += 1
                self.objects.append({
                    "id": f"{detection.label}-{self.sequence:03d}",
                    "label": detection.label,
                    "position_ned": [float(value) for value in position],
                    "observations": 1,
                    "max_confidence": float(detection.confidence),
                    "last_seen": float(seen_at),
                    "approximate": True,
                })
                continue
            count = int(matched["observations"]) + 1
            weight = 1.0 / min(count, 12)
            matched["position_ned"] = [
                (1.0 - weight) * old + weight * float(new)
                for old, new in zip(matched["position_ned"], position)
            ]
            matched["observations"] = count
            matched["max_confidence"] = max(
                float(matched["max_confidence"]), float(detection.confidence)
            )
            matched["last_seen"] = float(seen_at)

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
