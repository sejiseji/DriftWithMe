from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from drift_with_me.events import EventQueue, GameEvent
from drift_with_me.math3d import CameraState, screen_to_world_direction
from drift_with_me.world import WorldData


@dataclass
class PlayerState:
    x: float
    z: float
    moved_distance: float = 0.0
    barrier_active: bool = False


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
        self.water = float(self.config["resources"]["water_start"])
        self.energy = float(self.config["resources"]["energy_start"])
        self.world_tick = 0
        self.debug = DebugCounters()
        self.last_events = []
        self.action_lock_remaining = 0.0

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

        self.last_events = events
        return events


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
