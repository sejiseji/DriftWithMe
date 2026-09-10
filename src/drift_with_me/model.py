from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from drift_with_me.camera import camera_ground_axes, smoothing_alpha
from drift_with_me.events import EventQueue, GameEvent
from drift_with_me.math3d import CameraState, Vec3, screen_to_world_direction
from drift_with_me.world import StaticObject, WorldData


@dataclass
class PlayerState:
    x: float
    z: float
    moved_distance: float = 0.0
    barrier_active: bool = False
    stun_remaining: float = 0.0
    invulnerable_remaining: float = 0.0
    last_move_x: float = 0.0
    last_move_z: float = 1.0


@dataclass
class BuddyState:
    x: float
    y: float
    z: float
    goal_x: float
    goal_y: float
    goal_z: float

    def distance_to_goal(self) -> float:
        return (
            (self.x - self.goal_x) ** 2 + (self.y - self.goal_y) ** 2 + (self.z - self.goal_z) ** 2
        ) ** 0.5


@dataclass
class EnemyState:
    id: str
    kind: str
    x: float
    z: float
    home_x: float
    home_z: float
    state: str = "IDLE"
    state_timer: float = 0.0
    push_x_per_sec: float = 0.0
    push_z_per_sec: float = 0.0


@dataclass
class InteractionState:
    kind: str
    object_id: str
    title: str
    lines: tuple[str, ...]
    duration_sec: float
    elapsed_sec: float = 0.0

    @property
    def progress(self) -> float:
        if self.duration_sec <= 1e-6:
            return 1.0
        return max(0.0, min(self.elapsed_sec / self.duration_sec, 1.0))


@dataclass(frozen=True)
class InputIntent:
    screen_x: float = 0.0
    screen_y: float = 0.0
    strength: float = 0.0
    barrier: bool = False
    action_pressed: bool = False
    interact_pressed: bool = False


@dataclass
class DebugCounters:
    discarded_elapsed_count: int = 0
    fixed_steps_last_callback: int = 0
    denied_actions: int = 0
    barrier_repels: int = 0
    player_contacts: int = 0
    completed_refills: int = 0
    cancelled_interactions: int = 0


