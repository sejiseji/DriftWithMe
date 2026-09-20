from __future__ import annotations

import math
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass

from drift_with_me.effects import EffectSystem, EnemySnapshot, ReactiveEnvironmentState
from drift_with_me.hex_assets import (
    LoadedSpriteAsset,
    LoadedSpriteFrame,
    SpriteAssetLibrary,
    draw_scaled_sprite,
    placement_for_upright_height_billboard,
)
from drift_with_me.math3d import (
    CameraState,
    ProjectedPoint,
    Vec3,
    screen_to_ground_affine,
    screen_to_ground_point,
)
from drift_with_me.model import GameModel
from drift_with_me.world import (
    BakedGroundPatch,
    GroundDetail,
    GroundSurface,
    StaticObject,
    WorldData,
    WorldRect,
)

ATMOSPHERE_WEAK_PALETTE = ((0, 1), (1, 5))
ATMOSPHERE_MID_PALETTE = ((0, 1), (1, 5), (2, 5), (4, 5), (8, 5))
ATMOSPHERE_FAR_PALETTE = (
    (0, 5),
    (1, 5),
    (2, 5),
    (3, 13),
    (4, 5),
    (5, 13),
    (6, 13),
    (8, 5),
    (9, 13),
    (10, 13),
    (11, 13),
    (12, 13),
    (14, 13),
    (15, 13),
)
ATMOSPHERE_BAYER_4X4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)
ATMOSPHERE_MID_DITHER_CELLS = 2
ATMOSPHERE_FAR_DITHER_CELLS = 4
ATMOSPHERE_DITHER_MIN_STRENGTH = 0.5
ATMOSPHERE_DITHER_FOG_COLOR = 13
ATMOSPHERE_SHADOW_NEAR_CELLS = 12
ATMOSPHERE_SHADOW_MID_CELLS = 8
ATMOSPHERE_SHADOW_FAR_CELLS = 4
ATMOSPHERE_SHADOW_IMPORTANT_MIN_CELLS = 6

GRASSLAND_BAYER4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)
ATMOSPHERE_GROUND_DETAIL_STRENGTH = 1.0
ATMOSPHERE_NATURE_PROP_STRENGTH = 1.0
ATMOSPHERE_REACTIVE_PROP_STRENGTH = 1.0
ATMOSPHERE_EQUIPMENT_STRENGTH = 0.7
ATMOSPHERE_SOLID_STRENGTH = 0.8
ATMOSPHERE_DEFAULT_STATIC_STRENGTH = 0.5
ATMOSPHERE_ENEMY_STRENGTH = 0.35
ATMOSPHERE_BUDDY_STRENGTH = 0.15
ATMOSPHERE_PLAYER_STRENGTH = 0.1
GRASSLAND_MICRO_CLUMP_PATTERNS = (
    ((0.15, 0.24, 5, 0), (0.58, 0.38, 4, 1), (0.84, 0.78, 6, 0)),
    ((0.28, 0.18, 4, 1), (0.48, 0.68, 6, 0), (0.76, 0.42, 5, 2)),
    ((0.12, 0.70, 5, 2), (0.42, 0.32, 4, 0), (0.88, 0.58, 5, 0)),
    ((0.24, 0.52, 4, 0), (0.66, 0.22, 5, 2), (0.78, 0.86, 4, 1)),
)


@dataclass(frozen=True)
class DrawCommand:
    depth: float
    layer_bias: int
    stable_id: str
    draw: Callable[[], None]
    atmosphere_strength: float = 1.0


@dataclass(frozen=True)
class ScreenRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def max_x(self) -> int:
        return self.x + self.width

    @property
    def max_y(self) -> int:
        return self.y + self.height

    def overlaps(self, other: ScreenRect) -> bool:
        return (
            self.x < other.max_x
            and self.max_x > other.x
            and self.y < other.max_y
            and self.max_y > other.y
        )

    def contains(self, px: float, py: float, margin: float = 0.0) -> bool:
        return (
            self.x - margin <= px <= self.max_x + margin
            and self.y - margin <= py <= self.max_y + margin
        )


@dataclass(frozen=True)
class GrasslandTransitionCell:
    x0: float
    z0: float
    x1: float
    z1: float
    color: int


@dataclass(frozen=True)
class RenderStats:
    total_static_objects: int = 0
    candidate_chunks: int = 0
    candidate_static_objects: int = 0
    visible_static_objects: int = 0
    visible_ground_details: int = 0
    visible_grassland_micro_areas: int = 0
    visible_forest_light_spots: int = 0
    visible_ambient_motes: int = 0
    visible_baked_ground_patches: int = 0
    baked_ground_cache_size: int = 0
    draw_commands: int = 0
    active_enemies: int = 0
    dormant_enemies: int = 0


@dataclass(frozen=True)
class BakedGroundImage:
    image: object
    left: int
    top: int
    width: int
    height: int
    scale: int
    bucket_x: float
    bucket_z: float
    reference_center_x: float
    reference_center_y: float


@dataclass(frozen=True)
class ActorPresentation:
    x: float
    z: float
    jump_y: float = 0.0


