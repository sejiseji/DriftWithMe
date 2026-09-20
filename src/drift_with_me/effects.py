from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from drift_with_me.events import GameEvent


@dataclass
class WorldParticle:
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    color: int
    lifetime: float
    age: float = 0.0

    @property
    def progress(self) -> float:
        if self.lifetime <= 1e-6:
            return 1.0
        return max(0.0, min(self.age / self.lifetime, 1.0))


@dataclass
class WorldRing:
    x: float
    z: float
    start_radius: float
    end_radius: float
    color: int
    lifetime: float
    thickness: int = 1
    layer: str = "foreground"
    age: float = 0.0

    @property
    def progress(self) -> float:
        if self.lifetime <= 1e-6:
            return 1.0
        return max(0.0, min(self.age / self.lifetime, 1.0))

    @property
    def radius(self) -> float:
        return self.start_radius + (self.end_radius - self.start_radius) * self.progress


@dataclass
class WorldStroke:
    start_x: float
    start_y: float
    start_z: float
    end_x: float
    end_y: float
    end_z: float
    color: int
    lifetime: float
    layer: str = "foreground"
    age: float = 0.0

    @property
    def progress(self) -> float:
        if self.lifetime <= 1e-6:
            return 1.0
        return max(0.0, min(self.age / self.lifetime, 1.0))


@dataclass
class ActorEmote:
    anchor_kind: str
    anchor_id: str
    fallback_x: float
    fallback_z: float
    symbol: str
    color: int
    lifetime: float
    age: float = 0.0

    @property
    def progress(self) -> float:
        if self.lifetime <= 1e-6:
            return 1.0
        return max(0.0, min(self.age / self.lifetime, 1.0))


@dataclass
class EnemySnapshot:
    enemy_id: str
    enemy_kind: str
    x: float
    z: float
    lifetime: float
    age: float = 0.0

    @property
    def progress(self) -> float:
        if self.lifetime <= 1e-6:
            return 1.0
        return max(0.0, min(self.age / self.lifetime, 1.0))


@dataclass
class ScreenCue:
    kind: str
    lifetime: float
    age: float = 0.0

    @property
    def progress(self) -> float:
        if self.lifetime <= 1e-6:
            return 1.0
        return max(0.0, min(self.age / self.lifetime, 1.0))


@dataclass
class CameraImpulse:
    cue_id: str
    lifetime: float
    delay: float = 0.0
    age: float = 0.0
    shake_amplitude_px: float = 0.0
    shake_duration: float = 0.0
    zoom_peak: float = 0.0
    zoom_attack: float = 0.0
    zoom_hold: float = 0.0
    zoom_return: float = 0.0

    @property
    def local_age(self) -> float:
        return self.age - self.delay

    @property
    def active(self) -> bool:
        return self.local_age >= 0.0 and self.age < self.delay + self.lifetime

    def zoom_envelope(self, age: float) -> float:
        return _zoom_envelope(age, self.zoom_attack, self.zoom_hold, self.zoom_return)

    def shake_amount(self, age: float) -> float:
        return _shake_amount(age, self.shake_amplitude_px, self.shake_duration)

    def shake_offset(self, age: float, amount: float) -> tuple[float, float]:
        return _shake_offset(age, amount)


@dataclass(frozen=True)
class CameraPresentationTransform:
    offset_x: float = 0.0
    offset_y: float = 0.0
    zoom_multiplier: float = 1.0


@dataclass
class ReactiveEnvironmentState:
    object_id: str
    kind: str
    x: float
    z: float
    trigger_radius: float
    visual_radius: float
    strength: float
    direction_x: float
    direction_z: float
    recovery_sec: float
    age: float = 0.0
    phase: str = "PUSH"
    direction: str = "right"
    pose_id: str = "bend_right_1"
    phase_elapsed: float = 0.0
    touching: bool = True
    pending_direction: str | None = None
    push_sec: float = 0.1
    release_hold_sec: float = 0.08
    recover_bend1_sec: float = 0.12
    recover_near_idle_sec: float = 0.24
    redirect_step_sec: float = 0.04

    @property
    def progress(self) -> float:
        if self.phase == "IDLE":
            return 1.0
        if self.phase != "RECOVER":
            return 0.0
        recover_sec = max(1e-6, self.recover_bend1_sec + self.recover_near_idle_sec)
        return max(0.0, min(self.phase_elapsed / recover_sec, 1.0))


def presentation_cue_for_event(event: GameEvent) -> str | None:
    if event.kind == "resource_refilled":
        resource = event.payload.get("resource")
        if resource == "water":
            return "DWF_REFILL_DONE"
        if resource == "energy":
            return "DWF_CHARGE_DONE"
        return None
    if event.kind == "barrier_repelled":
        return "DWF_GUARD_REPEL"
    if event.kind == "enemy_captured":
        return "DWF_BUBBLE_CAPTURE"
    if event.kind == "discharge_succeeded":
        return "DWF_ZAP_HIT"
    if event.kind == "abnormal_windup_started":
        return "DWF_ABNORMAL_WINDUP"
    if event.kind == "combat_marker_hit":
        return "DWF_COMBAT_MARKER_HIT"
    if event.kind == "combat_marker_miss":
        return "DWF_COMBAT_MARKER_MISS"
    if event.kind == "combat_perfect_started":
        return "DWF_COMBAT_PERFECT"
    if event.kind == "combat_deflect_started":
        return "DWF_COMBAT_DEFLECT"
    if event.kind == "combat_victory_cue_started":
        outcome = event.payload.get("combat_outcome")
        if outcome == "capture":
            return "DWF_COMBAT_VICTORY_CAPTURE"
        if outcome == "defeat":
            return "DWF_COMBAT_VICTORY_DEFEAT"
        return "DWF_COMBAT_VICTORY_DEFLECT"
    return None