class GameModel:
    def __init__(self, config: dict[str, Any], world: WorldData) -> None:
        self.config = config
        self.world = world
        self.event_queue = EventQueue()
        self.player = PlayerState(world.spawn_x, world.spawn_z)
        self.enemies = [self.enemy_from_spawn(spawn) for spawn in self.world.enemies]
        buddy_height = float(config["buddy"]["height"])
        self.buddy = BuddyState(
            world.spawn_x,
            buddy_height,
            world.spawn_z,
            world.spawn_x,
            buddy_height,
            world.spawn_z,
        )
        self.water = float(config["resources"]["water_start"])
        self.energy = float(config["resources"]["energy_start"])
        self.world_tick = 0
        self.debug = DebugCounters()
        self.last_events: list[GameEvent] = []
        self.action_lock_remaining = 0.0
        self.interaction: InteractionState | None = None
        self.barrier_blocked_until_release = False

    def enemy_from_spawn(self, spawn) -> EnemyState:
        return EnemyState(
            id=spawn.id,
            kind=spawn.kind,
            x=spawn.x,
            z=spawn.z,
            home_x=spawn.home_x,
            home_z=spawn.home_z,
        )

    @property
    def player_half_x(self) -> float:
        return float(self.config["player"]["collider_half_x"])

    @property
    def player_half_z(self) -> float:
        return float(self.config["player"]["collider_half_z"])

    @property
    def player_cube_size(self) -> float:
        return float(self.config["player"]["cube_size"])

    def reset_scene(self) -> None:
        self.event_queue.reset()
        self.player = PlayerState(self.world.spawn_x, self.world.spawn_z)
        self.enemies = [self.enemy_from_spawn(spawn) for spawn in self.world.enemies]
        buddy_height = float(self.config["buddy"]["height"])
        self.buddy = BuddyState(
            self.world.spawn_x,
            buddy_height,
            self.world.spawn_z,
            self.world.spawn_x,
            buddy_height,
            self.world.spawn_z,
        )
        self.water = float(self.config["resources"]["water_start"])
        self.energy = float(self.config["resources"]["energy_start"])
        self.world_tick = 0
        self.debug = DebugCounters()
        self.last_events = []
        self.action_lock_remaining = 0.0
        self.interaction = None
        self.barrier_blocked_until_release = False

    @property
    def buddy_cube_size(self) -> float:
        return float(self.config["buddy"]["cube_size"])

    @property
    def world_paused(self) -> bool:
        return self.interaction is not None

    @property
    def water_max(self) -> float:
        return float(self.config["resources"]["water_max"])

    @property
    def energy_max(self) -> float:
        return float(self.config["resources"]["energy_max"])

    def snap_buddy(self, camera: CameraState) -> None:
        goal_x, goal_y, goal_z = self.buddy_goal(camera)
        self.buddy = BuddyState(goal_x, goal_y, goal_z, goal_x, goal_y, goal_z)

    def buddy_goal(self, camera: CameraState) -> tuple[float, float, float]:
        screen_right, ground_forward = camera_ground_axes(camera)
        buddy_config = self.config["buddy"]
        goal_x = (
            self.player.x
            + float(buddy_config["offset_screen_right_world"]) * screen_right.x
            - float(buddy_config["offset_behind_player_world"]) * ground_forward.x
        )
        goal_z = (
            self.player.z
            + float(buddy_config["offset_screen_right_world"]) * screen_right.y
            - float(buddy_config["offset_behind_player_world"]) * ground_forward.y
        )
        return (
            max(0.0, min(float(self.world.width), goal_x)),
            float(buddy_config["height"]),
            max(0.0, min(float(self.world.depth), goal_z)),
        )

    def step(self, intent: InputIntent, camera: CameraState, dt: float) -> list[GameEvent]:
        events: list[GameEvent] = []
        if self.world_paused:
            self.player.barrier_active = False
            self.last_events = events
            return events

        self.world_tick += 1
        self.action_lock_remaining = max(0.0, self.action_lock_remaining - dt)
        self.player.stun_remaining = max(0.0, self.player.stun_remaining - dt)
        self.player.invulnerable_remaining = max(0.0, self.player.invulnerable_remaining - dt)

        if intent.action_pressed:
            self.emit_denied(
                events,
                "busy" if intent.barrier else "no_target",
                scope="JWP004_action_placeholder",
            )

        if intent.interact_pressed:
            self.try_start_interaction(events, camera, busy=intent.barrier)
            if self.world_paused:
                self.player.barrier_active = False
                self.update_buddy(camera, dt)
                self.last_events = events
                return events

        self.update_barrier(intent.barrier, dt, events)

        if (
            not intent.barrier
            and not self.player.barrier_active
            and self.action_lock_remaining <= 0.0
            and self.player.stun_remaining <= 0.0
            and intent.strength > 0.0
        ):
            direction = screen_to_world_direction(
                camera,
                self.player.x,
                self.player.z,
                intent.screen_x,
                intent.screen_y,
            )
            move_speed = float(self.config["player"]["move_speed"])
            distance = move_speed * max(0.0, min(intent.strength, 1.0)) * dt
            delta_x = direction.x * distance
            delta_z = direction.y * distance
            before_x = self.player.x
            before_z = self.player.z
            next_x, next_z = self.world.move_player_sliding(
                before_x,
                before_z,
                delta_x,
                delta_z,
                self.player_half_x,
                self.player_half_z,
            )
            self.player.x = next_x
            self.player.z = next_z
            moved = ((next_x - before_x) ** 2 + (next_z - before_z) ** 2) ** 0.5
            self.player.moved_distance += moved
            if moved > 1e-6:
                self.player.last_move_x = (next_x - before_x) / moved
                self.player.last_move_z = (next_z - before_z) / moved

        self.update_enemies(dt)
        if self.player.barrier_active:
            self.resolve_barrier_contacts(events)
        self.resolve_player_contacts(events)

        self.update_buddy(camera, dt)

        self.last_events = events
        return events

    def update_barrier(self, requested: bool, dt: float, events: list[GameEvent]) -> None:
        self.player.barrier_active = False
        if not requested:
            self.barrier_blocked_until_release = False
            return
        if self.barrier_blocked_until_release:
            return

        cost = float(self.config["resources"]["barrier_water_per_sec"]) * dt
        if self.water + 1e-9 >= cost:
            self.water = clamp_resource(self.water - cost, self.water_max)
            self.player.barrier_active = True
            return

        self.water = 0.0
        self.barrier_blocked_until_release = True
        self.emit_denied(events, "insufficient_water", scope="barrier")

    def try_start_interaction(
        self,
        events: list[GameEvent],
        camera: CameraState,
        busy: bool = False,
    ) -> None:
        if busy or self.world_paused:
            self.emit_denied(events, "busy", scope="interaction")
            return

        target = self.interaction_candidate(camera)
        if target is None:
            self.emit_denied(events, "no_target", scope="interaction")
            return
        if self.danger_blocks_interaction():
            self.emit_denied(events, "blocked", target_id=target.id, scope="near_enemy")
            return

        if target.kind == "water_station":
            if target.supply == "working":
                self.start_interaction(
                    events,
                    kind="water_refill",
                    target=target,
                    title="WATER REFILL",
                    lines=("REFILLING WATER",),
                    duration_sec=float(self.config["resources"]["refill_duration_sec"]),
                )
            else:
                self.start_interaction(
                    events,
                    kind="message",
                    target=target,
                    title="NO WATER",
                    lines=("SUPPLY STOPPED",),
                    duration_sec=0.8,
                )
            return

        if target.kind == "solar_station":
            if self.config["simulation"]["day_phase"] != "day":
                self.emit_denied(events, "night", target_id=target.id, scope="interaction")
                return
            self.start_interaction(
                events,
                kind="energy_refill",
                target=target,
                title="ENERGY CHARGE",
                lines=("CHARGING BUDDY",),
                duration_sec=float(self.config["resources"]["solar_charge_duration_sec"]),
            )
            return

        self.start_interaction(
            events,
            kind="message",
            target=target,
            title="CHECKED",
            lines=self.object_ascii_lines(target),
            duration_sec=0.8,
        )

    def start_interaction(
        self,
        events: list[GameEvent],
        kind: str,
        target: StaticObject,
        title: str,
        lines: tuple[str, ...],
        duration_sec: float,
    ) -> None:
        self.player.barrier_active = False
        self.interaction = InteractionState(
            kind=kind,
            object_id=target.id,
            title=title,
            lines=lines,
            duration_sec=duration_sec,
        )
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="interaction_started",
                actor_id="player",
                target_id=target.id,
                world_position=(target.x, 0.0, target.z),
                payload={"interaction_kind": kind, "duration_sec": duration_sec},
            )
        )

    def update_paused(self, dt: float) -> list[GameEvent]:
        events: list[GameEvent] = []
        if self.interaction is None:
            self.last_events = events
            return events

        self.interaction.elapsed_sec += max(0.0, dt)
        if self.interaction.progress < 1.0:
            self.last_events = events
            return events

        interaction = self.interaction
        target = self.world.object_by_id(interaction.object_id)
        if interaction.kind == "water_refill":
            self.water = self.water_max
            self.debug.completed_refills += 1
            events.append(
                self.event_queue.emit(
                    world_tick=self.world_tick,
                    kind="resource_refilled",
                    actor_id="player",
                    target_id=interaction.object_id,
                    world_position=object_position(target, self.player.x, self.player.z),
                    payload={"resource": "water"},
                )
            )
        elif interaction.kind == "energy_refill":
            self.energy = self.energy_max
            self.debug.completed_refills += 1
            events.append(
                self.event_queue.emit(
                    world_tick=self.world_tick,
                    kind="resource_refilled",
                    actor_id="buddy",
                    target_id=interaction.object_id,
                    world_position=object_position(target, self.player.x, self.player.z),
                    payload={"resource": "energy"},
                )
            )

        self.interaction = None
        self.last_events = events
        return events

    def cancel_interaction(self) -> list[GameEvent]:
        events: list[GameEvent] = []
        if self.interaction is None:
            return events
        interaction = self.interaction
        target = self.world.object_by_id(interaction.object_id)
        self.interaction = None
        self.debug.cancelled_interactions += 1
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="interaction_cancelled",
                actor_id="player",
                target_id=interaction.object_id,
                world_position=object_position(target, self.player.x, self.player.z),
                payload={"interaction_kind": interaction.kind},
            )
        )
        self.last_events = events
        return events

    def interaction_candidate(self, camera: CameraState | None = None) -> StaticObject | None:
        interaction_range = float(self.config["interaction"]["range"])
        candidates = []
        for obj in self.world.objects:
            if not obj.inspectable:
                continue
            distance = math.hypot(obj.x - self.player.x, obj.z - self.player.z)
            if distance > interaction_range:
                continue
            if camera is not None:
                marker = camera.project(Vec3(obj.x, max(8.0, obj.height), obj.z))
                if marker is None:
                    continue
                if not (
                    0.0 <= marker.x <= camera.viewport_width
                    and 0.0 <= marker.y <= camera.viewport_height
                ):
                    continue
            candidates.append((distance, obj.id, obj))
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item[0], item[1]))[2]

    def object_ascii_lines(self, obj: StaticObject) -> tuple[str, ...]:
        if obj.text_key is None:
            return ("CHECKED",)
        text = self.world.texts.get(obj.text_key, {})
        lines = tuple(str(line).upper() for line in text.get("ascii", ()))
        return lines or ("CHECKED",)

    def danger_blocks_interaction(self) -> bool:
        if self.world.point_in_safe_zone(self.player.x, self.player.z):
            return False
        radius = float(self.config["interaction"]["danger_block_radius"])
        return any(
            enemy.state not in {"DEFEATED"}
            and math.hypot(enemy.x - self.player.x, enemy.z - self.player.z) <= radius
            for enemy in self.enemies
        )

    def update_enemies(self, dt: float) -> None:
        for enemy in self.enemies:
            if enemy.state == "DEFEATED":
                continue
            if enemy.state == "REPELLED":
                self.update_repelled_enemy(enemy, dt)
                continue
            if enemy.state == "REST":
                enemy.state_timer = max(0.0, enemy.state_timer - dt)
                if enemy.state_timer <= 0.0:
                    self.resolve_enemy_after_rest(enemy)
                continue
            if enemy.state == "RETURN_HOME":
                self.move_enemy_towards(
                    enemy, enemy.home_x, enemy.home_z, self.enemy_speed(enemy), dt
                )
                if self.enemy_home_distance(enemy) <= 1.0:
                    enemy.x = enemy.home_x
                    enemy.z = enemy.home_z
                    enemy.state = "IDLE"
                continue

            if enemy.kind != "normal":
                continue
            if self.enemy_home_distance(enemy) > self.enemy_leash(enemy):
                enemy.state = "RETURN_HOME"
                continue
            if enemy.state == "IDLE":
                if self.should_normal_approach(enemy):
                    enemy.state = "APPROACH"
                continue
            if enemy.state == "APPROACH":
                if not self.should_normal_approach(enemy):
                    enemy.state = "RETURN_HOME" if self.enemy_home_distance(enemy) > 2.0 else "IDLE"
                    continue
                moved = self.move_enemy_towards(
                    enemy, self.player.x, self.player.z, self.enemy_speed(enemy), dt
                )
                if moved <= 1e-4:
                    enemy.state = "REST"
                    enemy.state_timer = 0.5

    def update_repelled_enemy(self, enemy: EnemyState, dt: float) -> None:
        active_dt = min(dt, max(enemy.state_timer, 0.0))
        if active_dt > 0.0:
            self.move_enemy(
                enemy, enemy.push_x_per_sec * active_dt, enemy.push_z_per_sec * active_dt
            )
        enemy.state_timer = max(0.0, enemy.state_timer - dt)
        if enemy.state_timer <= 0.0:
            enemy.push_x_per_sec = 0.0
            enemy.push_z_per_sec = 0.0
            enemy.state = "REST"
            enemy.state_timer = self.enemy_rest_seconds(enemy)

    def resolve_enemy_after_rest(self, enemy: EnemyState) -> None:
        if self.enemy_home_distance(enemy) > 2.0:
            enemy.state = "RETURN_HOME"
        elif self.should_normal_approach(enemy):
            enemy.state = "APPROACH"
        else:
            enemy.state = "IDLE"

    def should_normal_approach(self, enemy: EnemyState) -> bool:
        if enemy.kind != "normal":
            return False
        if self.world.point_in_safe_zone(self.player.x, self.player.z):
            return False
        if self.enemy_home_distance(enemy) > self.enemy_leash(enemy):
            return False
        return math.hypot(enemy.x - self.player.x, enemy.z - self.player.z) <= float(
            self.config["enemy"]["normal"]["aggro_radius"]
        )

    def move_enemy_towards(
        self, enemy: EnemyState, target_x: float, target_z: float, speed: float, dt: float
    ) -> float:
        dx = target_x - enemy.x
        dz = target_z - enemy.z
        distance = math.hypot(dx, dz)
        if distance <= 1e-6:
            return 0.0
        amount = min(speed * dt, distance)
        return self.move_enemy(enemy, dx / distance * amount, dz / distance * amount)

    def move_enemy(self, enemy: EnemyState, delta_x: float, delta_z: float) -> float:
        before_x = enemy.x
        before_z = enemy.z
        enemy.x, enemy.z = self.world.move_enemy_circle_sliding(
            enemy.x,
            enemy.z,
            delta_x,
            delta_z,
            self.enemy_radius(enemy),
        )
        return math.hypot(enemy.x - before_x, enemy.z - before_z)

    def resolve_barrier_contacts(self, events: list[GameEvent]) -> None:
        barrier_radius = float(self.config["barrier"]["radius"])
        for enemy in self.enemies:
            if enemy.state in {"DEFEATED", "REPELLED", "REST"}:
                continue
            if math.hypot(enemy.x - self.player.x, enemy.z - self.player.z) <= (
                barrier_radius + self.enemy_radius(enemy)
            ):
                self.repel_enemy(enemy, events)

    def repel_enemy(self, enemy: EnemyState, events: list[GameEvent]) -> None:
        dx = enemy.x - self.player.x
        dz = enemy.z - self.player.z
        length = math.hypot(dx, dz)
        if length <= 1e-6:
            dx, dz = stable_direction(enemy.id)
        else:
            dx /= length
            dz /= length

        barrier = self.config["barrier"]
        push_distance = float(
            barrier["normal_push_distance"]
            if enemy.kind == "normal"
            else barrier["abnormal_push_distance"]
        )
        duration = max(float(barrier["push_duration_sec"]), 1e-6)
        enemy.state = "REPELLED"
        enemy.state_timer = duration
        enemy.push_x_per_sec = dx * push_distance / duration
        enemy.push_z_per_sec = dz * push_distance / duration
        self.debug.barrier_repels += 1
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="barrier_repelled",
                actor_id="player",
                target_id=enemy.id,
                world_position=(enemy.x, 0.0, enemy.z),
                payload={"enemy_kind": enemy.kind},
            )
        )

    def resolve_player_contacts(self, events: list[GameEvent]) -> None:
        if self.player.barrier_active or self.player.invulnerable_remaining > 0.0:
            return
        if self.world.point_in_safe_zone(self.player.x, self.player.z):
            return
        for enemy in self.enemies:
            if enemy.state in {"DEFEATED", "REPELLED", "REST", "CAPTURED"}:
                continue
            if self.player_overlaps_enemy(enemy):
                self.knock_player_from(enemy)
                self.player.stun_remaining = float(self.config["player"]["contact_stun_sec"])
                self.player.invulnerable_remaining = float(
                    self.config["player"]["invulnerable_sec"]
                )
                self.debug.player_contacts += 1
                events.append(
                    self.event_queue.emit(
                        world_tick=self.world_tick,
                        kind="player_contacted",
                        actor_id=enemy.id,
                        target_id="player",
                        world_position=(self.player.x, 0.0, self.player.z),
                        payload={"enemy_kind": enemy.kind},
                    )
                )
                return

    def player_overlaps_enemy(self, enemy: EnemyState) -> bool:
        closest_x = min(
            max(enemy.x, self.player.x - self.player_half_x), self.player.x + self.player_half_x
        )
        closest_z = min(
            max(enemy.z, self.player.z - self.player_half_z), self.player.z + self.player_half_z
        )
        return (enemy.x - closest_x) ** 2 + (enemy.z - closest_z) ** 2 <= self.enemy_radius(
            enemy
        ) ** 2

    def knock_player_from(self, enemy: EnemyState) -> None:
        dx = self.player.x - enemy.x
        dz = self.player.z - enemy.z
        length = math.hypot(dx, dz)
        if length <= 1e-6:
            if math.hypot(self.player.last_move_x, self.player.last_move_z) > 1e-6:
                dx = -self.player.last_move_x
                dz = -self.player.last_move_z
            else:
                dx, dz = stable_direction(enemy.id)
        else:
            dx /= length
            dz /= length
        distance = float(self.config["player"]["contact_knockback"])
        self.player.x, self.player.z = self.world.move_player_sliding(
            self.player.x,
            self.player.z,
            dx * distance,
            dz * distance,
            self.player_half_x,
            self.player_half_z,
        )

    def enemy_radius(self, enemy: EnemyState) -> float:
        return float(self.config["enemy"][enemy.kind]["radius"])

    def enemy_speed(self, enemy: EnemyState) -> float:
        if enemy.kind == "normal":
            return float(self.config["enemy"]["normal"]["move_speed"])
        return float(self.config["enemy"]["abnormal"]["approach_speed"])

    def enemy_leash(self, enemy: EnemyState) -> float:
        return float(self.config["enemy"][enemy.kind]["home_leash_radius"])

    def enemy_home_distance(self, enemy: EnemyState) -> float:
        return math.hypot(enemy.x - enemy.home_x, enemy.z - enemy.home_z)

    def enemy_rest_seconds(self, enemy: EnemyState) -> float:
        barrier = self.config["barrier"]
        if enemy.kind == "normal":
            return float(barrier["normal_rest_sec"])
        return float(barrier["abnormal_rest_sec"])

    def enemy_by_id(self, enemy_id: str) -> EnemyState | None:
        for enemy in self.enemies:
            if enemy.id == enemy_id:
                return enemy
        return None

    def emit_denied(
        self,
        events: list[GameEvent],
        reason: str,
        target_id: str | None = None,
        **payload: Any,
    ) -> None:
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="action_denied",
                actor_id="player",
                target_id=target_id,
                world_position=(self.player.x, 0.0, self.player.z),
                payload={"reason": reason, **payload},
            )
        )
        self.debug.denied_actions += 1

    def update_buddy(self, camera: CameraState, dt: float) -> None:
        goal_x, goal_y, goal_z = self.buddy_goal(camera)
        self.buddy.goal_x = goal_x
        self.buddy.goal_y = goal_y
        self.buddy.goal_z = goal_z

        hard_limit = float(self.config["buddy"]["hard_follow_limit"])
        if self.buddy.distance_to_goal() > hard_limit:
            self.buddy.x = goal_x
            self.buddy.y = goal_y
            self.buddy.z = goal_z
            return

        alpha = smoothing_alpha(dt, float(self.config["buddy"]["follow_tau_sec"]))
        self.buddy.x += (goal_x - self.buddy.x) * alpha
        self.buddy.y += (goal_y - self.buddy.y) * alpha
        self.buddy.z += (goal_z - self.buddy.z) * alpha


