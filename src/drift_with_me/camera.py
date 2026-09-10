from __future__ import annotations

import math
from dataclasses import dataclass

from drift_with_me.math3d import CameraState, Vec2, Vec3, normalize2
from drift_with_me.world import CameraCue, CameraSequence, CameraZone, StaticObject, WorldData


@dataclass(frozen=True)
class CameraShot:
    target: Vec3
    yaw_deg: float
    pitch_deg: float
    zoom: float
    anchor_x: float
    anchor_y: float


@dataclass
class CameraBlend:
    origin: CameraShot
    duration: float
    elapsed: float = 0.0


@dataclass
class SequenceRuntime:
    sequence: CameraSequence
    index: int = 0
    phase: str = "blend"
    elapsed: float = 0.0
    origin: CameraShot | None = None
    target: CameraShot | None = None


@dataclass
class FocusRuntime:
    target_object: StaticObject
    hold_sec: float
    phase: str = "blend_in"
    elapsed: float = 0.0
    origin: CameraShot | None = None
    target: CameraShot | None = None


class CameraController:
    def __init__(
        self,
        raw_config: dict,
        world: WorldData,
        viewport_width: int,
        viewport_height: int,
        initial_target: Vec3,
    ) -> None:
        self.raw_config = raw_config
        self.world = world
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.camera_config = raw_config["camera"]
        self.follow_target = Vec3(initial_target.x, 0.0, initial_target.z)
        self.active_zone_id: str | None = None
        self.base_blend: CameraBlend | None = None
        self.sequence: SequenceRuntime | None = None
        self.focus: FocusRuntime | None = None
        self.current = self.to_camera_state(self.follow_shot())

    @property
    def freezes_world(self) -> bool:
        if self.focus is not None:
            return True
        if self.sequence is not None:
            return self.sequence.sequence.freeze_world
        return False

    @property
    def mode_name(self) -> str:
        if self.focus is not None:
            return "FOCUS"
        if self.sequence is not None:
            return "EVENT_PAN"
        if self.active_zone_id is not None:
            return "OVERVIEW"
        return "FOLLOW"

    def reset(self, target: Vec3) -> None:
        self.follow_target = Vec3(target.x, 0.0, target.z)
        self.active_zone_id = None
        self.base_blend = None
        self.sequence = None
        self.focus = None
        self.current = self.to_camera_state(self.follow_shot())

    def update(self, dt: float, player_x: float, player_z: float) -> CameraState:
        dt = max(0.0, dt)
        self.update_follow_target(dt, player_x, player_z)
        base = self.resolve_base_shot(player_x, player_z)

        if self.focus is not None:
            shot = self.update_focus(dt, base, player_x, player_z)
        elif self.sequence is not None:
            shot = self.update_sequence(dt, base)
        elif self.base_blend is not None:
            shot = self.update_base_blend(dt, base)
        else:
            shot = base

        self.current = self.to_camera_state(shot)
        return self.current

    def start_pan_demo(self) -> bool:
        sequence = self.world.camera_sequences.get("pan_demo")
        if sequence is None:
            return False
        self.sequence = SequenceRuntime(sequence=sequence)
        self.focus = None
        return True

    def start_focus_demo(self, target_object: StaticObject, hold_sec: float = 1.0) -> None:
        self.focus = FocusRuntime(target_object=target_object, hold_sec=hold_sec)
        self.sequence = None

    def follow_shot(self) -> CameraShot:
        camera = self.camera_config
        return CameraShot(
            target=self.follow_target,
            yaw_deg=float(camera["yaw_deg"]),
            pitch_deg=float(camera["pitch_deg"]),
            zoom=1.0,
            anchor_x=float(camera["screen_anchor"][0]),
            anchor_y=float(camera["screen_anchor"][1]),
        )

    def zone_shot(self, zone: CameraZone) -> CameraShot:
        camera = self.camera_config
        return CameraShot(
            target=zone.target,
            yaw_deg=zone.yaw_deg if zone.yaw_deg is not None else float(camera["yaw_deg"]),
            pitch_deg=zone.pitch_deg if zone.pitch_deg is not None else float(camera["pitch_deg"]),
            zoom=zone.zoom,
            anchor_x=float(camera["screen_anchor"][0]),
            anchor_y=float(camera["screen_anchor"][1]),
        )

    def resolve_base_shot(self, player_x: float, player_z: float) -> CameraShot:
        previous_zone_id = self.active_zone_id
        self.active_zone_id = self.resolve_active_zone_id(player_x, player_z)
        if previous_zone_id != self.active_zone_id:
            duration = self.base_transition_sec(previous_zone_id, self.active_zone_id)
            self.base_blend = CameraBlend(
                origin=self.from_camera_state(self.current), duration=duration
            )

        if self.active_zone_id is None:
            return self.follow_shot()
        return self.zone_shot(self.world.camera_zones[self.active_zone_id])

    def resolve_active_zone_id(self, player_x: float, player_z: float) -> str | None:
        if self.active_zone_id is not None:
            active = self.world.camera_zones.get(self.active_zone_id)
            if active is not None and active.contains_with_margin(player_x, player_z):
                return active.id

        candidates = [
            zone for zone in self.world.camera_zones.values() if zone.contains(player_x, player_z)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda zone: (-zone.priority, zone.id))
        return candidates[0].id

    def base_transition_sec(self, previous_id: str | None, next_id: str | None) -> float:
        if next_id is not None:
            return self.world.camera_zones[next_id].enter_sec
        if previous_id is not None:
            return self.world.camera_zones[previous_id].leave_sec
        return float(self.camera_config["default_blend_sec"])

    def update_follow_target(self, dt: float, player_x: float, player_z: float) -> None:
        follow = self.follow_shot()
        camera = self.to_camera_state(follow)
        player = camera.project(Vec3(player_x, 0.0, player_z))
        if player is None:
            self.follow_target = Vec3(player_x, 0.0, player_z)
            return

        deadzone_w = float(self.camera_config["deadzone_size_fraction"][0]) * self.viewport_width
        deadzone_h = float(self.camera_config["deadzone_size_fraction"][1]) * self.viewport_height
        center_x = camera.anchor_x * self.viewport_width
        center_y = camera.anchor_y * self.viewport_height
        clamped_x = min(max(player.x, center_x - deadzone_w / 2.0), center_x + deadzone_w / 2.0)
        clamped_y = min(max(player.y, center_y - deadzone_h / 2.0), center_y + deadzone_h / 2.0)
        error_x = player.x - clamped_x
        error_y = player.y - clamped_y
        if abs(error_x) <= 1e-6 and abs(error_y) <= 1e-6:
            return

        delta = screen_delta_to_world_delta(camera, player_x, player_z, error_x, error_y)
        if delta.length() <= 1e-6:
            return
        alpha = smoothing_alpha(dt, float(self.camera_config["follow_tau_sec"]))
        next_x = clamp(self.follow_target.x + delta.x * alpha, 0.0, self.world.width)
        next_z = clamp(self.follow_target.z + delta.y * alpha, 0.0, self.world.depth)
        self.follow_target = Vec3(next_x, 0.0, next_z)

    def update_base_blend(self, dt: float, target: CameraShot) -> CameraShot:
        assert self.base_blend is not None
        self.base_blend.elapsed += dt
        if self.base_blend.duration <= 1e-6 or self.base_blend.elapsed >= self.base_blend.duration:
            self.base_blend = None
            return target
        amount = smoothstep(self.base_blend.elapsed / self.base_blend.duration)
        return lerp_shot(self.base_blend.origin, target, amount)

    def update_sequence(self, dt: float, base: CameraShot) -> CameraShot:
        assert self.sequence is not None
        runtime = self.sequence
        if runtime.index >= len(runtime.sequence.cues):
            self.sequence = None
            return base

        cue = runtime.sequence.cues[runtime.index]
        if runtime.target is None:
            runtime.origin = self.from_camera_state(self.current)
            runtime.target = self.resolve_cue_shot(cue, base)
            runtime.elapsed = 0.0
            runtime.phase = "blend"

        assert runtime.origin is not None and runtime.target is not None
        if runtime.phase == "blend":
            runtime.elapsed += dt
            if cue.blend_sec <= 1e-6 or runtime.elapsed >= cue.blend_sec:
                runtime.phase = "hold"
                runtime.elapsed = 0.0
                return runtime.target
            return lerp_shot(
                runtime.origin, runtime.target, smoothstep(runtime.elapsed / cue.blend_sec)
            )

        runtime.elapsed += dt
        if runtime.elapsed >= cue.hold_sec:
            runtime.index += 1
            runtime.target = None
            runtime.origin = None
            runtime.elapsed = 0.0
            if runtime.index >= len(runtime.sequence.cues):
                self.sequence = None
                return base
            return self.from_camera_state(self.current)
        return runtime.target

    def update_focus(
        self, dt: float, base: CameraShot, player_x: float, player_z: float
    ) -> CameraShot:
        assert self.focus is not None
        runtime = self.focus
        if runtime.target is None:
            runtime.origin = self.from_camera_state(self.current)
            runtime.target = self.focus_shot(runtime.target_object, base, player_x, player_z)
            runtime.elapsed = 0.0
            runtime.phase = "blend_in"

        assert runtime.origin is not None and runtime.target is not None
        if runtime.phase == "blend_in":
            blend_sec = float(self.camera_config["focus_blend_sec"])
            runtime.elapsed += dt
            if blend_sec <= 1e-6 or runtime.elapsed >= blend_sec:
                runtime.phase = "hold"
                runtime.elapsed = 0.0
                return runtime.target
            return lerp_shot(
                runtime.origin, runtime.target, smoothstep(runtime.elapsed / blend_sec)
            )

        if runtime.phase == "hold":
            runtime.elapsed += dt
            if runtime.elapsed < runtime.hold_sec:
                return runtime.target
            runtime.origin = self.from_camera_state(self.current)
            runtime.target = base
            runtime.phase = "blend_out"
            runtime.elapsed = 0.0

        blend_sec = float(self.camera_config["return_blend_sec"])
        runtime.elapsed += dt
        if blend_sec <= 1e-6 or runtime.elapsed >= blend_sec:
            self.focus = None
            return base
        return lerp_shot(runtime.origin, base, smoothstep(runtime.elapsed / blend_sec))

    def resolve_cue_shot(self, cue: CameraCue, base: CameraShot) -> CameraShot:
        if cue.resolve_current_base:
            return base
        target = cue.target if cue.target is not None else base.target
        if cue.target_object is not None:
            obj = self.world.object_by_id(cue.target_object)
            if obj is not None:
                target = Vec3(obj.x, obj.height * 0.5, obj.z)
        return CameraShot(
            target=target,
            yaw_deg=cue.yaw_deg if cue.yaw_deg is not None else base.yaw_deg,
            pitch_deg=cue.pitch_deg if cue.pitch_deg is not None else base.pitch_deg,
            zoom=cue.zoom if cue.zoom is not None else base.zoom,
            anchor_x=base.anchor_x,
            anchor_y=base.anchor_y,
        )

    def focus_shot(
        self, target_object: StaticObject, base: CameraShot, player_x: float, player_z: float
    ) -> CameraShot:
        obj_center = Vec3(target_object.x, max(12.0, target_object.height * 0.5), target_object.z)
        player_center = Vec3(
            player_x,
            float(self.raw_config["player"]["cube_size"]) * 0.5,
            player_z,
        )
        target = player_center * 0.35 + obj_center * 0.65
        return CameraShot(
            target=target,
            yaw_deg=base.yaw_deg,
            pitch_deg=base.pitch_deg,
            zoom=float(self.camera_config["zoom_max"]),
            anchor_x=float(self.camera_config["focus_screen_anchor"][0]),
            anchor_y=float(self.camera_config["focus_screen_anchor"][1]),
        )

    def to_camera_state(self, shot: CameraShot) -> CameraState:
        return CameraState(
            target=shot.target,
            yaw_deg=shot.yaw_deg,
            pitch_deg=shot.pitch_deg,
            horizontal_fov_deg=float(self.camera_config["horizontal_fov_deg"]),
            distance=float(self.camera_config["base_distance"])
            / clamp_zoom(self.camera_config, shot.zoom),
            near=float(self.camera_config["near"]),
            far=float(self.camera_config["far"]),
            anchor_x=shot.anchor_x,
            anchor_y=shot.anchor_y,
            viewport_width=self.viewport_width,
            viewport_height=self.viewport_height,
        )

    def from_camera_state(self, camera: CameraState) -> CameraShot:
        return CameraShot(
            target=camera.target,
            yaw_deg=camera.yaw_deg,
            pitch_deg=camera.pitch_deg,
            zoom=float(self.camera_config["base_distance"]) / camera.distance,
            anchor_x=camera.anchor_x,
            anchor_y=camera.anchor_y,
        )