class EffectSystem:
    def __init__(self, config: dict[str, Any]) -> None:
        effects = config["effects"]
        self.max_particles = int(effects["max_particles"])
        self.max_emotes = int(effects["max_emotes"])
        self.max_screen_effects = int(effects["max_screen_effects"])
        self.max_particles_per_event = int(effects["max_particles_per_event"])
        self.concentration_line_count = int(effects["concentration_line_count"])
        self.shake_enabled = bool(effects.get("shake_enabled", False))
        self.combat_camera_pulse_enabled = bool(effects.get("combat_camera_pulse_enabled", False))
        self.camera_offset_cap_px = float(effects.get("camera_offset_cap_px", 2.0))
        self.camera_reactions = effects.get("camera_reactions", {})
        reactive = config.get("reactive_environment", {})
        self.reactive_environment_enabled = bool(reactive.get("enabled", True))
        self.reactive_environment_search_radius = float(reactive.get("search_radius_world", 0.0))
        self.reactive_environment_recovery_sec = float(reactive.get("recovery_sec", 0.8))
        self.reactive_environment_retrigger_sec = float(reactive.get("retrigger_sec", 0.8))
        self.reactive_environment_min_strength = float(reactive.get("min_strength", 0.0))
        self.max_active_reactive_environment = int(reactive.get("max_active", 32))
        self.reactive_environment_profiles = reactive.get("profiles", {})
        self.reactive_environment_player_radius = float(reactive.get("player_radius_world", 12.0))
        self.reactive_environment_min_move_speed = float(
            reactive.get("min_real_move_speed_world_per_sec", 1.2)
        )
        self.reactive_environment_horizontal_deadzone_ratio = float(
            reactive.get("horizontal_deadzone_ratio", 0.2)
        )
        shallow_water = config.get("shallow_water", {})
        self.shallow_water_enabled = bool(shallow_water.get("enabled", False))
        self.shallow_water_config_areas = tuple(shallow_water.get("areas", ()))
        self.shallow_water_min_move_world = max(
            0.0, float(shallow_water.get("min_move_world", 2.0))
        )
        self.shallow_water_ripple_spacing_world = max(
            0.0, float(shallow_water.get("ripple_spacing_world", 22.0))
        )
        self.shallow_water_ripple_start_radius = max(
            0.0, float(shallow_water.get("ripple_start_radius", 4.0))
        )
        self.shallow_water_ripple_end_radius = max(
            self.shallow_water_ripple_start_radius,
            float(shallow_water.get("ripple_end_radius", 18.0)),
        )
        self.shallow_water_ripple_lifetime_sec = max(
            0.0, float(shallow_water.get("ripple_lifetime_sec", 0.48))
        )
        self.shallow_water_ripple_color = int(shallow_water.get("ripple_color", 12))
        self.shallow_water_ripple_thickness_px = max(
            1, int(shallow_water.get("ripple_thickness_px", 1))
        )
        self.shallow_water_wake_color = int(shallow_water.get("wake_color", 5))
        self.shallow_water_wake_length_world = max(
            0.0, float(shallow_water.get("wake_length_world", 10.0))
        )
        self.shallow_water_max_ripples_per_update = max(
            0, int(shallow_water.get("max_ripples_per_update", 2))
        )
        self.particles: list[WorldParticle] = []
        self.rings: list[WorldRing] = []
        self.strokes: list[WorldStroke] = []
        self.emotes: list[ActorEmote] = []
        self.enemy_snapshots: list[EnemySnapshot] = []
        self.screen_cues: list[ScreenCue] = []
        self.camera_impulses: list[CameraImpulse] = []
        self.reactive_environment_states: dict[str, ReactiveEnvironmentState] = {}
        self.reactive_environment_last_query_count = 0
        self.reactive_environment_limit_skipped_count = 0
        self._grass_cooldowns: dict[str, float] = {}
        self._reactive_last_player_position: tuple[float, float] | None = None
        self._reactive_last_direction: str = "right"
        self._shallow_water_last_player_position: tuple[float, float] | None = None
        self._shallow_water_distance_since_ripple = 0.0
        self._processed_cues: set[tuple[int, str]] = set()
        self._processed_camera_cues: set[tuple[int, str]] = set()

    def reset(self) -> None:
        self.particles.clear()
        self.rings.clear()
        self.strokes.clear()
        self.emotes.clear()
        self.enemy_snapshots.clear()
        self.screen_cues.clear()
        self.camera_impulses.clear()
        self.reactive_environment_states.clear()
        self.reactive_environment_last_query_count = 0
        self.reactive_environment_limit_skipped_count = 0
        self._grass_cooldowns.clear()
        self._reactive_last_player_position = None
        self._reactive_last_direction = "right"
        self._shallow_water_last_player_position = None
        self._shallow_water_distance_since_ripple = 0.0
        self._processed_cues.clear()
        self._processed_camera_cues.clear()

    def process_events(
        self,
        events: list[GameEvent],
        model,
        camera_reaction_delay: float = 0.0,
        camera_reactions_allowed: bool = True,
    ) -> None:
        for event in events:
            x, y, z = event.world_position
            combat_defeat_restored = (
                event.kind == "combat_restored" and event.payload.get("combat_outcome") == "defeat"
            )
            cue_id = presentation_cue_for_event(event)
            if cue_id is not None:
                key = (event.event_id, cue_id)
                if key in self._processed_cues:
                    continue
                self._processed_cues.add(key)
                self.process_presentation_cue(cue_id, event, model)
                if camera_reactions_allowed:
                    self.process_camera_cue(cue_id, event, camera_reaction_delay)
            elif event.kind == "bubble_fired":
                self.spawn_burst(x, y, z, color=12, count=5, speed=16.0)
            elif combat_defeat_restored:
                self.add_defeated_enemy_linger(event, model)
            elif event.kind == "action_denied":
                self.add_emote("player", "player", model.player.x, model.player.z, "?", 8, 0.45)
            elif event.kind == "inspection_completed":
                self.add_emote("object", event.target_id or "", x, z, "?", 7, 0.8)
                self.add_screen_cue("focus_lines", 0.35)

    def process_presentation_cue(self, cue_id: str, event: GameEvent, model) -> None:
        x, y, z = event.world_position
        if cue_id == "DWF_REFILL_DONE":
            self.spawn_burst_palette(
                model.player.x,
                model.player_cube_size * 0.5,
                model.player.z,
                colors=(5, 12, 6, 7),
                count=8,
                speed=12.0,
            )
            self.add_ring(model.player.x, model.player.z, 6.0, 22.0, 12, 0.6)
        elif cue_id == "DWF_CHARGE_DONE":
            self.spawn_burst_palette(
                model.buddy.x,
                model.buddy.y,
                model.buddy.z,
                colors=(9, 10, 7),
                count=8,
                speed=14.0,
            )
            self.add_ring(model.buddy.x, model.buddy.z, 4.0, 12.0, 10, 0.55)
        elif cue_id == "DWF_GUARD_REPEL":
            self.spawn_burst_palette(x, y, z, colors=(5, 12, 6, 7), count=5, speed=18.0)
            self.add_ring(x, z, 6.0, 14.0, 12, 0.24)
            self.add_direction_strokes(model.player.x, model.player.z, x, z, 12.0, 7, 0.18)
            self.add_emote("enemy", event.target_id or "", x, z, "!", 7, 0.45)
        elif cue_id == "DWF_BUBBLE_CAPTURE":
            self.spawn_burst_palette(x, y, z, colors=(5, 12, 6, 7), count=7, speed=7.0)
            self.add_ring(x, z, 9.0, 20.0, 12, 0.55)
            self.add_glint_strokes(x, z, 12.0, 12, 0.42)
            self.add_emote("enemy", event.target_id or "", x, z, "!", 12, 0.9)
        elif cue_id == "DWF_ZAP_HIT":
            self.add_enemy_snapshot(event, model)
            self.spawn_burst_palette(x, y, z, colors=(9, 10, 7), count=10, speed=14.0)
            self.add_ring(x, z, 6.0, 20.0, 10, 0.62)
            self.add_stroke(model.buddy.x, model.buddy.y + 6.0, model.buddy.z, x, 10.0, z, 7, 0.28)
            self.add_stroke(model.buddy.x, model.buddy.y + 3.0, model.buddy.z, x, 2.0, z, 10, 0.22)
            self.add_glint_strokes(x, z, 14.0, 10, 0.36)
            self.add_emote("enemy", event.target_id or "", x, z, "!", 10, 0.8)
        elif cue_id == "DWF_ABNORMAL_WINDUP":
            self.add_ring(x, z, 8.0, 16.0, 8, 0.3)
            dx = float(event.payload.get("dash_x", 0.0))
            dz = float(event.payload.get("dash_z", 0.0))
            if math.hypot(dx, dz) > 1e-6:
                self.add_stroke(x, 1.0, z, x + dx * 28.0, 1.0, z + dz * 28.0, 8, 0.35)
        elif cue_id == "DWF_COMBAT_MARKER_HIT":
            self.spawn_burst_palette(
                model.player.x,
                model.player_cube_size * 0.6,
                model.player.z,
                colors=(7, 10),
                count=3,
                speed=8.0,
            )
            self.add_glint_strokes(model.player.x, model.player.z, 7.0, 10, 0.12)
        elif cue_id == "DWF_COMBAT_MARKER_MISS":
            self.add_ring(model.player.x, model.player.z, 5.0, 8.0, 5, 0.14)
            self.add_emote("player", "player", model.player.x, model.player.z, "x", 5, 0.22)
        elif cue_id == "DWF_COMBAT_PERFECT":
            self.spawn_burst_palette(
                model.player.x,
                model.player_cube_size * 0.8,
                model.player.z,
                colors=(7, 10, 12),
                count=8,
                speed=16.0,
            )
            self.add_ring(model.player.x, model.player.z, 8.0, 20.0, 10, 0.28)
            self.add_glint_strokes(model.player.x, model.player.z, 16.0, 7, 0.24)
            self.add_screen_cue("focus_lines", 0.2)
        elif cue_id == "DWF_COMBAT_DEFLECT":
            enemy = model.enemy_by_id(event.target_id or "")
            target_x = enemy.x if enemy is not None else x
            target_z = enemy.z if enemy is not None else z
            self.spawn_burst_palette(target_x, y, target_z, colors=(7, 10, 13), count=6, speed=18.0)
            self.add_ring(target_x, target_z, 7.0, 18.0, 7, 0.24)
            self.add_direction_strokes(
                model.player.x, model.player.z, target_x, target_z, 16.0, 7, 0.18
            )
        elif cue_id == "DWF_COMBAT_VICTORY_DEFLECT":
            self.spawn_burst_palette(
                model.player.x,
                model.player_cube_size * 0.9,
                model.player.z,
                colors=(7, 10),
                count=6,
                speed=12.0,
            )
            self.add_glint_strokes(model.player.x, model.player.z, 14.0, 7, 0.28)
        elif cue_id == "DWF_COMBAT_VICTORY_CAPTURE":
            self.spawn_burst_palette(
                model.player.x,
                model.player_cube_size * 0.9,
                model.player.z,
                colors=(5, 12, 7),
                count=7,
                speed=11.0,
            )
            self.add_ring(model.player.x, model.player.z, 7.0, 16.0, 12, 0.3)
        elif cue_id == "DWF_COMBAT_VICTORY_DEFEAT":
            self.spawn_burst_palette(
                model.player.x,
                model.player_cube_size * 0.9,
                model.player.z,
                colors=(7, 10, 9),
                count=8,
                speed=15.0,
            )
            self.add_glint_strokes(model.player.x, model.player.z, 18.0, 10, 0.28)

    def process_camera_cue(
        self, cue_id: str, event: GameEvent, camera_reaction_delay: float
    ) -> None:
        key = (event.event_id, cue_id)
        if key in self._processed_camera_cues:
            return
        reaction = self.camera_reactions.get(cue_id)
        if not isinstance(reaction, dict):
            return
        shake_amplitude = (
            float(reaction.get("shake_amplitude_px", 0.0)) if self.shake_enabled else 0.0
        )
        zoom_peak = (
            float(reaction.get("zoom_peak", 0.0)) if self.combat_camera_pulse_enabled else 0.0
        )
        if shake_amplitude <= 0.0 and zoom_peak <= 0.0:
            return
        self._processed_camera_cues.add(key)
        shake_duration = max(0.0, float(reaction.get("shake_duration_ms", 0.0)) / 1000.0)
        zoom_attack = max(0.0, float(reaction.get("zoom_attack_ms", 0.0)) / 1000.0)
        zoom_hold = max(0.0, float(reaction.get("zoom_hold_ms", 0.0)) / 1000.0)
        zoom_return = max(0.0, float(reaction.get("zoom_return_ms", 0.0)) / 1000.0)
        lifetime = max(shake_duration, zoom_attack + zoom_hold + zoom_return)
        if lifetime <= 0.0:
            return
        self.add_camera_impulse(
            CameraImpulse(
                cue_id=cue_id,
                lifetime=lifetime,
                delay=max(0.0, camera_reaction_delay),
                shake_amplitude_px=shake_amplitude,
                shake_duration=shake_duration,
                zoom_peak=zoom_peak,
                zoom_attack=zoom_attack,
                zoom_hold=zoom_hold,
                zoom_return=zoom_return,
            )
        )

    def update(self, dt: float, model) -> None:
        dt = max(0.0, dt)
        for particle in self.particles:
            particle.age += dt
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            particle.z += particle.vz * dt
            particle.vy -= 18.0 * dt
        self.particles = [
            particle for particle in self.particles if particle.age < particle.lifetime
        ]

        for ring in self.rings:
            ring.age += dt
        self.rings = [ring for ring in self.rings if ring.age < ring.lifetime]

        for stroke in self.strokes:
            stroke.age += dt
        self.strokes = [stroke for stroke in self.strokes if stroke.age < stroke.lifetime]

        for emote in self.emotes:
            emote.age += dt
        self.emotes = [emote for emote in self.emotes if emote.age < emote.lifetime]

        for snapshot in self.enemy_snapshots:
            snapshot.age += dt
        self.enemy_snapshots = [
            snapshot for snapshot in self.enemy_snapshots if snapshot.age < snapshot.lifetime
        ]

        for cue in self.screen_cues:
            cue.age += dt
        self.screen_cues = [cue for cue in self.screen_cues if cue.age < cue.lifetime]

        for impulse in self.camera_impulses:
            impulse.age += dt
        self.camera_impulses = [
            impulse
            for impulse in self.camera_impulses
            if impulse.age < impulse.delay + impulse.lifetime
        ]

        for object_id in tuple(self._grass_cooldowns):
            self._grass_cooldowns[object_id] = max(0.0, self._grass_cooldowns[object_id] - dt)

        reactive_dt = dt if self.reactive_environment_world_active(model) else 0.0
        if reactive_dt > 0.0:
            self.update_grass_reactions(model, reactive_dt)
            self.update_shallow_water_reactions(model, reactive_dt)
            for state in self.reactive_environment_states.values():
                self.advance_reactive_environment_state(state, reactive_dt)
            self.reactive_environment_states = {
                object_id: state
                for object_id, state in self.reactive_environment_states.items()
                if state.phase != "IDLE"
            }
        else:
            self.sync_reactive_environment_player_position(model)
            self.sync_shallow_water_player_position(model)

    def reactive_environment_world_active(self, model) -> bool:
        return model.combat_session is None and not model.world_paused

    def sync_reactive_environment_player_position(self, model) -> None:
        self._reactive_last_player_position = (float(model.player.x), float(model.player.z))

    def sync_shallow_water_player_position(self, model) -> None:
        self._shallow_water_last_player_position = (float(model.player.x), float(model.player.z))

    def update_shallow_water_reactions(self, model, dt: float) -> None:
        if not self.shallow_water_enabled or self.shallow_water_ripple_lifetime_sec <= 0.0:
            self.sync_shallow_water_player_position(model)
            self._shallow_water_distance_since_ripple = 0.0
            return
        areas = self.shallow_water_areas_for(model)
        if not areas:
            self.sync_shallow_water_player_position(model)
            self._shallow_water_distance_since_ripple = 0.0
            return
        current = (float(model.player.x), float(model.player.z))
        previous = self._shallow_water_last_player_position
        if previous is None:
            self._shallow_water_last_player_position = current
            return
        self._shallow_water_last_player_position = current

        dx = current[0] - previous[0]
        dz = current[1] - previous[1]
        moved = math.hypot(dx, dz)
        if moved < self.shallow_water_min_move_world:
            return
        if not self.shallow_water_segment_hits(previous, current, areas):
            self._shallow_water_distance_since_ripple = 0.0
            return

        self._shallow_water_distance_since_ripple += moved
        spacing = max(self.shallow_water_ripple_spacing_world, self.shallow_water_min_move_world)
        emitted = 0
        while (
            self._shallow_water_distance_since_ripple >= spacing
            and emitted < self.shallow_water_max_ripples_per_update
        ):
            fraction_from_current = (self._shallow_water_distance_since_ripple - spacing) / max(
                moved, 1e-6
            )
            fraction_from_current = max(0.0, min(1.0, fraction_from_current))
            ripple_x = current[0] - dx * fraction_from_current
            ripple_z = current[1] - dz * fraction_from_current
            if self.shallow_water_point_inside(ripple_x, ripple_z, areas):
                self.add_shallow_water_ripple(ripple_x, ripple_z, dx, dz)
                emitted += 1
            self._shallow_water_distance_since_ripple -= spacing

    def shallow_water_areas_for(self, model) -> tuple:
        world_areas = tuple(getattr(getattr(model, "world", None), "shallow_water_areas", ()))
        return self.shallow_water_config_areas or world_areas

    def add_shallow_water_ripple(
        self, x: float, z: float, movement_x: float, movement_z: float
    ) -> None:
        self.add_ring(
            x,
            z,
            self.shallow_water_ripple_start_radius,
            self.shallow_water_ripple_end_radius,
            self.shallow_water_ripple_color,
            self.shallow_water_ripple_lifetime_sec,
            thickness=self.shallow_water_ripple_thickness_px,
            layer="background",
        )
        movement_length = math.hypot(movement_x, movement_z)
        if movement_length <= 1e-6 or self.shallow_water_wake_length_world <= 0.0:
            return
        ux = movement_x / movement_length
        uz = movement_z / movement_length
        self.add_stroke(
            x - ux * self.shallow_water_wake_length_world,
            0.0,
            z - uz * self.shallow_water_wake_length_world,
            x,
            0.0,
            z,
            self.shallow_water_wake_color,
            min(self.shallow_water_ripple_lifetime_sec, 0.28),
            layer="background",
        )

    def shallow_water_segment_hits(
        self,
        previous: tuple[float, float],
        current: tuple[float, float],
        areas: tuple,
    ) -> bool:
        if self.shallow_water_point_inside(*previous, areas) or self.shallow_water_point_inside(
            *current, areas
        ):
            return True
        for area in areas:
            rect = self.shallow_water_area_rect(area)
            if rect is None:
                continue
            if self.segment_intersects_rect(previous, current, rect):
                return True
        return False

    def shallow_water_point_inside(self, x: float, z: float, areas: tuple) -> bool:
        for area in areas:
            rect = self.shallow_water_area_rect(area)
            if rect is None:
                continue
            min_x, min_z, max_x, max_z = rect
            if min_x <= x <= max_x and min_z <= z <= max_z:
                return True
        return False

    def shallow_water_area_rect(self, area) -> tuple[float, float, float, float] | None:
        if hasattr(area, "min_x") and hasattr(area, "min_z"):
            return (
                float(area.min_x),
                float(area.min_z),
                float(area.max_x),
                float(area.max_z),
            )
        if not isinstance(area, dict):
            return None
        rect = area.get("rect_xz", ())
        if len(rect) != 4:
            return None
        min_x, min_z, max_x, max_z = (float(value) for value in rect)
        if min_x > max_x:
            min_x, max_x = max_x, min_x
        if min_z > max_z:
            min_z, max_z = max_z, min_z
        return min_x, min_z, max_x, max_z

    def segment_intersects_rect(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        rect: tuple[float, float, float, float],
    ) -> bool:
        min_x, min_z, max_x, max_z = rect
        dx = end[0] - start[0]
        dz = end[1] - start[1]
        t_min = 0.0
        t_max = 1.0
        for origin, delta, lower, upper in (
            (start[0], dx, min_x, max_x),
            (start[1], dz, min_z, max_z),
        ):
            if abs(delta) <= 1e-9:
                if origin < lower or origin > upper:
                    return False
                continue
            inv = 1.0 / delta
            t1 = (lower - origin) * inv
            t2 = (upper - origin) * inv
            if t1 > t2:
                t1, t2 = t2, t1
            t_min = max(t_min, t1)
            t_max = min(t_max, t2)
            if t_min > t_max:
                return False
        return True

    def update_grass_reactions(self, model, dt: float) -> None:
        self.reactive_environment_last_query_count = 0
        self.reactive_environment_limit_skipped_count = 0
        if not self.reactive_environment_enabled:
            self.sync_reactive_environment_player_position(model)
            return
        current = (float(model.player.x), float(model.player.z))
        previous = self._reactive_last_player_position
        if previous is None:
            self._reactive_last_player_position = current
            return
        self._reactive_last_player_position = current

        moved = math.hypot(current[0] - previous[0], current[1] - previous[1])
        query_x = (previous[0] + current[0]) * 0.5
        query_z = (previous[1] + current[1]) * 0.5
        query_radius = max(
            self.reactive_environment_search_radius,
            moved * 0.5 + self.max_reactive_environment_enter_radius(model),
        )
        query = model.world.query_reactive_environment(query_x, query_z, query_radius)
        self.reactive_environment_last_query_count = query.candidate_object_count

        candidate_ids = {obj.id for obj in query.objects}
        active_ids = set(self.reactive_environment_states)
        objects_by_id = {obj.id: obj for obj in model.world.reactive_environment_objects}
        for object_id in sorted(candidate_ids | active_ids):
            obj = objects_by_id.get(object_id)
            if obj is None:
                continue
            profile = self.reactive_environment_profile(obj)
            if profile is None:
                continue
            self.update_reactive_environment_object(
                model, obj, profile, previous, current, moved, dt
            )

    def reactive_environment_profile(self, obj) -> dict | None:
        profiles = self.reactive_environment_profiles
        if not isinstance(profiles, dict):
            return None
        for profile in profiles.values():
            if not isinstance(profile, dict):
                continue
            visuals = profile.get("visuals", ())
            if obj.visual in visuals:
                return profile
        return None

    def max_reactive_environment_enter_radius(self, model) -> float:
        maximum = 0.0
        profiles = self.reactive_environment_profiles
        if isinstance(profiles, dict):
            for profile in profiles.values():
                if not isinstance(profile, dict):
                    continue
                maximum = max(maximum, self.profile_enter_radius(model, profile))
        return maximum

    def profile_enter_radius(self, model, profile: dict) -> float:
        if "enter_radius_world" in profile:
            return max(0.0, float(profile.get("enter_radius_world", 0.0)))
        factor = float(profile.get("enter_radius_factor", 1.6))
        return max(0.0, factor * self.reactive_player_radius(model))

    def profile_exit_radius(self, model, profile: dict, enter_radius: float) -> float:
        if "exit_radius_world" in profile:
            return max(enter_radius, float(profile.get("exit_radius_world", enter_radius)))
        factor = float(profile.get("exit_radius_extra_factor", 0.3))
        return max(enter_radius, enter_radius + factor * self.reactive_player_radius(model))

    def reactive_player_radius(self, model) -> float:
        configured = self.reactive_environment_player_radius
        if configured > 0.0:
            return configured
        return max(float(model.player_solid_half_x), float(model.player_solid_half_z))

    def update_reactive_environment_object(
        self,
        model,
        obj,
        profile: dict,
        previous: tuple[float, float],
        current: tuple[float, float],
        moved: float,
        dt: float,
    ) -> None:
        enter_radius = self.profile_enter_radius(model, profile)
        exit_radius = self.profile_exit_radius(model, profile, enter_radius)
        state = self.reactive_environment_states.get(obj.id)
        currently_touching = math.hypot(current[0] - obj.x, current[1] - obj.z) <= exit_radius
        speed = moved / max(dt, 1e-6)
        swept_hit = (
            speed >= self.reactive_environment_min_move_speed
            and self.segment_distance_to_point(previous, current, obj.x, obj.z) <= enter_radius
        )
        if state is None:
            if not swept_hit:
                return
            self.activate_reactive_environment(model, obj, profile, previous, current, enter_radius)
            return

        if currently_touching:
            self.touch_reactive_environment_state(model, obj, state, profile, previous, current)
        elif state.touching:
            state.touching = False
            state.phase_elapsed = 0.0 if state.phase == "HOLD" else state.phase_elapsed

    def activate_reactive_environment(self, model, obj, profile, previous, current, radius) -> None:
        if self.max_active_reactive_environment <= 0:
            return
        if (
            obj.id not in self.reactive_environment_states
            and len(self.reactive_environment_states) >= self.max_active_reactive_environment
        ):
            self.reactive_environment_limit_skipped_count += 1
            return
        direction = self.reactive_environment_direction_label(model, obj, previous, current)
        self._reactive_last_direction = direction
        direction_x, direction_z = self.reactive_environment_motion_direction(previous, current)
        distance = self.segment_distance_to_point(previous, current, obj.x, obj.z)
        contact = 1.0 - min(distance / max(radius, 1e-6), 1.0)
        min_strength = max(0.0, min(self.reactive_environment_min_strength, 1.0))
        strength = min_strength + (1.0 - min_strength) * contact
        visual_radius = max(
            radius,
            obj.sprite_world_width * 0.5,
            obj.sprite_world_height * 0.5,
        )
        push_sec = max(0.0, float(profile.get("push_sec", 0.1)))
        release_hold_sec = max(0.0, float(profile.get("release_hold_sec", 0.08)))
        recover_bend1_sec = max(0.0, float(profile.get("recover_bend1_sec", 0.12)))
        recover_near_idle_sec = max(0.0, float(profile.get("recover_near_idle_sec", 0.24)))
        redirect_step_sec = max(0.0, float(profile.get("redirect_step_sec", 0.04)))
        self.reactive_environment_states[obj.id] = ReactiveEnvironmentState(
            object_id=obj.id,
            kind=obj.visual or obj.kind,
            x=obj.x,
            z=obj.z,
            trigger_radius=radius,
            visual_radius=visual_radius,
            strength=strength,
            direction_x=direction_x,
            direction_z=direction_z,
            recovery_sec=push_sec + release_hold_sec + recover_bend1_sec + recover_near_idle_sec,
            direction=direction,
            pose_id=self.reactive_environment_pose_for("PUSH", direction, 0.0, push_sec),
            push_sec=push_sec,
            release_hold_sec=release_hold_sec,
            recover_bend1_sec=recover_bend1_sec,
            recover_near_idle_sec=recover_near_idle_sec,
            redirect_step_sec=redirect_step_sec,
        )

    def touch_reactive_environment_state(
        self, model, obj, state: ReactiveEnvironmentState, profile, previous, current
    ) -> None:
        direction = self.reactive_environment_direction_label(model, obj, previous, current)
        direction_x, direction_z = self.reactive_environment_motion_direction(previous, current)
        state.direction_x = direction_x
        state.direction_z = direction_z
        state.touching = True
        if state.phase == "REDIRECT":
            state.pending_direction = direction
            self._reactive_last_direction = direction
            return
        if direction == state.direction or state.phase == "IDLE":
            if state.phase == "RECOVER":
                state.phase = "PUSH"
                state.phase_elapsed = min(state.phase_elapsed, state.push_sec * 0.5)
            elif state.phase == "IDLE":
                state.phase = "PUSH"
                state.phase_elapsed = 0.0
            state.direction = direction
            state.pose_id = self.reactive_environment_pose_for(
                state.phase, state.direction, state.phase_elapsed, state.push_sec
            )
            self._reactive_last_direction = direction
            return
        state.pending_direction = direction
        state.phase = "REDIRECT"
        state.phase_elapsed = 0.0
        state.pose_id = f"recover_{state.direction}"
        self._reactive_last_direction = direction

    def advance_reactive_environment_state(
        self, state: ReactiveEnvironmentState, dt: float
    ) -> None:
        state.age += dt
        if state.phase == "PUSH":
            state.phase_elapsed += dt
            if state.phase_elapsed >= state.push_sec:
                state.phase = "HOLD"
                state.phase_elapsed = 0.0
                state.pose_id = f"bend_{state.direction}_2"
            else:
                state.pose_id = self.reactive_environment_pose_for(
                    "PUSH", state.direction, state.phase_elapsed, state.push_sec
                )
            return
        if state.phase == "HOLD":
            state.pose_id = f"bend_{state.direction}_2"
            if state.touching:
                state.phase_elapsed = 0.0
                return
            state.phase_elapsed += dt
            if state.phase_elapsed >= state.release_hold_sec:
                state.phase = "RECOVER"
                state.phase_elapsed = 0.0
                state.pose_id = f"bend_{state.direction}_1"
            return
        if state.phase == "RECOVER":
            state.phase_elapsed += dt
            if state.phase_elapsed < state.recover_bend1_sec:
                state.pose_id = f"bend_{state.direction}_1"
                return
            if state.phase_elapsed < state.recover_bend1_sec + state.recover_near_idle_sec:
                state.pose_id = f"recover_{state.direction}"
                return
            state.phase = "IDLE"
            state.pose_id = "idle"
            state.touching = False
            return
        if state.phase == "REDIRECT":
            state.phase_elapsed += dt
            state.pose_id = f"recover_{state.direction}"
            if state.phase_elapsed >= state.redirect_step_sec:
                state.direction = state.pending_direction or state.direction
                state.pending_direction = None
                state.phase = "PUSH"
                state.phase_elapsed = 0.0
                state.pose_id = f"bend_{state.direction}_1"

    def reactive_environment_pose_for(
        self, phase: str, direction: str, elapsed: float, push_sec: float
    ) -> str:
        if phase == "PUSH":
            return f"bend_{direction}_1" if elapsed < push_sec * 0.5 else f"bend_{direction}_2"
        if phase == "HOLD":
            return f"bend_{direction}_2"
        if phase == "RECOVER":
            return f"bend_{direction}_1"
        return "idle"

    def segment_distance_to_point(
        self, start: tuple[float, float], end: tuple[float, float], x: float, z: float
    ) -> float:
        vx = end[0] - start[0]
        vz = end[1] - start[1]
        denom = vx * vx + vz * vz
        if denom <= 1e-9:
            return math.hypot(x - end[0], z - end[1])
        t = ((x - start[0]) * vx + (z - start[1]) * vz) / denom
        t = max(0.0, min(1.0, t))
        nearest_x = start[0] + vx * t
        nearest_z = start[1] + vz * t
        return math.hypot(x - nearest_x, z - nearest_z)

    def reactive_environment_motion_direction(
        self, previous: tuple[float, float], current: tuple[float, float]
    ) -> tuple[float, float]:
        direction_x = current[0] - previous[0]
        direction_z = current[1] - previous[1]
        length = math.hypot(direction_x, direction_z)
        if length <= 1e-6:
            return 0.0, 1.0
        return direction_x / length, direction_z / length

    def reactive_environment_direction_label(
        self, model, obj, previous: tuple[float, float], current: tuple[float, float]
    ) -> str:
        dx = current[0] - previous[0]
        dz = current[1] - previous[1]
        screen_x, screen_y = self.reactive_environment_affine_vector(model, dx, dz)
        projected = math.hypot(screen_x, screen_y)
        if projected > 1e-6 and abs(screen_x) >= projected * max(
            0.0, self.reactive_environment_horizontal_deadzone_ratio
        ):
            return "right" if screen_x > 0.0 else "left"

        nearest = self.nearest_point_on_segment(previous, current, obj.x, obj.z)
        side_x, side_y = self.reactive_environment_affine_vector(
            model, obj.x - nearest[0], obj.z - nearest[1]
        )
        side_projected = math.hypot(side_x, side_y)
        if side_projected > 1e-6 and abs(side_x) >= side_projected * 0.1:
            return "right" if side_x > 0.0 else "left"
        return self._reactive_last_direction

    def nearest_point_on_segment(
        self, start: tuple[float, float], end: tuple[float, float], x: float, z: float
    ) -> tuple[float, float]:
        vx = end[0] - start[0]
        vz = end[1] - start[1]
        denom = vx * vx + vz * vz
        if denom <= 1e-9:
            return end
        t = ((x - start[0]) * vx + (z - start[1]) * vz) / denom
        t = max(0.0, min(1.0, t))
        return start[0] + vx * t, start[1] + vz * t

    def reactive_environment_affine_vector(
        self, model, dx: float, dz: float
    ) -> tuple[float, float]:
        affine = model.config.get("projection", {}).get("affine", {})
        basis_x = affine.get("basis_x", (1.0, 0.0))
        basis_z = affine.get("basis_z", (0.0, 1.0))
        return (
            dx * float(basis_x[0]) + dz * float(basis_z[0]),
            dx * float(basis_x[1]) + dz * float(basis_z[1]),
        )

    def spawn_burst(
        self, x: float, y: float, z: float, color: int, count: int, speed: float
    ) -> None:
        self.spawn_burst_palette(x, y, z, colors=(color,), count=count, speed=speed)

    def spawn_burst_palette(
        self, x: float, y: float, z: float, colors: tuple[int, ...], count: int, speed: float
    ) -> None:
        count = min(count, self.max_particles_per_event)
        colors = colors or (7,)
        for index in range(count):
            if len(self.particles) >= self.max_particles:
                return
            angle = index * math.tau / max(count, 1)
            self.particles.append(
                WorldParticle(
                    x=x,
                    y=y + 4.0,
                    z=z,
                    vx=math.cos(angle) * speed,
                    vy=8.0 + (index % 3) * 2.0,
                    vz=math.sin(angle) * speed,
                    color=colors[index % len(colors)],
                    lifetime=0.45 + (index % 2) * 0.1,
                )
            )

    def add_defeated_enemy_linger(self, event: GameEvent, model) -> None:
        cue_id = "DWF_ENEMY_DEFEAT_LINGER"
        key = (event.event_id, cue_id)
        if key in self._processed_cues:
            return
        self._processed_cues.add(key)

        enemy = model.enemy_by_id(event.actor_id or event.target_id or "")
        if enemy is None:
            return
        count = min(6, self.max_particles_per_event)
        colors = (13, 5, 1, 7)
        phase = (event.event_id % 7) * 0.31
        for index in range(count):
            if len(self.particles) >= self.max_particles:
                return
            angle = phase + index * math.tau / max(count, 1)
            speed = 4.0 + (index % 3) * 1.6
            self.particles.append(
                WorldParticle(
                    x=enemy.x + math.cos(angle) * 1.5,
                    y=3.0 + (index % 2) * 2.0,
                    z=enemy.z + math.sin(angle) * 1.5,
                    vx=math.cos(angle) * speed,
                    vy=6.0 + (index % 4) * 1.3,
                    vz=math.sin(angle) * speed,
                    color=colors[index % len(colors)],
                    lifetime=0.82 + (index % 3) * 0.14,
                )
            )

    def add_ring(
        self,
        x: float,
        z: float,
        start_radius: float,
        end_radius: float,
        color: int,
        lifetime: float,
        thickness: int = 1,
        layer: str = "foreground",
    ) -> None:
        if len(self.rings) >= self.max_particles:
            self.rings.pop(0)
        self.rings.append(
            WorldRing(x, z, start_radius, end_radius, color, lifetime, max(1, thickness), layer)
        )

    def add_stroke(
        self,
        start_x: float,
        start_y: float,
        start_z: float,
        end_x: float,
        end_y: float,
        end_z: float,
        color: int,
        lifetime: float,
        layer: str = "foreground",
    ) -> None:
        if len(self.strokes) >= self.max_particles:
            self.strokes.pop(0)
        self.strokes.append(
            WorldStroke(start_x, start_y, start_z, end_x, end_y, end_z, color, lifetime, layer)
        )

    def add_direction_strokes(
        self,
        origin_x: float,
        origin_z: float,
        hit_x: float,
        hit_z: float,
        length: float,
        color: int,
        lifetime: float,
    ) -> None:
        dx = hit_x - origin_x
        dz = hit_z - origin_z
        magnitude = math.hypot(dx, dz)
        if magnitude <= 1e-6:
            return
        dx /= magnitude
        dz /= magnitude
        side_x = -dz
        side_z = dx
        for offset in (-2.5, 2.5):
            sx = hit_x + side_x * offset
            sz = hit_z + side_z * offset
            self.add_stroke(sx, 5.0, sz, sx + dx * length, 5.0, sz + dz * length, color, lifetime)

    def add_glint_strokes(
        self, x: float, z: float, radius: float, color: int, lifetime: float
    ) -> None:
        self.add_stroke(
            x - radius * 0.35,
            14.0,
            z - radius * 0.2,
            x + radius * 0.2,
            14.0,
            z,
            color,
            lifetime,
        )
        self.add_stroke(
            x + radius * 0.2,
            11.0,
            z + radius * 0.3,
            x + radius * 0.45,
            11.0,
            z + radius * 0.05,
            color,
            lifetime,
        )

    def add_emote(
        self,
        anchor_kind: str,
        anchor_id: str,
        fallback_x: float,
        fallback_z: float,
        symbol: str,
        color: int,
        lifetime: float,
    ) -> None:
        if len(self.emotes) >= self.max_emotes:
            self.emotes.pop(0)
        self.emotes.append(
            ActorEmote(anchor_kind, anchor_id, fallback_x, fallback_z, symbol, color, lifetime)
        )

    def add_enemy_snapshot(self, event: GameEvent, model) -> None:
        if event.target_id is None:
            return
        enemy = model.enemy_by_id(event.target_id)
        if enemy is None:
            return
        effects = model.config["effects"]
        lifetime = float(effects.get("defeated_enemy_snapshot_ms", 100.0)) / 1000.0
        if lifetime <= 0.0:
            return
        x, _y, z = event.world_position
        self.enemy_snapshots = [
            snapshot for snapshot in self.enemy_snapshots if snapshot.enemy_id != event.target_id
        ]
        self.enemy_snapshots.append(
            EnemySnapshot(
                enemy_id=event.target_id,
                enemy_kind=enemy.kind,
                x=x,
                z=z,
                lifetime=lifetime,
            )
        )

    def add_screen_cue(self, kind: str, lifetime: float) -> None:
        if len(self.screen_cues) >= self.max_screen_effects:
            self.screen_cues.pop(0)
        self.screen_cues.append(ScreenCue(kind, lifetime))

    def add_camera_impulse(self, impulse: CameraImpulse) -> None:
        self.camera_impulses = [
            item for item in self.camera_impulses if item.cue_id != impulse.cue_id
        ]
        self.camera_impulses.append(impulse)

    def camera_transform(
        self, viewport_width: int, viewport_height: int
    ) -> CameraPresentationTransform:
        offset_x = 0.0
        offset_y = 0.0
        strongest_shake = 0.0
        zoom_multiplier = 1.0
        scale = viewport_height / 236.0
        offset_cap = self.camera_offset_cap_px * scale
        for impulse in self.camera_impulses:
            if not impulse.active:
                continue
            local_age = impulse.local_age
            shake_amount = impulse.shake_amount(local_age) * scale
            if shake_amount > strongest_shake:
                strongest_shake = shake_amount
                offset_x, offset_y = impulse.shake_offset(local_age, shake_amount)
            zoom_multiplier = max(
                zoom_multiplier, 1.0 + impulse.zoom_peak * impulse.zoom_envelope(local_age)
            )
        if offset_cap > 0.0:
            offset_x = max(-offset_cap, min(offset_x, offset_cap))
            offset_y = max(-offset_cap, min(offset_y, offset_cap))
        return CameraPresentationTransform(offset_x, offset_y, zoom_multiplier)


def _smoothstep(amount: float) -> float:
    amount = max(0.0, min(amount, 1.0))
    return amount * amount * (3.0 - 2.0 * amount)


def _zoom_envelope(age: float, attack: float, hold: float, return_: float) -> float:
    if age < 0.0:
        return 0.0
    if attack > 1e-6 and age < attack:
        return _smoothstep(age / attack)
    age -= attack
    if age < hold:
        return 1.0
    age -= hold
    if return_ <= 1e-6:
        return 0.0
    return 1.0 - _smoothstep(age / return_)


def _shake_amount(age: float, amplitude: float, duration: float) -> float:
    if age < 0.0 or duration <= 1e-6 or age >= duration:
        return 0.0
    return max(0.0, amplitude * (1.0 - age / duration))


def _shake_offset(age: float, amount: float) -> tuple[float, float]:
    if amount <= 0.0:
        return 0.0, 0.0
    x = math.sin(age * math.tau * 37.0) * amount
    y = math.sin(age * math.tau * 53.0 + math.tau * 0.25) * amount * 0.55
    return x, y
