from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

    def length(self) -> float:
        return math.hypot(self.x, self.y)


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)


@dataclass(frozen=True)
class ProjectedPoint:
    x: float
    y: float
    depth: float


@dataclass(frozen=True)
class CameraState:
    target: Vec3
    yaw_deg: float
    pitch_deg: float
    horizontal_fov_deg: float
    distance: float
    near: float
    far: float
    anchor_x: float
    anchor_y: float
    viewport_width: int
    viewport_height: int

    @classmethod
    def from_config(
        cls,
        raw_config: dict,
        target: Vec3,
        viewport_width: int,
        viewport_height: int,
        zoom: float = 1.0,
    ) -> CameraState:
        camera = raw_config["camera"]
        zoom = min(max(zoom, camera["zoom_min"]), camera["zoom_max"])
        return cls(
            target=target,
            yaw_deg=float(camera["yaw_deg"]),
            pitch_deg=float(camera["pitch_deg"]),
            horizontal_fov_deg=float(camera["horizontal_fov_deg"]),
            distance=float(camera["base_distance"]) / zoom,
            near=float(camera["near"]),
            far=float(camera["far"]),
            anchor_x=float(camera["screen_anchor"][0]),
            anchor_y=float(camera["screen_anchor"][1]),
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )

    @property
    def yaw_rad(self) -> float:
        return math.radians(self.yaw_deg)

    @property
    def pitch_rad(self) -> float:
        return math.radians(self.pitch_deg)

    @property
    def basis(self) -> tuple[Vec3, Vec3, Vec3, Vec3]:
        yaw = self.yaw_rad
        pitch = self.pitch_rad
        forward = Vec3(
            math.cos(pitch) * math.sin(yaw), -math.sin(pitch), math.cos(pitch) * math.cos(yaw)
        )
        right = Vec3(math.cos(yaw), 0.0, -math.sin(yaw))
        up = Vec3(math.sin(pitch) * math.sin(yaw), math.cos(pitch), math.sin(pitch) * math.cos(yaw))
        camera_position = self.target - forward * self.distance
        return camera_position, forward, right, up

    def project(self, point: Vec3) -> ProjectedPoint | None:
        camera_position, forward, right, up = self.basis
        view = point - camera_position
        r = dot(view, right)
        u = dot(view, up)
        depth = dot(view, forward)
        if depth < self.near or depth > self.far or not math.isfinite(depth):
            return None

        f = self.viewport_width / (2.0 * math.tan(math.radians(self.horizontal_fov_deg) / 2.0))
        x = self.anchor_x * self.viewport_width + f * r / depth
        y = self.anchor_y * self.viewport_height - f * u / depth
        if not math.isfinite(x) or not math.isfinite(y):
            return None
        return ProjectedPoint(x, y, depth)


def dot(a: Vec3, b: Vec3) -> float:
    return a.x * b.x + a.y * b.y + a.z * b.z


def normalize2(x: float, y: float) -> Vec2:
    length = math.hypot(x, y)
    if length <= 1e-9:
        return Vec2(0.0, 0.0)
    return Vec2(x / length, y / length)


def screen_to_world_direction(
    camera: CameraState,
    point_x: float,
    point_z: float,
    screen_x: float,
    screen_y: float,
) -> Vec2:
    if abs(screen_x) <= 1e-9 and abs(screen_y) <= 1e-9:
        return Vec2(0.0, 0.0)

    h = 1.0
    base_y = 0.0
    px1 = camera.project(Vec3(point_x + h, base_y, point_z))
    px0 = camera.project(Vec3(point_x - h, base_y, point_z))
    pz1 = camera.project(Vec3(point_x, base_y, point_z + h))
    pz0 = camera.project(Vec3(point_x, base_y, point_z - h))
    if px1 is None or px0 is None or pz1 is None or pz0 is None:
        return Vec2(0.0, 0.0)

    j00 = (px1.x - px0.x) / (2.0 * h)
    j10 = (px1.y - px0.y) / (2.0 * h)
    j01 = (pz1.x - pz0.x) / (2.0 * h)
    j11 = (pz1.y - pz0.y) / (2.0 * h)
    det = j00 * j11 - j01 * j10
    if abs(det) <= 1e-9 or not math.isfinite(det):
        return Vec2(0.0, 0.0)

    world_x = (j11 * screen_x - j01 * screen_y) / det
    world_z = (-j10 * screen_x + j00 * screen_y) / det
    return normalize2(world_x, world_z)