def screen_delta_to_world_delta(
    camera: CameraState, point_x: float, point_z: float, screen_x: float, screen_y: float
) -> Vec2:
    h = 1.0
    px1 = camera.project(Vec3(point_x + h, 0.0, point_z))
    px0 = camera.project(Vec3(point_x - h, 0.0, point_z))
    pz1 = camera.project(Vec3(point_x, 0.0, point_z + h))
    pz0 = camera.project(Vec3(point_x, 0.0, point_z - h))
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
    return Vec2(world_x, world_z)


def lerp_shot(origin: CameraShot, target: CameraShot, amount: float) -> CameraShot:
    amount = clamp(amount, 0.0, 1.0)
    return CameraShot(
        target=lerp_vec3(origin.target, target.target, amount),
        yaw_deg=lerp_angle(origin.yaw_deg, target.yaw_deg, amount),
        pitch_deg=lerp(origin.pitch_deg, target.pitch_deg, amount),
        zoom=lerp(origin.zoom, target.zoom, amount),
        anchor_x=lerp(origin.anchor_x, target.anchor_x, amount),
        anchor_y=lerp(origin.anchor_y, target.anchor_y, amount),
    )


def lerp_vec3(origin: Vec3, target: Vec3, amount: float) -> Vec3:
    return Vec3(
        lerp(origin.x, target.x, amount),
        lerp(origin.y, target.y, amount),
        lerp(origin.z, target.z, amount),
    )


def lerp(origin: float, target: float, amount: float) -> float:
    return origin + (target - origin) * amount


def lerp_angle(origin: float, target: float, amount: float) -> float:
    delta = ((target - origin + 180.0) % 360.0) - 180.0
    return origin + delta * amount


def smoothstep(value: float) -> float:
    value = clamp(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def smoothing_alpha(dt: float, tau: float) -> float:
    if tau <= 1e-6:
        return 1.0
    return 1.0 - math.exp(-max(0.0, dt) / tau)


def camera_ground_axes(camera: CameraState) -> tuple[Vec2, Vec2]:
    _position, forward, right, _up = camera.basis
    screen_right = normalize2(right.x, right.z)
    ground_forward = normalize2(forward.x, forward.z)
    return screen_right, ground_forward


def clamp_zoom(camera_config: dict, zoom: float) -> float:
    return clamp(float(zoom), float(camera_config["zoom_min"]), float(camera_config["zoom_max"]))


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)
