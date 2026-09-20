from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any

from drift_with_me.camera import camera_ground_axes, smoothing_alpha
from drift_with_me.events import EventQueue, GameEvent
from drift_with_me.math3d import (
    AffineCameraState,
    CameraState,
    Vec3,
    screen_to_ground_affine,
    screen_to_ground_point,
    screen_to_world_direction,
)
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
    dash_x: float = 0.0
    dash_z: float = 0.0


@dataclass(frozen=True)
class CombatActorSnapshot:
    x: float
    z: float
    state: str | None = None
    state_timer: float = 0.0
    push_x_per_sec: float = 0.0
    push_z_per_sec: float = 0.0
    dash_x: float = 0.0
    dash_z: float = 0.0
    last_move_x: float = 0.0
    last_move_z: float = 0.0


@dataclass(frozen=True)
class CombatSnapshot:
    player: CombatActorSnapshot
    enemy: CombatActorSnapshot
    enemy_id: str
    auto_move_goal: tuple[float, float] | None
    auto_move_path: tuple[tuple[float, float], ...]
    auto_move_stuck_elapsed: float


@dataclass
class CombatSession:
    enemy_id: str
    snapshot: CombatSnapshot
    player_return_x: float
    player_return_z: float
    enemy_return_x: float
    enemy_return_z: float
    duration_sec: float
    phase: str = "COMBAT_ENTRY"
    elapsed_sec: float = 0.0
    phase_elapsed_sec: float = 0.0
    pattern_id: str = ""
    marker_positions: tuple[float, ...] = ()
    marker_judgements: tuple[str | None, ...] = ()
    timing_elapsed_sec: float = 0.0
    defense_was_down: bool = False
    input_debounce_remaining: float = 0.0
    hit_count: int = 0
    result: str | None = None
    successful_defense_count: int = 0
    failed_round_count: int = 0
    outcome: str | None = None
    bubble_used: bool = False
    zap_used: bool = False
    victory_actor: str | None = None


@dataclass
class BubbleState:
    x: float
    z: float
    dir_x: float
    dir_z: float
    traveled: float = 0.0
    target_id: str | None = None


@dataclass
class InteractionState:
    kind: str
    object_id: str
    title: str
    lines: tuple[str, ...]
    duration_sec: float
    elapsed_sec: float = 0.0
    target_x: float | None = None
    target_z: float | None = None

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
    auto_move_goal_x: float | None = None
    auto_move_goal_z: float | None = None
    cancel_auto_move: bool = False


@dataclass
class DebugCounters:
    discarded_elapsed_count: int = 0
    fixed_steps_last_callback: int = 0
    denied_actions: int = 0
    barrier_repels: int = 0
    player_contacts: int = 0
    completed_refills: int = 0
    cancelled_interactions: int = 0
    bubbles_fired: int = 0
    enemies_captured: int = 0
    discharges: int = 0
    inspected_count: int = 0
    active_enemies: int = 0
    dormant_enemies: int = 0