def merge_intents(*intents: InputIntent) -> InputIntent:
    screen_x = 0.0
    screen_y = 0.0
    strength = 0.0
    barrier = False
    action_pressed = False
    interact_pressed = False
    for intent in intents:
        if intent.strength > strength:
            screen_x = intent.screen_x
            screen_y = intent.screen_y
            strength = intent.strength
        barrier = barrier or intent.barrier
        action_pressed = action_pressed or intent.action_pressed
        interact_pressed = interact_pressed or intent.interact_pressed
    return InputIntent(
        screen_x=screen_x,
        screen_y=screen_y,
        strength=strength,
        barrier=barrier,
        action_pressed=action_pressed,
        interact_pressed=interact_pressed,
    )


def object_position(
    obj: StaticObject | None, fallback_x: float, fallback_z: float
) -> tuple[float, float, float]:
    if obj is None:
        return (fallback_x, 0.0, fallback_z)
    return (obj.x, 0.0, obj.z)


def stable_direction(identifier: str) -> tuple[float, float]:
    bucket = sum(ord(char) for char in identifier) % 8
    angle = bucket * math.tau / 8.0
    return math.cos(angle), math.sin(angle)


def clamp_resource(value: float, maximum: float) -> float:
    return max(0.0, min(value, maximum))
