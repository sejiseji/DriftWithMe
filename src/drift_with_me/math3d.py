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
class AffineProjectionProfile:
    profile_id: str
    basis_x: Vec2
    basis_y: Vec2
    basis_z: Vec2
    fixed_forward: Vec3
    reference_viewport_width: int
    reference_viewport_height: int
    reference_depth: float
    ground_epsilon: float = 1e-9

    @classmethod
    def from_config(cls, raw_config: dict) -> AffineProjectionProfile:
        projection = raw_config.get("projection", {})
        affine = projection.get("affine", {})
        viewport = affine.get("reference_viewport", [512, 236])
        return cls(
            profile_id=str(affine.get("profile_id", "follow_spawn_medium_v1")),
            basis_x=vec2_from_sequence(affine["basis_x"]),
            basis_y=vec2_from_sequence(affine["basis_y"]),
            basis_z=vec2_from_sequence(affine["basis_z"]),
            fixed_forward=vec3_from_sequence(affine["fixed_forward"]),
            reference_viewport_width=int(viewport[0]),
            reference_viewport_height=int(viewport[1]),
            reference_depth=float(
                affine.get("reference_depth", raw_config["camera"]["base_distance"])
            ),
            ground_epsilon=float(affine.get("ground_epsilon", 1e-9)),
        )

    @property
    def ground_determinant(self) -> float:
        return self.basis_x.x * self.basis_z.y - self.basis_z.x * self.basis_x.y

    def viewport_scale(self, viewport_width: int) -> float:
        if self.reference_viewport_width <= 0:
            return 1.0
        return viewport_width / float(self.reference_viewport_width)


@dataclass(frozen=True)
class AffineCameraState:
    target: Vec3
    profile: AffineProjectionProfile
    zoom: float
    anchor_x: float
    anchor_y: float
    viewport_width: int
    viewport_height: int
    fx_offset_x: float = 0.0
    fx_offset_y: float = 0.0
    yaw_deg: float = 20.0
    pitch_deg: float = 25.0
    horizontal_fov_deg: float = 38.0
    distance: float = 480.0
    near: float = 8.0
    far: float = 1800.0
    projection_kind: str = "affine"

    @property
    def effective_scale(self) -> float:
        return self.profile.viewport_scale(self.viewport_width) * self.zoom

    def project(self, point: Vec3) -> ProjectedPoint | None:
        return project_affine(self, point)


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


