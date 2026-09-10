from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from drift_with_me.camera import camera_ground_axes, smoothing_alpha
from drift_with_me.events import EventQueue, GameEvent
from drift_with_me.math3d import CameraState, screen_to_world_direction
from drift_with_me.world import WorldData


@dataclass
class PlayerState:
    x: float
    z: float
    moved_distance: float = 0.0
    barrier_active: bool = False


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


class GameModel:
    def __init__(self, config: dict[str, Any], world: WorldData) -> None:
        self.config = config
        self.world = world
        self.event_queue = EventQueue()
        self.player = PlayerState(world.spawn_x, world.spawn_z)
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

    @property
    def buddy_cube_size(self) -> float:
        return float(self.config["buddy"]["cube_size"])

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
        self.world_tick += 1
        self.action_lock_remaining = max(0.0, self.action_lock_remaining - dt)

        if intent.action_pressed:
            events.append(
                self.event_queue.emit(
                    world_tick=self.world_tick,
                    kind="action_denied",
                    actor_id="player",
                    target_id=None,
                    world_position=(self.player.x, 0.0, self.player.z),
                    payload={"reason": "no_target", "scope": "E0_action_placeholder"},
                )
            )
            self.debug.denied_actions += 1

        self.player.barrier_active = intent.barrier
        if not intent.barrier and self.action_lock_remaining <= 0.0 and intent.strength > 0.0:
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
            self.player.moved_distance += (
                (next_x - before_x) ** 2 + (next_z - before_z) ** 2
            ) ** 0.5

        self.update_buddy(camera, dt)

        self.last_events = events
        return events

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