class GameModel:
    def __init__(
        self, config: dict[str, Any], world: WorldData, culling_enabled: bool = True
    ) -> None:
        self.config = config
        self.world = world
        self.culling_enabled = culling_enabled
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
        self.bubble: BubbleState | None = None
        self.bubble_cooldown_remaining = 0.0
        self.actor_facing_target_x: float | None = None
        self.actor_facing_target_z: float | None = None
        self.actor_facing_target_remaining = 0.0
        self.inspected_object_ids: set[str] = set()
        self.active_enemy_ids: set[str] = set()
        self.auto_move_goal: tuple[float, float] | None = None
        self.auto_move_path: list[tuple[float, float]] = []
        self.auto_move_stuck_elapsed = 0.0
        self.manual_velocity_x = 0.0
        self.manual_velocity_z = 0.0
        self.combat_session: CombatSession | None = None
        self.combat_reentry_cooldowns: dict[str, float] = {}
        self.buddy_hard_follow_suppressed_remaining = 0.0
        self.refresh_active_enemies()

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
    def player_solid_margin(self) -> float:
        return max(0.0, float(self.config["player"].get("solid_collision_margin", 0.0)))

    @property
    def player_solid_half_x(self) -> float:
        return self.player_half_x + self.player_solid_margin

    @property
    def player_solid_half_z(self) -> float:
        return self.player_half_z + self.player_solid_margin

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
        self.bubble = None
        self.bubble_cooldown_remaining = 0.0
        self.actor_facing_target_x = None
        self.actor_facing_target_z = None
        self.actor_facing_target_remaining = 0.0
        self.inspected_object_ids = set()
        self.active_enemy_ids = set()
        self.auto_move_goal = None
        self.auto_move_path = []
        self.auto_move_stuck_elapsed = 0.0
        self.combat_session = None
        self.combat_reentry_cooldowns = {}
        self.buddy_hard_follow_suppressed_remaining = 0.0
        self.refresh_active_enemies()

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
        side_offset, behind_offset = self.buddy_goal_offsets(camera)
        goal_x = self.player.x + side_offset * screen_right.x - behind_offset * ground_forward.x
        goal_z = self.player.z + side_offset * screen_right.y - behind_offset * ground_forward.y
        return (
            self.world.walkable_rect.clamp_x(goal_x),
            float(buddy_config["height"]),
            self.world.walkable_rect.clamp_z(goal_z),
        )

    def buddy_goal_offsets(self, camera: CameraState) -> tuple[float, float]:
        buddy_config = self.config["buddy"]
        side_offset = float(buddy_config["offset_screen_right_world"])
        behind_offset = float(buddy_config["offset_behind_player_world"])
        if not bool(buddy_config.get("side_reposition_enabled", False)):
            return side_offset, behind_offset

        delta = self.player_screen_move_delta(camera)
        if delta is None:
            return side_offset, behind_offset
        screen_dx, screen_dy = delta
        min_screen_px = float(buddy_config.get("side_reposition_min_screen_px", 0.25))
        if abs(screen_dx) < min_screen_px or abs(screen_dx) < abs(screen_dy):
            return side_offset, behind_offset

        side_distance = float(
            buddy_config.get("side_reposition_screen_right_world", abs(side_offset))
        )
        side_offset = -math.copysign(side_distance, screen_dx)
        behind_offset = float(
            buddy_config.get("side_reposition_behind_player_world", behind_offset)
        )
        return side_offset, behind_offset

    def buddy_follow_tau(self, camera: CameraState) -> float:
        buddy_config = self.config["buddy"]
        if self.buddy_side_reposition_active(camera):
            return float(
                buddy_config.get(
                    "side_reposition_follow_tau_sec",
                    buddy_config["follow_tau_sec"],
                )
            )
        return float(buddy_config["follow_tau_sec"])

    def buddy_side_reposition_active(self, camera: CameraState) -> bool:
        buddy_config = self.config["buddy"]
        if not bool(buddy_config.get("side_reposition_enabled", False)):
            return False
        delta = self.player_screen_move_delta(camera)
        if delta is None:
            return False
        screen_dx, screen_dy = delta
        min_screen_px = float(buddy_config.get("side_reposition_min_screen_px", 0.25))
        return abs(screen_dx) >= min_screen_px and abs(screen_dx) >= abs(screen_dy)

    def player_screen_move_delta(self, camera: CameraState) -> tuple[float, float] | None:
        move_length = math.hypot(self.player.last_move_x, self.player.last_move_z)
        if move_length <= 1e-6:
            return None
        root = camera.project(Vec3(self.player.x, 0.0, self.player.z))
        moved = camera.project(
            Vec3(
                self.player.x + self.player.last_move_x / move_length * 16.0,
                0.0,
                self.player.z + self.player.last_move_z / move_length * 16.0,
            )
        )
        if root is None or moved is None:
            return None
        return moved.x - root.x, moved.y - root.y

    def step(self, intent: InputIntent, camera: CameraState, dt: float) -> list[GameEvent]:
        events: list[GameEvent] = []
        if self.world_paused:
            self.cancel_auto_move()
            self.player.barrier_active = False
            self.last_events = events
            return events

        self.buddy_hard_follow_suppressed_remaining = max(
            0.0,
            self.buddy_hard_follow_suppressed_remaining - max(0.0, dt),
        )
        self.update_combat_reentry_cooldowns(dt)
        if self.combat_session is not None:
            self.player.barrier_active = False
            self.update_combat_session(intent, camera, dt, events)
            self.last_events = events
            return events

        self.world_tick += 1
        self.action_lock_remaining = max(0.0, self.action_lock_remaining - dt)
        self.bubble_cooldown_remaining = max(0.0, self.bubble_cooldown_remaining - dt)
        self.actor_facing_target_remaining = max(0.0, self.actor_facing_target_remaining - dt)
        if self.actor_facing_target_remaining <= 0.0:
            self.actor_facing_target_x = None
            self.actor_facing_target_z = None
        self.player.stun_remaining = max(0.0, self.player.stun_remaining - dt)
        self.player.invulnerable_remaining = max(0.0, self.player.invulnerable_remaining - dt)

        manual_cancel = (
            intent.cancel_auto_move
            or intent.strength > 0.0
            or intent.barrier
            or intent.action_pressed
            or intent.interact_pressed
        )
        if manual_cancel:
            self.cancel_auto_move()

        if (
            not manual_cancel
            and intent.auto_move_goal_x is not None
            and intent.auto_move_goal_z is not None
        ):
            self.request_auto_move_goal(intent.auto_move_goal_x, intent.auto_move_goal_z, events)

        if intent.action_pressed:
            self.try_context_action(events, camera, busy=intent.barrier)

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
            speed = move_speed * max(0.0, min(intent.strength, 1.0))
            speed *= self.manual_screen_speed_scale(camera, direction)
            delta_x, delta_z = self.manual_inertia_delta(
                direction.x * speed, direction.y * speed, dt
            )
            self.move_player_by_delta(delta_x, delta_z)
        elif (
            not intent.barrier
            and not self.player.barrier_active
            and self.action_lock_remaining <= 0.0
            and self.player.stun_remaining <= 0.0
            and self.auto_move_goal is not None
        ):
            self.reset_manual_velocity()
            self.update_auto_move(events, dt)
        else:
            self.reset_manual_velocity()

        self.refresh_active_enemies()
        self.update_enemies(dt, events)
        self.update_bubble(dt, events)
        if self.player.barrier_active:
            self.resolve_barrier_contacts(events)
        self.resolve_player_contacts(events)

        self.update_buddy(camera, dt)

        self.last_events = events
        return events

    def manual_inertia_delta(
        self, target_vx: float, target_vz: float, dt: float
    ) -> tuple[float, float]:
        player_config = self.config.get("player", {})
        if not bool(player_config.get("manual_inertia_enabled", True)):
            self.manual_velocity_x = target_vx
            self.manual_velocity_z = target_vz
            return target_vx * dt, target_vz * dt
        accel_tau = max(1e-6, float(player_config.get("manual_inertia_accel_tau_sec", 0.08)))
        reverse_tau = max(
            accel_tau, float(player_config.get("manual_inertia_reverse_tau_sec", 0.18))
        )
        current_speed = math.hypot(self.manual_velocity_x, self.manual_velocity_z)
        target_speed = math.hypot(target_vx, target_vz)
        dot_velocity = self.manual_velocity_x * target_vx + self.manual_velocity_z * target_vz
        tau = (
            reverse_tau
            if current_speed > 1e-6 and target_speed > 1e-6 and dot_velocity < 0.0
            else accel_tau
        )
        alpha = 1.0 - math.exp(-max(0.0, dt) / tau)
        self.manual_velocity_x += (target_vx - self.manual_velocity_x) * alpha
        self.manual_velocity_z += (target_vz - self.manual_velocity_z) * alpha
        return self.manual_velocity_x * dt, self.manual_velocity_z * dt

    def reset_manual_velocity(self) -> None:
        self.manual_velocity_x = 0.0
        self.manual_velocity_z = 0.0

    def cancel_auto_move(self) -> None:
        self.auto_move_goal = None
        self.auto_move_path = []
        self.auto_move_stuck_elapsed = 0.0

    def manual_screen_speed_scale(self, camera: Any, direction: Any) -> float:
        player_config = self.config.get("player", {})
        projection_config = self.config.get("projection", {})
        if projection_config.get("mode") != "affine":
            return 1.0
        if not bool(player_config.get("manual_affine_screen_speed_equalize", True)):
            return 1.0
        if abs(direction.x) <= 1e-9 and abs(direction.y) <= 1e-9:
            return 1.0
        affine_config = projection_config.get("affine", {})
        basis_x = affine_config.get("basis_x", [1.0, 0.0])
        basis_z = affine_config.get("basis_z", [0.0, 1.0])
        viewport = affine_config.get(
            "reference_viewport", [camera.viewport_width, camera.viewport_height]
        )
        viewport_scale = (
            float(camera.viewport_width) / float(viewport[0]) if float(viewport[0]) > 1e-9 else 1.0
        )
        projected = math.hypot(
            (direction.x * float(basis_x[0]) + direction.y * float(basis_z[0])) * viewport_scale,
            (direction.x * float(basis_x[1]) + direction.y * float(basis_z[1])) * viewport_scale,
        )
        if projected <= 1e-9 or not math.isfinite(projected):
            return 1.0
        reference_direction = screen_to_world_direction(
            camera,
            self.player.x,
            self.player.z,
            1.0,
            0.0,
        )
        reference_projected = math.hypot(
            (reference_direction.x * float(basis_x[0]) + reference_direction.y * float(basis_z[0]))
            * viewport_scale,
            (reference_direction.x * float(basis_x[1]) + reference_direction.y * float(basis_z[1]))
            * viewport_scale,
        )
        if reference_projected <= 1e-9 or not math.isfinite(reference_projected):
            return 1.0
        raw_scale = reference_projected / projected
        blend = max(
            0.0,
            min(1.0, float(player_config.get("manual_affine_screen_speed_blend", 0.35))),
        )
        scale = 1.0 + (raw_scale - 1.0) * blend
        max_scale = max(1.0, float(player_config.get("manual_affine_screen_speed_max_scale", 1.55)))
        return max(1.0, min(scale, max_scale))

    def request_auto_move_goal(self, goal_x: float, goal_z: float, events: list[GameEvent]) -> None:
        auto_move = self.config.get("auto_move", {})
        if not bool(auto_move.get("enabled", False)):
            return
        if not math.isfinite(goal_x) or not math.isfinite(goal_z):
            self.emit_denied(events, "auto_move_blocked", scope="auto_move")
            return
        if self.world.collides_player(
            goal_x,
            goal_z,
            self.player_solid_half_x,
            self.player_solid_half_z,
        ):
            self.emit_denied(events, "auto_move_blocked", scope="auto_move")
            return
        if not self.auto_move_path_clear(goal_x, goal_z):
            path = self.find_auto_move_path(goal_x, goal_z)
            if path is None:
                self.emit_denied(events, "auto_move_no_path", scope="auto_move")
                return
        else:
            path = [(goal_x, goal_z)]
        self.auto_move_goal = (goal_x, goal_z)
        self.auto_move_path = path
        self.auto_move_stuck_elapsed = 0.0

    def auto_move_path_clear(self, goal_x: float, goal_z: float) -> bool:
        radius = self.auto_move_nav_radius()
        return self.has_line_of_sight(self.player.x, self.player.z, goal_x, goal_z, radius=radius)

    def auto_move_nav_radius(self) -> float:
        auto_move = self.config.get("auto_move", {})
        clearance = float(auto_move.get("nav_clearance_world", 0.0))
        return max(self.player_solid_half_x, self.player_solid_half_z) + max(0.0, clearance)

    def find_auto_move_path(self, goal_x: float, goal_z: float) -> list[tuple[float, float]] | None:
        auto_move = self.config.get("auto_move", {})
        if not bool(auto_move.get("astar_enabled", True)):
            return None

        grid = float(auto_move.get("nav_grid_world", 16.0))
        if not math.isfinite(grid) or grid <= 0.0:
            return None
        radius = self.auto_move_nav_radius()
        walkable = self.world.walkable_rect
        cols = max(1, math.floor((walkable.width - radius * 2.0) / grid) + 1)
        rows = max(1, math.floor((walkable.depth - radius * 2.0) / grid) + 1)

        def node_position(node: tuple[int, int]) -> tuple[float, float]:
            ix, iz = node
            return walkable.min_x + radius + ix * grid, walkable.min_z + radius + iz * grid

        walkable_cache: dict[tuple[int, int], bool] = {}

        def node_walkable(node: tuple[int, int]) -> bool:
            value = walkable_cache.get(node)
            if value is not None:
                return value
            x, z = node_position(node)
            value = not self.world.collides_player(x, z, radius, radius)
            walkable_cache[node] = value
            return value

        def line_clear(a: tuple[float, float], b: tuple[float, float]) -> bool:
            return self.has_line_of_sight(a[0], a[1], b[0], b[1], radius=radius)

        def link_candidates(x: float, z: float) -> list[tuple[float, tuple[int, int]]]:
            limit = max(1, int(auto_move.get("max_link_candidates", 32)))
            nodes: list[tuple[float, tuple[int, int]]] = []
            origin = (x, z)
            for iz in range(rows):
                for ix in range(cols):
                    node = (ix, iz)
                    if not node_walkable(node):
                        continue
                    nx, nz = node_position(node)
                    if not line_clear(origin, (nx, nz)):
                        continue
                    nodes.append((math.hypot(nx - x, nz - z), node))
            nodes.sort(key=lambda item: (item[0], item[1]))
            return nodes[:limit]

        start = (self.player.x, self.player.z)
        goal = (goal_x, goal_z)
        start_links = link_candidates(*start)
        goal_links = link_candidates(*goal)
        if not start_links or not goal_links:
            return None

        goal_nodes = {node for _distance, node in goal_links}
        open_heap: list[tuple[float, int, tuple[int, int]]] = []
        best_cost: dict[tuple[int, int], float] = {}
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {}
        closed_nodes: set[tuple[int, int]] = set()
        sequence = 0

        for distance, node in start_links:
            best_cost[node] = distance
            came_from[node] = None
            nx, nz = node_position(node)
            priority = distance + math.hypot(goal_x - nx, goal_z - nz)
            heapq.heappush(open_heap, (priority, sequence, node))
            sequence += 1

        max_nodes = max(1, int(auto_move.get("max_astar_nodes", 4096)))
        visited = 0
        found: tuple[int, int] | None = None
        while open_heap and visited < max_nodes:
            _priority, _sequence, node = heapq.heappop(open_heap)
            if node in closed_nodes:
                continue
            closed_nodes.add(node)
            current_cost = best_cost[node]
            visited += 1
            if node in goal_nodes:
                found = node
                break

            x, z = node_position(node)
            for neighbor in self.auto_move_neighbors(node, cols, rows):
                if not node_walkable(neighbor):
                    continue
                nx, nz = node_position(neighbor)
                if not line_clear((x, z), (nx, nz)):
                    continue
                step_cost = math.hypot(nx - x, nz - z)
                next_cost = current_cost + step_cost
                if next_cost >= best_cost.get(neighbor, math.inf):
                    continue
                best_cost[neighbor] = next_cost
                came_from[neighbor] = node
                priority = next_cost + math.hypot(goal_x - nx, goal_z - nz)
                heapq.heappush(open_heap, (priority, sequence, neighbor))
                sequence += 1

        if found is None:
            return None

        nodes: list[tuple[int, int]] = []
        node: tuple[int, int] | None = found
        while node is not None:
            nodes.append(node)
            node = came_from[node]
        nodes.reverse()
        points = [start, *(node_position(node) for node in nodes), goal]
        return self.smooth_auto_move_path(points)

    def auto_move_neighbors(
        self, node: tuple[int, int], cols: int, rows: int
    ) -> tuple[tuple[int, int], ...]:
        ix, iz = node
        neighbors: list[tuple[int, int]] = []
        for dz in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dz == 0:
                    continue
                nx = ix + dx
                nz = iz + dz
                if 0 <= nx < cols and 0 <= nz < rows:
                    neighbors.append((nx, nz))
        return tuple(neighbors)

    def smooth_auto_move_path(
        self, points: list[tuple[float, float]]
    ) -> list[tuple[float, float]] | None:
        if len(points) < 2:
            return None
        radius = self.auto_move_nav_radius()
        result: list[tuple[float, float]] = []
        anchor_index = 0
        while anchor_index < len(points) - 1:
            next_index = len(points) - 1
            while next_index > anchor_index + 1:
                if self.has_line_of_sight(
                    points[anchor_index][0],
                    points[anchor_index][1],
                    points[next_index][0],
                    points[next_index][1],
                    radius=radius,
                ):
                    break
                next_index -= 1
            result.append(points[next_index])
            anchor_index = next_index
        return result

    def update_auto_move(self, events: list[GameEvent], dt: float) -> None:
        if self.auto_move_goal is None or not self.auto_move_path:
            self.cancel_auto_move()
            return
        target_x, target_z = self.auto_move_path[0]
        dx = target_x - self.player.x
        dz = target_z - self.player.z
        distance = math.hypot(dx, dz)
        auto_move = self.config.get("auto_move", {})
        arrival_radius = float(auto_move.get("arrival_radius_world", 2.0))
        waypoint_radius = float(auto_move.get("waypoint_radius_world", 4.0))
        current_radius = arrival_radius if len(self.auto_move_path) == 1 else waypoint_radius
        if distance <= current_radius:
            self.auto_move_path.pop(0)
            self.auto_move_stuck_elapsed = 0.0
        if not self.auto_move_path:
            self.cancel_auto_move()
            return

        target_x, target_z = self.auto_move_path[0]
        dx = target_x - self.player.x
        dz = target_z - self.player.z
        distance = math.hypot(dx, dz)
        if distance <= 1e-6:
            return

        move_speed = float(self.config["player"]["move_speed"])
        travel = min(move_speed * dt, distance)
        moved = self.move_player_by_delta(dx / distance * travel, dz / distance * travel)
        remaining = math.hypot(target_x - self.player.x, target_z - self.player.z)
        current_radius = arrival_radius if len(self.auto_move_path) == 1 else waypoint_radius
        if remaining <= current_radius:
            self.auto_move_path.pop(0)
            self.auto_move_stuck_elapsed = 0.0
        if not self.auto_move_path:
            self.cancel_auto_move()
            return

        if moved <= max(0.01, travel * 0.1):
            self.auto_move_stuck_elapsed += dt
        else:
            self.auto_move_stuck_elapsed = 0.0

        if self.auto_move_stuck_elapsed >= float(auto_move.get("stuck_sec", 0.5)):
            self.cancel_auto_move()
            self.emit_denied(events, "auto_move_no_path", scope="auto_move")

    def move_player_by_delta(self, delta_x: float, delta_z: float) -> float:
        before_x = self.player.x
        before_z = self.player.z
        next_x, next_z = self.world.move_player_sliding(
            before_x,
            before_z,
            delta_x,
            delta_z,
            self.player_solid_half_x,
            self.player_solid_half_z,
        )
        self.player.x = next_x
        self.player.z = next_z
        moved = math.hypot(next_x - before_x, next_z - before_z)
        self.player.moved_distance += moved
        if moved > 1e-6:
            self.player.last_move_x = (next_x - before_x) / moved
            self.player.last_move_z = (next_z - before_z) / moved
        return moved

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

    def try_context_action(
        self,
        events: list[GameEvent],
        camera: CameraState,
        busy: bool = False,
    ) -> None:
        if busy or self.player.barrier_active or self.world_paused:
            self.emit_denied(events, "busy", scope="action")
            return

        captured = self.captured_enemy(camera)
        if captured is not None:
            self.try_discharge(captured, events, camera)
            return

        self.try_fire_bubble(events, camera)

    def try_fire_bubble(self, events: list[GameEvent], camera: CameraState) -> None:
        if self.bubble is not None:
            self.emit_denied(events, "busy", scope="bubble")
            return
        if self.captured_enemy(None) is not None:
            self.emit_denied(events, "busy", scope="bubble")
            return
        if self.bubble_cooldown_remaining > 0.0:
            self.emit_denied(events, "cooldown", scope="bubble")
            return

        target = self.bubble_target(camera)
        if target is None:
            self.emit_denied(events, "no_target", scope="bubble")
            return

        cost = float(self.config["resources"]["bubble_water_cost"])
        if self.water < cost:
            self.emit_denied(events, "insufficient_water", target_id=target.id, scope="bubble")
            return

        dx = target.x - self.player.x
        dz = target.z - self.player.z
        length = math.hypot(dx, dz)
        if length <= 1e-6:
            dx, dz = stable_direction(target.id)
        else:
            dx /= length
            dz /= length

        self.water = clamp_resource(self.water - cost, self.water_max)
        self.face_actor_toward(target.x, target.z)
        self.bubble = BubbleState(
            x=self.player.x,
            z=self.player.z,
            dir_x=dx,
            dir_z=dz,
            target_id=target.id,
        )
        self.bubble_cooldown_remaining = float(self.config["bubble"]["cooldown_sec"])
        self.action_lock_remaining = float(self.config["input"]["action_lock_sec"])
        self.debug.bubbles_fired += 1
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="bubble_fired",
                actor_id="player",
                target_id=target.id,
                world_position=(self.player.x, 0.0, self.player.z),
                payload={"water_cost": cost},
            )
        )

    def try_discharge(
        self,
        enemy: EnemyState,
        events: list[GameEvent],
        camera: CameraState,
    ) -> None:
        cost = float(self.config["resources"]["discharge_energy_cost"])
        if self.energy < cost:
            self.emit_denied(events, "insufficient_energy", target_id=enemy.id, scope="discharge")
            return
        if self.config["simulation"]["day_phase"] != "day" and not bool(
            self.config["discharge"]["enabled_at_night"]
        ):
            self.emit_denied(events, "night", target_id=enemy.id, scope="discharge")
            return
        if math.hypot(enemy.x - self.player.x, enemy.z - self.player.z) > float(
            self.config["discharge"]["range_from_player"]
        ):
            self.emit_denied(events, "out_of_range", target_id=enemy.id, scope="discharge")
            return
        if math.hypot(self.buddy.x - self.player.x, self.buddy.z - self.player.z) > float(
            self.config["discharge"]["max_buddy_player_distance"]
        ):
            self.emit_denied(events, "out_of_range", target_id=enemy.id, scope="buddy")
            return
        if not self.enemy_visible(enemy, camera):
            self.emit_denied(events, "target_changed", target_id=enemy.id, scope="discharge")
            return
        if not self.has_line_of_sight(self.player.x, self.player.z, enemy.x, enemy.z):
            self.emit_denied(events, "blocked", target_id=enemy.id, scope="discharge")
            return

        self.energy = clamp_resource(self.energy - cost, self.energy_max)
        self.face_actor_toward(enemy.x, enemy.z)
        enemy.state = "DEFEATED"
        enemy.state_timer = 0.0
        self.action_lock_remaining = float(self.config["input"]["action_lock_sec"])
        self.debug.discharges += 1
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="discharge_succeeded",
                actor_id="buddy",
                target_id=enemy.id,
                world_position=(enemy.x, 0.0, enemy.z),
                payload={"energy_cost": cost},
            )
        )

    def update_bubble(self, dt: float, events: list[GameEvent]) -> None:
        if self.bubble is None:
            return

        bubble = self.bubble
        speed = float(self.config["bubble"]["speed"])
        radius = float(self.config["bubble"]["radius"])
        max_range = float(self.config["bubble"]["max_range"])
        remaining_range = max_range - bubble.traveled
        travel = min(speed * dt, remaining_range)
        start_x = bubble.x
        start_z = bubble.z
        end_x = start_x + bubble.dir_x * travel
        end_z = start_z + bubble.dir_z * travel

        wall_t = self.first_wall_hit_t(start_x, start_z, end_x, end_z, radius)
        enemy_hit = self.first_bubble_enemy_hit(start_x, start_z, end_x, end_z, radius)
        enemy_t = enemy_hit[0] if enemy_hit is not None else None

        if wall_t is not None and (enemy_t is None or wall_t <= enemy_t):
            self.bubble = None
            return

        if enemy_hit is not None:
            hit_t, enemy = enemy_hit
            bubble.x = start_x + (end_x - start_x) * hit_t
            bubble.z = start_z + (end_z - start_z) * hit_t
            self.capture_enemy(enemy, events)
            self.bubble = None
            return

        bubble.x = end_x
        bubble.z = end_z
        bubble.traveled += travel
        if bubble.traveled >= max_range - 1e-6:
            self.bubble = None

    def capture_enemy(self, enemy: EnemyState, events: list[GameEvent]) -> None:
        enemy.state = "CAPTURED"
        enemy.state_timer = float(self.config["bubble"]["capture_duration_sec"])
        enemy.push_x_per_sec = 0.0
        enemy.push_z_per_sec = 0.0
        enemy.dash_x = 0.0
        enemy.dash_z = 0.0
        self.debug.enemies_captured += 1
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="enemy_captured",
                actor_id="bubble",
                target_id=enemy.id,
                world_position=(enemy.x, 0.0, enemy.z),
                payload={"capture_duration_sec": enemy.state_timer},
            )
        )

    def bubble_target(self, camera: CameraState) -> EnemyState | None:
        select_range = float(self.config["bubble"]["target_select_range"])
        candidates = []
        for enemy in self.enemies:
            if enemy.kind != "abnormal" or enemy.state in {"CAPTURED", "DEFEATED"}:
                continue
            distance = math.hypot(enemy.x - self.player.x, enemy.z - self.player.z)
            if distance > select_range:
                continue
            if not self.enemy_visible(enemy, camera):
                continue
            if not self.has_line_of_sight(self.player.x, self.player.z, enemy.x, enemy.z):
                continue
            candidates.append((distance, enemy.id, enemy))
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item[0], item[1]))[2]

    def captured_enemy(self, camera: CameraState | None) -> EnemyState | None:
        candidates = [enemy for enemy in self.enemies if enemy.state == "CAPTURED"]
        if camera is not None:
            candidates = [enemy for enemy in candidates if self.enemy_visible(enemy, camera)]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda enemy: (
                math.hypot(enemy.x - self.player.x, enemy.z - self.player.z),
                enemy.id,
            ),
        )

    def guard_threat(self) -> EnemyState | None:
        barrier_radius = float(self.config["barrier"]["radius"])
        candidates = []
        for enemy in self.enemies:
            if enemy.kind != "normal" or enemy.state in {"DEFEATED", "REPELLED", "REST"}:
                continue
            distance = math.hypot(enemy.x - self.player.x, enemy.z - self.player.z)
            if distance <= barrier_radius + self.enemy_radius(enemy):
                candidates.append((distance, enemy.id, enemy))
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item[0], item[1]))[2]

    def enemy_visible(self, enemy: EnemyState, camera: CameraState) -> bool:
        point = camera.project(Vec3(enemy.x, 4.0, enemy.z))
        return (
            point is not None
            and 0.0 <= point.x <= camera.viewport_width
            and 0.0 <= point.y <= camera.viewport_height
        )

    def has_line_of_sight(
        self,
        start_x: float,
        start_z: float,
        end_x: float,
        end_z: float,
        radius: float = 0.0,
    ) -> bool:
        min_x = min(start_x, end_x) - radius
        max_x = max(start_x, end_x) + radius
        min_z = min(start_z, end_z) - radius
        max_z = max(start_z, end_z) + radius
        for obj in self.world.query_solids(min_x, min_z, max_x, max_z):
            if (
                segment_aabb_time(
                    start_x,
                    start_z,
                    end_x,
                    end_z,
                    obj.min_x - radius,
                    obj.min_z - radius,
                    obj.max_x + radius,
                    obj.max_z + radius,
                )
                is not None
            ):
                return False
        return True

    def first_wall_hit_t(
        self, start_x: float, start_z: float, end_x: float, end_z: float, radius: float
    ) -> float | None:
        candidates: list[float] = []
        walkable = self.world.walkable_rect
        dx = end_x - start_x
        dz = end_z - start_z
        if dx < -1e-9:
            candidates.append((walkable.min_x + radius - start_x) / dx)
        elif dx > 1e-9:
            candidates.append((walkable.max_x - radius - start_x) / dx)
        if dz < -1e-9:
            candidates.append((walkable.min_z + radius - start_z) / dz)
        elif dz > 1e-9:
            candidates.append((walkable.max_z - radius - start_z) / dz)

        min_x = min(start_x, end_x) - radius
        max_x = max(start_x, end_x) + radius
        min_z = min(start_z, end_z) - radius
        max_z = max(start_z, end_z) + radius
        for obj in self.world.query_solids(min_x, min_z, max_x, max_z):
            hit = segment_aabb_time(
                start_x,
                start_z,
                end_x,
                end_z,
                obj.min_x - radius,
                obj.min_z - radius,
                obj.max_x + radius,
                obj.max_z + radius,
            )
            if hit is not None:
                candidates.append(hit)

        valid = [value for value in candidates if 0.0 <= value <= 1.0]
        if not valid:
            return None
        return min(valid)

    def first_bubble_enemy_hit(
        self, start_x: float, start_z: float, end_x: float, end_z: float, bubble_radius: float
    ) -> tuple[float, EnemyState] | None:
        hits = []
        for enemy in self.enemies:
            if enemy.kind != "abnormal" or enemy.state in {"CAPTURED", "DEFEATED"}:
                continue
            hit = segment_circle_time(
                start_x,
                start_z,
                end_x,
                end_z,
                enemy.x,
                enemy.z,
                bubble_radius + self.enemy_radius(enemy),
            )
            if hit is not None:
                hits.append((hit, enemy.id, enemy))
        if not hits:
            return None
        hit_t, _enemy_id, enemy = min(hits, key=lambda item: (item[0], item[1]))
        return hit_t, enemy

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
        if self.danger_blocks_interaction() and not self.is_enemy_interaction_target(target):
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
                    kind="inspect",
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

        if self.is_enemy_interaction_target(target):
            self.start_interaction(
                events,
                kind="inspect",
                target=target,
                title=f"ENEMY {self.enemy_kind_from_target(target).upper()}",
                lines=self.enemy_ascii_lines(target),
                duration_sec=0.8,
            )
            return

        self.start_interaction(
            events,
            kind="inspect",
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
        self.cancel_auto_move()
        self.player.barrier_active = False
        self.interaction = InteractionState(
            kind=kind,
            object_id=target.id,
            title=title,
            lines=lines,
            duration_sec=duration_sec,
            target_x=target.x,
            target_z=target.z,
        )
        if kind == "inspect":
            self.face_actor_toward(target.x, target.z)
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

    def face_actor_toward(self, target_x: float, target_z: float) -> None:
        if not math.isfinite(target_x) or not math.isfinite(target_z):
            return
        self.actor_facing_target_x = target_x
        self.actor_facing_target_z = target_z
        self.actor_facing_target_remaining = float(
            self.config.get("interaction", {}).get("actor_face_target_sec", 0.75)
        )

    def clear_actor_facing_target(self) -> None:
        self.actor_facing_target_x = None
        self.actor_facing_target_z = None
        self.actor_facing_target_remaining = 0.0

    def actor_facing_target(self) -> tuple[float, float] | None:
        if (
            self.interaction is not None
            and self.interaction.kind == "inspect"
            and self.interaction.target_x is not None
            and self.interaction.target_z is not None
        ):
            return self.interaction.target_x, self.interaction.target_z
        if (
            self.actor_facing_target_remaining > 0.0
            and self.actor_facing_target_x is not None
            and self.actor_facing_target_z is not None
        ):
            return self.actor_facing_target_x, self.actor_facing_target_z
        return None

    def update_paused(self, dt: float) -> list[GameEvent]:
        events: list[GameEvent] = []
        if self.interaction is None:
            self.last_events = events
            return events

        if self.interaction.kind == "inspect":
            self.last_events = events
            return events

        self.interaction.elapsed_sec += max(0.0, dt)
        if self.interaction.progress < 1.0:
            self.last_events = events
            return events

        return self.finish_interaction()

    def finish_interaction(self) -> list[GameEvent]:
        events: list[GameEvent] = []
        if self.interaction is None:
            self.last_events = events
            return events

        interaction = self.interaction
        if interaction.kind == "water_refill":
            self.water = self.water_max
            self.debug.completed_refills += 1
            events.append(
                self.event_queue.emit(
                    world_tick=self.world_tick,
                    kind="resource_refilled",
                    actor_id="player",
                    target_id=interaction.object_id,
                    world_position=self.interaction_world_position(interaction),
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
                    world_position=self.interaction_world_position(interaction),
                    payload={"resource": "energy"},
                )
            )
        elif interaction.kind == "inspect":
            first_read = interaction.object_id not in self.inspected_object_ids
            self.inspected_object_ids.add(interaction.object_id)
            self.debug.inspected_count = len(self.inspected_object_ids)
            events.append(
                self.event_queue.emit(
                    world_tick=self.world_tick,
                    kind="inspection_completed",
                    actor_id="player",
                    target_id=interaction.object_id,
                    world_position=self.interaction_world_position(interaction),
                    payload={"first_read": first_read},
                )
            )

        self.interaction = None
        self.clear_actor_facing_target()
        self.last_events = events
        return events

    def complete_interaction(self) -> list[GameEvent]:
        if self.interaction is None:
            return []
        self.interaction.elapsed_sec = self.interaction.duration_sec
        return self.finish_interaction()

    def cancel_interaction(self) -> list[GameEvent]:
        events: list[GameEvent] = []
        if self.interaction is None:
            return events
        interaction = self.interaction
        self.interaction = None
        self.clear_actor_facing_target()
        self.debug.cancelled_interactions += 1
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="interaction_cancelled",
                actor_id="player",
                target_id=interaction.object_id,
                world_position=self.interaction_world_position(interaction),
                payload={"interaction_kind": interaction.kind},
            )
        )
        self.last_events = events
        return events

    def interaction_world_position(
        self, interaction: InteractionState
    ) -> tuple[float, float, float]:
        if interaction.target_x is not None and interaction.target_z is not None:
            return (interaction.target_x, 0.0, interaction.target_z)
        return object_position(
            self.world.object_by_id(interaction.object_id),
            self.player.x,
            self.player.z,
        )

    def interaction_candidate(self, camera: CameraState | None = None) -> StaticObject | None:
        interaction_range = float(self.config["interaction"]["range"])
        candidates = []
        for obj in self.world.objects:
            if not obj.inspectable:
                continue
            distance = math.hypot(obj.x - self.player.x, obj.z - self.player.z)
            if distance > interaction_range:
                continue
            if not self.has_line_of_sight(self.player.x, self.player.z, obj.x, obj.z):
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
            candidates.append((distance, 0, obj.id, obj))
        for enemy in self.enemies:
            if not self.enemy_can_be_inspected(enemy):
                continue
            distance = math.hypot(enemy.x - self.player.x, enemy.z - self.player.z)
            if distance > self.enemy_interaction_range(enemy):
                continue
            if not self.has_line_of_sight(self.player.x, self.player.z, enemy.x, enemy.z):
                continue
            if camera is not None and not self.enemy_visible(enemy, camera):
                continue
            target = self.enemy_interaction_target(enemy)
            candidates.append((distance, 1, target.id, target))
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item[0], item[1], item[2]))[3]

    def object_ascii_lines(self, obj: StaticObject) -> tuple[str, ...]:
        if obj.text_key is None:
            return ("CHECKED",)
        text = self.world.texts.get(obj.text_key, {})
        lines = tuple(str(line).upper() for line in text.get("ascii", ()))
        return lines or ("CHECKED",)

    def enemy_interaction_target(self, enemy: EnemyState) -> StaticObject:
        radius = self.enemy_radius(enemy)
        return StaticObject(
            id=enemy.id,
            kind=f"enemy_{enemy.kind}",
            x=enemy.x,
            z=enemy.z,
            solid=False,
            half_x=radius,
            half_z=radius,
            height=max(8.0, radius * 2.0),
            inspectable=True,
        )

    def enemy_can_be_inspected(self, enemy: EnemyState) -> bool:
        return enemy.state not in {"DEFEATED", "REPELLED", "REST", "CAPTURED"}

    def enemy_interaction_range(self, enemy: EnemyState) -> float:
        return float(self.config["barrier"]["radius"]) + self.enemy_radius(enemy)

    @staticmethod
    def is_enemy_interaction_target(target: StaticObject) -> bool:
        return target.kind.startswith("enemy_")

    @staticmethod
    def enemy_kind_from_target(target: StaticObject) -> str:
        return target.kind.removeprefix("enemy_")

    def enemy_ascii_lines(self, target: StaticObject) -> tuple[str, ...]:
        enemy_kind = self.enemy_kind_from_target(target)
        if enemy_kind == "normal":
            return ("ENEMY NORMAL APPROACH", "ENEMY NORMAL GUARD")
        if enemy_kind == "abnormal":
            return ("ENEMY ABNORMAL CAPTURE", "ENEMY ABNORMAL DISCHARGE")
        return ("UNKNOWN ENEMY",)

    def danger_blocks_interaction(self) -> bool:
        if self.world.point_in_safe_zone(self.player.x, self.player.z):
            return False
        radius = float(self.config["interaction"]["danger_block_radius"])
        return any(
            enemy.state not in {"DEFEATED"}
            and math.hypot(enemy.x - self.player.x, enemy.z - self.player.z) <= radius
            for enemy in self.enemies
        )

    def update_enemies(self, dt: float, events: list[GameEvent]) -> None:
        for enemy in self.enemies:
            if enemy.state == "DEFEATED":
                continue
            if self.culling_enabled and enemy.id not in self.active_enemy_ids:
                continue
            if enemy.state == "CAPTURED":
                enemy.state_timer = max(0.0, enemy.state_timer - dt)
                if enemy.state_timer <= 0.0:
                    enemy.state = "RECOVER"
                    enemy.state_timer = float(self.config["bubble"]["release_grace_sec"])
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

            if enemy.kind == "abnormal":
                self.update_abnormal_enemy(enemy, dt, events)
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

    def update_abnormal_enemy(self, enemy: EnemyState, dt: float, events: list[GameEvent]) -> None:
        if enemy.state == "RECOVER":
            enemy.state_timer = max(0.0, enemy.state_timer - dt)
            if enemy.state_timer <= 0.0:
                self.resolve_abnormal_after_recover(enemy)
            return

        if enemy.state == "WINDUP":
            enemy.state_timer = max(0.0, enemy.state_timer - dt)
            if enemy.state_timer <= 0.0:
                enemy.state = "DASH"
                enemy.state_timer = float(self.config["enemy"]["abnormal"]["dash_duration_sec"])
            return

        if enemy.state == "DASH":
            dash_speed = float(self.config["enemy"]["abnormal"]["dash_speed"])
            expected = dash_speed * dt
            moved = self.move_enemy(enemy, enemy.dash_x * expected, enemy.dash_z * expected)
            enemy.state_timer = max(0.0, enemy.state_timer - dt)
            if enemy.state_timer <= 0.0 or moved < expected * 0.5:
                enemy.state = "RECOVER"
                enemy.state_timer = float(self.config["enemy"]["abnormal"]["recover_sec"])
            return

        if self.world.point_in_safe_zone(self.player.x, self.player.z):
            enemy.state = "RETURN_HOME" if self.enemy_home_distance(enemy) > 2.0 else "IDLE"
            return
        if self.enemy_home_distance(enemy) > self.enemy_leash(enemy):
            enemy.state = "RETURN_HOME"
            return

        distance_to_player = math.hypot(enemy.x - self.player.x, enemy.z - self.player.z)
        abnormal = self.config["enemy"]["abnormal"]
        if enemy.state == "IDLE":
            if distance_to_player <= float(abnormal["aggro_radius"]):
                enemy.state = "APPROACH"
            return

        if enemy.state == "APPROACH":
            if distance_to_player > float(abnormal["aggro_radius"]):
                enemy.state = "RETURN_HOME" if self.enemy_home_distance(enemy) > 2.0 else "IDLE"
                return
            if distance_to_player <= float(abnormal["windup_range"]):
                self.start_abnormal_windup(enemy, events)
                return
            moved = self.move_enemy_towards(
                enemy,
                self.player.x,
                self.player.z,
                float(abnormal["approach_speed"]),
                dt,
            )
            if moved <= 1e-4:
                enemy.state = "RECOVER"
                enemy.state_timer = float(abnormal["recover_sec"])

    def start_abnormal_windup(self, enemy: EnemyState, events: list[GameEvent]) -> None:
        dx = self.player.x - enemy.x
        dz = self.player.z - enemy.z
        length = math.hypot(dx, dz)
        if length <= 1e-6:
            dx, dz = stable_direction(enemy.id)
        else:
            dx /= length
            dz /= length
        enemy.dash_x = dx
        enemy.dash_z = dz
        enemy.state = "WINDUP"
        enemy.state_timer = float(self.config["enemy"]["abnormal"]["windup_sec"])
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="abnormal_windup_started",
                actor_id=enemy.id,
                target_id="player",
                world_position=(enemy.x, 0.0, enemy.z),
                payload={"dash_x": enemy.dash_x, "dash_z": enemy.dash_z},
            )
        )

    def resolve_abnormal_after_recover(self, enemy: EnemyState) -> None:
        if self.enemy_home_distance(enemy) > 2.0:
            enemy.state = "RETURN_HOME"
            return
        distance_to_player = math.hypot(enemy.x - self.player.x, enemy.z - self.player.z)
        if not self.world.point_in_safe_zone(
            self.player.x, self.player.z
        ) and distance_to_player <= float(self.config["enemy"]["abnormal"]["aggro_radius"]):
            enemy.state = "APPROACH"
        else:
            enemy.state = "IDLE"

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
            if enemy.state in {"DEFEATED", "REPELLED", "REST", "CAPTURED"}:
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

    def combat_v1_config(self) -> dict[str, Any]:
        config = self.config.get("combat_v1", {})
        return config if isinstance(config, dict) else {}

    def combat_v1_enabled(self) -> bool:
        config = self.combat_v1_config()
        feature_flag = config.get("feature_flag", {})
        key = "combat_v1_enabled"
        default = bool(config.get("enabled", False))
        if isinstance(feature_flag, dict):
            key = str(feature_flag.get("key", key))
            default = bool(feature_flag.get("bat001_default", default))
        return bool(self.config.get(key, default))

    def update_combat_reentry_cooldowns(self, dt: float) -> None:
        if not self.combat_reentry_cooldowns:
            return
        expired: list[str] = []
        for enemy_id, remaining in self.combat_reentry_cooldowns.items():
            next_remaining = max(0.0, remaining - dt)
            if next_remaining <= 0.0:
                expired.append(enemy_id)
            else:
                self.combat_reentry_cooldowns[enemy_id] = next_remaining
        for enemy_id in expired:
            self.combat_reentry_cooldowns.pop(enemy_id, None)

    def update_combat_session(
        self,
        intent: InputIntent,
        camera: CameraState | AffineCameraState,
        dt: float,
        events: list[GameEvent],
    ) -> None:
        session = self.combat_session
        if session is None:
            return
        elapsed = max(0.0, dt)
        session.elapsed_sec += elapsed
        session.phase_elapsed_sec += elapsed
        session.input_debounce_remaining = max(0.0, session.input_debounce_remaining - elapsed)
        defense_pressed = (
            intent.barrier
            and not session.defense_was_down
            and session.input_debounce_remaining <= 0.0
        )
        session.defense_was_down = intent.barrier

        if session.phase == "COMBAT_ENTRY":
            if session.phase_elapsed_sec >= self.combat_duration_sec():
                self.advance_combat_phase(session, "COMBAT_READY", events)
            return
        if session.phase == "COMBAT_READY":
            if session.phase_elapsed_sec >= self.combat_ready_total_sec():
                self.advance_combat_phase(session, "PARRY_TIMING", events)
            return
        if session.phase == "ENEMY_WINDUP":
            if session.phase_elapsed_sec >= self.combat_windup_sec():
                self.advance_combat_phase(session, "ENEMY_CHARGE", events)
            return
        if session.phase == "ENEMY_CHARGE":
            if session.phase_elapsed_sec >= self.combat_charge_normal_sec():
                self.advance_combat_phase(session, "PREIMPACT_SLOW", events)
            return
        if session.phase == "PREIMPACT_SLOW":
            if session.phase_elapsed_sec >= self.combat_preimpact_slow_sec():
                self.advance_combat_phase(session, "COMBAT_READY", events)
            return
        if session.phase == "PARRY_TIMING":
            self.update_combat_parry_timing(session, defense_pressed, elapsed, events)
            return
        if session.phase == "PARRY_RESOLVE":
            if session.phase_elapsed_sec >= self.combat_resolve_sec(session):
                if session.result == "perfect":
                    self.advance_combat_phase(session, "PERFECT_FREEZE", events)
                elif session.outcome == "player_knockback":
                    self.advance_combat_phase(session, "COMBAT_EXIT_PLAYER_KNOCKBACK", events)
                elif session.outcome == "deflect":
                    self.advance_combat_phase(session, "COMBAT_EXIT_DEFLECT", events)
                else:
                    self.advance_combat_phase(session, "ENEMY_WINDUP", events)
            return
        if session.phase == "PERFECT_FREEZE":
            if session.phase_elapsed_sec >= self.combat_perfect_hold_sec():
                if not self.combat_bubble_counter_available(session):
                    session.outcome = "deflect"
                    self.advance_combat_phase(session, "COMBAT_EXIT_DEFLECT", events)
                else:
                    self.advance_combat_phase(session, "PERFECT_BUBBLE_WINDOW", events)
            return
        if session.phase == "PERFECT_BUBBLE_WINDOW":
            if intent.action_pressed:
                self.try_combat_counter_bubble(session, events)
                return
            if session.phase_elapsed_sec >= self.combat_bubble_window_sec():
                session.outcome = "deflect"
                self.advance_combat_phase(session, "COMBAT_EXIT_DEFLECT", events)
            return
        if session.phase == "PERFECT_ZAP_WINDOW":
            if intent.action_pressed:
                self.try_combat_counter_zap(session, events)
                return
            if session.phase_elapsed_sec >= self.combat_zap_window_sec():
                session.outcome = "capture"
                self.advance_combat_phase(session, "COMBAT_EXIT_COUNTER", events)
            return
        if session.phase == "COMBAT_EXIT_DEFLECT":
            if session.phase_elapsed_sec >= self.combat_deflect_knockback_sec():
                self.start_combat_victory_cue(session, events)
            return
        if session.phase == "COMBAT_EXIT_COUNTER":
            if session.phase_elapsed_sec >= self.combat_deflect_knockback_sec():
                self.start_combat_victory_cue(session, events)
            return
        if session.phase == "COMBAT_EXIT_PLAYER_KNOCKBACK":
            if session.phase_elapsed_sec >= self.combat_player_knockback_sec():
                self.prepare_combat_restore_jump(session, camera, events)
            return
        if session.phase == "VICTORY_CUE":
            if session.phase_elapsed_sec >= self.combat_victory_cue_sec():
                self.prepare_combat_restore_jump(session, camera, events)
            return
        if session.phase == "COMBAT_RESTORE_JUMP":
            if session.phase_elapsed_sec >= self.combat_restore_jump_sec():
                self.restore_combat_session(events)
            return

    def advance_combat_phase(
        self, session: CombatSession, phase: str, events: list[GameEvent]
    ) -> None:
        session.phase = phase
        session.phase_elapsed_sec = 0.0
        if phase == "PARRY_TIMING":
            session.timing_elapsed_sec = 0.0
            session.marker_judgements = tuple(None for _ in session.marker_positions)
            session.hit_count = 0
            session.result = None
        if phase in {"PERFECT_BUBBLE_WINDOW", "PERFECT_ZAP_WINDOW"}:
            session.input_debounce_remaining = 0.0
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="combat_phase_changed",
                actor_id=session.enemy_id,
                target_id="player",
                world_position=(self.player.x, 0.0, self.player.z),
                payload={"phase": phase},
            )
        )
        if phase == "PERFECT_FREEZE":
            events.append(
                self.event_queue.emit(
                    world_tick=self.world_tick,
                    kind="combat_perfect_started",
                    actor_id="player",
                    target_id=session.enemy_id,
                    world_position=(self.player.x, 0.0, self.player.z),
                    payload={"hit_count": session.hit_count},
                )
            )
        elif phase == "COMBAT_EXIT_DEFLECT":
            events.append(
                self.event_queue.emit(
                    world_tick=self.world_tick,
                    kind="combat_deflect_started",
                    actor_id="player",
                    target_id=session.enemy_id,
                    world_position=(self.player.x, 0.0, self.player.z),
                    payload={"combat_outcome": session.outcome},
                )
            )
        elif phase == "COMBAT_EXIT_PLAYER_KNOCKBACK":
            events.append(
                self.event_queue.emit(
                    world_tick=self.world_tick,
                    kind="combat_player_knockback_started",
                    actor_id=session.enemy_id,
                    target_id="player",
                    world_position=(self.player.x, 0.0, self.player.z),
                    payload={
                        "combat_outcome": session.outcome,
                        "failed_round_count": session.failed_round_count,
                    },
                )
            )

    def update_combat_parry_timing(
        self,
        session: CombatSession,
        defense_pressed: bool,
        dt: float,
        events: list[GameEvent],
    ) -> None:
        sweep_sec = self.combat_parry_sweep_sec()
        radius = self.combat_parry_hit_radius_normalized()
        session.timing_elapsed_sec = min(sweep_sec, session.timing_elapsed_sec + max(0.0, dt))
        slider = self.combat_timing_slider_position(session)
        if slider is None:
            return
        if defense_pressed:
            hit_index = self.combat_marker_hit_index(session, slider, radius)
            if hit_index is None:
                events.append(
                    self.event_queue.emit(
                        world_tick=self.world_tick,
                        kind="combat_parry_input_missed",
                        actor_id="player",
                        target_id=session.enemy_id,
                        world_position=(self.player.x, 0.0, self.player.z),
                        payload={"slider": slider},
                    )
                )
            else:
                self.resolve_combat_marker(session, hit_index, "HIT", slider, events)
                session.input_debounce_remaining = self.combat_parry_input_debounce_sec()
        for index, marker in enumerate(session.marker_positions):
            if (
                index < len(session.marker_judgements)
                and session.marker_judgements[index] is None
                and slider > marker + radius
            ):
                self.resolve_combat_marker(session, index, "MISS", slider, events)
        if session.timing_elapsed_sec >= sweep_sec:
            for index in range(len(session.marker_positions)):
                if (
                    index < len(session.marker_judgements)
                    and session.marker_judgements[index] is None
                ):
                    self.resolve_combat_marker(session, index, "MISS", slider, events)
            self.resolve_combat_round(session, events)

    def combat_marker_hit_index(
        self, session: CombatSession, slider: float, radius: float
    ) -> int | None:
        best_index: int | None = None
        best_distance = radius
        for index, marker in enumerate(session.marker_positions):
            if (
                index >= len(session.marker_judgements)
                or session.marker_judgements[index] is not None
            ):
                continue
            distance = abs(slider - marker)
            if distance <= best_distance:
                best_distance = distance
                best_index = index
        return best_index

    def resolve_combat_marker(
        self,
        session: CombatSession,
        index: int,
        judgement: str,
        slider: float,
        events: list[GameEvent],
    ) -> None:
        if index < 0 or index >= len(session.marker_judgements):
            return
        if session.marker_judgements[index] is not None:
            return
        judgements = list(session.marker_judgements)
        judgements[index] = judgement
        session.marker_judgements = tuple(judgements)
        session.hit_count = sum(1 for item in session.marker_judgements if item == "HIT")
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="combat_marker_judged",
                actor_id="player",
                target_id=session.enemy_id,
                world_position=(self.player.x, 0.0, self.player.z),
                payload={
                    "index": index,
                    "judgement": judgement,
                    "marker": session.marker_positions[index],
                    "slider": slider,
                },
            )
        )
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="combat_marker_hit" if judgement == "HIT" else "combat_marker_miss",
                actor_id="player",
                target_id=session.enemy_id,
                world_position=(self.player.x, 0.0, self.player.z),
                payload={
                    "index": index,
                    "judgement": judgement,
                    "marker": session.marker_positions[index],
                    "slider": slider,
                },
            )
        )

    def resolve_combat_round(self, session: CombatSession, events: list[GameEvent]) -> None:
        hit_count = sum(1 for item in session.marker_judgements if item == "HIT")
        if hit_count >= self.combat_perfect_hits():
            result = "perfect"
        elif hit_count >= self.combat_success_min_hits():
            result = "defense_success"
        else:
            result = "failure"
        session.hit_count = hit_count
        session.result = result
        if result == "defense_success":
            session.successful_defense_count += 1
        elif result == "failure":
            session.failed_round_count += 1
        if session.successful_defense_count >= self.combat_successful_rounds_to_deflect():
            session.outcome = "deflect"
        if session.failed_round_count >= self.combat_failed_rounds_to_knockback():
            session.outcome = "player_knockback"
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="combat_timing_resolved",
                actor_id="player",
                target_id=session.enemy_id,
                world_position=(self.player.x, 0.0, self.player.z),
                payload={
                    "hit_count": hit_count,
                    "result": result,
                    "successful_defense_count": session.successful_defense_count,
                    "failed_round_count": session.failed_round_count,
                    "outcome": session.outcome,
                },
            )
        )
        self.advance_combat_phase(session, "PARRY_RESOLVE", events)

    def combat_duration_sec(self) -> float:
        entry = self.combat_v1_config().get("entry", {})
        if not isinstance(entry, dict):
            return 0.4
        duration = (
            float(entry.get("isolation_sec", 0.18))
            + float(entry.get("actor_settle_sec", 0.2))
            + float(entry.get("battle_banner_sec", 0.0))
        )
        return max(1.0 / 60.0, duration)

    def combat_enemy_charge_config(self) -> dict[str, Any]:
        charge = self.combat_v1_config().get("enemy_charge", {})
        return charge if isinstance(charge, dict) else {}

    def combat_parry_config(self) -> dict[str, Any]:
        parry = self.combat_v1_config().get("parry", {})
        return parry if isinstance(parry, dict) else {}

    def combat_time_scale_config(self) -> dict[str, Any]:
        time_scale = self.combat_v1_config().get("time_scale", {})
        return time_scale if isinstance(time_scale, dict) else {}

    def combat_defense_config(self) -> dict[str, Any]:
        defense = self.combat_v1_config().get("defense", {})
        return defense if isinstance(defense, dict) else {}

    def combat_counter_config(self) -> dict[str, Any]:
        counter = self.combat_v1_config().get("counter", {})
        return counter if isinstance(counter, dict) else {}

    def combat_ready_config(self) -> dict[str, Any]:
        ready = self.combat_v1_config().get("ready_sequence", {})
        return ready if isinstance(ready, dict) else {}

    def combat_victory_config(self) -> dict[str, Any]:
        victory = self.combat_v1_config().get("victory", {})
        return victory if isinstance(victory, dict) else {}

    def combat_ready_ready_sec(self) -> float:
        return max(0.0, float(self.combat_ready_config().get("ready_sec", 0.45)))

    def combat_ready_count_step_sec(self) -> float:
        return max(1.0 / 60.0, float(self.combat_ready_config().get("count_step_sec", 0.38)))

    def combat_ready_total_sec(self) -> float:
        return self.combat_ready_ready_sec() + self.combat_ready_count_step_sec() * 3.0

    def combat_ready_go_sec(self) -> float:
        return max(0.0, float(self.combat_ready_config().get("go_sec", 0.22)))

    def combat_windup_sec(self) -> float:
        return max(0.0, float(self.combat_enemy_charge_config().get("windup_sec", 0.7)))

    def combat_charge_sec(self) -> float:
        return max(0.0, float(self.combat_enemy_charge_config().get("charge_sec", 0.38)))

    def combat_preimpact_slow_sec(self) -> float:
        charge_sec = self.combat_charge_sec()
        configured = max(
            0.0, float(self.combat_enemy_charge_config().get("preimpact_slow_start_sec", 0.22))
        )
        return min(charge_sec, configured)

    def combat_charge_normal_sec(self) -> float:
        return max(0.0, self.combat_charge_sec() - self.combat_preimpact_slow_sec())

    def combat_charge_closest_approach_world(self) -> float:
        return max(
            0.0,
            float(self.combat_enemy_charge_config().get("closest_approach_world", 18.0)),
        )

    def combat_enemy_charge_progress(self, session: CombatSession | None = None) -> float:
        session = self.combat_session if session is None else session
        if session is None:
            return 0.0
        if session.phase == "PARRY_TIMING":
            slider = self.combat_timing_slider_position(session)
            return 0.0 if slider is None else max(0.0, min(slider, 1.0))
        if session.phase == "PARRY_RESOLVE":
            return 1.0
        return 0.0

    def combat_round_gap_sec(self) -> float:
        return max(0.0, float(self.combat_enemy_charge_config().get("round_gap_sec", 0.55)))

    def combat_parry_sweep_sec(self) -> float:
        return max(1.0 / 60.0, float(self.combat_parry_config().get("sweep_sec", 1.35)))

    def combat_parry_input_debounce_sec(self) -> float:
        return max(0.0, float(self.combat_parry_config().get("input_debounce_sec", 0.08)))

    def combat_parry_track_width_px(self) -> float:
        presentation = self.combat_v1_config().get("presentation_medium_512x236", {})
        candidates = []
        if isinstance(presentation, dict):
            candidates = presentation.get("timing_bar_candidates", [])
        width = 204.0
        if isinstance(candidates, list) and candidates:
            first = candidates[0]
            if isinstance(first, list | tuple) and len(first) >= 3:
                width = float(first[2])
        padding = max(0.0, float(self.combat_parry_config().get("track_padding_px", 12)))
        return max(1.0, width - padding * 2.0)

    def combat_parry_hit_radius_normalized(self) -> float:
        radius_px = max(0.0, float(self.combat_parry_config().get("hit_radius_px", 9)))
        return min(0.5, radius_px / self.combat_parry_track_width_px())

    def combat_parry_gate_radius_normalized(self) -> float:
        radius_px = max(0.0, float(self.combat_parry_config().get("gate_radius_px", 18)))
        return min(0.5, radius_px / self.combat_parry_track_width_px())

    def combat_success_min_hits(self) -> int:
        return max(1, int(self.combat_defense_config().get("normal_success_min_hits", 1)))

    def combat_perfect_hits(self) -> int:
        return max(1, int(self.combat_defense_config().get("perfect_hits", 3)))

    def combat_successful_rounds_to_deflect(self) -> int:
        return max(1, int(self.combat_defense_config().get("successful_rounds_to_deflect", 2)))

    def combat_failed_rounds_to_knockback(self) -> int:
        return max(1, int(self.combat_defense_config().get("failed_rounds_to_knockback", 3)))

    def combat_perfect_hold_sec(self) -> float:
        return max(0.0, float(self.combat_time_scale_config().get("perfect_hold_sec", 0.32)))

    def combat_bubble_window_sec(self) -> float:
        return max(0.0, float(self.combat_counter_config().get("bubble_window_sec", 1.2)))

    def combat_zap_window_sec(self) -> float:
        return max(0.0, float(self.combat_counter_config().get("zap_window_sec", 0.85)))

    def combat_victory_cue_sec(self) -> float:
        return max(0.0, float(self.combat_victory_config().get("cue_sec", 0.72)))

    def combat_bubble_water_cost(self) -> float:
        return max(0.0, float(self.config["resources"]["bubble_water_cost"]))

    def combat_zap_energy_cost(self) -> float:
        return max(0.0, float(self.config["resources"]["discharge_energy_cost"]))

    def combat_resolve_sec(self, session: CombatSession) -> float:
        if session.result == "failure":
            return max(0.0, float(self.combat_defense_config().get("failure_recovery_sec", 0.45)))
        return self.combat_round_gap_sec()

    def combat_deflect_knockback_sec(self) -> float:
        return max(0.0, float(self.combat_exit_config().get("knockback_visual_sec", 0.28)))

    def combat_player_knockback_sec(self) -> float:
        return max(0.0, float(self.combat_exit_config().get("player_knockback_visual_sec", 0.32)))

    def combat_restore_jump_sec(self) -> float:
        return max(0.0, float(self.combat_exit_config().get("player_restore_jump_sec", 0.28)))

    def combat_restore_jump_height_world(self) -> float:
        return max(
            0.0,
            float(self.combat_exit_config().get("player_restore_jump_height_world", 16.0)),
        )

    def combat_buddy_follow_grace_sec(self) -> float:
        return max(0.0, float(self.combat_exit_config().get("buddy_follow_snap_grace_sec", 0.6)))

    def combat_actor_anchor_ground(
        self, camera: CameraState | AffineCameraState, actor: str
    ) -> tuple[float, float] | None:
        screen_anchor = self.combat_actor_screen_anchor(camera, actor)
        if screen_anchor is None:
            return None
        screen_x, screen_y = screen_anchor
        ground = (
            screen_to_ground_affine(camera, screen_x, screen_y)
            if isinstance(camera, AffineCameraState)
            else screen_to_ground_point(camera, screen_x, screen_y)
        )
        if ground is None:
            return None
        return ground.x, ground.y

    def combat_actor_screen_anchor(
        self, camera: CameraState | AffineCameraState, actor: str
    ) -> tuple[float, float] | None:
        presentation = self.combat_v1_config().get("presentation_medium_512x236", {})
        if not isinstance(presentation, dict):
            presentation = {}
        if actor == "player":
            key = "player_anchor_px"
            fallback = (214.0, 142.0)
        elif actor == "buddy":
            key = "fuse_victory_anchor_px"
            fallback = (175.0, 132.0)
        else:
            key = "enemy_anchor_px"
            fallback = (318.0, 112.0)
        raw_anchor = presentation.get(key, fallback)
        if not isinstance(raw_anchor, (list, tuple)) or len(raw_anchor) != 2:
            raw_anchor = fallback
        ref_w = 512.0
        ref_h = 236.0
        return (
            float(raw_anchor[0]) * camera.viewport_width / ref_w,
            float(raw_anchor[1]) * camera.viewport_height / ref_h,
        )

    def combat_enemy_knockback_world(self) -> float:
        return max(0.0, float(self.combat_exit_config().get("enemy_knockback_world", 34.0)))

    def combat_player_knockback_world(self, enemy: EnemyState | None = None) -> float:
        configured = max(0.0, float(self.combat_exit_config().get("player_knockback_world", 104.0)))
        if enemy is None:
            return configured
        aggro = float(self.config["enemy"][enemy.kind].get("aggro_radius", 80.0))
        clearance = self.enemy_radius(enemy) + max(self.player_half_x, self.player_half_z) + 6.0
        return max(configured, aggro + clearance)

    def combat_enemy_knockback_direction(
        self, session: CombatSession, enemy: EnemyState | None = None
    ) -> tuple[float, float]:
        dx = session.snapshot.enemy.x - session.snapshot.player.x
        dz = session.snapshot.enemy.z - session.snapshot.player.z
        length = math.hypot(dx, dz)
        if length <= 1e-6 and enemy is not None:
            dx = enemy.x - self.player.x
            dz = enemy.z - self.player.z
            length = math.hypot(dx, dz)
        if length <= 1e-6:
            dx = 1.0
            dz = 0.0
            length = 1.0
        return dx / length, dz / length

    def combat_enemy_presentation_offset(self, enemy: EnemyState) -> tuple[float, float]:
        session = self.combat_session
        if session is None or session.enemy_id != enemy.id:
            return (0.0, 0.0)
        if session.phase not in {"COMBAT_EXIT_DEFLECT", "COMBAT_EXIT_COUNTER", "VICTORY_CUE"}:
            return (0.0, 0.0)
        duration = self.combat_deflect_knockback_sec()
        dx, dz = self.combat_enemy_knockback_direction(session, enemy)
        if session.phase == "VICTORY_CUE" or duration <= 1e-6:
            t = 1.0
        else:
            t = max(0.0, min(session.phase_elapsed_sec / duration, 1.0))
        eased = 1.0 - (1.0 - t) * (1.0 - t)
        distance = self.combat_enemy_knockback_world() * eased
        return (dx * distance, dz * distance)

    def enemy_presentation_position(self, enemy: EnemyState) -> tuple[float, float]:
        offset_x, offset_z = self.combat_enemy_presentation_offset(enemy)
        return (enemy.x + offset_x, enemy.z + offset_z)

    def combat_presentation_time_scale(self) -> float:
        session = self.combat_session
        if session is None:
            return 1.0
        if session.phase in {"PERFECT_FREEZE", "PERFECT_BUBBLE_WINDOW", "PERFECT_ZAP_WINDOW"}:
            return max(0.0, float(self.combat_time_scale_config().get("perfect_world", 0.12)))
        if session.phase != "PREIMPACT_SLOW":
            return 1.0
        return max(0.0, float(self.combat_time_scale_config().get("preimpact_world", 0.3)))

    def combat_victory_actor(self, session: CombatSession | None = None) -> str | None:
        session = self.combat_session if session is None else session
        if session is None or session.phase != "VICTORY_CUE":
            return None
        if session.victory_actor:
            return session.victory_actor
        return "buddy" if self.config["simulation"].get("day_phase") == "day" else "player"

    def combat_victory_progress(self, session: CombatSession | None = None) -> float:
        session = self.combat_session if session is None else session
        if session is None or session.phase != "VICTORY_CUE":
            return 0.0
        duration = self.combat_victory_cue_sec()
        if duration <= 1e-6:
            return 1.0
        return max(0.0, min(session.phase_elapsed_sec / duration, 1.0))

    def start_combat_victory_cue(self, session: CombatSession, events: list[GameEvent]) -> None:
        session.victory_actor = (
            "buddy" if self.config["simulation"].get("day_phase") == "day" else "player"
        )
        self.advance_combat_phase(session, "VICTORY_CUE", events)
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="combat_victory_cue_started",
                actor_id=session.victory_actor,
                target_id=session.enemy_id,
                world_position=(self.player.x, 0.0, self.player.z),
                payload={
                    "combat_outcome": session.outcome,
                    "victory_actor": session.victory_actor,
                    "duration_sec": self.combat_victory_cue_sec(),
                },
            )
        )

    def prepare_combat_restore_jump(
        self,
        session: CombatSession,
        camera: CameraState | AffineCameraState,
        events: list[GameEvent],
    ) -> None:
        enemy = self.enemy_by_id(session.enemy_id)
        player_x = session.snapshot.player.x
        player_z = session.snapshot.player.z
        if session.outcome == "player_knockback" and enemy is not None:
            session.enemy_return_x = session.snapshot.enemy.x
            session.enemy_return_z = session.snapshot.enemy.z
            dx = session.snapshot.player.x - session.snapshot.enemy.x
            dz = session.snapshot.player.z - session.snapshot.enemy.z
            length = math.hypot(dx, dz)
            if length <= 1e-6:
                dx, dz = stable_direction(f"{session.enemy_id}:player_knockback")
                length = math.hypot(dx, dz)
            dx /= length
            dz /= length
            distance = self.combat_player_knockback_world(enemy)
            desired_x = session.snapshot.player.x + dx * distance
            desired_z = session.snapshot.player.z + dz * distance
            player_x, player_z = self.find_combat_player_safe_along_direction(
                desired_x,
                desired_z,
                enemy.x,
                enemy.z,
                dx,
                dz,
                self.combat_min_safe_separation(enemy),
            )
        if self.world.collides_player(
            player_x, player_z, self.player_solid_half_x, self.player_solid_half_z
        ):
            player_x = session.player_return_x
            player_z = session.player_return_z
        session.player_return_x = player_x
        session.player_return_z = player_z
        if enemy is not None and session.outcome != "player_knockback":
            dx, dz = self.combat_enemy_knockback_direction(session, enemy)
            enemy_anchor = self.combat_actor_anchor_ground(camera, "enemy")
            base_enemy_x, base_enemy_z = (
                enemy_anchor
                if enemy_anchor is not None
                else (session.enemy_return_x, session.enemy_return_z)
            )
            desired_x = base_enemy_x + dx * self.combat_enemy_knockback_world()
            desired_z = base_enemy_z + dz * self.combat_enemy_knockback_world()
            min_separation = self.combat_min_safe_separation(enemy)
            session.enemy_return_x, session.enemy_return_z = (
                self.find_combat_enemy_safe_along_direction(
                    enemy,
                    desired_x,
                    desired_z,
                    player_x,
                    player_z,
                    dx,
                    dz,
                    min_separation,
                )
            )
        self.advance_combat_phase(session, "COMBAT_RESTORE_JUMP", events)

    def combat_counter_enemy(self, session: CombatSession | None = None) -> EnemyState | None:
        session = self.combat_session if session is None else session
        if session is None:
            return None
        return self.enemy_by_id(session.enemy_id)

    def combat_bubble_counter_available(self, session: CombatSession | None = None) -> bool:
        session = self.combat_session if session is None else session
        if session is None or session.bubble_used:
            return False
        if self.combat_counter_enemy(session) is None:
            return False
        return self.water + 1e-9 >= self.combat_bubble_water_cost()

    def combat_zap_counter_available(self, session: CombatSession | None = None) -> bool:
        session = self.combat_session if session is None else session
        if session is None or session.zap_used:
            return False
        enemy = self.combat_counter_enemy(session)
        if enemy is None or enemy.state == "DEFEATED":
            return False
        return self.energy + 1e-9 >= self.combat_zap_energy_cost()

    def combat_counter_action_mode(self) -> str:
        session = self.combat_session
        if session is None:
            return "NONE"
        if session.phase == "PERFECT_BUBBLE_WINDOW" and self.combat_bubble_counter_available(
            session
        ):
            return "BUBBLE"
        if session.phase == "PERFECT_ZAP_WINDOW" and self.combat_zap_counter_available(session):
            return "ZAP"
        return "NONE"

    def try_combat_counter_bubble(self, session: CombatSession, events: list[GameEvent]) -> None:
        if session.phase != "PERFECT_BUBBLE_WINDOW" or session.bubble_used:
            return
        enemy = self.combat_counter_enemy(session)
        if enemy is None or self.water + 1e-9 < self.combat_bubble_water_cost():
            session.outcome = "deflect"
            self.advance_combat_phase(session, "COMBAT_EXIT_DEFLECT", events)
            return

        cost = self.combat_bubble_water_cost()
        self.water = clamp_resource(self.water - cost, self.water_max)
        session.bubble_used = True
        self.face_actor_toward(enemy.x, enemy.z)
        self.debug.bubbles_fired += 1
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="bubble_fired",
                actor_id="player",
                target_id=enemy.id,
                world_position=(self.player.x, 0.0, self.player.z),
                payload={"water_cost": cost, "combat_counter": True},
            )
        )
        self.capture_enemy(enemy, events)
        if not self.combat_zap_counter_available(session):
            session.outcome = "capture"
            self.advance_combat_phase(session, "COMBAT_EXIT_COUNTER", events)
            return
        self.advance_combat_phase(session, "PERFECT_ZAP_WINDOW", events)

    def try_combat_counter_zap(self, session: CombatSession, events: list[GameEvent]) -> None:
        if session.phase != "PERFECT_ZAP_WINDOW" or session.zap_used:
            return
        enemy = self.combat_counter_enemy(session)
        if enemy is None:
            session.outcome = "capture"
            self.advance_combat_phase(session, "COMBAT_EXIT_COUNTER", events)
            return
        if self.energy + 1e-9 < self.combat_zap_energy_cost():
            session.outcome = "capture"
            self.advance_combat_phase(session, "COMBAT_EXIT_COUNTER", events)
            return

        cost = self.combat_zap_energy_cost()
        self.energy = clamp_resource(self.energy - cost, self.energy_max)
        session.zap_used = True
        session.outcome = "defeat"
        self.face_actor_toward(enemy.x, enemy.z)
        self.debug.discharges += 1
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="discharge_succeeded",
                actor_id="buddy",
                target_id=enemy.id,
                world_position=(enemy.x, 0.0, enemy.z),
                payload={"energy_cost": cost, "combat_counter": True},
            )
        )
        self.advance_combat_phase(session, "COMBAT_EXIT_COUNTER", events)

    def combat_timing_slider_position(self, session: CombatSession | None = None) -> float | None:
        session = self.combat_session if session is None else session
        if session is None:
            return None
        if session.phase == "COMBAT_READY":
            return 0.0
        if session.phase not in {"PARRY_TIMING", "PARRY_RESOLVE"}:
            return None
        return max(0.0, min(session.timing_elapsed_sec / self.combat_parry_sweep_sec(), 1.0))

    def combat_marker_patterns(self) -> tuple[tuple[float, ...], ...]:
        parry = self.combat_parry_config()
        marker_count = max(1, int(parry.get("marker_count", 3)))
        raw_patterns = parry.get("patterns_normalized", [])
        if not isinstance(raw_patterns, list):
            raw_patterns = []
        hit_radius = self.combat_parry_hit_radius_normalized()
        gate_radius = self.combat_parry_gate_radius_normalized()
        edge_margin = min(0.45, max(hit_radius, gate_radius * 0.5))
        min_gap = max(hit_radius * 2.0, 0.12)
        patterns: list[tuple[float, ...]] = []
        for raw in raw_patterns:
            if not isinstance(raw, list | tuple) or len(raw) != marker_count:
                continue
            pattern = tuple(float(value) for value in raw)
            if tuple(sorted(pattern)) != pattern:
                continue
            if pattern[0] < edge_margin or pattern[-1] > 1.0 - edge_margin:
                continue
            if any(b - a < min_gap for a, b in zip(pattern, pattern[1:], strict=False)):
                continue
            patterns.append(pattern)
        if patterns:
            return tuple(patterns)
        return ((0.22, 0.5, 0.78),)

    def combat_pattern_for_enemy(self, enemy: EnemyState) -> tuple[str, tuple[float, ...]]:
        patterns = self.combat_marker_patterns()
        seed = sum(ord(char) for char in enemy.id) + self.debug.player_contacts
        index = seed % len(patterns)
        return f"pattern_{index:02d}", patterns[index]

    def combat_exit_config(self) -> dict[str, Any]:
        exit_config = self.combat_v1_config().get("exit", {})
        return exit_config if isinstance(exit_config, dict) else {}

    def combat_enemy_stun_sec(self) -> float:
        return max(0.0, float(self.combat_exit_config().get("enemy_stun_sec", 1.5)))

    def combat_player_invulnerability_sec(self) -> float:
        return max(0.0, float(self.combat_exit_config().get("player_invulnerability_sec", 0.5)))

    def combat_reentry_cooldown_sec(self) -> float:
        return max(0.0, float(self.combat_exit_config().get("combat_reentry_cooldown_sec", 2.0)))

    def combat_min_safe_separation(self, enemy: EnemyState) -> float:
        configured = float(self.combat_exit_config().get("min_safe_separation_world", 18.0))
        non_overlap = self.enemy_radius(enemy) + max(self.player_half_x, self.player_half_z) + 0.5
        return max(configured, non_overlap)

    def combat_contact_on_cooldown(self, enemy: EnemyState) -> bool:
        return self.combat_reentry_cooldowns.get(enemy.id, 0.0) > 0.0

    def can_start_contact_combat(self, enemy: EnemyState) -> bool:
        if not self.combat_v1_enabled():
            return False
        if self.combat_session is not None:
            return False
        if enemy.kind not in {"normal", "abnormal"}:
            return False
        return not self.combat_contact_on_cooldown(enemy)

    def combat_snapshot_for(self, enemy: EnemyState) -> CombatSnapshot:
        return CombatSnapshot(
            player=CombatActorSnapshot(
                x=self.player.x,
                z=self.player.z,
                last_move_x=self.player.last_move_x,
                last_move_z=self.player.last_move_z,
            ),
            enemy=CombatActorSnapshot(
                x=enemy.x,
                z=enemy.z,
                state=enemy.state,
                state_timer=enemy.state_timer,
                push_x_per_sec=enemy.push_x_per_sec,
                push_z_per_sec=enemy.push_z_per_sec,
                dash_x=enemy.dash_x,
                dash_z=enemy.dash_z,
            ),
            enemy_id=enemy.id,
            auto_move_goal=self.auto_move_goal,
            auto_move_path=tuple(self.auto_move_path),
            auto_move_stuck_elapsed=self.auto_move_stuck_elapsed,
        )

    def start_contact_combat(self, enemy: EnemyState, events: list[GameEvent]) -> None:
        snapshot = self.combat_snapshot_for(enemy)
        min_separation = self.combat_min_safe_separation(enemy)
        enemy_return_x, enemy_return_z = self.find_combat_enemy_anchor(
            enemy,
            self.player.x,
            self.player.z,
            min_separation,
        )
        player_return_x, player_return_z = self.find_combat_player_anchor(
            self.player.x,
            self.player.z,
            enemy_return_x,
            enemy_return_z,
            enemy,
            min_separation,
        )
        enemy_return_x, enemy_return_z = self.find_combat_enemy_anchor(
            enemy,
            player_return_x,
            player_return_z,
            min_separation,
        )
        if not self.combat_player_anchor_safe(
            player_return_x, player_return_z, enemy_return_x, enemy_return_z, min_separation
        ):
            player_return_x, player_return_z = self.find_combat_player_anchor(
                player_return_x,
                player_return_z,
                enemy_return_x,
                enemy_return_z,
                enemy,
                min_separation,
            )

        self.cancel_auto_move()
        self.player.barrier_active = False
        self.face_actor_toward(enemy.x, enemy.z)
        pattern_id, marker_positions = self.combat_pattern_for_enemy(enemy)
        self.combat_session = CombatSession(
            enemy_id=enemy.id,
            snapshot=snapshot,
            player_return_x=player_return_x,
            player_return_z=player_return_z,
            enemy_return_x=enemy_return_x,
            enemy_return_z=enemy_return_z,
            duration_sec=self.combat_duration_sec(),
            pattern_id=pattern_id,
            marker_positions=marker_positions,
            marker_judgements=tuple(None for _ in marker_positions),
        )
        self.debug.player_contacts += 1
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="combat_started",
                actor_id=enemy.id,
                target_id="player",
                world_position=(self.player.x, 0.0, self.player.z),
                payload={
                    "enemy_kind": enemy.kind,
                    "player_return": (player_return_x, player_return_z),
                    "enemy_return": (enemy_return_x, enemy_return_z),
                    "duration_sec": self.combat_session.duration_sec,
                    "phase": self.combat_session.phase,
                    "pattern_id": pattern_id,
                    "marker_positions": marker_positions,
                },
            )
        )

    def restore_combat_session(self, events: list[GameEvent]) -> None:
        session = self.combat_session
        if session is None:
            return
        enemy = self.enemy_by_id(session.enemy_id)
        player_x = session.player_return_x
        player_z = session.player_return_z
        enemy_x = session.enemy_return_x
        enemy_z = session.enemy_return_z
        enemy_kind = "unknown"
        enemy_stun_sec = self.combat_enemy_stun_sec()
        player_invulnerability_sec = self.combat_player_invulnerability_sec()
        reentry_cooldown_sec = self.combat_reentry_cooldown_sec()

        if enemy is not None:
            enemy_kind = enemy.kind
            min_separation = self.combat_min_safe_separation(enemy)
            dx = enemy_x - player_x
            dz = enemy_z - player_z
            if math.hypot(dx, dz) <= 1e-6:
                dx, dz = self.combat_enemy_knockback_direction(session, enemy)
            enemy_x, enemy_z = self.find_combat_enemy_safe_along_direction(
                enemy, enemy_x, enemy_z, player_x, player_z, dx, dz, min_separation
            )
            if not self.combat_player_anchor_safe(
                player_x, player_z, enemy_x, enemy_z, min_separation
            ):
                player_x, player_z = self.find_combat_player_anchor(
                    player_x, player_z, enemy_x, enemy_z, enemy, min_separation
                )
            enemy.x = enemy_x
            enemy.z = enemy_z
            if session.outcome == "defeat":
                enemy.state = "DEFEATED"
                enemy.state_timer = 0.0
            elif session.outcome == "capture":
                enemy.state = "CAPTURED"
                enemy.state_timer = max(
                    enemy.state_timer,
                    float(self.config["bubble"]["capture_duration_sec"]),
                )
            else:
                enemy.state = "REST"
                enemy.state_timer = enemy_stun_sec
            enemy.push_x_per_sec = 0.0
            enemy.push_z_per_sec = 0.0
            enemy.dash_x = 0.0
            enemy.dash_z = 0.0
            if session.outcome not in {"capture", "defeat"}:
                self.combat_reentry_cooldowns[enemy.id] = reentry_cooldown_sec

        if not self.world.collides_player(
            player_x, player_z, self.player_solid_half_x, self.player_solid_half_z
        ):
            self.player.x = player_x
            self.player.z = player_z
        self.player.stun_remaining = 0.0
        self.player.invulnerable_remaining = max(
            self.player.invulnerable_remaining,
            player_invulnerability_sec,
        )
        self.player.barrier_active = False
        self.player.last_move_x = session.snapshot.player.last_move_x
        self.player.last_move_z = session.snapshot.player.last_move_z
        self.buddy_hard_follow_suppressed_remaining = max(
            self.buddy_hard_follow_suppressed_remaining,
            self.combat_buddy_follow_grace_sec(),
        )
        self.combat_session = None
        events.append(
            self.event_queue.emit(
                world_tick=self.world_tick,
                kind="combat_restored",
                actor_id=session.enemy_id,
                target_id="player",
                world_position=(self.player.x, 0.0, self.player.z),
                payload={
                    "enemy_kind": enemy_kind,
                    "enemy_stun_sec": enemy_stun_sec,
                    "player_invulnerability_sec": player_invulnerability_sec,
                    "reentry_cooldown_sec": reentry_cooldown_sec,
                    "combat_result": session.result,
                    "combat_hits": session.hit_count,
                    "combat_outcome": session.outcome,
                    "successful_defense_count": session.successful_defense_count,
                },
            )
        )

    def find_combat_player_anchor(
        self,
        start_x: float,
        start_z: float,
        enemy_x: float,
        enemy_z: float,
        enemy: EnemyState,
        min_separation: float,
    ) -> tuple[float, float]:
        if self.combat_player_anchor_safe(start_x, start_z, enemy_x, enemy_z, min_separation):
            return start_x, start_z
        preferred_x = start_x - enemy_x
        preferred_z = start_z - enemy_z
        if math.hypot(preferred_x, preferred_z) <= 1e-6:
            preferred_x = -self.player.last_move_x
            preferred_z = -self.player.last_move_z
        for x, z in self.combat_anchor_candidates(start_x, start_z, preferred_x, preferred_z):
            if self.combat_player_anchor_safe(x, z, enemy_x, enemy_z, min_separation):
                return x, z
        return start_x, start_z

    def find_combat_enemy_anchor(
        self,
        enemy: EnemyState,
        player_x: float,
        player_z: float,
        min_separation: float,
        start_x: float | None = None,
        start_z: float | None = None,
    ) -> tuple[float, float]:
        origin_x = enemy.x if start_x is None else start_x
        origin_z = enemy.z if start_z is None else start_z
        if self.combat_enemy_anchor_safe(
            enemy, origin_x, origin_z, player_x, player_z, min_separation
        ):
            return origin_x, origin_z
        preferred_x = origin_x - player_x
        preferred_z = origin_z - player_z
        for x, z in self.combat_anchor_candidates(origin_x, origin_z, preferred_x, preferred_z):
            if self.combat_enemy_anchor_safe(enemy, x, z, player_x, player_z, min_separation):
                return x, z
        return origin_x, origin_z

    def find_combat_enemy_safe_along_direction(
        self,
        enemy: EnemyState,
        desired_x: float,
        desired_z: float,
        player_x: float,
        player_z: float,
        direction_x: float,
        direction_z: float,
        min_separation: float,
    ) -> tuple[float, float]:
        length = math.hypot(direction_x, direction_z)
        if length <= 1e-6:
            direction_x = desired_x - player_x
            direction_z = desired_z - player_z
            length = math.hypot(direction_x, direction_z)
        if length <= 1e-6:
            direction_x, direction_z = stable_direction(f"{desired_x:.3f}:{desired_z:.3f}")
            length = math.hypot(direction_x, direction_z)
        direction_x /= length
        direction_z /= length
        if self.combat_enemy_anchor_safe(
            enemy, desired_x, desired_z, player_x, player_z, min_separation
        ):
            return desired_x, desired_z
        perpendicular_x = -direction_z
        perpendicular_z = direction_x
        candidate_offsets = (
            (8.0, 0.0),
            (16.0, 0.0),
            (24.0, 0.0),
            (32.0, 0.0),
            (48.0, 0.0),
            (64.0, 0.0),
            (96.0, 0.0),
            (128.0, 0.0),
            (0.0, 8.0),
            (0.0, -8.0),
            (8.0, 8.0),
            (8.0, -8.0),
            (16.0, 8.0),
            (16.0, -8.0),
            (0.0, 16.0),
            (0.0, -16.0),
            (8.0, 16.0),
            (8.0, -16.0),
            (16.0, 16.0),
            (16.0, -16.0),
            (24.0, 16.0),
            (24.0, -16.0),
            (0.0, 24.0),
            (0.0, -24.0),
            (16.0, 24.0),
            (16.0, -24.0),
            (32.0, 24.0),
            (32.0, -24.0),
            (24.0, 32.0),
            (24.0, -32.0),
            (48.0, 32.0),
            (48.0, -32.0),
            (64.0, 48.0),
            (64.0, -48.0),
        )
        for forward, lateral in candidate_offsets:
            x = desired_x + direction_x * forward + perpendicular_x * lateral
            z = desired_z + direction_z * forward + perpendicular_z * lateral
            if self.combat_enemy_anchor_safe(enemy, x, z, player_x, player_z, min_separation):
                return x, z
        return self.find_combat_enemy_anchor(
            enemy, player_x, player_z, min_separation, start_x=desired_x, start_z=desired_z
        )

    def find_combat_player_safe_along_direction(
        self,
        desired_x: float,
        desired_z: float,
        enemy_x: float,
        enemy_z: float,
        direction_x: float,
        direction_z: float,
        min_separation: float,
    ) -> tuple[float, float]:
        length = math.hypot(direction_x, direction_z)
        if length <= 1e-6:
            direction_x = desired_x - enemy_x
            direction_z = desired_z - enemy_z
            length = math.hypot(direction_x, direction_z)
        if length <= 1e-6:
            direction_x, direction_z = stable_direction(f"{desired_x:.3f}:{desired_z:.3f}:player")
            length = math.hypot(direction_x, direction_z)
        direction_x /= length
        direction_z /= length
        if self.combat_player_anchor_safe(desired_x, desired_z, enemy_x, enemy_z, min_separation):
            return desired_x, desired_z
        for distance in (8.0, 16.0, 24.0, 32.0, 48.0, 64.0, 96.0, 128.0):
            x = desired_x + direction_x * distance
            z = desired_z + direction_z * distance
            if self.combat_player_anchor_safe(x, z, enemy_x, enemy_z, min_separation):
                return x, z
        for x, z in self.combat_anchor_candidates(desired_x, desired_z, direction_x, direction_z):
            if self.combat_player_anchor_safe(x, z, enemy_x, enemy_z, min_separation):
                return x, z
        return desired_x, desired_z

    def combat_anchor_candidates(
        self, start_x: float, start_z: float, preferred_x: float, preferred_z: float
    ) -> tuple[tuple[float, float], ...]:
        length = math.hypot(preferred_x, preferred_z)
        if length <= 1e-6:
            preferred_x, preferred_z = stable_direction(f"{start_x:.3f}:{start_z:.3f}")
        else:
            preferred_x /= length
            preferred_z /= length
        base_angle = math.atan2(preferred_z, preferred_x)
        angle_offsets = (
            0.0,
            math.pi / 8.0,
            -math.pi / 8.0,
            math.pi / 4.0,
            -math.pi / 4.0,
            math.pi / 2.0,
            -math.pi / 2.0,
            math.pi,
        )
        candidates: list[tuple[float, float]] = []
        for radius in (18.0, 24.0, 32.0, 48.0, 64.0, 96.0, 128.0):
            for offset in angle_offsets:
                angle = base_angle + offset
                candidates.append(
                    (start_x + math.cos(angle) * radius, start_z + math.sin(angle) * radius)
                )
        return tuple(candidates)

    def combat_player_anchor_safe(
        self, x: float, z: float, enemy_x: float, enemy_z: float, min_separation: float
    ) -> bool:
        if self.world.collides_player(x, z, self.player_solid_half_x, self.player_solid_half_z):
            return False
        return math.hypot(x - enemy_x, z - enemy_z) >= min_separation

    def combat_enemy_anchor_safe(
        self,
        enemy: EnemyState,
        x: float,
        z: float,
        player_x: float,
        player_z: float,
        min_separation: float,
    ) -> bool:
        if self.world.collides_enemy_circle(x, z, self.enemy_radius(enemy)):
            return False
        return math.hypot(x - player_x, z - player_z) >= min_separation

    def resolve_player_contacts(self, events: list[GameEvent]) -> None:
        if self.player.barrier_active or self.player.invulnerable_remaining > 0.0:
            return
        if self.world.point_in_safe_zone(self.player.x, self.player.z):
            return
        for enemy in self.enemies:
            if enemy.state in {"DEFEATED", "REPELLED", "REST", "CAPTURED"}:
                continue
            if self.player_overlaps_enemy(enemy):
                if self.combat_v1_enabled() and enemy.kind in {"normal", "abnormal"}:
                    if self.combat_contact_on_cooldown(enemy):
                        return
                    if self.can_start_contact_combat(enemy):
                        self.start_contact_combat(enemy, events)
                        return
                self.cancel_auto_move()
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
            self.player_solid_half_x,
            self.player_solid_half_z,
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

    def refresh_active_enemies(self) -> None:
        if not self.culling_enabled:
            self.active_enemy_ids = {
                enemy.id for enemy in self.enemies if enemy.state != "DEFEATED"
            }
            self.debug.active_enemies = len(self.active_enemy_ids)
            self.debug.dormant_enemies = len(self.enemies) - self.debug.active_enemies
            return

        culling = self.config["culling"]
        enter_radius = float(culling["active_enter_radius"])
        exit_radius = float(culling["active_exit_radius"])
        next_active: set[str] = set()
        for enemy in self.enemies:
            if enemy.state == "DEFEATED":
                continue
            distance = math.hypot(enemy.x - self.player.x, enemy.z - self.player.z)
            pinned = enemy.state not in {"IDLE"}
            was_active = enemy.id in self.active_enemy_ids
            if pinned or distance <= enter_radius or (was_active and distance <= exit_radius):
                next_active.add(enemy.id)
        self.active_enemy_ids = next_active
        self.debug.active_enemies = len(next_active)
        self.debug.dormant_enemies = len(self.enemies) - len(next_active)

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
        if (
            self.buddy.distance_to_goal() > hard_limit
            and self.buddy_hard_follow_suppressed_remaining <= 0.0
        ):
            self.buddy.x = goal_x
            self.buddy.y = goal_y
            self.buddy.z = goal_z
            return

        alpha = smoothing_alpha(dt, self.buddy_follow_tau(camera))
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
    auto_move_goal_x: float | None = None
    auto_move_goal_z: float | None = None
    cancel_auto_move = False
    for intent in intents:
        if intent.strength > strength:
            screen_x = intent.screen_x
            screen_y = intent.screen_y
            strength = intent.strength
        barrier = barrier or intent.barrier
        action_pressed = action_pressed or intent.action_pressed
        interact_pressed = interact_pressed or intent.interact_pressed
        if intent.auto_move_goal_x is not None and intent.auto_move_goal_z is not None:
            auto_move_goal_x = intent.auto_move_goal_x
            auto_move_goal_z = intent.auto_move_goal_z
        cancel_auto_move = cancel_auto_move or intent.cancel_auto_move
    return InputIntent(
        screen_x=screen_x,
        screen_y=screen_y,
        strength=strength,
        barrier=barrier,
        action_pressed=action_pressed,
        interact_pressed=interact_pressed,
        auto_move_goal_x=auto_move_goal_x,
        auto_move_goal_z=auto_move_goal_z,
        cancel_auto_move=cancel_auto_move,
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


def segment_circle_time(
    start_x: float,
    start_z: float,
    end_x: float,
    end_z: float,
    center_x: float,
    center_z: float,
    radius: float,
) -> float | None:
    dx = end_x - start_x
    dz = end_z - start_z
    fx = start_x - center_x
    fz = start_z - center_z
    a = dx * dx + dz * dz
    if a <= 1e-12:
        return 0.0 if fx * fx + fz * fz <= radius * radius else None
    b = 2.0 * (fx * dx + fz * dz)
    c = fx * fx + fz * fz - radius * radius
    discriminant = b * b - 4.0 * a * c
    if discriminant < 0.0:
        return None
    root = math.sqrt(discriminant)
    t0 = (-b - root) / (2.0 * a)
    t1 = (-b + root) / (2.0 * a)
    candidates = [time for time in (t0, t1) if 0.0 <= time <= 1.0]
    if not candidates:
        return None
    return min(candidates)


def segment_aabb_time(
    start_x: float,
    start_z: float,
    end_x: float,
    end_z: float,
    min_x: float,
    min_z: float,
    max_x: float,
    max_z: float,
) -> float | None:
    dx = end_x - start_x
    dz = end_z - start_z
    t_min = 0.0
    t_max = 1.0
    for origin, delta, low, high in (
        (start_x, dx, min_x, max_x),
        (start_z, dz, min_z, max_z),
    ):
        if abs(delta) <= 1e-12:
            if origin < low or origin > high:
                return None
            continue
        inv_delta = 1.0 / delta
        t1 = (low - origin) * inv_delta
        t2 = (high - origin) * inv_delta
        axis_min = min(t1, t2)
        axis_max = max(t1, t2)
        t_min = max(t_min, axis_min)
        t_max = min(t_max, axis_max)
        if t_min > t_max:
            return None
    if t_min < 0.0 or t_min > 1.0:
        return None
    return t_min