class Renderer:
    SPIN_DIRECTION_VIEWS = (
        "right",
        "front_right",
        "front",
        "front_left",
        "left",
        "back_left",
        "back",
        "back_right",
    )

    def __init__(self, pyxel_module, sprite_assets: SpriteAssetLibrary | None = None) -> None:
        self.pyxel = pyxel_module
        self.sprite_assets = sprite_assets or SpriteAssetLibrary.empty()
        self._ground_source_pixels: dict[
            tuple[str, str, int], tuple[tuple[int, int, str], ...]
        ] = {}
        self._baked_ground_cache: dict[tuple[object, ...], BakedGroundImage] = {}
        self._active_baked_ground_patches: tuple[BakedGroundPatch, ...] = ()
        self._baked_ground_builds_this_frame = 0
        self.max_baked_ground_builds_per_frame = 1
        self.player_sprite_flipped_x = False
        self.player_sprite_view_name = "idle"
        self.buddy_sprite_view_name = "front_right"
        self._atmosphere_config: dict = {}
        self._active_atmosphere_dither_cells = 0
        self._active_atmosphere_dither_fog_color = ATMOSPHERE_DITHER_FOG_COLOR
        self._atmosphere_dither_cache: dict[tuple[str, str, str, int, int], LoadedSpriteFrame] = {}
        self._grassland_transition_cell_cache: dict[
            tuple[
                tuple[float, float, float, float],
                float,
                float,
                int,
                int,
                int,
                str,
            ],
            tuple[GrasslandTransitionCell, ...],
        ] = {}
        self._visible_grassland_micro_areas = 0
        self._visible_forest_light_spots = 0
        self._visible_ambient_motes = 0
        self.last_stats = RenderStats()

    def draw_scene(
        self,
        model: GameModel,
        camera: CameraState,
        presentation_time: float,
        debug: bool,
        effects: EffectSystem | None = None,
    ) -> None:
        pyxel = self.pyxel
        self._atmosphere_config = model.config.get("atmosphere", {})
        pyxel.cls(13)
        self.draw_ground(model.world, camera)
        self._active_baked_ground_patches = self.draw_baked_ground_patches(model, camera)
        self._visible_grassland_micro_areas = self.draw_grassland_micro_layer(model, camera)
        self._visible_forest_light_spots = self.draw_forest_light_layer(model, camera)
        self._visible_ambient_motes = self.draw_ambient_motes_layer(model, camera)
        self.draw_shallow_water_tiles(model, camera)
        self.draw_shallow_water_shoreline_tiles(model, camera)
        self.draw_shallow_water_symbols(model, camera, presentation_time)
        self.draw_ground_surfaces(model, camera)
        self.draw_background_effects(model, camera, effects)
        self.draw_walkable_boundary_overlay(model, camera)
        self.draw_safe_zones(model.world, camera)
        self.draw_auto_move_goal(model, camera, presentation_time)
        commands = self.world_commands(model, camera, presentation_time, effects)
        for command in sorted(
            commands, key=lambda item: (-item.depth, item.layer_bias, item.stable_id)
        ):
            with self.atmosphere_depth_effects(camera, command.depth, command.atmosphere_strength):
                command.draw()
        self.draw_barrier(model, camera)
        if model.combat_session is None and self.player_is_occluded(
            model, camera, presentation_time
        ):
            self.draw_player_outline(model, camera, presentation_time)
        self.draw_interaction_marker(model, camera)
        self.draw_action_marker(model, camera)
        self.draw_effects(model, camera, effects)
        self.draw_combat_bubble_counter(model, camera)
        self.draw_combat_defeat_special(model, camera)
        self.draw_combat_victory_cue(model, camera)
        if debug:
            self.draw_affine_debug_grid(model, camera)
            self.draw_debug_world(model, camera)

    def draw_ground(self, world: WorldData, camera: CameraState) -> None:
        pyxel = self.pyxel
        ground_color = 13
        border_color = 7
        ground_rect = self.visible_ground_draw_rect(world.visual_ground_rect, camera, margin_px=8.0)
        if ground_rect is None:
            return
        corners = [
            camera.project(Vec3(ground_rect.min_x, 0.0, ground_rect.min_z)),
            camera.project(Vec3(ground_rect.max_x, 0.0, ground_rect.min_z)),
            camera.project(Vec3(ground_rect.max_x, 0.0, ground_rect.max_z)),
            camera.project(Vec3(ground_rect.min_x, 0.0, ground_rect.max_z)),
        ]
        if all(point is not None for point in corners):
            p0, p1, p2, p3 = corners
            pyxel.tri(
                int(p0.x), int(p0.y), int(p1.x), int(p1.y), int(p2.x), int(p2.y), ground_color
            )
            pyxel.tri(
                int(p0.x), int(p0.y), int(p2.x), int(p2.y), int(p3.x), int(p3.y), ground_color
            )

        self.draw_world_rect(camera, world.walkable_rect, border_color)

    def draw_walkable_boundary_overlay(self, model: GameModel, camera: CameraState) -> None:
        config = model.config.get("world_debug", {})
        if not config.get("show_walkable_boundary", True):
            return
        color = int(config.get("walkable_boundary_color", 7))
        self.draw_world_rect(camera, model.world.walkable_rect, color)

    def visible_ground_draw_rect(
        self, rect: WorldRect, camera: CameraState, margin_px: float
    ) -> WorldRect | None:
        if not self.camera_is_affine(camera):
            return rect
        visible_rect = self.grassland_micro_visible_world_rect(camera, margin_px)
        if visible_rect is None:
            return rect
        vx0, vz0, vx1, vz1 = visible_rect
        min_x = max(rect.min_x, vx0)
        min_z = max(rect.min_z, vz0)
        max_x = min(rect.max_x, vx1)
        max_z = min(rect.max_z, vz1)
        if min_x >= max_x or min_z >= max_z:
            return None
        return WorldRect(min_x, min_z, max_x, max_z)

    def draw_world_rect(self, camera: CameraState, rect: WorldRect, color: int) -> None:
        self.draw_world_line(
            camera, Vec3(rect.min_x, 0.0, rect.min_z), Vec3(rect.max_x, 0.0, rect.min_z), color
        )
        self.draw_world_line(
            camera, Vec3(rect.max_x, 0.0, rect.min_z), Vec3(rect.max_x, 0.0, rect.max_z), color
        )
        self.draw_world_line(
            camera, Vec3(rect.max_x, 0.0, rect.max_z), Vec3(rect.min_x, 0.0, rect.max_z), color
        )
        self.draw_world_line(
            camera, Vec3(rect.min_x, 0.0, rect.max_z), Vec3(rect.min_x, 0.0, rect.min_z), color
        )

    def draw_safe_zones(self, world: WorldData, camera: CameraState) -> None:
        for zone in world.safe_zones:
            self.draw_world_circle(camera, zone.x, zone.z, zone.radius, 12)

    def draw_auto_move_goal(
        self, model: GameModel, camera: CameraState, presentation_time: float
    ) -> None:
        if model.auto_move_goal is None:
            return
        goal_x, goal_z = model.auto_move_goal
        pulse = 1.0 + 0.14 * math.sin(presentation_time * math.tau * 2.0)
        self.draw_world_circle(camera, goal_x, goal_z, 10.0 * pulse, 10)
        self.draw_world_circle(camera, goal_x, goal_z, 4.5 * pulse, 7)

    def world_commands(
        self,
        model: GameModel,
        camera: CameraState,
        presentation_time: float,
        effects: EffectSystem | None = None,
    ) -> list[DrawCommand]:
        commands: list[DrawCommand] = []
        combat_session = model.combat_session
        combat_enemy_id = combat_session.enemy_id if combat_session is not None else None
        combat_isolated = combat_enemy_id is not None
        margin = float(model.config["culling"]["screen_margin_ref_px"])
        visible_query = model.world.query_visible_static_objects(camera, margin)
        combat_background_depth_floor = (
            self.combat_background_depth_floor(model, camera) if combat_isolated else None
        )
        combat_background_screen_rect = (
            self.combat_background_screen_exclusion_rect(model, camera) if combat_isolated else None
        )
        visible_objects = [
            obj for obj in visible_query.objects if self.object_is_visible(obj, camera, margin)
        ]
        visible_details = [
            detail
            for detail in model.world.ground_details_for_chunks(visible_query.chunk_ids)
            if self.ground_detail_is_visible(detail, camera, margin)
            and not self.point_in_active_baked_ground_patch(detail.x, detail.z)
        ]
        for detail in visible_details:
            anchor = camera.project(Vec3(detail.x, 0.0, detail.z))
            if anchor is None:
                continue
            detail_bounds = ScreenRect(int(anchor.x - 4), int(anchor.y - 4), 8, 8)
            if not self.combat_background_command_is_visible(
                combat_background_depth_floor,
                anchor.depth,
                combat_background_screen_rect,
                detail_bounds,
            ):
                continue
            commands.append(
                DrawCommand(
                    depth=anchor.depth,
                    layer_bias=1,
                    stable_id=detail.id,
                    draw=lambda detail=detail: self.draw_ground_detail(
                        model, detail, camera, model.world_tick
                    ),
                    atmosphere_strength=self.atmosphere_strength_config(
                        "ground_detail_strength", ATMOSPHERE_GROUND_DETAIL_STRENGTH
                    ),
                )
            )
        for obj in visible_objects:
            object_bounds = self.object_screen_bounds(obj, camera)
            if self.camera_is_affine(camera) and self.object_uses_box_geometry(obj):
                box_commands = self.solid_box_face_commands(obj, camera)
                if combat_background_depth_floor is not None:
                    box_commands = [
                        command
                        for command in box_commands
                        if self.combat_background_command_is_visible(
                            combat_background_depth_floor,
                            command.depth,
                            combat_background_screen_rect,
                            object_bounds,
                        )
                    ]
                commands.extend(box_commands)
                continue
            anchor = camera.project(Vec3(obj.x, 0.0, obj.z))
            if anchor is None:
                continue
            if not self.combat_background_command_is_visible(
                combat_background_depth_floor,
                anchor.depth,
                combat_background_screen_rect,
                object_bounds,
            ):
                continue
            commands.append(
                DrawCommand(
                    depth=anchor.depth,
                    layer_bias=0,
                    stable_id=obj.id,
                    draw=lambda obj=obj: self.draw_object(model, obj, camera, effects),
                    atmosphere_strength=self.object_atmosphere_strength(obj),
                )
            )
        for enemy in model.enemies:
            if combat_isolated and enemy.id != combat_enemy_id:
                continue
            enemy_presentation = self.enemy_actor_presentation(model, enemy, camera)
            anchor = camera.project(Vec3(enemy_presentation.x, 0.0, enemy_presentation.z))
            if anchor is None:
                continue
            commands.append(
                DrawCommand(
                    depth=anchor.depth,
                    layer_bias=0,
                    stable_id=enemy.id,
                    draw=lambda enemy=enemy, presentation=enemy_presentation: self.draw_enemy(
                        model, enemy, camera, presentation
                    ),
                    atmosphere_strength=self.atmosphere_strength_config(
                        "enemy_strength", ATMOSPHERE_ENEMY_STRENGTH
                    ),
                )
            )
        if effects is not None and not combat_isolated:
            for snapshot in effects.enemy_snapshots:
                anchor = camera.project(Vec3(snapshot.x, 0.0, snapshot.z))
                if anchor is None:
                    continue
                commands.append(
                    DrawCommand(
                        depth=anchor.depth,
                        layer_bias=0,
                        stable_id=f"enemy_snapshot:{snapshot.enemy_id}",
                        draw=lambda snapshot=snapshot: self.draw_enemy_snapshot(
                            model, snapshot, camera
                        ),
                        atmosphere_strength=self.atmosphere_strength_config(
                            "enemy_strength", ATMOSPHERE_ENEMY_STRENGTH
                        ),
                    )
                )
        if model.bubble is not None and not combat_isolated:
            bubble_anchor = camera.project(Vec3(model.bubble.x, 4.0, model.bubble.z))
            if bubble_anchor is not None:
                commands.append(
                    DrawCommand(
                        depth=bubble_anchor.depth,
                        layer_bias=-1,
                        stable_id="bubble",
                        draw=lambda: self.draw_bubble(model, camera),
                        atmosphere_strength=0.0,
                    )
                )
        buddy_presentation = self.buddy_actor_presentation(model, camera, presentation_time)
        buddy_anchor = camera.project(
            Vec3(
                buddy_presentation.x,
                model.buddy.y + buddy_presentation.jump_y,
                buddy_presentation.z,
            )
        )
        if buddy_anchor is not None:
            commands.append(
                DrawCommand(
                    depth=buddy_anchor.depth,
                    layer_bias=0,
                    stable_id="buddy",
                    draw=lambda presentation=buddy_presentation: self.draw_buddy(
                        model, camera, presentation_time, presentation
                    ),
                    atmosphere_strength=self.atmosphere_strength_config(
                        "buddy_strength", ATMOSPHERE_BUDDY_STRENGTH
                    ),
                )
            )
        player_presentation = self.player_actor_presentation(model, camera)
        player_anchor = camera.project(Vec3(player_presentation.x, 0.0, player_presentation.z))
        if player_anchor is not None:
            commands.append(
                DrawCommand(
                    depth=player_anchor.depth,
                    layer_bias=0,
                    stable_id="player",
                    draw=lambda presentation=player_presentation: self.draw_player(
                        model, camera, presentation_time, presentation
                    ),
                    atmosphere_strength=self.atmosphere_strength_config(
                        "player_strength", ATMOSPHERE_PLAYER_STRENGTH
                    ),
                )
            )
        self.last_stats = RenderStats(
            total_static_objects=len(model.world.objects),
            candidate_chunks=visible_query.candidate_chunk_count,
            candidate_static_objects=visible_query.candidate_object_count,
            visible_static_objects=len(visible_objects),
            visible_ground_details=len(visible_details),
            visible_grassland_micro_areas=self._visible_grassland_micro_areas,
            visible_forest_light_spots=self._visible_forest_light_spots,
            visible_ambient_motes=self._visible_ambient_motes,
            visible_baked_ground_patches=len(self._active_baked_ground_patches),
            baked_ground_cache_size=len(self._baked_ground_cache),
            draw_commands=len(commands),
            active_enemies=model.debug.active_enemies,
            dormant_enemies=model.debug.dormant_enemies,
        )
        return commands

    def combat_background_depth_floor(self, model: GameModel, camera: CameraState) -> float | None:
        depths: list[float] = []
        for actor in ("player", "buddy", "enemy"):
            anchor_ground = model.combat_actor_anchor_ground(camera, actor)
            if anchor_ground is None:
                continue
            projected = camera.project(Vec3(anchor_ground[0], 0.0, anchor_ground[1]))
            if projected is not None and math.isfinite(projected.depth):
                depths.append(projected.depth)
        return min(depths) if depths else None

    def combat_background_screen_exclusion_rect(
        self, model: GameModel, camera: CameraState
    ) -> ScreenRect | None:
        anchors = [
            self.combat_actor_screen_anchor(model, camera, actor)
            for actor in ("player", "buddy", "enemy")
        ]
        xs = [anchor[0] for anchor in anchors if anchor is not None]
        if not xs:
            return None
        margin = max(16.0, 24.0 * camera.viewport_width / 512.0)
        min_x = int(math.floor(min(xs) - margin))
        max_x = int(math.ceil(max(xs) + margin))
        return ScreenRect(min_x, 0, max(1, max_x - min_x), int(camera.viewport_height))

    def combat_background_command_is_visible(
        self,
        depth_floor: float | None,
        command_depth: float,
        screen_exclusion_rect: ScreenRect | None = None,
        command_bounds: ScreenRect | None = None,
    ) -> bool:
        if depth_floor is None:
            return True
        if (
            screen_exclusion_rect is not None
            and command_bounds is not None
            and (
                command_bounds.max_x <= screen_exclusion_rect.x
                or command_bounds.x >= screen_exclusion_rect.max_x
            )
        ):
            return True
        return command_depth >= depth_floor - 1e-6

    def player_actor_presentation(self, model: GameModel, camera: CameraState) -> ActorPresentation:
        session = model.combat_session
        if session is None:
            return ActorPresentation(model.player.x, model.player.z)
        target = self.combat_actor_anchor_ground(model, camera, "player")
        if target is None:
            target_x = model.player.x
            target_z = model.player.z
        else:
            target_x, target_z = target
        if session.phase == "COMBAT_ENTRY":
            progress = self.combat_actor_settle_progress(model)
            return ActorPresentation(
                _lerp(session.snapshot.player.x, target_x, progress),
                _lerp(session.snapshot.player.z, target_z, progress),
                self.combat_actor_entry_jump_y(model, progress),
            )
        if session.phase == "COMBAT_RESTORE_JUMP":
            progress = self.combat_actor_restore_progress(model)
            return ActorPresentation(
                _lerp(target_x, session.player_return_x, progress),
                _lerp(target_z, session.player_return_z, progress),
                self.combat_actor_restore_jump_y(model, progress),
            )
        return ActorPresentation(target_x, target_z)

    def enemy_actor_presentation(
        self, model: GameModel, enemy, camera: CameraState
    ) -> ActorPresentation:
        session = model.combat_session
        if session is None or session.enemy_id != enemy.id:
            enemy_x, enemy_z = model.enemy_presentation_position(enemy)
            return ActorPresentation(enemy_x, enemy_z)
        target = self.combat_actor_anchor_ground(model, camera, "enemy")
        if target is None:
            target_x = enemy.x
            target_z = enemy.z
        else:
            target_x, target_z = target
        if session.phase == "COMBAT_ENTRY":
            progress = self.combat_actor_settle_progress(model)
            return ActorPresentation(
                _lerp(session.snapshot.enemy.x, target_x, progress),
                _lerp(session.snapshot.enemy.z, target_z, progress),
                self.combat_actor_entry_jump_y(model, progress),
            )
        if session.phase == "COMBAT_RESTORE_JUMP":
            return ActorPresentation(session.enemy_return_x, session.enemy_return_z)
        offset_x, offset_z = model.combat_enemy_presentation_offset(enemy)
        return ActorPresentation(target_x + offset_x, target_z + offset_z)

    def buddy_actor_presentation(
        self, model: GameModel, camera: CameraState, presentation_time: float
    ) -> ActorPresentation:
        if self.combat_defeat_restore_active(model):
            target = self.combat_actor_anchor_ground(model, camera, "buddy")
            if target is None:
                start_x = model.buddy.x
                start_z = model.buddy.z
            else:
                start_x, start_z = target
            progress = self.combat_actor_restore_progress(model)
            jump_y = math.sin(max(0.0, min(progress, 1.0)) * math.pi) * 10.0
            return ActorPresentation(
                _lerp(start_x, model.buddy.x, progress),
                _lerp(start_z, model.buddy.z, progress),
                _lerp(18.0, 0.0, progress) + jump_y,
            )
        if not self.combat_defeat_special_active(model):
            return ActorPresentation(model.buddy.x, model.buddy.z)
        target = self.combat_actor_anchor_ground(model, camera, "buddy")
        if target is None:
            target_x = model.buddy.x
            target_z = model.buddy.z
        else:
            target_x, target_z = target
        progress = self.combat_defeat_special_progress(model)
        move_progress = _smoothstep(progress / 0.34)
        float_progress = _smoothstep(progress / 0.24)
        float_y = 18.0 * float_progress
        wobble = math.sin(max(0.0, progress - 0.18) * math.tau * 2.2) * 1.8
        wobble *= 1.0 - _smoothstep((progress - 0.72) / 0.28)
        float_y += wobble
        return ActorPresentation(
            _lerp(model.buddy.x, target_x, move_progress),
            _lerp(model.buddy.z, target_z, move_progress),
            float_y,
        )

    def combat_actor_anchor_ground(
        self, model: GameModel, camera: CameraState, actor: str
    ) -> tuple[float, float] | None:
        screen_anchor = self.combat_actor_screen_anchor(model, camera, actor)
        if screen_anchor is None:
            return None
        screen_x, screen_y = screen_anchor
        ground = (
            screen_to_ground_affine(camera, screen_x, screen_y)
            if self.camera_is_affine(camera)
            else screen_to_ground_point(camera, screen_x, screen_y)
        )
        if ground is None:
            return None
        return ground.x, ground.y

    def combat_actor_screen_anchor(
        self, model: GameModel, camera: CameraState, actor: str
    ) -> tuple[float, float] | None:
        presentation = (
            model.combat_v1_config().get("presentation_medium_512x236", {})
            if hasattr(model, "combat_v1_config")
            else {}
        )
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

    def combat_actor_settle_progress(self, model: GameModel) -> float:
        session = model.combat_session
        if session is None:
            return 0.0
        if session.phase != "COMBAT_ENTRY":
            return 1.0
        entry = model.combat_v1_config().get("entry", {})
        if not isinstance(entry, dict):
            entry = {}
        isolation_sec = max(0.0, float(entry.get("isolation_sec", 0.18)))
        settle_sec = max(0.0, float(entry.get("actor_settle_sec", 0.2)))
        if settle_sec <= 1e-6:
            return 1.0 if session.phase_elapsed_sec >= isolation_sec else 0.0
        return _smoothstep((session.phase_elapsed_sec - isolation_sec) / settle_sec)

    def combat_defeat_special_active(self, model: GameModel) -> bool:
        session = model.combat_session
        return (
            session is not None
            and session.outcome == "defeat"
            and session.zap_used
            and session.phase in {"COMBAT_EXIT_COUNTER", "VICTORY_CUE"}
        )

    def combat_defeat_restore_active(self, model: GameModel) -> bool:
        session = model.combat_session
        return (
            session is not None
            and session.outcome == "defeat"
            and session.zap_used
            and session.phase == "COMBAT_RESTORE_JUMP"
        )

    def combat_defeat_special_progress(self, model: GameModel) -> float:
        session = model.combat_session
        if session is None or not self.combat_defeat_special_active(model):
            return 0.0
        exit_duration = max(0.0, model.combat_deflect_knockback_sec())
        victory_duration = max(0.0, model.combat_victory_cue_sec())
        if session.phase == "COMBAT_EXIT_COUNTER":
            elapsed = session.phase_elapsed_sec
        else:
            elapsed = exit_duration + session.phase_elapsed_sec
        total = max(exit_duration + victory_duration, 1e-6)
        return max(0.0, min(elapsed / total, 1.0))

    def combat_defeat_exit_progress(self, model: GameModel) -> float:
        session = model.combat_session
        if session is None or not self.combat_defeat_special_active(model):
            return 0.0
        if session.phase == "VICTORY_CUE":
            return 1.0
        duration = max(model.combat_deflect_knockback_sec(), 1e-6)
        return max(0.0, min(session.phase_elapsed_sec / duration, 1.0))

    def combat_defeat_enemy_visibility(self, model: GameModel, enemy) -> float:
        session = model.combat_session
        if (
            session is not None
            and session.enemy_id == enemy.id
            and self.combat_defeat_restore_active(model)
        ):
            return 0.0
        if (
            session is None
            or session.enemy_id != enemy.id
            or not self.combat_defeat_special_active(model)
        ):
            return 1.0
        progress = self.combat_defeat_special_progress(model)
        if progress < 0.91:
            return 1.0
        return max(0.0, 1.0 - _smoothstep((progress - 0.91) / 0.09))

    def combat_defeat_enemy_flicker_hidden(self, model: GameModel, enemy) -> bool:
        visibility = self.combat_defeat_enemy_visibility(model, enemy)
        if visibility >= 0.95:
            return False
        if visibility <= 0.05:
            return True
        session = model.combat_session
        elapsed = session.phase_elapsed_sec if session is not None else 0.0
        tick = int(elapsed * 30.0) + sum(ord(char) for char in enemy.id)
        if visibility < 0.35:
            return tick % 2 == 0
        if visibility < 0.7:
            return tick % 4 == 0
        return False

    def combat_actor_entry_jump_y(self, model: GameModel, progress: float) -> float:
        session = model.combat_session
        if session is None or session.phase != "COMBAT_ENTRY":
            return 0.0
        entry = model.combat_v1_config().get("entry", {})
        if not isinstance(entry, dict):
            entry = {}
        height = float(entry.get("actor_jump_height_world", 18.0))
        return math.sin(max(0.0, min(progress, 1.0)) * math.pi) * height

    def combat_actor_restore_progress(self, model: GameModel) -> float:
        session = model.combat_session
        if session is None or session.phase != "COMBAT_RESTORE_JUMP":
            return 1.0
        duration = model.combat_restore_jump_sec()
        if duration <= 1e-6:
            return 1.0
        return _smoothstep(session.phase_elapsed_sec / duration)

    def combat_actor_restore_jump_y(self, model: GameModel, progress: float) -> float:
        session = model.combat_session
        if session is None or session.phase != "COMBAT_RESTORE_JUMP":
            return 0.0
        height = model.combat_restore_jump_height_world()
        return math.sin(max(0.0, min(progress, 1.0)) * math.pi) * height

    def draw_grassland_micro_layer(self, model: GameModel, camera: CameraState) -> int:
        config = model.config.get("grassland_micro", {})
        if not bool(config.get("enabled", False)):
            return 0
        if bool(config.get("affine_only", True)) and not self.camera_is_affine(camera):
            return 0
        areas = config.get("areas", ())
        if not isinstance(areas, (list, tuple)):
            return 0
        visible_count = 0
        for area in areas:
            if isinstance(area, dict) and self.draw_grassland_micro_area(
                model.world, camera, area, config
            ):
                visible_count += 1
        return visible_count

    def draw_grassland_micro_area(
        self, world: WorldData, camera: CameraState, area: dict, config: dict
    ) -> bool:
        area_rect = self.grassland_micro_world_rect(world, area)
        if area_rect is None:
            return False
        draw_rect = self.grassland_micro_visible_draw_rect(camera, area_rect, area, config)
        if draw_rect is None:
            return False
        x0, z0, x1, z1 = draw_rect
        corners = (
            camera.project(Vec3(x0, 0.0, z0)),
            camera.project(Vec3(x1, 0.0, z0)),
            camera.project(Vec3(x1, 0.0, z1)),
            camera.project(Vec3(x0, 0.0, z1)),
        )
        if any(point is None for point in corners):
            return False
        p0, p1, p2, p3 = corners
        bounds = self.projected_quad_bounds(corners)
        if bounds is None or not self.screen_rect_visible(bounds, camera, 2.0):
            return False

        base_color = self.clamped_palette_color(area.get("base_color", config.get("base_color", 3)))
        self.draw_grassland_base_transition(camera, area_rect, draw_rect, area, config, base_color)
        self.draw_grassland_micro_base_variation(
            camera, corners, bounds, area_rect, draw_rect, area, config
        )
        self.draw_grassland_micro_pattern(
            camera, corners, bounds, area_rect, draw_rect, area, config
        )
        return True

    def draw_grassland_base_transition(
        self,
        camera: CameraState,
        area_rect: tuple[float, float, float, float],
        draw_rect: tuple[float, float, float, float],
        area: dict,
        config: dict,
        color: int,
    ) -> None:
        transition_world = self.grassland_transition_world(area, config)
        if transition_world <= 1e-6:
            self.draw_ground_rect(camera, draw_rect, color)
            return

        x0, z0, x1, z1 = area_rect
        inner_rect = (
            max(draw_rect[0], x0 + transition_world),
            max(draw_rect[1], z0 + transition_world),
            min(draw_rect[2], x1 - transition_world),
            min(draw_rect[3], z1 - transition_world),
        )
        if inner_rect[0] < inner_rect[2] and inner_rect[1] < inner_rect[3]:
            self.draw_ground_rect(camera, inner_rect, color)
        if (
            draw_rect[0] >= x0 + transition_world
            and draw_rect[1] >= z0 + transition_world
            and draw_rect[2] <= x1 - transition_world
            and draw_rect[3] <= z1 - transition_world
        ):
            return

        tile_world = self.grassland_transition_cell_world(area, config)
        phase = int(area.get("phase", config.get("phase", 0)))
        soft_color = self.grassland_transition_soft_color(area, config, color)
        cells = self.grassland_transition_cells(
            area_rect,
            area,
            config,
            color,
            soft_color,
            transition_world,
            tile_world,
            phase,
        )
        for cell in cells:
            if (
                cell.x1 <= draw_rect[0]
                or cell.x0 >= draw_rect[2]
                or cell.z1 <= draw_rect[1]
                or cell.z0 >= draw_rect[3]
            ):
                continue
            clipped = (
                max(cell.x0, draw_rect[0]),
                max(cell.z0, draw_rect[1]),
                min(cell.x1, draw_rect[2]),
                min(cell.z1, draw_rect[3]),
            )
            if clipped[0] < clipped[2] and clipped[1] < clipped[3]:
                self.draw_ground_rect(camera, clipped, cell.color)

    def grassland_transition_cells(
        self,
        area_rect: tuple[float, float, float, float],
        area: dict,
        config: dict,
        color: int,
        soft_color: int,
        transition_world: float,
        tile_world: float,
        phase: int,
    ) -> tuple[GrasslandTransitionCell, ...]:
        pattern = str(area.get("transition_pattern", config.get("transition_pattern", "noise")))
        key = (
            tuple(round(value, 4) for value in area_rect),
            round(float(transition_world), 4),
            round(float(tile_world), 4),
            round(self.grassland_edge_irregularity_world(area, config), 4),
            int(color),
            int(soft_color),
            int(phase),
            pattern,
        )
        cached = self._grassland_transition_cell_cache.get(key)
        if cached is not None:
            return cached

        x0, z0, x1, z1 = area_rect
        min_cell_x = math.floor(x0 / tile_world)
        max_cell_x = math.ceil(x1 / tile_world)
        min_cell_z = math.floor(z0 / tile_world)
        max_cell_z = math.ceil(z1 / tile_world)
        inner_x0 = x0 + transition_world
        inner_z0 = z0 + transition_world
        inner_x1 = x1 - transition_world
        inner_z1 = z1 - transition_world
        cells: list[GrasslandTransitionCell] = []
        for cell_z in range(min_cell_z, max_cell_z):
            cell_z0 = max(z0, cell_z * tile_world)
            cell_z1 = min(z1, (cell_z + 1) * tile_world)
            if cell_z0 >= cell_z1:
                continue
            for cell_x in range(min_cell_x, max_cell_x):
                cell_x0 = max(x0, cell_x * tile_world)
                cell_x1 = min(x1, (cell_x + 1) * tile_world)
                if cell_x0 >= cell_x1:
                    continue
                if (
                    cell_x0 >= inner_x0
                    and cell_z0 >= inner_z0
                    and cell_x1 <= inner_x1
                    and cell_z1 <= inner_z1
                ):
                    continue
                center_x = (cell_x0 + cell_x1) * 0.5
                center_z = (cell_z0 + cell_z1) * 0.5
                coverage = self.grassland_base_coverage(
                    area_rect,
                    center_x,
                    center_z,
                    transition_world,
                    area,
                    config,
                )
                if coverage <= 0:
                    continue
                soft_coverage = self.grassland_transition_soft_coverage(coverage)
                base_coverage = self.grassland_transition_base_coverage(coverage)
                if soft_color != color and self.grassland_transition_pass(
                    cell_x,
                    cell_z,
                    soft_coverage,
                    phase + 31,
                    area,
                    config,
                ):
                    cells.append(
                        GrasslandTransitionCell(cell_x0, cell_z0, cell_x1, cell_z1, soft_color)
                    )
                if not self.grassland_transition_pass(
                    cell_x,
                    cell_z,
                    base_coverage,
                    phase,
                    area,
                    config,
                ):
                    continue
                cells.append(GrasslandTransitionCell(cell_x0, cell_z0, cell_x1, cell_z1, color))

        result = tuple(cells)
        self._grassland_transition_cell_cache[key] = result
        return result

    def draw_ground_rect(
        self, camera: CameraState, rect: tuple[float, float, float, float], color: int
    ) -> None:
        x0, z0, x1, z1 = rect
        corners = (
            camera.project(Vec3(x0, 0.0, z0)),
            camera.project(Vec3(x1, 0.0, z0)),
            camera.project(Vec3(x1, 0.0, z1)),
            camera.project(Vec3(x0, 0.0, z1)),
        )
        if any(point is None for point in corners):
            return
        p0, p1, p2, p3 = corners
        self.pyxel.tri(int(p0.x), int(p0.y), int(p1.x), int(p1.y), int(p2.x), int(p2.y), color)
        self.pyxel.tri(int(p0.x), int(p0.y), int(p2.x), int(p2.y), int(p3.x), int(p3.y), color)

    def grassland_micro_world_rect(
        self, world: WorldData, area: dict
    ) -> tuple[float, float, float, float] | None:
        if area.get("bounds_ref") == "visual_ground":
            rect = world.visual_ground_rect
            return rect.min_x, rect.min_z, rect.max_x, rect.max_z
        raw_rect = area.get("rect_xz")
        if not isinstance(raw_rect, (list, tuple)) or len(raw_rect) != 4:
            return None
        x0, z0, x1, z1 = (float(value) for value in raw_rect)
        if not all(math.isfinite(value) for value in (x0, z0, x1, z1)):
            return None
        if abs(x1 - x0) <= 1e-6 or abs(z1 - z0) <= 1e-6:
            return None
        return min(x0, x1), min(z0, z1), max(x0, x1), max(z0, z1)

    def grassland_micro_visible_draw_rect(
        self,
        camera: CameraState,
        rect: tuple[float, float, float, float],
        area: dict,
        config: dict,
    ) -> tuple[float, float, float, float] | None:
        if not self.camera_is_affine(camera):
            return rect
        visible_rect = self.grassland_micro_visible_world_rect(camera, margin_px=16.0)
        if visible_rect is None:
            return rect
        x0, z0, x1, z1 = rect
        vx0, vz0, vx1, vz1 = visible_rect
        x0 = max(x0, vx0)
        z0 = max(z0, vz0)
        x1 = min(x1, vx1)
        z1 = min(z1, vz1)
        if x0 >= x1 or z0 >= z1:
            return None
        return x0, z0, x1, z1

    def projected_quad_bounds(self, points: tuple[ProjectedPoint | None, ...]) -> ScreenRect | None:
        projected = [point for point in points if point is not None]
        if len(projected) != 4:
            return None
        min_x = math.floor(min(point.x for point in projected))
        max_x = math.ceil(max(point.x for point in projected))
        min_y = math.floor(min(point.y for point in projected))
        max_y = math.ceil(max(point.y for point in projected))
        if not all(math.isfinite(value) for value in (min_x, max_x, min_y, max_y)):
            return None
        return ScreenRect(
            int(min_x),
            int(min_y),
            max(1, int(max_x - min_x)),
            max(1, int(max_y - min_y)),
        )

    def draw_grassland_micro_pattern(
        self,
        camera: CameraState,
        corners: tuple[ProjectedPoint | None, ...],
        bounds: ScreenRect,
        area_rect: tuple[float, float, float, float],
        draw_rect: tuple[float, float, float, float],
        area: dict,
        config: dict,
    ) -> None:
        cell_world = max(12.0, float(area.get("cell_world", config.get("cell_world", 24.0))))
        max_visible = max(
            0, int(area.get("max_visible_clumps", config.get("max_visible_clumps", 520)))
        )
        if max_visible <= 0:
            return
        x0, z0, x1, z1 = draw_rect
        visible_rect = self.grassland_micro_visible_world_rect(camera, margin_px=16.0)
        if visible_rect is not None:
            vx0, vz0, vx1, vz1 = visible_rect
            x0 = max(x0, vx0 - cell_world)
            z0 = max(z0, vz0 - cell_world)
            x1 = min(x1, vx1 + cell_world)
            z1 = min(z1, vz1 + cell_world)
            if x0 >= x1 or z0 >= z1:
                return
        colors = (
            self.clamped_palette_color(area.get("blade_color", config.get("blade_color", 11))),
            self.clamped_palette_color(
                area.get("blade_shadow_color", config.get("blade_shadow_color", 3))
            ),
            self.clamped_palette_color(
                area.get("blade_accent_color", config.get("blade_accent_color", 10))
            ),
        )
        jitter_seed = int(area.get("phase", config.get("phase", 0)))
        min_blades = max(
            0, int(area.get("min_blades_per_cell", config.get("min_blades_per_cell", 1)))
        )
        max_blades = max(
            min_blades,
            int(area.get("max_blades_per_cell", config.get("max_blades_per_cell", 4))),
        )
        min_height = self.grassland_micro_min_blade_height(area, config)
        max_height = self.grassland_micro_max_blade_height(area, config, min_height)
        density_inner = self.grassland_micro_density_inner(area, config)
        density_edge = self.grassland_micro_density_edge(area, config)
        transition_world = self.grassland_transition_world(area, config)
        cell_min_x = math.floor(x0 / cell_world)
        cell_max_x = math.ceil(x1 / cell_world)
        cell_min_z = math.floor(z0 / cell_world)
        cell_max_z = math.ceil(z1 / cell_world)
        margin = 8.0
        drawn = 0
        for cell_z in range(cell_min_z, cell_max_z):
            origin_z = cell_z * cell_world
            for cell_x in range(cell_min_x, cell_max_x):
                origin_x = cell_x * cell_world
                blade_count = min_blades + self.grassland_hash(cell_x, cell_z, 0, jitter_seed) % (
                    max_blades - min_blades + 1
                )
                for blade_index in range(blade_count):
                    salt = blade_index * 7
                    rel_x = 0.08 + self.grassland_unit(cell_x, cell_z, salt + 1, jitter_seed) * 0.84
                    rel_z = 0.08 + self.grassland_unit(cell_x, cell_z, salt + 2, jitter_seed) * 0.84
                    height = min_height + int(
                        self.grassland_unit(cell_x, cell_z, salt + 3, jitter_seed)
                        * (max_height - min_height + 1)
                    )
                    color = self.grassland_micro_blade_color(
                        cell_x, cell_z, salt + 4, jitter_seed, colors, area, config
                    )
                    lean = int(self.grassland_unit(cell_x, cell_z, salt + 5, jitter_seed) * 3.0) - 1
                    shape = self.grassland_micro_blade_shape(cell_x, cell_z, salt + 8, jitter_seed)
                    world_x = origin_x + rel_x * cell_world
                    world_z = origin_z + rel_z * cell_world
                    if world_x < x0 or world_x > x1 or world_z < z0 or world_z > z1:
                        continue
                    density = self.grassland_micro_density(
                        area_rect,
                        world_x,
                        world_z,
                        transition_world,
                        density_inner,
                        density_edge,
                        area,
                        config,
                    )
                    density *= self.grassland_micro_density_variation(
                        world_x, world_z, area, config
                    )
                    density = max(0.0, min(density, 1.0))
                    if density <= 0.0:
                        continue
                    if (
                        density < 1.0
                        and self.grassland_unit(cell_x, cell_z, salt + 6, jitter_seed) > density
                    ):
                        continue
                    root = camera.project(Vec3(world_x, 0.0, world_z))
                    if root is None:
                        continue
                    if not bounds.contains(root.x, root.y, margin):
                        continue
                    if root.x < -margin or root.x > camera.viewport_width + margin:
                        continue
                    if root.y < -margin or root.y > camera.viewport_height + margin:
                        continue
                    if not self.point_in_projected_quad(root.x, root.y, corners):
                        continue
                    self.draw_micro_grass_blade(
                        int(round(root.x)),
                        int(round(root.y)),
                        max(min_height, min(max_height, height)),
                        color,
                        colors[1],
                        lean,
                        shape,
                    )
                    drawn += 1
                    if drawn >= max_visible:
                        return

    def draw_grassland_micro_base_variation(
        self,
        camera: CameraState,
        corners: tuple[ProjectedPoint | None, ...],
        bounds: ScreenRect,
        area_rect: tuple[float, float, float, float],
        draw_rect: tuple[float, float, float, float],
        area: dict,
        config: dict,
    ) -> None:
        if not bool(
            area.get(
                "base_variation_enabled",
                config.get("base_variation_enabled", False),
            )
        ):
            return
        tile_world = max(
            32.0,
            float(
                area.get("base_variation_cell_world", config.get("base_variation_cell_world", 96.0))
            ),
        )
        max_patches = max(
            0,
            int(area.get("max_visible_base_patches", config.get("max_visible_base_patches", 48))),
        )
        if max_patches <= 0:
            return
        x0, z0, x1, z1 = draw_rect
        visible_rect = self.grassland_micro_visible_world_rect(camera, margin_px=24.0)
        if visible_rect is not None:
            vx0, vz0, vx1, vz1 = visible_rect
            x0 = max(x0, vx0 - tile_world)
            z0 = max(z0, vz0 - tile_world)
            x1 = min(x1, vx1 + tile_world)
            z1 = min(z1, vz1 + tile_world)
            if x0 >= x1 or z0 >= z1:
                return
        color = self.clamped_palette_color(
            area.get("base_variation_color", config.get("base_variation_color", 13))
        )
        phase = int(area.get("phase", config.get("phase", 0)))
        transition_world = self.grassland_transition_world(area, config)
        cell_min_x = math.floor(x0 / tile_world)
        cell_max_x = math.ceil(x1 / tile_world)
        cell_min_z = math.floor(z0 / tile_world)
        cell_max_z = math.ceil(z1 / tile_world)
        drawn = 0
        for cell_z in range(cell_min_z, cell_max_z):
            origin_z = cell_z * tile_world
            for cell_x in range(cell_min_x, cell_max_x):
                origin_x = cell_x * tile_world
                if self.grassland_hash(cell_x, cell_z, 71, phase) % 100 >= 26:
                    continue
                inset_x0 = tile_world * (
                    0.08 + self.grassland_unit(cell_x, cell_z, 72, phase) * 0.18
                )
                inset_z0 = tile_world * (
                    0.08 + self.grassland_unit(cell_x, cell_z, 73, phase) * 0.18
                )
                inset_x1 = tile_world * (
                    0.08 + self.grassland_unit(cell_x, cell_z, 74, phase) * 0.22
                )
                inset_z1 = tile_world * (
                    0.08 + self.grassland_unit(cell_x, cell_z, 75, phase) * 0.22
                )
                px0 = max(x0, origin_x)
                pz0 = max(z0, origin_z)
                px1 = min(x1, origin_x + tile_world)
                pz1 = min(z1, origin_z + tile_world)
                vx0 = min(px1, px0 + inset_x0)
                vz0 = min(pz1, pz0 + inset_z0)
                vx1 = max(px0, px1 - inset_x1)
                vz1 = max(pz0, pz1 - inset_z1)
                if vx1 - vx0 < 12.0 or vz1 - vz0 < 12.0:
                    continue
                center_x = (vx0 + vx1) * 0.5
                center_z = (vz0 + vz1) * 0.5
                coverage = self.grassland_base_coverage(
                    area_rect,
                    center_x,
                    center_z,
                    transition_world,
                    area,
                    config,
                )
                if coverage <= 0.0:
                    continue
                if coverage < 1.0 and not self.grassland_transition_pass(
                    cell_x,
                    cell_z,
                    coverage,
                    phase + 17,
                    area,
                    config,
                ):
                    continue
                patch_corners = (
                    camera.project(Vec3(vx0, 0.0, vz0)),
                    camera.project(Vec3(vx1, 0.0, vz0)),
                    camera.project(Vec3(vx1, 0.0, vz1)),
                    camera.project(Vec3(vx0, 0.0, vz1)),
                )
                if any(point is None for point in patch_corners):
                    continue
                patch_bounds = self.projected_quad_bounds(patch_corners)
                if patch_bounds is None or not patch_bounds.overlaps(bounds):
                    continue
                q0, q1, q2, q3 = patch_corners
                if not self.screen_rect_visible(patch_bounds, camera, 2.0):
                    continue
                if not any(
                    self.point_in_projected_quad(point.x, point.y, corners)
                    for point in patch_corners
                    if point is not None
                ):
                    continue
                self.pyxel.tri(
                    int(q0.x),
                    int(q0.y),
                    int(q1.x),
                    int(q1.y),
                    int(q2.x),
                    int(q2.y),
                    color,
                )
                self.pyxel.tri(
                    int(q0.x),
                    int(q0.y),
                    int(q2.x),
                    int(q2.y),
                    int(q3.x),
                    int(q3.y),
                    color,
                )
                drawn += 1
                if drawn >= max_patches:
                    return

    def grassland_micro_visible_world_rect(
        self, camera: CameraState, margin_px: float
    ) -> tuple[float, float, float, float] | None:
        if not self.camera_is_affine(camera):
            return None
        points = [
            screen_to_ground_affine(camera, -margin_px, -margin_px),
            screen_to_ground_affine(camera, camera.viewport_width + margin_px, -margin_px),
            screen_to_ground_affine(
                camera,
                camera.viewport_width + margin_px,
                camera.viewport_height + margin_px,
            ),
            screen_to_ground_affine(camera, -margin_px, camera.viewport_height + margin_px),
        ]
        visible = [point for point in points if point is not None]
        if len(visible) < 3:
            return None
        min_x = min(point.x for point in visible)
        max_x = max(point.x for point in visible)
        min_z = min(point.y for point in visible)
        max_z = max(point.y for point in visible)
        if not all(math.isfinite(value) for value in (min_x, min_z, max_x, max_z)):
            return None
        return min_x, min_z, max_x, max_z

    def draw_forest_light_layer(self, model: GameModel, camera: CameraState) -> int:
        config = model.config.get("forest_light", {})
        if not bool(config.get("enabled", False)):
            return 0
        if bool(config.get("affine_only", True)) and not self.camera_is_affine(camera):
            return 0
        if bool(config.get("combat_hidden", True)) and model.combat_session is not None:
            return 0
        areas = config.get("areas", ())
        if not isinstance(areas, (list, tuple)):
            return 0

        cell_world = max(16.0, float(config.get("cell_world", 72.0)))
        max_spots = max(0, int(config.get("max_visible_spots", 56)))
        if max_spots <= 0:
            return 0
        color = self.clamped_palette_color(config.get("color", 7))
        secondary_color = self.clamped_palette_color(config.get("secondary_color", color))
        total = 0
        for area in areas:
            if not isinstance(area, dict):
                continue
            area_rect = self.forest_light_world_rect(model.world, area)
            if area_rect is None:
                continue
            draw_rect = self.visible_ground_draw_rect(WorldRect(*area_rect), camera, margin_px=32.0)
            if draw_rect is None:
                continue
            total += self.draw_forest_light_area(
                camera,
                area,
                area_rect,
                draw_rect,
                cell_world,
                color,
                secondary_color,
                max_spots - total,
            )
            if total >= max_spots:
                return total
        return total

    def forest_light_world_rect(
        self, world: WorldData, area: dict
    ) -> tuple[float, float, float, float] | None:
        if area.get("bounds_ref") == "visual_ground":
            rect = world.visual_ground_rect
            return rect.min_x, rect.min_z, rect.max_x, rect.max_z
        raw_rect = area.get("rect_xz")
        if not isinstance(raw_rect, (list, tuple)) or len(raw_rect) != 4:
            return None
        try:
            x0, z0, x1, z1 = (float(value) for value in raw_rect)
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (x0, z0, x1, z1)):
            return None
        if abs(x1 - x0) <= 1e-6 or abs(z1 - z0) <= 1e-6:
            return None
        return min(x0, x1), min(z0, z1), max(x0, x1), max(z0, z1)

    def draw_forest_light_area(
        self,
        camera: CameraState,
        area: dict,
        area_rect: tuple[float, float, float, float],
        draw_rect: WorldRect,
        cell_world: float,
        color: int,
        secondary_color: int,
        max_count: int,
    ) -> int:
        if max_count <= 0:
            return 0
        density = max(0.0, min(float(area.get("density", 0.28)), 1.0))
        if density <= 0.0:
            return 0
        phase = int(area.get("phase", 0))
        start_x = math.floor(draw_rect.min_x / cell_world) - 1
        end_x = math.ceil(draw_rect.max_x / cell_world) + 1
        start_z = math.floor(draw_rect.min_z / cell_world) - 1
        end_z = math.ceil(draw_rect.max_z / cell_world) + 1
        area_x0, area_z0, area_x1, area_z1 = area_rect
        count = 0
        for zi in range(start_z, end_z + 1):
            for xi in range(start_x, end_x + 1):
                seed = self._forest_light_seed(xi, zi, phase)
                if ((seed & 1023) / 1023.0) > density:
                    continue
                jitter_x = (((seed >> 10) & 31) / 31.0 - 0.5) * 0.72
                jitter_z = (((seed >> 15) & 31) / 31.0 - 0.5) * 0.72
                x = (xi + 0.5 + jitter_x) * cell_world
                z = (zi + 0.5 + jitter_z) * cell_world
                if not (area_x0 <= x <= area_x1 and area_z0 <= z <= area_z1):
                    continue
                if not draw_rect.contains_point(x, z):
                    continue
                point = camera.project(Vec3(x, 0.0, z))
                if point is None or not self._screen_point_visible(point, camera, 8.0):
                    continue
                self.draw_forest_light_spot(
                    int(point.x), int(point.y), seed, color, secondary_color
                )
                count += 1
                if count >= max_count:
                    return count
        return count

    def draw_forest_light_spot(
        self, x: int, y: int, seed: int, color: int, secondary_color: int
    ) -> None:
        style = seed % 4
        if style == 0:
            self.pyxel.pset(x, y, color)
            self.pyxel.pset(x + 1, y, secondary_color)
        elif style == 1:
            self.pyxel.line(x - 2, y, x + 2, y - 1, color)
        elif style == 2:
            self.pyxel.rect(x - 1, y - 1, 2, 1, secondary_color)
            self.pyxel.pset(x + 1, y, color)
        else:
            self.pyxel.pset(x, y, secondary_color)

    def _forest_light_seed(self, x_index: int, z_index: int, phase: int) -> int:
        value = (x_index * 83492791) ^ (z_index * 2654435761) ^ (phase * 374761393)
        value ^= value >> 16
        value *= 2246822519
        return value & 0xFFFFFFFF

    def draw_ambient_motes_layer(self, model: GameModel, camera: CameraState) -> int:
        config = model.config.get("ambient_motes", {})
        if not bool(config.get("enabled", False)):
            return 0
        if bool(config.get("affine_only", True)) and not self.camera_is_affine(camera):
            return 0
        if bool(config.get("combat_hidden", True)) and model.combat_session is not None:
            return 0
        areas = config.get("areas", ())
        if not isinstance(areas, (list, tuple)):
            return 0

        cell_world = max(12.0, float(config.get("cell_world", 64.0)))
        max_motes = max(0, int(config.get("max_visible_motes", 80)))
        if max_motes <= 0:
            return 0
        total = 0
        for area in areas:
            if not isinstance(area, dict):
                continue
            area_rect = self.forest_light_world_rect(model.world, area)
            if area_rect is None:
                continue
            draw_rect = self.visible_ground_draw_rect(WorldRect(*area_rect), camera, margin_px=48.0)
            if draw_rect is None:
                continue
            total += self.draw_ambient_motes_area(
                camera,
                area,
                area_rect,
                draw_rect,
                cell_world,
                max_motes - total,
            )
            if total >= max_motes:
                return total
        return total

    def draw_ambient_motes_area(
        self,
        camera: CameraState,
        area: dict,
        area_rect: tuple[float, float, float, float],
        draw_rect: WorldRect,
        cell_world: float,
        max_count: int,
    ) -> int:
        if max_count <= 0:
            return 0
        density = max(0.0, min(float(area.get("density", 0.22)), 1.0))
        if density <= 0.0:
            return 0
        phase = int(area.get("phase", 0))
        min_y = max(0.0, float(area.get("min_y", 6.0)))
        max_y = max(min_y, float(area.get("max_y", 36.0)))
        kind = str(area.get("kind", "green_mote"))
        color = self.clamped_palette_color(area.get("color", 11))
        secondary_color = self.clamped_palette_color(area.get("secondary_color", color))
        start_x = math.floor(draw_rect.min_x / cell_world) - 1
        end_x = math.ceil(draw_rect.max_x / cell_world) + 1
        start_z = math.floor(draw_rect.min_z / cell_world) - 1
        end_z = math.ceil(draw_rect.max_z / cell_world) + 1
        area_x0, area_z0, area_x1, area_z1 = area_rect
        count = 0
        for zi in range(start_z, end_z + 1):
            for xi in range(start_x, end_x + 1):
                seed = self._ambient_mote_seed(xi, zi, phase)
                if ((seed & 1023) / 1023.0) > density:
                    continue
                jitter_x = (((seed >> 10) & 63) / 63.0 - 0.5) * 0.84
                jitter_z = (((seed >> 16) & 63) / 63.0 - 0.5) * 0.84
                x = (xi + 0.5 + jitter_x) * cell_world
                z = (zi + 0.5 + jitter_z) * cell_world
                if not (area_x0 <= x <= area_x1 and area_z0 <= z <= area_z1):
                    continue
                if not draw_rect.contains_point(x, z):
                    continue
                height_t = ((seed >> 22) & 255) / 255.0
                y = min_y + (max_y - min_y) * height_t
                point = camera.project(Vec3(x, y, z))
                if point is None or not self._screen_point_visible(point, camera, 10.0):
                    continue
                self.draw_ambient_mote(
                    int(point.x), int(point.y), seed, kind, color, secondary_color
                )
                count += 1
                if count >= max_count:
                    return count
        return count

    def draw_ambient_mote(
        self, x: int, y: int, seed: int, kind: str, color: int, secondary_color: int
    ) -> None:
        style = seed % 5
        if kind == "photon":
            if style in {0, 1}:
                self.pyxel.pset(x, y, color)
                self.pyxel.pset(x + 1, y - 1, secondary_color)
            elif style == 2:
                self.pyxel.line(x - 1, y, x + 1, y, color)
                self.pyxel.pset(x, y - 1, secondary_color)
            else:
                self.pyxel.pset(x, y, secondary_color)
            return

        if style == 0:
            self.pyxel.pset(x, y, color)
            self.pyxel.pset(x + 1, y, secondary_color)
        elif style == 1:
            self.pyxel.pset(x, y, color)
            self.pyxel.pset(x, y + 1, secondary_color)
        elif style == 2:
            self.pyxel.line(x - 1, y, x + 1, y, color)
        elif style == 3:
            self.pyxel.pset(x, y, secondary_color)
            self.pyxel.pset(x + 1, y - 1, color)
        else:
            self.pyxel.pset(x, y, color)

    def _ambient_mote_seed(self, x_index: int, z_index: int, phase: int) -> int:
        value = (x_index * 1597334677) ^ (z_index * 3812015801) ^ (phase * 958689179)
        value ^= value >> 15
        value *= 846930887
        return value & 0xFFFFFFFF

    def grassland_transition_world(self, area: dict, config: dict) -> float:
        try:
            return max(
                0.0, float(area.get("transition_world", config.get("transition_world", 32.0)))
            )
        except (TypeError, ValueError):
            return 32.0

    def grassland_transition_cell_world(self, area: dict, config: dict) -> float:
        try:
            return max(
                4.0,
                float(area.get("transition_cell_world", config.get("transition_cell_world", 8.0))),
            )
        except (TypeError, ValueError):
            return 8.0

    def grassland_edge_irregularity_world(self, area: dict, config: dict) -> float:
        try:
            return max(
                0.0,
                float(
                    area.get(
                        "edge_irregularity_world",
                        config.get("edge_irregularity_world", 0.0),
                    )
                ),
            )
        except (TypeError, ValueError):
            return 0.0

    def grassland_edge_offset_world(
        self,
        world_x: float,
        world_z: float,
        area: dict | None,
        config: dict | None,
    ) -> float:
        if area is None or config is None:
            return 0.0
        amplitude = self.grassland_edge_irregularity_world(area, config)
        if amplitude <= 0.0:
            return 0.0
        cell_world = self.grassland_transition_cell_world(area, config)
        seed = int(area.get("phase", config.get("phase", 0)))
        cell_x = math.floor(world_x / cell_world)
        cell_z = math.floor(world_z / cell_world)
        coarse_x = math.floor(world_x / max(cell_world * 2.0, 1.0))
        coarse_z = math.floor(world_z / max(cell_world * 2.0, 1.0))
        fine = self.grassland_unit(cell_x, cell_z, 401, seed)
        coarse = self.grassland_unit(coarse_x, coarse_z, 402, seed)
        return ((fine * 0.45 + coarse * 0.55) * 2.0 - 1.0) * amplitude

    def grassland_transition_t(
        self,
        area_rect: tuple[float, float, float, float],
        world_x: float,
        world_z: float,
        transition_world: float,
        area: dict | None = None,
        config: dict | None = None,
    ) -> float:
        x0, z0, x1, z1 = area_rect
        if world_x < x0 or world_x > x1 or world_z < z0 or world_z > z1:
            return 0.0
        if transition_world <= 1e-6:
            return 1.0
        distance_inside = min(world_x - x0, x1 - world_x, world_z - z0, z1 - world_z)
        distance_inside += self.grassland_edge_offset_world(world_x, world_z, area, config)
        return max(0.0, min(distance_inside / transition_world, 1.0))

    def grassland_base_coverage(
        self,
        area_rect: tuple[float, float, float, float],
        world_x: float,
        world_z: float,
        transition_world: float,
        area: dict | None = None,
        config: dict | None = None,
    ) -> float:
        t = self.grassland_transition_t(
            area_rect,
            world_x,
            world_z,
            transition_world,
            area,
            config,
        )
        return max(0.0, min(t * t * (3.0 - 2.0 * t), 1.0))

    def grassland_transition_soft_color(self, area: dict, config: dict, fallback: int) -> int:
        return self.clamped_palette_color(
            area.get("transition_soft_color", config.get("transition_soft_color", fallback))
        )

    def grassland_transition_soft_coverage(self, coverage: float) -> float:
        return max(0.0, min(coverage * 1.35, 1.0))

    def grassland_transition_base_coverage(self, coverage: float) -> float:
        t = max(0.0, min((coverage - 0.25) / 0.75, 1.0))
        return t * t * (3.0 - 2.0 * t)

    def grassland_transition_pass(
        self,
        cell_x: int,
        cell_z: int,
        coverage: float,
        phase: int,
        area: dict,
        config: dict,
    ) -> bool:
        pattern = str(area.get("transition_pattern", config.get("transition_pattern", "noise")))
        if pattern == "bayer4":
            return self.grassland_bayer_pass(cell_x, cell_z, coverage, phase)
        return self.grassland_noise_pass(cell_x, cell_z, coverage, phase)

    def grassland_bayer_pass(
        self, cell_x: int, cell_z: int, coverage: float, phase: int = 0
    ) -> bool:
        if coverage <= 0.0:
            return False
        if coverage >= 1.0:
            return True
        threshold = GRASSLAND_BAYER4[(cell_z + phase) & 3][(cell_x + phase * 3) & 3]
        return threshold < int(round(max(0.0, min(coverage, 1.0)) * 16.0))

    def grassland_noise_pass(
        self, cell_x: int, cell_z: int, coverage: float, phase: int = 0
    ) -> bool:
        if coverage <= 0.0:
            return False
        if coverage >= 1.0:
            return True
        return self.grassland_unit(cell_x, cell_z, 131, phase) < max(
            0.0,
            min(coverage, 1.0),
        )

    def grassland_micro_density_inner(self, area: dict, config: dict) -> float:
        try:
            return max(
                0.0,
                min(
                    float(
                        area.get(
                            "micro_density_inner",
                            config.get("micro_density_inner", 1.0),
                        )
                    ),
                    1.0,
                ),
            )
        except (TypeError, ValueError):
            return 1.0

    def grassland_micro_density_edge(self, area: dict, config: dict) -> float:
        try:
            return max(
                0.0,
                min(
                    float(
                        area.get(
                            "micro_density_edge",
                            config.get("micro_density_edge", 0.2),
                        )
                    ),
                    1.0,
                ),
            )
        except (TypeError, ValueError):
            return 0.2

    def grassland_micro_density(
        self,
        area_rect: tuple[float, float, float, float],
        world_x: float,
        world_z: float,
        transition_world: float,
        density_inner: float,
        density_edge: float,
        area: dict | None = None,
        config: dict | None = None,
    ) -> float:
        t = self.grassland_transition_t(
            area_rect,
            world_x,
            world_z,
            transition_world,
            area,
            config,
        )
        return max(0.0, min(density_edge + (density_inner - density_edge) * t, 1.0))

    def grassland_micro_density_variation(
        self,
        world_x: float,
        world_z: float,
        area: dict,
        config: dict,
    ) -> float:
        if not bool(
            area.get("density_variation_enabled", config.get("density_variation_enabled", False))
        ):
            return 1.0
        try:
            cell_world = max(
                16.0,
                float(
                    area.get(
                        "density_variation_cell_world",
                        config.get("density_variation_cell_world", 64.0),
                    )
                ),
            )
        except (TypeError, ValueError):
            cell_world = 64.0
        try:
            min_factor = max(
                0.0,
                float(
                    area.get(
                        "density_variation_min",
                        config.get("density_variation_min", 0.55),
                    )
                ),
            )
        except (TypeError, ValueError):
            min_factor = 0.55
        try:
            max_factor = max(
                min_factor,
                float(
                    area.get(
                        "density_variation_max",
                        config.get("density_variation_max", 1.1),
                    )
                ),
            )
        except (TypeError, ValueError):
            max_factor = 1.1
        seed = int(area.get("phase", config.get("phase", 0)))
        cell_x = math.floor(world_x / cell_world)
        cell_z = math.floor(world_z / cell_world)
        coarse_x = math.floor(world_x / max(cell_world * 2.0, 1.0))
        coarse_z = math.floor(world_z / max(cell_world * 2.0, 1.0))
        fine = self.grassland_unit(cell_x, cell_z, 501, seed)
        coarse = self.grassland_unit(coarse_x, coarse_z, 502, seed)
        value = fine * 0.4 + coarse * 0.6
        return min_factor + (max_factor - min_factor) * value

    def grassland_micro_min_blade_height(self, area: dict, config: dict) -> int:
        try:
            return max(
                1,
                int(area.get("min_blade_height_px", config.get("min_blade_height_px", 2))),
            )
        except (TypeError, ValueError):
            return 2

    def grassland_micro_max_blade_height(self, area: dict, config: dict, min_height: int) -> int:
        try:
            return max(
                min_height,
                int(area.get("max_blade_height_px", config.get("max_blade_height_px", 6))),
            )
        except (TypeError, ValueError):
            return max(min_height, 6)

    def grassland_micro_blade_color(
        self,
        cell_x: int,
        cell_z: int,
        salt: int,
        seed: int,
        colors: tuple[int, int, int],
        area: dict,
        config: dict,
    ) -> int:
        primary = self.grassland_micro_color_weight(area, config, "blade_primary_weight", 0.58)
        shadow = self.grassland_micro_color_weight(area, config, "blade_shadow_weight", 0.34)
        accent = self.grassland_micro_color_weight(area, config, "blade_accent_weight", 0.08)
        total = primary + shadow + accent
        if total <= 0.0:
            return colors[0]
        roll = self.grassland_unit(cell_x, cell_z, salt, seed) * total
        if roll < primary:
            return colors[0]
        if roll < primary + shadow:
            return colors[1]
        return colors[2]

    def grassland_micro_color_weight(
        self, area: dict, config: dict, key: str, default: float
    ) -> float:
        try:
            return max(0.0, float(area.get(key, config.get(key, default))))
        except (TypeError, ValueError):
            return default

    def grassland_micro_blade_shape(self, cell_x: int, cell_z: int, salt: int, seed: int) -> int:
        roll = self.grassland_unit(cell_x, cell_z, salt, seed)
        if roll < 0.40:
            return 0
        if roll < 0.72:
            return 1
        if roll < 0.90:
            return 2
        return 3

    def draw_micro_grass_blade(
        self,
        root_x: int,
        root_y: int,
        height: int,
        color: int,
        shadow_color: int,
        lean: int = 1,
        shape: int = 0,
    ) -> None:
        tip_y = root_y - height
        tip_x = root_x + max(-1, min(1, lean))
        if shape == 1:
            self.pyxel.line(root_x, root_y, root_x - 1, tip_y + 1, shadow_color)
            self.pyxel.line(root_x, root_y, tip_x, tip_y, color)
        elif shape == 2:
            self.pyxel.line(root_x, root_y, tip_x, tip_y, color)
            side_tip_x = root_x + 1 - max(-1, min(1, lean))
            self.pyxel.line(root_x + 1, root_y, side_tip_x, tip_y + 2, color)
        elif shape == 3:
            short_tip_y = root_y - max(1, height - 2)
            self.pyxel.line(root_x, root_y, root_x, short_tip_y, shadow_color)
            self.pyxel.pset(root_x + max(-1, min(1, lean)), tip_y + 1, color)
        else:
            self.pyxel.line(root_x, root_y, tip_x, tip_y, color)
            if height >= 5:
                self.pyxel.pset(tip_x, tip_y, color)
        if shape in {1, 2} and height >= 5:
            self.pyxel.pset(tip_x, tip_y, color)

    def grassland_hash(self, cell_x: int, cell_z: int, salt: int, seed: int = 0) -> int:
        value = (
            cell_x * 73_856_093 ^ cell_z * 19_349_663 ^ salt * 83_492_791 ^ seed * 2_654_435_761
        ) & 0xFFFFFFFF
        value ^= value >> 13
        value = (value * 1_274_126_177) & 0xFFFFFFFF
        value ^= value >> 16
        return value & 0xFFFFFFFF

    def grassland_unit(self, cell_x: int, cell_z: int, salt: int, seed: int = 0) -> float:
        return self.grassland_hash(cell_x, cell_z, salt, seed) / 0xFFFFFFFF

    def point_in_projected_quad(
        self, x: float, y: float, corners: tuple[ProjectedPoint | None, ...]
    ) -> bool:
        projected = [point for point in corners if point is not None]
        if len(projected) != 4:
            return False
        signs: list[float] = []
        for index, point in enumerate(projected):
            next_point = projected[(index + 1) % len(projected)]
            cross = (next_point.x - point.x) * (y - point.y) - (next_point.y - point.y) * (
                x - point.x
            )
            if abs(cross) > 1e-6:
                signs.append(cross)
        return not signs or all(value >= 0 for value in signs) or all(value <= 0 for value in signs)

    def clamped_palette_color(self, value: object) -> int:
        try:
            color = int(value)
        except (TypeError, ValueError):
            color = 0
        return max(0, min(15, color))

    def draw_object(
        self,
        model: GameModel,
        obj: StaticObject,
        camera: CameraState,
        effects: EffectSystem | None = None,
    ) -> None:
        if self.draw_object_sprite(model, obj, camera, effects):
            return
        if obj.kind == "sprite_prop":
            self.draw_sprite_prop(obj, camera)
            return
        if obj.solid:
            height = obj.height if obj.height > 0 else 24.0
            color = self.solid_box_color(obj)
            self.draw_box(camera, obj.x, obj.z, obj.half_x, obj.half_z, height, 0.0, color)
            return
        point = camera.project(Vec3(obj.x, 0.0, obj.z))
        if point is None:
            return
        pyxel = self.pyxel
        x = int(point.x)
        y = int(point.y)
        if obj.kind == "water_station":
            color = 12 if obj.supply == "working" else 13
            pyxel.rect(x - 4, y - 12, 8, 12, color)
            pyxel.line(x - 6, y - 10, x + 6, y - 10, 7)
        elif obj.kind == "solar_station":
            pyxel.tri(x, y - 14, x - 7, y - 2, x + 7, y - 2, 10)
        elif obj.kind == "ambient_maintenance":
            pyxel.rect(x - 5, y - 12, 10, 12, 13)
            pyxel.rectb(x - 5, y - 12, 10, 12, 7)
            pyxel.pset(x - 2, y - 7, 10)
            pyxel.pset(x + 2, y - 7, 10)
        elif obj.inspectable:
            pyxel.rectb(x - 5, y - 13, 10, 12, 7)
            pyxel.pset(x, y - 7, 10)
        elif obj.kind == "reactive_prop":
            phase = (int(obj.x + obj.z) // 16) % 2
            pyxel.line(x - 4, y, x - 1, y - 5 - phase, 11)
            pyxel.line(x, y, x + 1, y - 6 + phase, 3)
            pyxel.line(x + 4, y, x + 2, y - 4 - phase, 11)
        else:
            pyxel.pset(x, y, 7)

    def draw_ground_detail(
        self, model: GameModel, detail: GroundDetail, camera: CameraState, world_tick: int
    ) -> None:
        if self.draw_ground_detail_sprite(model, detail, camera):
            return
        point = camera.project(Vec3(detail.x, 0.0, detail.z))
        if point is None:
            return
        x = int(point.x)
        y = int(point.y)
        phase = (world_tick // 8 + detail.phase) % 2
        self.pyxel.pset(x, y, detail.color)
        self.pyxel.line(x - 1, y, x - 1 + phase, y - 3, detail.color)

    def draw_ground_surfaces(self, model: GameModel, camera: CameraState) -> None:
        for surface in model.world.ground_surfaces:
            if self.ground_surface_is_baked(surface):
                continue
            self.draw_ground_surface(model, surface, camera)

    def draw_shallow_water_tiles(self, model: GameModel, camera: CameraState) -> None:
        config = model.config.get("shallow_water", {})
        if not config.get("enabled", False) or not config.get("surface_tiles_enabled", False):
            return
        areas = tuple(getattr(model.world, "shallow_water_areas", ()))
        if not areas:
            return
        pattern = config.get("surface_tile_pattern", ())
        if not isinstance(pattern, list) or not pattern:
            return
        tile_world_size = max(1.0, float(config.get("surface_tile_world_size", 64.0)))
        for area in areas:
            rect = area.rect
            columns = max(1, math.ceil(rect.width / tile_world_size))
            rows = max(1, math.ceil(rect.depth / tile_world_size))
            for row_index in range(rows):
                pattern_row = pattern[row_index % len(pattern)]
                if not isinstance(pattern_row, list) or not pattern_row:
                    continue
                z = rect.min_z + tile_world_size * (row_index + 0.5)
                for column_index in range(columns):
                    visual = pattern_row[column_index % len(pattern_row)]
                    if not isinstance(visual, str):
                        continue
                    asset = self.ground_surface_sprite_asset(model, visual)
                    if asset is None:
                        continue
                    x = rect.min_x + tile_world_size * (column_index + 0.5)
                    self.draw_ground_source_asset(asset, camera, x, z)

    def draw_shallow_water_shoreline_tiles(self, model: GameModel, camera: CameraState) -> None:
        config = model.config.get("shallow_water", {})
        if not config.get("enabled", False) or not config.get("shoreline_tiles_enabled", False):
            return
        areas = tuple(getattr(model.world, "shallow_water_areas", ()))
        if not areas:
            return
        tile_names = config.get("shoreline_tiles", {})
        if not isinstance(tile_names, dict):
            return
        tile_world_size = max(1.0, float(config.get("shoreline_tile_world_size", 64.0)))
        draw_corners = bool(config.get("shoreline_corner_tiles_enabled", True))
        corner_inset = max(
            0.0,
            min(
                tile_world_size * 0.5,
                float(config.get("shoreline_corner_inset_world", 0.0)),
            ),
        )

        def draw_tile(name_key: str, x: float, z: float) -> None:
            visual = tile_names.get(name_key)
            if not isinstance(visual, str):
                return
            asset = self.ground_surface_sprite_asset(model, visual)
            if asset is None:
                return
            self.draw_ground_source_asset(asset, camera, x, z)

        for area in areas:
            rect = area.rect
            columns = max(1, math.ceil(rect.width / tile_world_size))
            rows = max(1, math.ceil(rect.depth / tile_world_size))
            for column_index in range(columns):
                x = rect.min_x + tile_world_size * (column_index + 0.5)
                draw_tile("top", x, rect.min_z)
                draw_tile("bottom", x, rect.max_z)
            for row_index in range(rows):
                z = rect.min_z + tile_world_size * (row_index + 0.5)
                draw_tile("left", rect.min_x, z)
                draw_tile("right", rect.max_x, z)
            if draw_corners:
                draw_tile("corner_nw", rect.min_x + corner_inset, rect.min_z + corner_inset)
                draw_tile("corner_ne", rect.max_x - corner_inset, rect.min_z + corner_inset)
                draw_tile("corner_sw", rect.min_x + corner_inset, rect.max_z - corner_inset)
                draw_tile("corner_se", rect.max_x - corner_inset, rect.max_z - corner_inset)

    def draw_shallow_water_symbols(
        self, model: GameModel, camera: CameraState, presentation_time: float
    ) -> int:
        config = model.config.get("shallow_water", {})
        if not config.get("enabled", False) or not config.get("symbol_layer_enabled", False):
            return 0
        if config.get("symbol_combat_hidden", True) and model.combat_session is not None:
            return 0
        areas = tuple(getattr(model.world, "shallow_water_areas", ()))
        if not areas:
            return 0

        grid = max(8.0, float(config.get("symbol_grid_world", 30.0)))
        edge_grid = max(8.0, float(config.get("symbol_edge_grid_world", 26.0)))
        inner_margin = max(0.0, float(config.get("symbol_inner_margin_world", 14.0)))
        color = int(config.get("symbol_color", 7))
        secondary_color = int(config.get("symbol_secondary_color", color))
        max_per_area = max(0, int(config.get("symbol_max_per_area", 54)))
        if max_per_area <= 0:
            return 0
        total = 0

        for area in areas:
            rect = area.rect
            screen_bounds = self.ground_source_screen_bounds(
                camera, rect.min_x, rect.min_z, rect.width, rect.depth
            )
            if screen_bounds is None or not self.screen_rect_visible(screen_bounds, camera, 24.0):
                continue
            visible_rect = self.visible_ground_draw_rect(rect, camera, 24.0)
            if visible_rect is None:
                continue
            total += self._draw_shallow_water_interior_symbols(
                camera,
                visible_rect,
                grid,
                color,
                secondary_color,
                presentation_time,
                max_per_area,
            )
            total += self._draw_shallow_water_edge_symbols(
                camera,
                rect,
                visible_rect,
                edge_grid,
                inner_margin,
                color,
                secondary_color,
                presentation_time,
                max_per_area,
            )
        return total

    def _draw_shallow_water_interior_symbols(
        self,
        camera: CameraState,
        rect: WorldRect,
        grid: float,
        color: int,
        secondary_color: int,
        presentation_time: float,
        max_count: int,
    ) -> int:
        start_x = math.floor(rect.min_x / grid) - 1
        end_x = math.ceil(rect.max_x / grid) + 1
        start_z = math.floor(rect.min_z / grid) - 1
        end_z = math.ceil(rect.max_z / grid) + 1
        count = 0
        for zi in range(start_z, end_z + 1):
            for xi in range(start_x, end_x + 1):
                seed = self._water_symbol_seed(xi, zi)
                if seed % 5 == 0:
                    continue
                jitter_x = ((seed >> 4) & 15) / 15.0 - 0.5
                jitter_z = ((seed >> 9) & 15) / 15.0 - 0.5
                x = (xi + 0.5 + jitter_x * 0.52) * grid
                z = (zi + 0.5 + jitter_z * 0.52) * grid
                if not rect.contains_point(x, z):
                    continue
                point = camera.project(Vec3(x, 0.0, z))
                if point is None or not self._screen_point_visible(point, camera, 6.0):
                    continue
                style = seed % 4
                pulse = int((presentation_time * 5.0 + (seed & 7)) % 2)
                px = int(point.x)
                py = int(point.y)
                if style == 0:
                    self.pyxel.circb(px, py, 1 + pulse, color)
                elif style == 1:
                    self.pyxel.line(px - 2, py, px + 2, py - 1, color)
                    self.pyxel.pset(px + 3, py - 1, secondary_color)
                elif style == 2:
                    self.pyxel.pset(px, py, color)
                    self.pyxel.pset(px + 1, py - 1, secondary_color)
                else:
                    self.pyxel.line(px - 1, py + 1, px + 2, py, secondary_color)
                count += 1
                if count >= max_count:
                    return count
        return count

    def _draw_shallow_water_edge_symbols(
        self,
        camera: CameraState,
        area_rect: WorldRect,
        visible_rect: WorldRect,
        edge_grid: float,
        inner_margin: float,
        color: int,
        secondary_color: int,
        presentation_time: float,
        max_count: int,
    ) -> int:
        count = 0

        def draw_edge_point(x: float, z: float, seed: int, horizontal: bool) -> None:
            point = camera.project(Vec3(x, 0.0, z))
            if point is None or not self._screen_point_visible(point, camera, 8.0):
                return
            px = int(point.x)
            py = int(point.y)
            pulse = int((presentation_time * 4.0 + (seed & 3)) % 2)
            if horizontal:
                self.pyxel.line(px - 3, py, px + 3, py - 1, color)
                if pulse:
                    self.pyxel.pset(px, py - 2, secondary_color)
            else:
                self.pyxel.line(px - 1, py - 3, px, py + 3, color)
                if pulse:
                    self.pyxel.pset(px + 1, py, secondary_color)

        min_index_x = math.floor(visible_rect.min_x / edge_grid) - 1
        max_index_x = math.ceil(visible_rect.max_x / edge_grid) + 1
        min_index_z = math.floor(visible_rect.min_z / edge_grid) - 1
        max_index_z = math.ceil(visible_rect.max_z / edge_grid) + 1
        limit = max(8, max_count // 3 if max_count > 0 else 18)
        for xi in range(min_index_x, max_index_x + 1):
            x = xi * edge_grid
            if area_rect.min_x <= x <= area_rect.max_x:
                if visible_rect.min_z <= area_rect.min_z <= visible_rect.max_z:
                    seed = self._water_symbol_seed(xi, -73)
                    if seed % 3:
                        draw_edge_point(x, area_rect.min_z + inner_margin, seed, True)
                        count += 1
                if visible_rect.min_z <= area_rect.max_z <= visible_rect.max_z:
                    seed = self._water_symbol_seed(xi, 73)
                    if seed % 3:
                        draw_edge_point(x, area_rect.max_z - inner_margin, seed, True)
                        count += 1
            if count >= limit:
                return count
        for zi in range(min_index_z, max_index_z + 1):
            z = zi * edge_grid
            if area_rect.min_z <= z <= area_rect.max_z:
                if visible_rect.min_x <= area_rect.min_x <= visible_rect.max_x:
                    seed = self._water_symbol_seed(-71, zi)
                    if seed % 3:
                        draw_edge_point(area_rect.min_x + inner_margin, z, seed, False)
                        count += 1
                if visible_rect.min_x <= area_rect.max_x <= visible_rect.max_x:
                    seed = self._water_symbol_seed(71, zi)
                    if seed % 3:
                        draw_edge_point(area_rect.max_x - inner_margin, z, seed, False)
                        count += 1
            if count >= limit:
                return count
        return count

    def _water_symbol_seed(self, x_index: int, z_index: int) -> int:
        value = (x_index * 73856093) ^ (z_index * 19349663) ^ 0x9E3779B9
        value ^= value >> 13
        value *= 1274126177
        return value & 0xFFFFFFFF

    def _screen_point_visible(
        self, point: ProjectedPoint, camera: CameraState, margin: float
    ) -> bool:
        return (
            -margin <= point.x <= camera.viewport_width + margin
            and -margin <= point.y <= camera.viewport_height + margin
        )

    def draw_ground_surface(
        self, model: GameModel, surface: GroundSurface, camera: CameraState
    ) -> None:
        for visual in surface.layers:
            asset = self.ground_surface_sprite_asset(model, visual)
            if asset is None:
                continue
            self.draw_ground_source_asset(asset, camera, surface.x, surface.z)

    def draw_baked_ground_patches(
        self, model: GameModel, camera: CameraState
    ) -> tuple[BakedGroundPatch, ...]:
        if not self.baked_ground_camera_supported(model, camera):
            self._active_baked_ground_patches = ()
            return ()
        active: list[BakedGroundPatch] = []
        self._baked_ground_builds_this_frame = 0
        for patch in self.visible_baked_ground_patches(model, camera):
            baked = self.baked_ground_image(model, patch, camera)
            if baked is None:
                continue
            current_center = camera.project(Vec3(patch.x, 0.0, patch.z))
            if current_center is None:
                continue
            x = int(round(baked.left + current_center.x - baked.reference_center_x))
            y = int(round(baked.top + current_center.y - baked.reference_center_y))
            rect = ScreenRect(x, y, baked.width * baked.scale, baked.height * baked.scale)
            if not self.screen_rect_visible(rect, camera, 2.0):
                continue
            self.pyxel.blt(
                x,
                y,
                baked.image,
                0,
                0,
                baked.width,
                baked.height,
                colkey=8,
                scale=baked.scale,
            )
            active.append(patch)
        self._active_baked_ground_patches = tuple(active)
        return self._active_baked_ground_patches

    def visible_baked_ground_patches(
        self, model: GameModel, camera: CameraState
    ) -> tuple[BakedGroundPatch, ...]:
        projection_kind = "affine" if self.camera_is_affine(camera) else "perspective"
        patches = [
            patch
            for patch in model.world.baked_ground_patches
            if patch.enabled and patch.projection_kind == projection_kind
        ]
        patches.sort(
            key=lambda patch: (
                (patch.x - camera.target.x) * (patch.x - camera.target.x)
                + (patch.z - camera.target.z) * (patch.z - camera.target.z),
                patch.id,
            )
        )
        return tuple(patches)

    def baked_ground_camera_supported(self, model: GameModel, camera: CameraState) -> bool:
        if self.camera_is_affine(camera):
            return True
        camera_config = model.config["camera"]
        return (
            abs(camera.yaw_deg - float(camera_config["yaw_deg"])) <= 0.01
            and abs(camera.pitch_deg - float(camera_config["pitch_deg"])) <= 0.01
            and abs(camera.distance - float(camera_config["base_distance"])) <= 0.75
            and abs(camera.anchor_x - float(camera_config["screen_anchor"][0])) <= 0.001
            and abs(camera.anchor_y - float(camera_config["screen_anchor"][1])) <= 0.001
        )

    def baked_ground_image(
        self, model: GameModel, patch: BakedGroundPatch, camera: CameraState
    ) -> BakedGroundImage | None:
        bucket_x, bucket_z = self.baked_ground_camera_bucket(patch, camera)
        key = self.baked_ground_cache_key(patch, camera, bucket_x, bucket_z)
        cached = self._baked_ground_cache.get(key)
        if cached is not None:
            return cached
        if self._baked_ground_builds_this_frame >= self.max_baked_ground_builds_per_frame:
            return self.fallback_baked_ground_image(patch, camera, bucket_x, bucket_z)
        self._baked_ground_builds_this_frame += 1

        reference_camera = self.baked_ground_reference_camera(camera, bucket_x, bucket_z)
        bounds = self.ground_source_screen_bounds(
            reference_camera,
            patch.min_x,
            patch.min_z,
            patch.width,
            patch.depth,
        )
        center = reference_camera.project(Vec3(patch.x, 0.0, patch.z))
        if bounds is None or center is None:
            return None
        overlap = max(0, patch.screen_overlap_px)
        left = bounds.x - overlap
        top = bounds.y - overlap
        draw_width = bounds.width + overlap * 2
        draw_height = bounds.height + overlap * 2
        sample = max(1, patch.screen_sample_px)
        width = math.ceil(draw_width / sample)
        height = math.ceil(draw_height / sample)
        if width <= 0 or height <= 0 or width > 1024 or height > 1024:
            return None

        image = self.pyxel.Image(width, height)
        image.cls(8)
        for py in range(height):
            screen_y = top + (py + 0.5) * sample
            for px in range(width):
                screen_x = left + (px + 0.5) * sample
                ground = self.baked_ground_screen_to_ground(reference_camera, screen_x, screen_y)
                if ground is None or not patch.contains(ground.x, ground.y, margin=0.5):
                    continue
                color = self.baked_ground_color_at(model, patch, ground.x, ground.y)
                if color is not None:
                    image.pset(px, py, color)
        baked = BakedGroundImage(
            image=image,
            left=left,
            top=top,
            width=width,
            height=height,
            scale=sample,
            bucket_x=bucket_x,
            bucket_z=bucket_z,
            reference_center_x=center.x,
            reference_center_y=center.y,
        )
        self._baked_ground_cache[key] = baked
        return baked

    def baked_ground_reference_camera(
        self, camera: CameraState, bucket_x: float, bucket_z: float
    ) -> CameraState:
        if self.camera_is_affine(camera):
            return camera
        return CameraState(
            target=Vec3(bucket_x, 0.0, bucket_z),
            yaw_deg=camera.yaw_deg,
            pitch_deg=camera.pitch_deg,
            horizontal_fov_deg=camera.horizontal_fov_deg,
            distance=camera.distance,
            near=camera.near,
            far=camera.far,
            anchor_x=camera.anchor_x,
            anchor_y=camera.anchor_y,
            viewport_width=camera.viewport_width,
            viewport_height=camera.viewport_height,
        )

    def baked_ground_screen_to_ground(self, camera: CameraState, screen_x: float, screen_y: float):
        if self.camera_is_affine(camera):
            return screen_to_ground_affine(camera, screen_x, screen_y)
        return screen_to_ground_point(camera, screen_x, screen_y)

    def baked_ground_cache_key(
        self,
        patch: BakedGroundPatch,
        camera: CameraState,
        bucket_x: float,
        bucket_z: float,
    ) -> tuple[object, ...]:
        if self.camera_is_affine(camera):
            profile = getattr(camera, "profile", None)
            return (
                patch.id,
                patch.group,
                "affine",
                getattr(profile, "profile_id", "unknown"),
                camera.viewport_width,
                camera.viewport_height,
                round(getattr(camera, "effective_scale", 1.0), 4),
                patch.tile_world_size,
                patch.default_layers,
                tuple((tile.cell_x, tile.cell_z, tile.layers) for tile in patch.tiles),
            )
        return (
            patch.id,
            patch.group,
            round(bucket_x, 3),
            round(bucket_z, 3),
            camera.viewport_width,
            camera.viewport_height,
            round(camera.yaw_deg, 3),
            round(camera.pitch_deg, 3),
            round(camera.horizontal_fov_deg, 3),
            round(camera.distance, 3),
            round(camera.anchor_x, 3),
            round(camera.anchor_y, 3),
        )

    def fallback_baked_ground_image(
        self,
        patch: BakedGroundPatch,
        camera: CameraState,
        bucket_x: float,
        bucket_z: float,
    ) -> BakedGroundImage | None:
        best: tuple[float, BakedGroundImage] | None = None
        if self.camera_is_affine(camera):
            return None
        profile = (
            camera.viewport_width,
            camera.viewport_height,
            round(camera.yaw_deg, 3),
            round(camera.pitch_deg, 3),
            round(camera.horizontal_fov_deg, 3),
            round(camera.distance, 3),
            round(camera.anchor_x, 3),
            round(camera.anchor_y, 3),
        )
        for key, baked in self._baked_ground_cache.items():
            if key[0] != patch.id or key[1] != patch.group or key[4:] != profile:
                continue
            distance_sq = (baked.bucket_x - bucket_x) ** 2 + (baked.bucket_z - bucket_z) ** 2
            if best is None or distance_sq < best[0]:
                best = (distance_sq, baked)
        return None if best is None else best[1]

    def baked_ground_camera_bucket(
        self, patch: BakedGroundPatch, camera: CameraState
    ) -> tuple[float, float]:
        if self.camera_is_affine(camera):
            return patch.x, patch.z
        bucket = patch.camera_bucket_world_size
        if bucket <= 1e-6:
            return patch.x, patch.z
        return round(camera.target.x / bucket) * bucket, round(camera.target.z / bucket) * bucket

    def baked_ground_color_at(
        self, model: GameModel, patch: BakedGroundPatch, x: float, z: float
    ) -> int | None:
        color: int | None = None
        local_x = x - patch.min_x
        local_z = z - patch.min_z
        cell_x = int(math.floor(local_x / patch.tile_world_size))
        cell_z = int(math.floor(local_z / patch.tile_world_size))
        cell_x = max(0, min(int(math.ceil(patch.width / patch.tile_world_size)) - 1, cell_x))
        cell_z = max(0, min(int(math.ceil(patch.depth / patch.tile_world_size)) - 1, cell_z))
        tile_layers = self.baked_ground_tile_layers(patch, cell_x, cell_z)
        tile_origin_x = patch.min_x + cell_x * patch.tile_world_size
        tile_origin_z = patch.min_z + cell_z * patch.tile_world_size
        for visual in tile_layers:
            layer_color = self.sample_ground_layer_color(
                model,
                visual,
                x,
                z,
                tile_origin_x,
                tile_origin_z,
                patch.tile_world_size,
                patch.tile_world_size,
            )
            if layer_color is not None:
                color = layer_color

        for detail in model.world.ground_details:
            if not patch.contains(detail.x, detail.z, margin=patch.tile_world_size):
                continue
            detail_color = self.sample_ground_detail_color(model, detail, x, z)
            if detail_color is not None:
                color = detail_color
        return color

    def baked_ground_tile_layers(
        self, patch: BakedGroundPatch, cell_x: int, cell_z: int
    ) -> tuple[str, ...]:
        for tile in patch.tiles:
            if tile.cell_x == cell_x and tile.cell_z == cell_z:
                return tile.layers
        return patch.default_layers

    def sample_ground_layer_color(
        self,
        model: GameModel,
        visual: str,
        x: float,
        z: float,
        origin_x: float,
        origin_z: float,
        width_world: float,
        depth_world: float,
    ) -> int | None:
        asset = self.ground_surface_sprite_asset(model, visual)
        return self.sample_ground_asset_color(
            asset, x, z, origin_x, origin_z, width_world, depth_world
        )

    def sample_ground_detail_color(
        self, model: GameModel, detail: GroundDetail, x: float, z: float
    ) -> int | None:
        asset = self.ground_detail_sprite_asset(model, detail)
        if asset is None:
            return None
        frame = asset.frame()
        source = frame.source
        if source is None:
            return None
        width_world, depth_world = asset.definition.world_size
        anchor_x, anchor_y = asset.definition.anchor_px
        origin_x = detail.x - anchor_x * width_world / source.width
        origin_z = detail.z - anchor_y * depth_world / source.height
        return self.sample_ground_asset_color(
            asset, x, z, origin_x, origin_z, width_world, depth_world
        )

    def sample_ground_asset_color(
        self,
        asset: LoadedSpriteAsset | None,
        x: float,
        z: float,
        origin_x: float,
        origin_z: float,
        width_world: float,
        depth_world: float,
    ) -> int | None:
        if asset is None:
            return None
        frame = asset.frame()
        source = frame.source
        if source is None:
            return None
        if not (origin_x <= x < origin_x + width_world and origin_z <= z < origin_z + depth_world):
            return None
        src_x = int((x - origin_x) / width_world * source.width)
        src_y = int((z - origin_z) / depth_world * source.height)
        src_x = max(0, min(source.width - 1, src_x))
        src_y = max(0, min(source.height - 1, src_y))
        char = source.rows[src_y][src_x]
        if int(char, 16) == asset.definition.colkey:
            return None
        return int(char, 16)

    def ground_surface_is_baked(self, surface: GroundSurface) -> bool:
        return any(
            patch.contains(surface.x, surface.z, margin=patch.tile_world_size * 0.5)
            for patch in self._active_baked_ground_patches
        )

    def point_in_active_baked_ground_patch(self, x: float, z: float) -> bool:
        return any(patch.contains(x, z) for patch in self._active_baked_ground_patches)

    def ground_surface_sprite_asset(
        self, model: GameModel, visual: str
    ) -> LoadedSpriteAsset | None:
        return self.configured_sprite_asset(model, f"{visual}_asset")

    def draw_object_sprite(
        self,
        model: GameModel,
        obj: StaticObject,
        camera: CameraState,
        effects: EffectSystem | None = None,
    ) -> bool:
        asset = self.object_sprite_asset(model, obj)
        if asset is None:
            return False
        if obj.kind == "reactive_prop":
            return self.draw_reactive_prop_sprite(model, obj, camera, asset, effects)
        if asset.definition.projection_mode == "ground_decal_source_v1":
            return self.draw_ground_source_asset(asset, camera, obj.x, obj.z)
        placement = placement_for_upright_height_billboard(
            camera,
            asset.definition,
            Vec3(obj.x, 0.0, obj.z),
        )
        if placement is None:
            return False
        self.draw_atmospheric_scaled_sprite(asset, placement)
        return True

    def draw_reactive_prop_sprite(
        self,
        model: GameModel,
        obj: StaticObject,
        camera: CameraState,
        asset: LoadedSpriteAsset,
        effects: EffectSystem | None,
    ) -> bool:
        state = self.reactive_environment_state(effects, obj.id)
        if asset.definition.projection_mode == "ground_decal_source_v1":
            drawn = self.draw_ground_source_asset(asset, camera, obj.x, obj.z)
            if drawn and state is not None:
                self.draw_reactive_ground_prop_overlay(model, obj, camera, state)
            return drawn

        placement = placement_for_upright_height_billboard(
            camera,
            asset.definition,
            Vec3(obj.x, 0.0, obj.z),
        )
        if placement is None:
            return False
        if (
            state is not None
            and self.reactive_upright_deform_enabled(model)
            and self.draw_reactive_upright_prop(model, obj, camera, asset, placement, state)
        ):
            self.draw_reactive_ground_prop_overlay(model, obj, camera, state)
            return True
        self.draw_atmospheric_scaled_sprite(
            asset,
            placement,
            self.reactive_environment_pose_frame(model, asset, state),
        )
        return True

    def reactive_upright_deform_enabled(self, model: GameModel) -> bool:
        config = model.config.get("reactive_environment", {})
        return bool(config.get("upright_deform_enabled", False))

    def reactive_environment_pose_frames_enabled(self, model: GameModel) -> bool:
        config = model.config.get("reactive_environment", {})
        return bool(config.get("pose_frames_enabled", False))

    def reactive_environment_pose_frame(
        self,
        model: GameModel,
        asset: LoadedSpriteAsset,
        state: ReactiveEnvironmentState | None,
    ):
        if state is None or not self.reactive_environment_pose_frames_enabled(model):
            return None
        if state.pose_id not in asset.frames:
            return None
        return asset.frame(state.pose_id)

    def reactive_environment_state(
        self, effects: EffectSystem | None, object_id: str
    ) -> ReactiveEnvironmentState | None:
        if effects is None:
            return None
        state = effects.reactive_environment_states.get(object_id)
        if state is None or state.phase == "IDLE":
            return None
        return state

    def draw_reactive_upright_prop(
        self,
        model: GameModel,
        obj: StaticObject,
        camera: CameraState,
        asset: LoadedSpriteAsset,
        placement,
        state: ReactiveEnvironmentState,
    ) -> bool:
        frame = asset.frame()
        source = frame.source
        if source is None:
            return False
        direction = self.reactive_environment_screen_direction(camera, obj, state)
        if direction is None:
            return False
        dir_x, dir_y = direction
        config = model.config.get("reactive_environment", {})
        bend_px = float(config.get("upright_bend_px", 10.0))
        part_px = float(config.get("upright_part_px", 0.0))
        intensity = self.reactive_environment_intensity(state)
        if intensity <= 1e-6:
            return False
        side_x, side_y = -dir_y, dir_x

        sample_step = 2 if placement.scale < 0.5 else 1
        pixel_size = max(1, int(round(placement.scale * sample_step)))
        source_width = max(1, int(source.width))
        source_height = max(1, int(source.height))
        for row_index, row in enumerate(source.rows):
            if row_index % sample_step != 0:
                continue
            lift = 1.0 - row_index / max(source_height - 1, 1)
            row_shift = bend_px * intensity * lift**1.35
            for col_index, char in enumerate(row):
                if col_index % sample_step != 0:
                    continue
                if int(char, 16) == asset.definition.colkey:
                    continue
                col_t = (col_index + 0.5) / source_width
                side = -1.0 if col_t < 0.5 else 1.0
                side_amount = abs(col_t - 0.5) * 2.0
                part_shift = part_px * intensity * (0.3 + 0.7 * lift) * side_amount
                px = (
                    placement.left
                    + (col_index + 0.5) / source_width * (placement.right - placement.left)
                    + dir_x * row_shift
                    + side_x * side * part_shift
                )
                py = (
                    placement.top
                    + (row_index + 0.5) / source_height * (placement.bottom - placement.top)
                    + dir_y * row_shift * 0.5
                    + side_y * side * part_shift * 0.5
                )
                color = self.atmosphere_dither_color(
                    int(char, 16), col_index, row_index, asset.definition.colkey
                )
                if pixel_size <= 1:
                    self.pyxel.pset(int(px), int(py), color)
                else:
                    self.pyxel.rect(int(px), int(py), pixel_size, pixel_size, color)
        return True

    def draw_reactive_ground_prop_overlay(
        self,
        model: GameModel,
        obj: StaticObject,
        camera: CameraState,
        state: ReactiveEnvironmentState,
    ) -> None:
        root = camera.project(Vec3(obj.x, 0.0, obj.z))
        direction = self.reactive_environment_screen_direction(camera, obj, state)
        if root is None or direction is None:
            return
        dir_x, dir_y = direction
        side_x, side_y = -dir_y, dir_x
        config = model.config.get("reactive_environment", {})
        length = float(config.get("overlay_line_px", 8.0)) * self.reactive_environment_intensity(
            state
        )
        if length <= 1e-6:
            return
        spread = max(2.0, min(5.0, state.visual_radius * 0.18))
        x = int(root.x)
        y = int(root.y)
        pyxel = self.pyxel
        for side, color in ((-1.0, 11), (1.0, 3)):
            sx = x + int(round(side_x * spread * side))
            sy = y + int(round(side_y * spread * side))
            ex = sx + int(round(dir_x * length + side_x * spread * side * 0.7))
            ey = sy + int(round(dir_y * length + side_y * spread * side * 0.7))
            pyxel.line(sx, sy, ex, ey, color)

    def reactive_environment_intensity(self, state: ReactiveEnvironmentState) -> float:
        return max(0.0, min(state.strength, 1.0)) * (1.0 - max(0.0, min(state.progress, 1.0)))

    def reactive_environment_screen_direction(
        self, camera: CameraState, obj: StaticObject, state: ReactiveEnvironmentState
    ) -> tuple[float, float] | None:
        root = camera.project(Vec3(obj.x, 0.0, obj.z))
        moved = camera.project(
            Vec3(obj.x + state.direction_x * 16.0, 0.0, obj.z + state.direction_z * 16.0)
        )
        if root is None or moved is None:
            return None
        dx = moved.x - root.x
        dy = moved.y - root.y
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            return None
        return dx / length, dy / length

    def object_sprite_asset(self, model: GameModel, obj: StaticObject) -> LoadedSpriteAsset | None:
        if obj.kind == "water_station":
            key = (
                "water_station_working_asset"
                if obj.supply == "working"
                else "water_station_stopped_asset"
            )
            return self.configured_sprite_asset(model, key)
        if obj.kind == "solar_station":
            active = (
                model.interaction is not None
                and model.interaction.kind == "energy_refill"
                and model.interaction.object_id == obj.id
            )
            return self.configured_sprite_asset(
                model,
                "solar_station_active_asset" if active else "solar_station_idle_asset",
            )
        if obj.kind in {"obstacle", "sprite_prop"}:
            asset = self.configured_sprite_asset(model, f"{obj.visual}_asset")
            if asset is not None:
                return asset
        if obj.kind == "sprite_prop":
            key = "tree_thin_asset" if obj.visual == "tree_thin_b" else "tree_leafy_asset"
            return self.configured_sprite_asset(model, key)
        if obj.kind == "reactive_prop":
            asset = self.configured_sprite_asset(model, f"{obj.visual}_asset")
            if asset is not None:
                return asset
            key = (
                "reactive_grass_low_asset"
                if obj.visual == "reactive_grass_low"
                else "reactive_grass_tall_asset"
            )
            return self.configured_sprite_asset(model, key)
        return None

    def draw_ground_detail_sprite(
        self, model: GameModel, detail: GroundDetail, camera: CameraState
    ) -> bool:
        asset = self.ground_detail_sprite_asset(model, detail)
        return self.draw_ground_source_asset(asset, camera, detail.x, detail.z)

    def draw_ground_source_asset(
        self, asset: LoadedSpriteAsset | None, camera: CameraState, x: float, z: float
    ) -> bool:
        if asset is None or asset.definition.projection_mode != "ground_decal_source_v1":
            return False
        frame = asset.frame()
        source = frame.source
        if source is None:
            return False
        width_world, depth_world = asset.definition.world_size
        anchor_x, anchor_y = asset.definition.anchor_px
        origin_x = x - anchor_x * width_world / source.width
        origin_z = z - anchor_y * depth_world / source.height
        step_x = width_world / source.width
        step_z = depth_world / source.height
        bounds = self.ground_source_screen_bounds(
            camera,
            origin_x,
            origin_z,
            width_world,
            depth_world,
        )
        if bounds is None or not self.screen_rect_visible(bounds, camera, 2.0):
            return True
        draw_size = self.ground_decal_screen_pixel_size(camera, x, z, step_x, step_z)
        sample_step = 2 if draw_size <= 1 else 1
        pixel_size = max(draw_size, sample_step)
        for col_index, row_index, char in self.ground_source_visible_pixels(asset, source):
            if col_index % sample_step != 0 or row_index % sample_step != 0:
                continue
            world_z = origin_z + (row_index + 0.5) * step_z
            world_x = origin_x + (col_index + 0.5) * step_x
            point = camera.project(Vec3(world_x, 0.0, world_z))
            if point is None:
                continue
            px = int(point.x)
            py = int(point.y)
            color = int(char, 16)
            color = self.atmosphere_dither_color(
                color, col_index, row_index, asset.definition.colkey
            )
            if pixel_size <= 1:
                self.pyxel.pset(px, py, color)
            else:
                self.pyxel.rect(px, py, pixel_size, pixel_size, color)
        return True

    def ground_source_visible_pixels(
        self, asset: LoadedSpriteAsset, source
    ) -> tuple[tuple[int, int, str], ...]:
        key = (asset.definition.asset_id, source.frame_id, asset.definition.colkey)
        cached = self._ground_source_pixels.get(key)
        if cached is not None:
            return cached
        colkey_char = format(asset.definition.colkey, "X")
        pixels = tuple(
            (col_index, row_index, char)
            for row_index, row in enumerate(source.rows)
            for col_index, char in enumerate(row)
            if char != colkey_char
        )
        self._ground_source_pixels[key] = pixels
        return pixels

    def ground_source_screen_bounds(
        self,
        camera: CameraState,
        origin_x: float,
        origin_z: float,
        width_world: float,
        depth_world: float,
    ) -> ScreenRect | None:
        corners = [
            camera.project(Vec3(origin_x, 0.0, origin_z)),
            camera.project(Vec3(origin_x + width_world, 0.0, origin_z)),
            camera.project(Vec3(origin_x + width_world, 0.0, origin_z + depth_world)),
            camera.project(Vec3(origin_x, 0.0, origin_z + depth_world)),
        ]
        points = [point for point in corners if point is not None]
        if not points:
            return None
        min_x = math.floor(min(point.x for point in points)) - 2
        min_y = math.floor(min(point.y for point in points)) - 2
        max_x = math.ceil(max(point.x for point in points)) + 2
        max_y = math.ceil(max(point.y for point in points)) + 2
        return ScreenRect(min_x, min_y, max(1, max_x - min_x), max(1, max_y - min_y))

    def ground_decal_screen_pixel_size(
        self, camera: CameraState, x: float, z: float, step_x: float, step_z: float
    ) -> int:
        center = camera.project(Vec3(x, 0.0, z))
        right = camera.project(Vec3(x + step_x, 0.0, z))
        forward = camera.project(Vec3(x, 0.0, z + step_z))
        if center is None or right is None or forward is None:
            return 1
        size = max(
            math.hypot(right.x - center.x, right.y - center.y),
            math.hypot(forward.x - center.x, forward.y - center.y),
        )
        return max(1, min(3, int(round(size))))

    def ground_detail_sprite_asset(
        self, model: GameModel, detail: GroundDetail
    ) -> LoadedSpriteAsset | None:
        return self.configured_sprite_asset(model, f"{detail.visual}_asset")

    def draw_sprite_prop(self, obj: StaticObject, camera: CameraState) -> None:
        bounds = self.sprite_prop_bounds(obj, camera)
        if bounds is None:
            return
        pyxel = self.pyxel
        trunk_w = max(3, bounds.width // 5)
        trunk_h = max(8, bounds.height // 3)
        trunk_x = bounds.x + bounds.width // 2 - trunk_w // 2
        trunk_y = bounds.max_y - trunk_h
        crown_w = max(12, bounds.width)
        crown_h = max(12, bounds.height - trunk_h // 2)
        pyxel.rect(trunk_x, trunk_y, trunk_w, trunk_h, 4)
        pyxel.rectb(trunk_x, trunk_y, trunk_w, trunk_h, 0)
        pyxel.circ(bounds.x + bounds.width // 2, bounds.y + crown_h // 3, crown_w // 3, 11)
        pyxel.circ(bounds.x + bounds.width // 3, bounds.y + crown_h // 2, crown_w // 4, 3)
        pyxel.circ(bounds.x + bounds.width * 2 // 3, bounds.y + crown_h // 2, crown_w // 4, 3)
        pyxel.line(bounds.x + 2, bounds.max_y - 1, bounds.max_x - 2, bounds.max_y - 1, 0)

    def draw_enemy(
        self,
        model: GameModel,
        enemy,
        camera: CameraState,
        presentation: ActorPresentation | None = None,
    ) -> None:
        if enemy.state == "DEFEATED":
            return
        if self.combat_defeat_enemy_flicker_hidden(model, enemy):
            return
        if presentation is None:
            presentation = self.enemy_actor_presentation(model, enemy, camera)
        enemy_x = presentation.x
        enemy_z = presentation.z
        point = camera.project(Vec3(enemy_x, 4.0 + presentation.jump_y, enemy_z))
        if point is None:
            return
        pyxel = self.pyxel
        radius = self.depth_scaled_radius(camera, point.depth, numerator=900, minimum=3)
        color = 8 if enemy.kind == "normal" else 2
        if enemy.state == "REPELLED":
            color = 12
        elif enemy.state == "REST":
            color = 13
        elif enemy.state == "RETURN_HOME":
            color = 5
        elif enemy.state == "CAPTURED":
            color = 12
        elif enemy.state == "WINDUP":
            color = 8
        elif enemy.state == "RECOVER":
            color = 13
        x = int(point.x)
        y = int(point.y)
        sprite_placement = self.draw_enemy_sprite(
            model, enemy, camera, enemy_x, enemy_z, presentation.jump_y
        )
        if sprite_placement is not None:
            left, top, width, height = sprite_placement.rect
            x = left + width // 2
            y = top + height // 2
            radius = max(radius, max(width, height) // 2)
        else:
            pyxel.circ(x, y, radius, color)
            for index in range(8):
                angle = index * math.tau / 8.0
                pyxel.line(
                    x + int(math.cos(angle) * radius),
                    y + int(math.sin(angle) * radius),
                    x + int(math.cos(angle) * (radius + 3)),
                    y + int(math.sin(angle) * (radius + 3)),
                    7,
                )
        if enemy.state == "REST":
            pyxel.line(x - radius, y - radius - 3, x + radius, y - radius - 3, 7)
        elif enemy.state == "APPROACH":
            pyxel.circb(x, y, radius + 4, 8)
        elif enemy.state == "WINDUP":
            self.draw_world_line(
                camera,
                Vec3(enemy_x, 0.0, enemy_z),
                Vec3(enemy_x + enemy.dash_x * 56.0, 0.0, enemy_z + enemy.dash_z * 56.0),
                8,
            )
            pyxel.circb(x, y, radius + 5, 8)
        elif enemy.state == "DASH":
            pyxel.circb(x, y, radius + 5, 2)
        elif enemy.state == "CAPTURED":
            self.draw_world_circle(camera, enemy_x, enemy_z, 16.0, 12)
            pyxel.circb(x, y, radius + 5, 12)

    def enemy_sprite_asset(self, model: GameModel, enemy) -> LoadedSpriteAsset | None:
        return self.enemy_kind_sprite_asset(model, enemy.kind)

    def enemy_kind_sprite_asset(
        self, model: GameModel, enemy_kind: str
    ) -> LoadedSpriteAsset | None:
        if enemy_kind == "normal":
            return self.configured_sprite_asset(model, "normal_urchin_idle_asset")
        if enemy_kind == "abnormal":
            return self.configured_sprite_asset(model, "abnormal_urchin_idle_asset")
        return None

    def enemy_sprite_placement(
        self,
        model: GameModel,
        enemy,
        camera: CameraState,
        x: float | None = None,
        z: float | None = None,
        y: float = 0.0,
    ):
        asset = self.enemy_sprite_asset(model, enemy)
        if asset is None:
            return None
        draw_x = enemy.x if x is None else x
        draw_z = enemy.z if z is None else z
        return placement_for_upright_height_billboard(
            camera,
            asset.definition,
            Vec3(draw_x, y, draw_z),
        )

    def draw_enemy_sprite(
        self,
        model: GameModel,
        enemy,
        camera: CameraState,
        x: float | None = None,
        z: float | None = None,
        y: float = 0.0,
    ):
        placement = self.enemy_sprite_placement(model, enemy, camera, x, z, y)
        if placement is None:
            return None
        asset = self.enemy_sprite_asset(model, enemy)
        if asset is None:
            return None
        self.draw_atmospheric_scaled_sprite(asset, placement)
        return placement

    def draw_enemy_snapshot(
        self, model: GameModel, snapshot: EnemySnapshot, camera: CameraState
    ) -> None:
        asset = self.enemy_kind_sprite_asset(model, snapshot.enemy_kind)
        point = camera.project(Vec3(snapshot.x, 4.0, snapshot.z))
        if point is None:
            return
        if asset is not None:
            placement = placement_for_upright_height_billboard(
                camera,
                asset.definition,
                Vec3(snapshot.x, 0.0, snapshot.z),
            )
            if placement is None:
                return
            self.draw_atmospheric_scaled_sprite(asset, placement)
            left, top, width, height = placement.rect
            x = left + width // 2
            y = top + height // 2
            radius = max(4, max(width, height) // 2)
        else:
            x = int(point.x)
            y = int(point.y)
            radius = self.depth_scaled_radius(camera, point.depth, numerator=900, minimum=3)
            self.pyxel.circb(x, y, radius, 10)
            for index in range(4):
                angle = index * math.tau / 4.0
                self.pyxel.line(
                    x,
                    y,
                    x + int(math.cos(angle) * radius),
                    y + int(math.sin(angle) * radius),
                    7,
                )
        accent = 7 if snapshot.progress < 0.55 else 10
        self.pyxel.circb(x, y, radius + 4, accent)
        self.pyxel.line(x - radius - 2, y, x - radius + 2, y, 10)
        self.pyxel.line(x + radius - 2, y, x + radius + 2, y, 10)
        self.pyxel.line(x, y - radius - 2, x, y - radius + 2, 7)

    def normal_enemy_sprite_asset(self, model: GameModel) -> LoadedSpriteAsset | None:
        return self.configured_sprite_asset(model, "normal_urchin_idle_asset")

    def normal_enemy_sprite_placement(self, model: GameModel, enemy, camera: CameraState):
        if enemy.kind != "normal":
            return None
        return self.enemy_sprite_placement(model, enemy, camera)

    def abnormal_enemy_sprite_asset(self, model: GameModel) -> LoadedSpriteAsset | None:
        return self.configured_sprite_asset(model, "abnormal_urchin_idle_asset")

    def abnormal_enemy_sprite_placement(self, model: GameModel, enemy, camera: CameraState):
        if enemy.kind != "abnormal":
            return None
        return self.enemy_sprite_placement(model, enemy, camera)

    def draw_bubble(self, model: GameModel, camera: CameraState) -> None:
        bubble = model.bubble
        if bubble is None:
            return
        point = camera.project(Vec3(bubble.x, 5.0, bubble.z))
        if point is None:
            return
        radius = self.depth_scaled_radius(camera, point.depth, numerator=600, minimum=3)
        x = int(point.x)
        y = int(point.y)
        self.pyxel.circb(x, y, radius, 12)
        self.pyxel.pset(x, y, 7)

    def draw_player(
        self,
        model: GameModel,
        camera: CameraState,
        presentation_time: float,
        presentation: ActorPresentation | None = None,
    ) -> None:
        if presentation is None:
            presentation = self.player_actor_presentation(model, camera)
        hover = self.player_visual_y_offset(model, presentation_time) + presentation.jump_y
        shadow = camera.project(Vec3(presentation.x, 0.0, presentation.z))
        if shadow is not None:
            radius = self.depth_scaled_radius(camera, shadow.depth, numerator=1200, minimum=3)
            self.draw_shadow_ellipse(
                int(shadow.x - radius),
                int(shadow.y - radius // 3),
                radius * 2,
                max(2, radius // 2),
                self.atmosphere_shadow_dither_cells(camera, shadow.depth, important_actor=True),
            )
        if self.draw_player_sprite(
            model, camera, presentation_time, presentation.x, presentation.z, hover
        ):
            return
        half = model.player_cube_size / 2.0
        self.draw_box(
            camera,
            presentation.x,
            presentation.z,
            half,
            half,
            model.player_cube_size,
            hover,
            11,
        )

    def player_visual_y_offset(self, model: GameModel, presentation_time: float) -> float:
        return (
            self.player_visual_hover(model, presentation_time)
            + self.interaction_actor_jump(model, "water_refill")
            + self.combat_victory_actor_jump(model, "player")
        )

    def player_visual_hover(self, model: GameModel, presentation_time: float) -> float:
        hover = float(model.config["player"]["visual_hover_base"])
        hover += math.sin(
            presentation_time / float(model.config["player"]["visual_hover_period_sec"]) * math.tau
        )
        return hover * float(model.config["player"]["visual_hover_amplitude"]) / 2.0

    def player_sprite_asset(
        self, model: GameModel, camera: CameraState | None = None
    ) -> LoadedSpriteAsset | None:
        if camera is None:
            return self.configured_sprite_asset(model, "player_idle_asset")
        selection = self.player_sprite_selection(model, camera)
        if selection is None:
            return None
        asset, _flip_x = selection
        return asset

    def player_sprite_selection(
        self, model: GameModel, camera: CameraState
    ) -> tuple[LoadedSpriteAsset, bool] | None:
        view_name = self.player_sprite_direction_view(model, camera)
        config_key = f"player_{view_name}_asset" if view_name != "idle" else "player_idle_asset"
        asset = self.configured_sprite_asset(model, config_key)
        using_idle_fallback = False
        if asset is None and config_key != "player_idle_asset":
            asset = self.configured_sprite_asset(model, "player_idle_asset")
            using_idle_fallback = asset is not None
        if asset is None:
            return None
        return asset, using_idle_fallback and self.player_sprite_flip_x(model, camera)

    def player_sprite_direction_view(self, model: GameModel, camera: CameraState) -> str:
        spin_view = self.combat_victory_spin_view_name(model, "player")
        if spin_view is not None:
            self.player_sprite_view_name = spin_view
            return spin_view
        spin_view = self.interaction_spin_view_name(model, "water_refill")
        if spin_view is not None:
            self.player_sprite_view_name = spin_view
            return spin_view
        facing_delta = self.combat_actor_screen_facing_delta(model, camera, "player")
        if facing_delta is None:
            facing_delta = self.actor_screen_facing_delta(
                model, camera, model.player.x, model.player.z
            )
        if facing_delta is not None:
            screen_dx, screen_dy = facing_delta
            next_view = self.screen_direction_view_name(screen_dx, screen_dy)
            if next_view is not None:
                self.player_sprite_view_name = next_view
            return self.player_sprite_view_name
        if model.player.moved_distance <= 1e-6:
            self.player_sprite_view_name = "idle"
            return self.player_sprite_view_name
        delta = self.player_screen_move_delta(model, camera)
        if delta is None:
            return self.player_sprite_view_name
        screen_dx, screen_dy = delta
        next_view = self.screen_direction_view_name(screen_dx, screen_dy)
        if next_view is not None:
            self.player_sprite_view_name = next_view
        return self.player_sprite_view_name

    def player_screen_move_delta(
        self, model: GameModel, camera: CameraState
    ) -> tuple[float, float] | None:
        return model.player_screen_move_delta(camera)

    def combat_actor_screen_facing_delta(
        self, model: GameModel, camera: CameraState, actor: str
    ) -> tuple[float, float] | None:
        session = model.combat_session
        if session is None or session.phase == "VICTORY_CUE":
            return None
        enemy = model.enemy_by_id(session.enemy_id)
        if enemy is None:
            return None
        player = self.player_actor_presentation(model, camera)
        enemy_presentation = self.enemy_actor_presentation(model, enemy, camera)
        if actor == "player":
            origin = player
            target = enemy_presentation
        elif actor == "enemy":
            origin = enemy_presentation
            target = player
        elif actor == "buddy":
            origin = self.buddy_actor_presentation(model, camera, 0.0)
            target = enemy_presentation
        else:
            return None
        if math.hypot(target.x - origin.x, target.z - origin.z) <= 1e-6:
            return None
        origin_point = camera.project(Vec3(origin.x, 0.0, origin.z))
        target_point = camera.project(Vec3(target.x, 0.0, target.z))
        if origin_point is None or target_point is None:
            return None
        return target_point.x - origin_point.x, target_point.y - origin_point.y

    def buddy_sprite_asset(
        self, model: GameModel, camera: CameraState | None = None
    ) -> LoadedSpriteAsset | None:
        if camera is None:
            return self.configured_sprite_asset(model, "buddy_idle_asset")
        view_name = self.buddy_sprite_direction_view(model, camera)
        asset = self.configured_sprite_asset(model, f"buddy_{view_name}_asset")
        if asset is None:
            asset = self.configured_sprite_asset(model, "buddy_idle_asset")
        return asset

    def buddy_sprite_direction_view(self, model: GameModel, camera: CameraState) -> str:
        spin_view = self.combat_zap_spin_view_name(model)
        if spin_view is not None:
            self.buddy_sprite_view_name = spin_view
            return spin_view
        spin_view = self.combat_victory_spin_view_name(model, "buddy")
        if spin_view is not None:
            self.buddy_sprite_view_name = spin_view
            return spin_view
        spin_view = self.interaction_spin_view_name(model, "energy_refill")
        if spin_view is not None:
            self.buddy_sprite_view_name = spin_view
            return spin_view
        facing_delta = self.combat_actor_screen_facing_delta(model, camera, "buddy")
        if facing_delta is None:
            facing_delta = self.actor_screen_facing_delta(
                model, camera, model.buddy.x, model.buddy.z
            )
        if facing_delta is not None:
            screen_dx, screen_dy = facing_delta
            next_view = self.screen_direction_view_name(screen_dx, screen_dy)
            if next_view is not None:
                self.buddy_sprite_view_name = next_view
            return self.buddy_sprite_view_name
        delta = self.player_screen_move_delta(model, camera)
        if delta is None:
            return self.buddy_sprite_view_name
        screen_dx, screen_dy = delta
        next_view = self.screen_direction_view_name(screen_dx, screen_dy)
        if next_view is not None:
            self.buddy_sprite_view_name = next_view
        return self.buddy_sprite_view_name

    def screen_direction_view_name(self, screen_dx: float, screen_dy: float) -> str | None:
        if math.hypot(screen_dx, screen_dy) <= 0.25:
            return None
        angle = math.atan2(screen_dy, screen_dx)
        sector = int(math.floor((angle + math.pi / 8.0) / (math.pi / 4.0))) % 8
        return self.SPIN_DIRECTION_VIEWS[sector]

    def actor_screen_facing_delta(
        self,
        model: GameModel,
        camera: CameraState,
        origin_x: float,
        origin_z: float,
    ) -> tuple[float, float] | None:
        target = model.actor_facing_target()
        if target is None:
            return None
        target_x, target_z = target
        if math.hypot(target_x - origin_x, target_z - origin_z) <= 1e-6:
            return None
        origin = camera.project(Vec3(origin_x, 0.0, origin_z))
        target_point = camera.project(Vec3(target_x, 0.0, target_z))
        if origin is None or target_point is None:
            return None
        return target_point.x - origin.x, target_point.y - origin.y

    def interaction_spin_view_name(self, model: GameModel, interaction_kind: str) -> str | None:
        interaction = model.interaction
        if interaction is None or interaction.kind != interaction_kind:
            return None
        direction_count = max(1, int(model.config["interaction"].get("actor_spin_directions", 8)))
        progress = max(0.0, min(interaction.progress, 0.999999))
        index = int(progress * direction_count) % len(self.SPIN_DIRECTION_VIEWS)
        return self.SPIN_DIRECTION_VIEWS[index]

    def interaction_actor_jump(self, model: GameModel, interaction_kind: str) -> float:
        interaction = model.interaction
        if interaction is None or interaction.kind != interaction_kind:
            return 0.0
        height = float(model.config["interaction"].get("actor_jump_height", 0.0))
        return math.sin(max(0.0, min(interaction.progress, 1.0)) * math.pi) * height

    def combat_zap_spin_view_name(self, model: GameModel) -> str | None:
        session = model.combat_session
        if (
            session is None
            or session.outcome != "defeat"
            or not session.zap_used
            or session.phase != "COMBAT_EXIT_COUNTER"
        ):
            return None
        progress = self.combat_defeat_exit_progress(model)
        if progress < 0.16 or progress > 0.72:
            return None
        spin_progress = max(0.0, min((progress - 0.16) / 0.56, 0.999999))
        direction_count = len(self.SPIN_DIRECTION_VIEWS)
        index = int(spin_progress * direction_count) % direction_count
        return self.SPIN_DIRECTION_VIEWS[index]

    def combat_victory_spin_view_name(self, model: GameModel, actor: str) -> str | None:
        session = model.combat_session
        if (
            session is None
            or session.phase != "VICTORY_CUE"
            or model.combat_victory_actor(session) != actor
        ):
            return None
        direction_count = len(self.SPIN_DIRECTION_VIEWS)
        progress = max(0.0, min(model.combat_victory_progress(session), 0.999999))
        index = int(progress * direction_count) % direction_count
        return self.SPIN_DIRECTION_VIEWS[index]

    def combat_victory_actor_jump(self, model: GameModel, actor: str) -> float:
        session = model.combat_session
        if (
            session is None
            or session.phase != "VICTORY_CUE"
            or model.combat_victory_actor(session) != actor
        ):
            return 0.0
        height = float(model.config["interaction"].get("actor_jump_height", 7.0))
        return math.sin(model.combat_victory_progress(session) * math.pi) * height

    def configured_sprite_asset(
        self, model: GameModel, config_key: str
    ) -> LoadedSpriteAsset | None:
        if not self.sprite_assets.enabled:
            return None
        asset_config = model.config.get("assets", {})
        asset_id = str(asset_config.get(config_key, ""))
        if not asset_id:
            return None
        return self.sprite_assets.get(asset_id)

    def player_sprite_placement(
        self,
        model: GameModel,
        camera: CameraState,
        presentation_time: float,
        x: float | None = None,
        z: float | None = None,
        y: float | None = None,
    ):
        selection = self.player_sprite_selection(model, camera)
        if selection is None:
            return None
        asset, flip_x = selection
        draw_x = model.player.x if x is None else x
        draw_z = model.player.z if z is None else z
        draw_y = self.player_visual_y_offset(model, presentation_time) if y is None else y
        anchor = Vec3(
            draw_x,
            draw_y,
            draw_z,
        )
        return placement_for_upright_height_billboard(
            camera,
            asset.definition,
            anchor,
            flip_x=flip_x,
        )

    def player_sprite_flip_x(self, model: GameModel, camera: CameraState) -> bool:
        delta = self.combat_actor_screen_facing_delta(model, camera, "player")
        if delta is None:
            delta = self.actor_screen_facing_delta(model, camera, model.player.x, model.player.z)
        if delta is None:
            delta = self.player_screen_move_delta(model, camera)
        if delta is None:
            return self.player_sprite_flipped_x
        screen_dx, _screen_dy = delta
        if screen_dx > 0.25:
            self.player_sprite_flipped_x = True
        elif screen_dx < -0.25:
            self.player_sprite_flipped_x = False
        return self.player_sprite_flipped_x

    def draw_player_sprite(
        self,
        model: GameModel,
        camera: CameraState,
        presentation_time: float,
        x: float | None = None,
        z: float | None = None,
        y: float | None = None,
    ) -> bool:
        asset = self.player_sprite_asset(model, camera)
        if asset is None:
            return False
        placement = self.player_sprite_placement(model, camera, presentation_time, x, z, y)
        if placement is None:
            return False
        self.draw_atmospheric_scaled_sprite(asset, placement)
        return True

    def draw_buddy(
        self,
        model: GameModel,
        camera: CameraState,
        presentation_time: float,
        presentation: ActorPresentation | None = None,
    ) -> None:
        buddy = model.buddy
        if presentation is None:
            presentation = self.buddy_actor_presentation(model, camera, presentation_time)
        shadow = camera.project(Vec3(presentation.x, 0.0, presentation.z))
        if shadow is not None:
            radius = self.depth_scaled_radius(camera, shadow.depth, numerator=700, minimum=2)
            self.draw_shadow_ellipse(
                int(shadow.x - radius),
                int(shadow.y - max(1, radius // 4)),
                radius * 2,
                max(1, radius // 2),
                self.atmosphere_shadow_dither_cells(camera, shadow.depth, important_actor=True),
            )
        bob = math.sin(presentation_time * math.tau / 1.3) * 2.0
        bob += self.interaction_actor_jump(model, "energy_refill")
        bob += self.combat_victory_actor_jump(model, "buddy")
        bob += presentation.jump_y
        if self.draw_buddy_sprite(model, camera, bob, presentation.x, presentation.z):
            return
        half = model.buddy_cube_size / 2.0
        self.draw_box(
            camera,
            presentation.x,
            presentation.z,
            half,
            half,
            model.buddy_cube_size,
            buddy.y + bob,
            10,
        )

    def buddy_sprite_placement(
        self,
        model: GameModel,
        camera: CameraState,
        bob: float,
        x: float | None = None,
        z: float | None = None,
    ):
        asset = self.buddy_sprite_asset(model, camera)
        if asset is None:
            return None
        draw_x = model.buddy.x if x is None else x
        draw_z = model.buddy.z if z is None else z
        anchor = Vec3(draw_x, model.buddy.y + bob, draw_z)
        return placement_for_upright_height_billboard(camera, asset.definition, anchor)

    def draw_buddy_sprite(
        self,
        model: GameModel,
        camera: CameraState,
        bob: float,
        x: float | None = None,
        z: float | None = None,
    ) -> bool:
        asset = self.buddy_sprite_asset(model, camera)
        if asset is None:
            return False
        placement = self.buddy_sprite_placement(model, camera, bob, x, z)
        if placement is None:
            return False
        self.draw_atmospheric_scaled_sprite(asset, placement)
        return True

    def combat_bubble_counter_active(self, model: GameModel) -> bool:
        session = model.combat_session
        return (
            session is not None
            and session.bubble_used
            and session.phase in {"PERFECT_ZAP_WINDOW", "COMBAT_EXIT_COUNTER", "VICTORY_CUE"}
            and session.outcome in {None, "capture", "defeat"}
        )

    def combat_bubble_counter_progress(self, model: GameModel) -> float:
        session = model.combat_session
        if session is None or not self.combat_bubble_counter_active(model):
            return 0.0
        if session.phase == "PERFECT_ZAP_WINDOW":
            return _smoothstep(session.phase_elapsed_sec / 0.7)
        return 1.0

    def combat_bubble_counter_visibility(self, model: GameModel) -> float:
        session = model.combat_session
        if session is None or not self.combat_bubble_counter_active(model):
            return 0.0
        if session.outcome != "defeat":
            return 1.0
        if session.phase == "COMBAT_EXIT_COUNTER":
            duration = max(model.combat_deflect_knockback_sec(), 1e-6)
            fade_progress = (session.phase_elapsed_sec - duration * 0.54) / (duration * 0.32)
            return max(0.0, 1.0 - _smoothstep(fade_progress))
        return 0.0

    def draw_combat_bubble_counter(self, model: GameModel, camera: CameraState) -> None:
        if self.pyxel is None or not self.combat_bubble_counter_active(model):
            return
        session = model.combat_session
        if session is None:
            return
        enemy = model.enemy_by_id(session.enemy_id)
        if enemy is None:
            return
        player = self.player_actor_presentation(model, camera)
        enemy_presentation = self.enemy_actor_presentation(model, enemy, camera)
        source = camera.project(
            Vec3(
                player.x,
                self.player_visual_y_offset(model, 0.0) + player.jump_y + 12.0,
                player.z,
            )
        )
        target = camera.project(
            Vec3(enemy_presentation.x, 8.0 + enemy_presentation.jump_y, enemy_presentation.z)
        )
        if source is None or target is None:
            return
        progress = self.combat_bubble_counter_progress(model)
        visibility = self.combat_bubble_counter_visibility(model)
        if visibility <= 0.0:
            return
        self.draw_combat_bubble_spray(source, target, progress, session.phase_elapsed_sec)
        self.draw_combat_bubble_wrap(target, progress, visibility, session.phase_elapsed_sec)

    def draw_combat_bubble_spray(
        self,
        source: ProjectedPoint,
        target: ProjectedPoint,
        progress: float,
        elapsed: float,
    ) -> None:
        dx = target.x - source.x
        dy = target.y - source.y
        length = max(math.hypot(dx, dy), 1.0)
        dir_x = dx / length
        dir_y = dy / length
        side_x = -dir_y
        side_y = dir_x
        spray_reach = max(0.18, min(progress * 1.18, 1.0))
        for index in range(18):
            stream = (elapsed * 0.72 + index * 0.087) % 1.0
            amount = 0.08 + 0.88 * stream
            if amount > spray_reach + 0.12:
                continue
            amount = min(amount, spray_reach)
            taper = math.sin(amount * math.pi)
            wobble = math.sin(index * 1.81 + elapsed * 5.2) * (2.0 + 5.0 * taper)
            px = _lerp(source.x + dir_x * 3.0, target.x, amount) + side_x * wobble
            py = _lerp(source.y + dir_y * 2.0, target.y, amount) + side_y * wobble * 0.55
            radius = 1 + (1 if index % 5 == 0 else 0)
            color = (12, 7, 6, 12)[index % 4]
            self.pyxel.circb(int(px), int(py), radius, color)
            if radius > 1:
                self.pyxel.pset(int(px), int(py), 7)
        mouth_pulse = 1 + int(math.sin(elapsed * math.tau * 2.0) > 0.2)
        self.pyxel.circb(
            int(source.x + dir_x * 5.0),
            int(source.y + dir_y * 3.0),
            mouth_pulse + 2,
            12,
        )

    def draw_combat_bubble_wrap(
        self,
        target: ProjectedPoint,
        progress: float,
        visibility: float,
        elapsed: float,
    ) -> None:
        wrap = _smoothstep((progress - 0.22) / 0.58)
        if wrap <= 0.0:
            return
        center_x = int(target.x)
        center_y = int(target.y)
        radius_x = 8 + int(9 * wrap)
        radius_y = 5 + int(6 * wrap)
        ring_color = 12 if visibility > 0.4 else 5
        self.pyxel.ellib(
            center_x - radius_x,
            center_y - radius_y,
            radius_x * 2,
            radius_y * 2,
            ring_color,
        )
        self.pyxel.ellib(
            center_x - max(3, radius_x - 4),
            center_y - max(2, radius_y - 3),
            max(6, (radius_x - 4) * 2),
            max(4, (radius_y - 3) * 2),
            7,
        )
        for index in range(10):
            angle = elapsed * 1.5 + index * math.tau / 10.0
            orbit = 0.78 + 0.18 * math.sin(elapsed * 2.0 + index)
            px = center_x + int(math.cos(angle) * radius_x * orbit)
            py = center_y + int(math.sin(angle) * radius_y * orbit)
            color = 7 if index % 3 == 0 else 12
            self.pyxel.circb(px, py, 1 + (index % 4 == 0), color)

    def draw_combat_defeat_special(self, model: GameModel, camera: CameraState) -> None:
        if self.pyxel is None or not self.combat_defeat_special_active(model):
            return
        session = model.combat_session
        if session is None:
            return
        enemy = model.enemy_by_id(session.enemy_id)
        if enemy is None:
            return
        progress = self.combat_defeat_special_progress(model)
        buddy = self.buddy_actor_presentation(model, camera, 0.0)
        source = camera.project(Vec3(buddy.x, model.buddy.y + buddy.jump_y + 5.0, buddy.z))
        target = self.combat_enemy_effect_target_point(model, enemy, camera)
        if source is None or target is None:
            return
        self.draw_combat_homing_zaps(source, target, progress)
        self.draw_combat_enemy_disappear(target, progress)

    def combat_enemy_effect_target_point(
        self, model: GameModel, enemy, camera: CameraState
    ) -> ProjectedPoint | None:
        presentation = self.enemy_actor_presentation(model, enemy, camera)
        return camera.project(Vec3(presentation.x, 4.0 + presentation.jump_y, presentation.z))

    def draw_combat_homing_zaps(
        self, source: ProjectedPoint, target: ProjectedPoint, progress: float
    ) -> None:
        bolt_starts = (0.26, 0.38, 0.5)
        for index, start in enumerate(bolt_starts):
            local = (progress - start) / 0.3
            if local < 0.0 or local > 1.25:
                continue
            travel = _smoothstep(min(local, 1.0))
            end_x = _lerp(source.x, target.x, travel)
            end_y = _lerp(source.y, target.y, travel)
            color = (10, 7, 9, 10, 7)[index % 5]
            self.draw_combat_lightning_bolt(
                source.x,
                source.y,
                end_x,
                end_y,
                seed=index + int(progress * 60.0),
                color=color,
            )
            if local >= 0.75:
                pulse = max(1, int(3.0 * (1.25 - min(local, 1.25))))
                self.pyxel.circb(int(target.x), int(target.y), 5 + index + pulse, color)
            if local >= 0.35:
                contact = _smoothstep((min(local, 1.0) - 0.35) / 0.65)
                spread = 3 + int(5 * contact) + index
                self.draw_combat_lightning_bolt(
                    target.x - spread,
                    target.y - 2,
                    target.x + spread,
                    target.y + 2,
                    seed=20 + index * 7 + int(progress * 90.0),
                    color=color,
                )
        self.draw_combat_final_zap(source, target, progress)

    def draw_combat_final_zap(
        self, source: ProjectedPoint, target: ProjectedPoint, progress: float
    ) -> None:
        local = (progress - 0.78) / 0.17
        if local < 0.0 or local > 1.35:
            return
        if local < 0.28:
            charge = _smoothstep(local / 0.28)
            radius = 4 + int(charge * 8)
            self.pyxel.circb(int(source.x), int(source.y), radius, 10)
            self.pyxel.circb(int(source.x), int(source.y), max(2, radius - 3), 7)
            return
        travel = _smoothstep((local - 0.28) / 0.42)
        end_x = _lerp(source.x, target.x, travel)
        end_y = _lerp(source.y, target.y, travel)
        for offset, color in ((0.0, 7), (2.0, 10), (-2.0, 10), (4.0, 9)):
            self.draw_combat_lightning_bolt(
                source.x,
                source.y + offset,
                end_x,
                end_y - offset * 0.35,
                seed=40 + int(progress * 80.0) + int(offset * 3.0),
                color=color,
            )
        if local >= 0.72:
            impact = _smoothstep((local - 0.72) / 0.3)
            ring = 7 + int(14 * impact)
            self.pyxel.circb(int(target.x), int(target.y), ring, 7)
            self.pyxel.circb(int(target.x), int(target.y), max(2, ring - 4), 10)
            for index in range(8):
                angle = index * math.tau / 8.0
                length = 6 + int(14 * impact)
                sx = int(target.x + math.cos(angle) * 3)
                sy = int(target.y + math.sin(angle) * 2)
                ex = int(target.x + math.cos(angle) * length)
                ey = int(target.y + math.sin(angle) * length * 0.62)
                self.pyxel.line(sx, sy, ex, ey, 7 if index % 2 == 0 else 10)

    def draw_combat_lightning_bolt(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        *,
        seed: int,
        color: int,
    ) -> None:
        dx = end_x - start_x
        dy = end_y - start_y
        length = max(math.hypot(dx, dy), 1.0)
        perp_x = -dy / length
        perp_y = dx / length
        previous_x = start_x
        previous_y = start_y
        segments = 5
        for step in range(1, segments + 1):
            amount = step / segments
            taper = math.sin(amount * math.pi)
            jitter = math.sin(seed * 1.71 + step * 2.43) * 5.0 * taper
            if step == segments:
                jitter = 0.0
            current_x = _lerp(start_x, end_x, amount) + perp_x * jitter
            current_y = _lerp(start_y, end_y, amount) + perp_y * jitter
            self.pyxel.line(
                int(previous_x),
                int(previous_y),
                int(current_x),
                int(current_y),
                color,
            )
            previous_x = current_x
            previous_y = current_y

    def draw_combat_enemy_disappear(self, target: ProjectedPoint, progress: float) -> None:
        if progress < 0.9:
            return
        vanish = _smoothstep((progress - 0.9) / 0.1)
        x = int(target.x)
        y = int(target.y)
        radius = 5 + int(18 * vanish)
        self.pyxel.circb(x, y, radius, 10 if vanish < 0.7 else 13)
        for index in range(10):
            angle = index * math.tau / 10.0 + vanish * math.tau * 0.35
            distance = radius * (0.35 + 0.75 * ((index % 3) / 2.0))
            sx = int(x + math.cos(angle) * distance)
            sy = int(y + math.sin(angle) * distance * 0.62)
            color = (10, 7, 13, 9)[index % 4]
            self.pyxel.pset(sx, sy, color)
            if index % 3 == 0:
                self.pyxel.pset(sx + 1, sy, color)

    def draw_combat_victory_cue(self, model: GameModel, camera: CameraState) -> None:
        session = model.combat_session
        if session is None or session.phase != "VICTORY_CUE":
            return
        actor = model.combat_victory_actor(session)
        progress = model.combat_victory_progress(session)
        if actor == "buddy":
            presentation = self.buddy_actor_presentation(model, camera, 0.0)
            x = presentation.x
            y = (
                model.buddy.y
                + presentation.jump_y
                + self.combat_victory_actor_jump(model, "buddy")
                + 12.0
            )
            z = presentation.z
            label = "YAY!"
        else:
            x = model.player.x
            y = self.player_visual_y_offset(model, 0.0) + 16.0
            z = model.player.z
            label = "POP!"
        point = camera.project(Vec3(x, y, z))
        if point is None:
            return
        px = int(point.x)
        py = int(point.y)
        color = {"capture": 12, "defeat": 10, "deflect": 7}.get(session.outcome or "", 7)
        pulse = 1 + int(math.sin(progress * math.pi) * 2)
        self.pyxel.text(px - len(label) * 2, py - 15, label, color)
        for index in range(6):
            angle = progress * math.tau + index * math.tau / 6.0
            radius = 7 + progress * 10 + (index % 2) * 3
            sx = int(px + math.cos(angle) * radius)
            sy = int(py - 4 + math.sin(angle) * radius * 0.55)
            self.pyxel.rect(sx, sy, pulse, pulse, color if index % 2 == 0 else 7)

    def draw_barrier(self, model: GameModel, camera: CameraState) -> None:
        if not model.player.barrier_active:
            return
        radius = float(model.config["barrier"]["radius"])
        self.draw_world_circle(camera, model.player.x, model.player.z, radius, 12)

    def depth_scaled_radius(
        self, camera: CameraState, depth: float, *, numerator: float, minimum: int
    ) -> int:
        if self.camera_is_affine(camera):
            return self.affine_screen_px(camera, minimum)
        return max(minimum, int(numerator / max(depth, 1.0)))

    def affine_screen_px(self, camera: CameraState, medium_px: int) -> int:
        scale = getattr(camera, "effective_scale", 1.0)
        if not math.isfinite(scale) or scale <= 0.0:
            scale = 1.0
        return max(1, int(round(medium_px * scale)))

    def camera_is_affine(self, camera: CameraState) -> bool:
        return getattr(camera, "projection_kind", "perspective") == "affine"

    def object_atmosphere_strength(self, obj: StaticObject) -> float:
        if obj.kind == "reactive_prop":
            return self.atmosphere_strength_config(
                "reactive_prop_strength", ATMOSPHERE_REACTIVE_PROP_STRENGTH
            )
        if obj.kind == "sprite_prop":
            return self.atmosphere_strength_config(
                "nature_prop_strength", ATMOSPHERE_NATURE_PROP_STRENGTH
            )
        if obj.kind in {"water_station", "solar_station", "ambient_maintenance"}:
            return self.atmosphere_strength_config(
                "equipment_strength", ATMOSPHERE_EQUIPMENT_STRENGTH
            )
        if obj.solid:
            return self.atmosphere_strength_config("solid_strength", ATMOSPHERE_SOLID_STRENGTH)
        return self.atmosphere_strength_config(
            "default_static_strength", ATMOSPHERE_DEFAULT_STATIC_STRENGTH
        )

    def atmosphere_strength_config(self, key: str, default: float) -> float:
        value = self._atmosphere_config.get(key, default)
        try:
            strength = float(value)
        except (TypeError, ValueError):
            strength = default
        if not math.isfinite(strength):
            strength = default
        return max(0.0, min(1.0, strength))

    @contextmanager
    def atmosphere_depth_effects(self, camera: CameraState, depth: float, strength: float):
        mappings = self.atmosphere_palette_mappings(camera, depth, strength)
        previous_dither_cells = self._active_atmosphere_dither_cells
        previous_dither_fog = self._active_atmosphere_dither_fog_color
        self._active_atmosphere_dither_cells = self.atmosphere_dither_cells(camera, depth, strength)
        self._active_atmosphere_dither_fog_color = self.atmosphere_dither_fog_color()
        if not mappings or self.pyxel is None:
            try:
                yield
            finally:
                self._active_atmosphere_dither_cells = previous_dither_cells
                self._active_atmosphere_dither_fog_color = previous_dither_fog
            return
        for source, target in mappings:
            self.pyxel.pal(source, target)
        try:
            yield
        finally:
            self.pyxel.pal()
            self._active_atmosphere_dither_cells = previous_dither_cells
            self._active_atmosphere_dither_fog_color = previous_dither_fog

    def atmosphere_palette_mappings(
        self, camera: CameraState, depth: float, strength: float
    ) -> tuple[tuple[int, int], ...]:
        config = self._atmosphere_config
        if not bool(config.get("enabled", False)):
            return ()
        if bool(config.get("affine_only", True)) and not self.camera_is_affine(camera):
            return ()
        if strength <= 0.0 or not math.isfinite(strength) or not math.isfinite(depth):
            return ()

        depth_progress = self.atmosphere_depth_progress(camera, depth)
        if depth_progress <= 0.0:
            return ()

        base_stage = 2.0 * depth_progress
        effective_stage = base_stage * strength
        if effective_stage < 0.25:
            return ()
        if effective_stage < 0.75:
            return ATMOSPHERE_WEAK_PALETTE
        if effective_stage < 1.5:
            return ATMOSPHERE_MID_PALETTE
        return ATMOSPHERE_FAR_PALETTE

    def atmosphere_depth_progress(self, camera: CameraState, depth: float) -> float:
        if not math.isfinite(depth):
            return 0.0
        config = self._atmosphere_config
        reference_depth = float(
            config.get(
                "reference_depth",
                getattr(getattr(camera, "profile", None), "reference_depth", 480.0),
            )
        )
        near_offset = float(config.get("near_depth_offset", 64.0))
        far_offset = float(config.get("far_depth_offset", 176.0))
        relative_depth = depth - reference_depth
        if relative_depth <= near_offset:
            return 0.0
        if far_offset <= near_offset:
            return 1.0
        return max(0.0, min((relative_depth - near_offset) / (far_offset - near_offset), 1.0))

    def atmosphere_interpolated_dither_cells(
        self,
        progress: float,
        mid_cells: int,
        far_cells: int,
    ) -> int:
        progress = max(0.0, min(progress, 1.0))
        mid_cells = max(0, min(16, mid_cells))
        far_cells = max(0, min(16, far_cells))
        if progress <= 0.0:
            cells = 0.0
        elif progress < 0.5:
            cells = mid_cells * (progress / 0.5)
        else:
            cells = mid_cells + (far_cells - mid_cells) * ((progress - 0.5) / 0.5)
        return max(0, min(16, int(math.floor(cells + 0.5))))

    def atmosphere_dither_cells(self, camera: CameraState, depth: float, strength: float) -> int:
        config = self._atmosphere_config
        if not bool(config.get("enabled", False)):
            return 0
        if not bool(config.get("dither_enabled", True)):
            return 0
        if bool(config.get("affine_only", True)) and not self.camera_is_affine(camera):
            return 0
        if (
            strength < float(config.get("dither_min_strength", ATMOSPHERE_DITHER_MIN_STRENGTH))
            or not math.isfinite(strength)
            or not math.isfinite(depth)
        ):
            return 0

        progress = self.atmosphere_depth_progress(camera, depth)
        if progress <= 0.0:
            return 0

        base_cells = self.atmosphere_interpolated_dither_cells(
            progress,
            int(config.get("mid_dither_cells", ATMOSPHERE_MID_DITHER_CELLS)),
            int(config.get("far_dither_cells", ATMOSPHERE_FAR_DITHER_CELLS)),
        )
        return max(0, min(16, int(round(base_cells * strength))))

    def atmosphere_shadow_dither_cells(
        self, camera: CameraState, depth: float, *, important_actor: bool = False
    ) -> int:
        config = self._atmosphere_config
        if not bool(config.get("enabled", False)):
            return 16
        if not bool(config.get("shadow_enabled", True)):
            return 16
        if bool(config.get("affine_only", True)) and not self.camera_is_affine(camera):
            return 16
        if not math.isfinite(depth):
            return 16

        reference_depth = float(
            config.get(
                "reference_depth",
                getattr(getattr(camera, "profile", None), "reference_depth", 480.0),
            )
        )
        near_offset = float(config.get("near_depth_offset", 64.0))
        far_offset = float(config.get("far_depth_offset", 176.0))
        relative_depth = depth - reference_depth
        if relative_depth < near_offset:
            cells = int(config.get("shadow_near_cells", ATMOSPHERE_SHADOW_NEAR_CELLS))
        elif relative_depth < far_offset:
            cells = int(config.get("shadow_mid_cells", ATMOSPHERE_SHADOW_MID_CELLS))
        else:
            cells = int(config.get("shadow_far_cells", ATMOSPHERE_SHADOW_FAR_CELLS))
        if important_actor:
            cells = max(
                cells,
                int(
                    config.get(
                        "shadow_important_min_cells",
                        ATMOSPHERE_SHADOW_IMPORTANT_MIN_CELLS,
                    )
                ),
            )
        return max(0, min(16, cells))

    def draw_shadow_ellipse(self, x: int, y: int, width: int, height: int, cells: int) -> None:
        cells = max(0, min(16, int(cells)))
        if cells <= 0:
            return
        if cells >= 16:
            self.pyxel.elli(x, y, width, height, 0)
            return

        radius_x = max(width / 2.0, 0.5)
        radius_y = max(height / 2.0, 0.5)
        center_x = x + (width - 1) / 2.0
        center_y = y + (height - 1) / 2.0
        screen_width = int(getattr(self.pyxel, "width", 0) or 0)
        screen_height = int(getattr(self.pyxel, "height", 0) or 0)
        left = max(0, x) if screen_width > 0 else x
        right = min(x + width, screen_width) if screen_width > 0 else x + width
        top = max(0, y) if screen_height > 0 else y
        bottom = min(y + height, screen_height) if screen_height > 0 else y + height
        for py in range(top, bottom):
            local_y = py - y
            normalized_y = (py + 0.5 - center_y) / radius_y
            for px in range(left, right):
                local_x = px - x
                normalized_x = (px + 0.5 - center_x) / radius_x
                if normalized_x * normalized_x + normalized_y * normalized_y > 1.0:
                    continue
                if ATMOSPHERE_BAYER_4X4[local_y % 4][local_x % 4] < cells:
                    self.pyxel.pset(px, py, 0)

    def atmosphere_dither_fog_color(self) -> int:
        color = int(self._atmosphere_config.get("dither_fog_color", ATMOSPHERE_DITHER_FOG_COLOR))
        return max(0, min(15, color))

    def atmospheric_sprite_frame(
        self, asset: LoadedSpriteAsset, frame: LoadedSpriteFrame
    ) -> LoadedSpriteFrame:
        cells = self._active_atmosphere_dither_cells
        fog_color = self._active_atmosphere_dither_fog_color
        colkey = asset.definition.colkey
        if cells <= 0 or self.pyxel is None or fog_color == colkey:
            return frame
        key = (asset.definition.asset_id, frame.frame_id, frame.source_hash, cells, fog_color)
        cached = self._atmosphere_dither_cache.get(key)
        if cached is not None:
            return cached

        image = self.pyxel.Image(frame.width, frame.height)
        for y in range(frame.height):
            for x in range(frame.width):
                color = self.sprite_frame_pixel(frame, x, y)
                color = self.atmosphere_dither_color(color, x, y, colkey)
                image.pset(x, y, color)
        derived = LoadedSpriteFrame(
            frame_id=frame.frame_id,
            image=image,
            source=frame.source,
            u=0,
            v=0,
            width=frame.width,
            height=frame.height,
            source_hash=frame.source_hash,
        )
        self._atmosphere_dither_cache[key] = derived
        return derived

    def sprite_frame_pixel(self, frame: LoadedSpriteFrame, x: int, y: int) -> int:
        if isinstance(frame.image, int):
            return int(self.pyxel.images[frame.image].pget(frame.u + x, frame.v + y))
        return int(frame.image.pget(frame.u + x, frame.v + y))

    def atmosphere_dither_color(self, color: int, local_x: int, local_y: int, colkey: int) -> int:
        if color == colkey:
            return color
        cells = self._active_atmosphere_dither_cells
        if cells <= 0:
            return color
        threshold = self.atmosphere_dither_threshold(local_x, local_y)
        if threshold < cells:
            return self._active_atmosphere_dither_fog_color
        return color

    def atmosphere_dither_threshold(self, local_x: int, local_y: int) -> int:
        value = (local_x * 73856093) ^ (local_y * 19349663) ^ (local_x * local_y * 83492791)
        value ^= value >> 13
        value *= 1274126177
        value ^= value >> 16
        return value & 15

    def draw_atmospheric_scaled_sprite(
        self, asset: LoadedSpriteAsset, placement, frame: LoadedSpriteFrame | None = None
    ) -> None:
        base_frame = frame or asset.frame()
        draw_scaled_sprite(
            self.pyxel,
            self.atmospheric_sprite_frame(asset, base_frame),
            asset.definition,
            placement,
        )

    def object_prefers_sprite_geometry(self, obj: StaticObject) -> bool:
        return (
            obj.sprite_world_width > 0.0
            and obj.sprite_world_height > 0.0
            and obj.visual not in {"", "small_block"}
        )

    def object_uses_box_geometry(self, obj: StaticObject) -> bool:
        return (
            obj.solid and obj.kind != "sprite_prop" and not self.object_prefers_sprite_geometry(obj)
        )

    def solid_box_color(self, obj: StaticObject) -> int:
        return 5 if obj.kind == "obstacle" else 4

    def solid_box_face_commands(self, obj: StaticObject, camera: CameraState) -> list[DrawCommand]:
        height = obj.height if obj.height > 0.0 else 24.0
        projected_faces = self.project_box_faces(
            camera,
            obj.x,
            obj.z,
            obj.half_x,
            obj.half_z,
            height,
            0.0,
            self.solid_box_color(obj),
        )
        return [
            DrawCommand(
                depth=depth,
                layer_bias=0,
                stable_id=f"{obj.id}:{name}",
                draw=lambda points=points, face_color=face_color: self.draw_projected_box_face(
                    points, face_color
                ),
                atmosphere_strength=self.object_atmosphere_strength(obj),
            )
            for depth, name, points, face_color in projected_faces
        ]

    def draw_box(
        self,
        camera: CameraState,
        x: float,
        z: float,
        half_x: float,
        half_z: float,
        height: float,
        y_offset: float,
        color: int,
    ) -> None:
        projected_faces = self.project_box_faces(
            camera, x, z, half_x, half_z, height, y_offset, color
        )
        for _depth, _name, points, face_color in sorted(projected_faces, key=lambda item: -item[0]):
            self.draw_projected_box_face(points, face_color)

    def project_box_faces(
        self,
        camera: CameraState,
        x: float,
        z: float,
        half_x: float,
        half_z: float,
        height: float,
        y_offset: float,
        color: int,
    ) -> list[tuple[float, str, list[ProjectedPoint], int]]:
        bottom = y_offset
        top = y_offset + height
        vertices = {
            "nwl": Vec3(x - half_x, bottom, z - half_z),
            "nel": Vec3(x + half_x, bottom, z - half_z),
            "sel": Vec3(x + half_x, bottom, z + half_z),
            "swl": Vec3(x - half_x, bottom, z + half_z),
            "nwh": Vec3(x - half_x, top, z - half_z),
            "neh": Vec3(x + half_x, top, z - half_z),
            "seh": Vec3(x + half_x, top, z + half_z),
            "swh": Vec3(x - half_x, top, z + half_z),
        }
        faces = [
            ("top", ("nwh", "neh", "seh", "swh"), min(color + 1, 15)),
            ("north", ("nwl", "nel", "neh", "nwh"), color),
            ("east", ("nel", "sel", "seh", "neh"), max(color - 1, 1)),
            ("south", ("sel", "swl", "swh", "seh"), color),
            ("west", ("swl", "nwl", "nwh", "swh"), max(color - 1, 1)),
        ]
        projected_faces = []
        for name, keys, face_color in faces:
            projected = [camera.project(vertices[key]) for key in keys]
            if any(point is None for point in projected):
                continue
            avg_depth = sum(point.depth for point in projected if point is not None) / len(
                projected
            )
            projected_faces.append((avg_depth, name, projected, face_color))
        return projected_faces

    def draw_projected_box_face(self, points: list[ProjectedPoint], face_color: int) -> None:
        p0, p1, p2, p3 = points
        self.pyxel.tri(int(p0.x), int(p0.y), int(p1.x), int(p1.y), int(p2.x), int(p2.y), face_color)
        self.pyxel.tri(int(p0.x), int(p0.y), int(p2.x), int(p2.y), int(p3.x), int(p3.y), face_color)
        for start, end in ((p0, p1), (p1, p2), (p2, p3), (p3, p0)):
            self.pyxel.line(int(start.x), int(start.y), int(end.x), int(end.y), 0)

    def draw_world_circle(
        self,
        camera: CameraState,
        x: float,
        z: float,
        radius: float,
        color: int,
        thickness: int = 1,
    ) -> None:
        last = None
        for index in range(33):
            angle = index * math.tau / 32.0
            point = camera.project(
                Vec3(x + math.cos(angle) * radius, 0.0, z + math.sin(angle) * radius)
            )
            if point is not None and last is not None:
                self.pyxel.line(int(last.x), int(last.y), int(point.x), int(point.y), color)
                if thickness >= 2:
                    self.pyxel.line(
                        int(last.x),
                        int(last.y) + 1,
                        int(point.x),
                        int(point.y) + 1,
                        color,
                    )
                if thickness >= 3:
                    self.pyxel.line(
                        int(last.x) + 1,
                        int(last.y),
                        int(point.x) + 1,
                        int(point.y),
                        color,
                    )
            last = point

    def draw_world_line(self, camera: CameraState, start: Vec3, end: Vec3, color: int) -> None:
        a = camera.project(start)
        b = camera.project(end)
        if a is None or b is None:
            return
        self.pyxel.line(int(a.x), int(a.y), int(b.x), int(b.y), color)

    def draw_affine_debug_grid(self, model: GameModel, camera: CameraState) -> None:
        if not self.camera_is_affine(camera):
            return
        step = float(
            model.config.get("projection", {}).get("affine", {}).get("debug_grid_world", 32.0)
        )
        if step <= 1e-6 or not math.isfinite(step):
            return
        rect = model.world.minimap_rect
        cols = int(math.floor(rect.width / step))
        rows = int(math.floor(rect.depth / step))
        for index in range(cols + 1):
            x = min(rect.max_x, rect.min_x + index * step)
            self.draw_world_line(camera, Vec3(x, 0.0, rect.min_z), Vec3(x, 0.0, rect.max_z), 5)
        for index in range(rows + 1):
            z = min(rect.max_z, rect.min_z + index * step)
            self.draw_world_line(camera, Vec3(rect.min_x, 0.0, z), Vec3(rect.max_x, 0.0, z), 6)

    def draw_debug_world(self, model: GameModel, camera: CameraState) -> None:
        self.draw_world_rect(camera, model.world.visual_ground_rect, 11)
        self.draw_world_rect(camera, model.world.walkable_rect, 7)
        point = camera.project(Vec3(model.player.x, 0.0, model.player.z))
        if point is None:
            return
        self.pyxel.circb(int(point.x), int(point.y), 5, 7)
        buddy = camera.project(Vec3(model.buddy.goal_x, model.buddy.goal_y, model.buddy.goal_z))
        if buddy is not None:
            self.pyxel.circb(int(buddy.x), int(buddy.y), 4, 10)
        for enemy in model.enemies:
            point = camera.project(Vec3(enemy.home_x, 0.0, enemy.home_z))
            if point is not None:
                self.pyxel.circb(int(point.x), int(point.y), 3, 8 if enemy.kind == "normal" else 2)

    def draw_interaction_marker(self, model: GameModel, camera: CameraState) -> None:
        target = model.interaction_candidate(camera)
        if target is None:
            return
        point = camera.project(Vec3(target.x, max(16.0, target.height + 8.0), target.z))
        if point is None:
            return
        x = int(point.x)
        y = int(point.y)
        color = 8 if model.danger_blocks_interaction() else 7
        self.pyxel.line(x, y - 5, x + 5, y, color)
        self.pyxel.line(x + 5, y, x, y + 5, color)
        self.pyxel.line(x, y + 5, x - 5, y, color)
        self.pyxel.line(x - 5, y, x, y - 5, color)

    def draw_action_marker(self, model: GameModel, camera: CameraState) -> None:
        enemy = model.captured_enemy(camera) or model.bubble_target(camera)
        if enemy is None:
            return
        point = camera.project(Vec3(enemy.x, 24.0, enemy.z))
        if point is None:
            return
        x = int(point.x)
        y = int(point.y)
        color = 10 if enemy.state == "CAPTURED" else 12
        self.pyxel.circb(x, y, 7, color)
        self.pyxel.line(x - 3, y, x + 3, y, color)
        self.pyxel.line(x, y - 3, x, y + 3, color)

    def draw_effects(
        self, model: GameModel, camera: CameraState, effects: EffectSystem | None
    ) -> None:
        if effects is None:
            return
        self.draw_world_rings(camera, effects, layer="foreground")
        self.draw_world_strokes(camera, effects, layer="foreground")
        self.draw_world_particles(camera, effects)
        self.draw_actor_emotes(model, camera, effects)
        self.draw_screen_cues(camera, effects)

    def draw_background_effects(
        self, model: GameModel, camera: CameraState, effects: EffectSystem | None
    ) -> None:
        if effects is None:
            return
        hidden_sources = {"shallow_water"} if model.combat_session is not None else set()
        self.draw_world_rings(camera, effects, layer="background", hidden_sources=hidden_sources)
        self.draw_world_strokes(camera, effects, layer="background", hidden_sources=hidden_sources)

    def draw_world_rings(
        self,
        camera: CameraState,
        effects: EffectSystem,
        *,
        layer: str | None = None,
        hidden_sources: set[str] | None = None,
    ) -> None:
        for ring in effects.rings:
            if layer is not None and ring.layer != layer:
                continue
            if hidden_sources is not None and ring.source in hidden_sources:
                continue
            self.draw_world_circle(
                camera, ring.x, ring.z, ring.radius, ring.color, thickness=ring.thickness
            )

    def draw_world_strokes(
        self,
        camera: CameraState,
        effects: EffectSystem,
        *,
        layer: str | None = None,
        hidden_sources: set[str] | None = None,
    ) -> None:
        for stroke in effects.strokes:
            if layer is not None and stroke.layer != layer:
                continue
            if hidden_sources is not None and stroke.source in hidden_sources:
                continue
            self.draw_world_line(
                camera,
                Vec3(stroke.start_x, stroke.start_y, stroke.start_z),
                Vec3(stroke.end_x, stroke.end_y, stroke.end_z),
                stroke.color,
            )

    def draw_world_particles(self, camera: CameraState, effects: EffectSystem) -> None:
        for particle in effects.particles:
            point = camera.project(Vec3(particle.x, max(0.0, particle.y), particle.z))
            if point is None:
                continue
            if self.camera_is_affine(camera):
                size = 2 if particle.progress < 0.5 else 1
            else:
                size = 2 if particle.progress < 0.5 and point.depth < 620.0 else 1
            x = int(point.x)
            y = int(point.y)
            if size > 1:
                self.pyxel.rect(x - 1, y - 1, 2, 2, particle.color)
            else:
                self.pyxel.pset(x, y, particle.color)

    def draw_actor_emotes(
        self, model: GameModel, camera: CameraState, effects: EffectSystem
    ) -> None:
        for emote in effects.emotes:
            anchor = self.emote_anchor(model, emote.anchor_kind, emote.anchor_id)
            x, y, z = anchor if anchor is not None else (emote.fallback_x, 24.0, emote.fallback_z)
            point = camera.project(Vec3(x, y + 8.0 + emote.progress * 8.0, z))
            if point is None:
                continue
            self.pyxel.text(int(point.x) - 2, int(point.y) - 3, emote.symbol, emote.color)

    def emote_anchor(
        self, model: GameModel, anchor_kind: str, anchor_id: str
    ) -> tuple[float, float, float] | None:
        if anchor_kind == "player":
            return (model.player.x, model.player_cube_size + 8.0, model.player.z)
        if anchor_kind == "buddy":
            return (model.buddy.x, model.buddy.y + model.buddy_cube_size + 8.0, model.buddy.z)
        if anchor_kind == "enemy":
            enemy = model.enemy_by_id(anchor_id)
            if enemy is None or enemy.state == "DEFEATED":
                return None
            return (enemy.x, 22.0, enemy.z)
        if anchor_kind == "object":
            obj = model.world.object_by_id(anchor_id)
            if obj is None:
                return None
            return (obj.x, max(18.0, obj.height + 12.0), obj.z)
        return None

    def draw_screen_cues(self, camera: CameraState, effects: EffectSystem) -> None:
        for cue in effects.screen_cues:
            if cue.kind != "focus_lines":
                continue
            center_x = camera.viewport_width // 2
            center_y = camera.viewport_height // 2
            line_count = max(1, effects.concentration_line_count)
            length = int(12 * (1.0 - cue.progress)) + 8
            color = 13 if cue.progress < 0.45 else 5
            for index in range(line_count):
                angle = index * math.tau / line_count
                start_x = center_x + int(math.cos(angle) * (camera.viewport_width * 0.42))
                start_y = center_y + int(math.sin(angle) * (camera.viewport_height * 0.42))
                end_x = start_x - int(math.cos(angle) * length)
                end_y = start_y - int(math.sin(angle) * length)
                self.pyxel.line(start_x, start_y, end_x, end_y, color)

    def sprite_prop_bounds(self, obj: StaticObject, camera: CameraState) -> ScreenRect | None:
        root = camera.project(Vec3(obj.x, 0.0, obj.z))
        top = camera.project(Vec3(obj.x, obj.sprite_world_height or obj.height or 48.0, obj.z))
        if root is None or top is None:
            return None
        height = max(16, int(abs(root.y - top.y)))
        width = max(
            14,
            int(
                height
                * (
                    (obj.sprite_world_width or 36.0)
                    / max(obj.sprite_world_height or obj.height or 48.0, 1.0)
                )
            ),
        )
        return ScreenRect(int(root.x - width / 2), int(root.y - height), width, height)

    def object_is_visible(self, obj: StaticObject, camera: CameraState, margin: float) -> bool:
        bounds = self.object_screen_bounds(obj, camera)
        return bounds is not None and self.screen_rect_visible(bounds, camera, margin)

    def object_ground_pick_block_bounds(
        self, obj: StaticObject, camera: CameraState
    ) -> ScreenRect | None:
        if obj.kind == "sprite_prop" or self.object_prefers_sprite_geometry(obj):
            return self.sprite_prop_bounds(obj, camera)
        if obj.solid:
            bounds = obj.height if obj.height > 0.0 else 24.0
            return self.project_box_bounds(
                camera, obj.x, obj.z, obj.half_x, obj.half_z, bounds, 0.0
            )

        visual = camera.project(Vec3(obj.x, max(16.0, obj.height + 14.0), obj.z))
        root = camera.project(Vec3(obj.x, 0.0, obj.z))
        points = [point for point in (root, visual) if point is not None]
        if not points:
            return None
        min_x = int(min(point.x for point in points) - 8)
        max_x = int(max(point.x for point in points) + 8)
        min_y = int(min(point.y for point in points) - 16)
        max_y = int(max(point.y for point in points) + 4)
        return ScreenRect(min_x, min_y, max(1, max_x - min_x), max(1, max_y - min_y))

    def object_screen_bounds(self, obj: StaticObject, camera: CameraState) -> ScreenRect | None:
        if obj.kind == "sprite_prop" or (
            obj.sprite_world_width > 0.0 and obj.sprite_world_height > 0.0
        ):
            return self.sprite_prop_bounds(obj, camera)
        if obj.solid:
            bounds = obj.height if obj.height > 0.0 else 24.0
            return self.project_box_bounds(
                camera, obj.x, obj.z, obj.half_x, obj.half_z, bounds, 0.0
            )

        visual = camera.project(Vec3(obj.x, max(16.0, obj.height + 14.0), obj.z))
        root = camera.project(Vec3(obj.x, 0.0, obj.z))
        points = [point for point in (root, visual) if point is not None]
        if not points:
            return None
        min_x = int(min(point.x for point in points) - 8)
        max_x = int(max(point.x for point in points) + 8)
        min_y = int(min(point.y for point in points) - 16)
        max_y = int(max(point.y for point in points) + 4)
        return ScreenRect(min_x, min_y, max(1, max_x - min_x), max(1, max_y - min_y))

    def ground_detail_is_visible(
        self, detail: GroundDetail, camera: CameraState, margin: float
    ) -> bool:
        point = camera.project(Vec3(detail.x, 0.0, detail.z))
        if point is None:
            return False
        return (
            -margin <= point.x <= camera.viewport_width + margin
            and -margin <= point.y <= camera.viewport_height + margin
        )

    def screen_rect_visible(self, rect: ScreenRect, camera: CameraState, margin: float) -> bool:
        viewport = ScreenRect(
            int(-margin),
            int(-margin),
            int(camera.viewport_width + margin * 2.0),
            int(camera.viewport_height + margin * 2.0),
        )
        return rect.overlaps(viewport)

    def project_box_bounds(
        self,
        camera: CameraState,
        x: float,
        z: float,
        half_x: float,
        half_z: float,
        height: float,
        y_offset: float,
    ) -> ScreenRect | None:
        vertices = [
            Vec3(x - half_x, y_offset, z - half_z),
            Vec3(x + half_x, y_offset, z - half_z),
            Vec3(x + half_x, y_offset, z + half_z),
            Vec3(x - half_x, y_offset, z + half_z),
            Vec3(x - half_x, y_offset + height, z - half_z),
            Vec3(x + half_x, y_offset + height, z - half_z),
            Vec3(x + half_x, y_offset + height, z + half_z),
            Vec3(x - half_x, y_offset + height, z + half_z),
        ]
        projected = [camera.project(vertex) for vertex in vertices]
        points = [point for point in projected if point is not None]
        if not points:
            return None
        min_x = int(min(point.x for point in points))
        min_y = int(min(point.y for point in points))
        max_x = int(max(point.x for point in points))
        max_y = int(max(point.y for point in points))
        return ScreenRect(min_x, min_y, max(1, max_x - min_x), max(1, max_y - min_y))

    def player_screen_bounds(
        self, model: GameModel, camera: CameraState, presentation_time: float | None = None
    ) -> ScreenRect | None:
        if presentation_time is not None:
            placement = self.player_sprite_placement(model, camera, presentation_time)
            if placement is not None:
                return ScreenRect(*placement.rect)
        half = model.player_cube_size / 2.0
        return self.project_box_bounds(
            camera,
            model.player.x,
            model.player.z,
            half,
            half,
            model.player_cube_size,
            float(model.config["player"]["visual_hover_base"]),
        )

    def player_is_occluded(
        self, model: GameModel, camera: CameraState, presentation_time: float | None = None
    ) -> bool:
        player_anchor = camera.project(Vec3(model.player.x, 0.0, model.player.z))
        player_bounds = self.player_screen_bounds(model, camera, presentation_time)
        if player_anchor is None or player_bounds is None:
            return False
        for obj in model.world.objects:
            if not self.object_can_occlude_player(obj):
                continue
            obj_depth = self.object_occlusion_depth(obj, camera)
            if obj_depth is None or obj_depth >= player_anchor.depth:
                continue
            obj_bounds = self.object_occlusion_bounds(obj, camera)
            if obj_bounds is not None and obj_bounds.overlaps(player_bounds):
                return True
        return False

    def object_can_occlude_player(self, obj: StaticObject) -> bool:
        return obj.occludes_player or self.object_uses_box_geometry(obj)

    def object_occlusion_depth(self, obj: StaticObject, camera: CameraState) -> float | None:
        if self.object_uses_box_geometry(obj):
            height = obj.height if obj.height > 0.0 else 24.0
            projected_faces = self.project_box_faces(
                camera,
                obj.x,
                obj.z,
                obj.half_x,
                obj.half_z,
                height,
                0.0,
                self.solid_box_color(obj),
            )
            if not projected_faces:
                return None
            return min(depth for depth, _name, _points, _face_color in projected_faces)
        anchor = camera.project(Vec3(obj.x, 0.0, obj.z))
        return None if anchor is None else anchor.depth

    def object_occlusion_bounds(self, obj: StaticObject, camera: CameraState) -> ScreenRect | None:
        if self.object_uses_box_geometry(obj):
            height = obj.height if obj.height > 0.0 else 24.0
            return self.project_box_bounds(
                camera, obj.x, obj.z, obj.half_x, obj.half_z, height, 0.0
            )
        return self.sprite_prop_bounds(obj, camera)

    def draw_player_outline(
        self, model: GameModel, camera: CameraState, presentation_time: float | None = None
    ) -> None:
        bounds = self.player_screen_bounds(model, camera, presentation_time)
        if bounds is None:
            return
        self.pyxel.rectb(bounds.x - 2, bounds.y - 2, bounds.width + 4, bounds.height + 4, 7)
        self.pyxel.rectb(bounds.x - 1, bounds.y - 1, bounds.width + 2, bounds.height + 2, 12)


def _lerp(start: float, end: float, amount: float) -> float:
    t = max(0.0, min(amount, 1.0))
    return start + (end - start) * t


def _smoothstep(value: float) -> float:
    t = max(0.0, min(value, 1.0))
    return t * t * (3.0 - 2.0 * t)