def vec2_from_sequence(value: object) -> Vec2:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"expected 2-number sequence, got {value!r}")
    x = float(value[0])
    y = float(value[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError(f"expected finite Vec2 values, got {value!r}")
    return Vec2(x, y)


def vec3_from_sequence(value: object) -> Vec3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"expected 3-number sequence, got {value!r}")
    x = float(value[0])
    y = float(value[1])
    z = float(value[2])
    if not math.isfinite(x) or not math.isfinite(y) or not math.isfinite(z):
        raise ValueError(f"expected finite Vec3 values, got {value!r}")
    return Vec3(x, y, z)


def affine_camera_from_perspective(
    camera: CameraState,
    profile: AffineProjectionProfile,
    *,
    base_distance: float,
    fx_offset_x: float = 0.0,
    fx_offset_y: float = 0.0,
) -> AffineCameraState:
    if camera.distance <= 1e-9 or not math.isfinite(camera.distance):
        zoom = 1.0
    else:
        zoom = base_distance / camera.distance
    yaw_deg, pitch_deg = yaw_pitch_from_forward(profile.fixed_forward)
    return AffineCameraState(
        target=camera.target,
        profile=profile,
        zoom=zoom,
        anchor_x=camera.anchor_x,
        anchor_y=camera.anchor_y,
        viewport_width=camera.viewport_width,
        viewport_height=camera.viewport_height,
        fx_offset_x=fx_offset_x,
        fx_offset_y=fx_offset_y,
        yaw_deg=yaw_deg,
        pitch_deg=pitch_deg,
        horizontal_fov_deg=camera.horizontal_fov_deg,
        distance=camera.distance,
        near=camera.near,
        far=camera.far,
    )


def yaw_pitch_from_forward(forward: Vec3) -> tuple[float, float]:
    length = math.sqrt(forward.x * forward.x + forward.y * forward.y + forward.z * forward.z)
    if length <= 1e-9 or not math.isfinite(length):
        return 0.0, 0.0
    x = forward.x / length
    y = forward.y / length
    z = forward.z / length
    yaw_deg = math.degrees(math.atan2(x, z))
    pitch_deg = math.degrees(math.asin(max(-1.0, min(1.0, -y))))
    return yaw_deg, pitch_deg


def project_affine(camera: AffineCameraState, point: Vec3) -> ProjectedPoint | None:
    dx = point.x - camera.target.x
    dy = point.y - camera.target.y
    dz = point.z - camera.target.z
    scale = camera.effective_scale
    x = (
        camera.anchor_x * camera.viewport_width
        + scale
        * (
            dx * camera.profile.basis_x.x
            + dy * camera.profile.basis_y.x
            + dz * camera.profile.basis_z.x
        )
        + camera.fx_offset_x
    )
    y = (
        camera.anchor_y * camera.viewport_height
        + scale
        * (
            dx * camera.profile.basis_x.y
            + dy * camera.profile.basis_y.y
            + dz * camera.profile.basis_z.y
        )
        + camera.fx_offset_y
    )
    depth = camera.profile.reference_depth + dot(
        point - camera.target, camera.profile.fixed_forward
    )
    if (
        not math.isfinite(x)
        or not math.isfinite(y)
        or not math.isfinite(depth)
        or depth < camera.near
        or depth > camera.far
    ):
        return None
    return ProjectedPoint(x, y, depth)


def screen_to_ground_affine(
    camera: AffineCameraState, screen_x: float, screen_y: float
) -> Vec2 | None:
    scale = camera.effective_scale
    det = camera.profile.ground_determinant
    if (
        abs(scale) <= camera.profile.ground_epsilon
        or abs(det) <= camera.profile.ground_epsilon
        or not math.isfinite(scale)
        or not math.isfinite(det)
    ):
        return None

    y_delta = -camera.target.y
    qx = (
        screen_x
        - camera.anchor_x * camera.viewport_width
        - camera.fx_offset_x
        - scale * y_delta * camera.profile.basis_y.x
    ) / scale
    qy = (
        screen_y
        - camera.anchor_y * camera.viewport_height
        - camera.fx_offset_y
        - scale * y_delta * camera.profile.basis_y.y
    ) / scale
    if not math.isfinite(qx) or not math.isfinite(qy):
        return None

    dx = (camera.profile.basis_z.y * qx - camera.profile.basis_z.x * qy) / det
    dz = (-camera.profile.basis_x.y * qx + camera.profile.basis_x.x * qy) / det
    x = camera.target.x + dx
    z = camera.target.z + dz
    if not math.isfinite(x) or not math.isfinite(z):
        return None
    return Vec2(x, z)


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


def screen_to_ground_point(camera: CameraState, screen_x: float, screen_y: float) -> Vec2 | None:
    camera_position, forward, right, up = camera.basis
    f = camera.viewport_width / (2.0 * math.tan(math.radians(camera.horizontal_fov_deg) / 2.0))
    if not math.isfinite(f) or abs(f) <= 1e-9:
        return None

    ray = (
        forward
        + right * ((screen_x - camera.anchor_x * camera.viewport_width) / f)
        + up * ((camera.anchor_y * camera.viewport_height - screen_y) / f)
    )
    if not math.isfinite(ray.y) or abs(ray.y) <= 1e-9:
        return None

    t = -camera_position.y / ray.y
    if not math.isfinite(t) or t <= 0.0:
        return None

    point = camera_position + ray * t
    view = point - camera_position
    depth = dot(view, forward)
    if depth < camera.near or depth > camera.far or not math.isfinite(depth):
        return None
    if not math.isfinite(point.x) or not math.isfinite(point.z):
        return None
    return Vec2(point.x, point.z)
