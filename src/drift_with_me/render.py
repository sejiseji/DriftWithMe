from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from drift_with_me.effects import EffectSystem
from drift_with_me.hex_assets import (
    LoadedSpriteAsset,
    SpriteAssetLibrary,
    draw_scaled_sprite,
    placement_for_upright_height_billboard,
)
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel
from drift_with_me.world import GroundDetail, StaticObject, WorldData


@dataclass(frozen=True)
class DrawCommand:
    depth: float
    layer_bias: int
    stable_id: str
    draw: Callable[[], None]


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


@dataclass(frozen=True)
class RenderStats:
    total_static_objects: int = 0
    candidate_chunks: int = 0
    candidate_static_objects: int = 0
    visible_static_objects: int = 0
    visible_ground_details: int = 0
    draw_commands: int = 0
    active_enemies: int = 0
    dormant_enemies: int = 0


class Renderer:
    def __init__(self, pyxel_module, sprite_assets: SpriteAssetLibrary | None = None) -> None:
        self.pyxel = pyxel_module
        self.sprite_assets = sprite_assets or SpriteAssetLibrary.empty()
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
        pyxel.cls(1)
        self.draw_ground(model.world, camera)
        self.draw_safe_zones(model.world, camera)
        commands = self.world_commands(model, camera, presentation_time)
        for command in sorted(
            commands, key=lambda item: (-item.depth, item.layer_bias, item.stable_id)
        ):
            command.draw()
        self.draw_barrier(model, camera)
        if self.player_is_occluded(model, camera, presentation_time):
            self.draw_player_outline(model, camera, presentation_time)
        self.draw_interaction_marker(model, camera)
        self.draw_action_marker(model, camera)
        self.draw_effects(model, camera, effects)
        if debug:
            self.draw_debug_world(model, camera)

    def draw_ground(self, world: WorldData, camera: CameraState) -> None:
        pyxel = self.pyxel
        corners = [
            camera.project(Vec3(0.0, 0.0, 0.0)),
            camera.project(Vec3(world.width, 0.0, 0.0)),
            camera.project(Vec3(world.width, 0.0, world.depth)),
            camera.project(Vec3(0.0, 0.0, world.depth)),
        ]
        if all(point is not None for point in corners):
            p0, p1, p2, p3 = corners
            pyxel.tri(int(p0.x), int(p0.y), int(p1.x), int(p1.y), int(p2.x), int(p2.y), 3)
            pyxel.tri(int(p0.x), int(p0.y), int(p2.x), int(p2.y), int(p3.x), int(p3.y), 3)

        for line in range(0, int(world.width) + 1, 128):
            self.draw_world_line(camera, Vec3(line, 0.0, 0.0), Vec3(line, 0.0, world.depth), 11)
            self.draw_world_line(camera, Vec3(0.0, 0.0, line), Vec3(world.width, 0.0, line), 11)
        self.draw_world_line(camera, Vec3(0.0, 0.0, 0.0), Vec3(world.width, 0.0, 0.0), 7)
        self.draw_world_line(
            camera, Vec3(world.width, 0.0, 0.0), Vec3(world.width, 0.0, world.depth), 7
        )
        self.draw_world_line(
            camera, Vec3(world.width, 0.0, world.depth), Vec3(0.0, 0.0, world.depth), 7
        )
        self.draw_world_line(camera, Vec3(0.0, 0.0, world.depth), Vec3(0.0, 0.0, 0.0), 7)

    def draw_safe_zones(self, world: WorldData, camera: CameraState) -> None:
        for zone in world.safe_zones:
            self.draw_world_circle(camera, zone.x, zone.z, zone.radius, 12)

    def world_commands(
        self,
        model: GameModel,
        camera: CameraState,
        presentation_time: float,
    ) -> list[DrawCommand]:
        commands: list[DrawCommand] = []
        margin = float(model.config["culling"]["screen_margin_ref_px"])
        visible_query = model.world.query_visible_static_objects(camera, margin)
        visible_objects = [
            obj for obj in visible_query.objects if self.object_is_visible(obj, camera, margin)
        ]
        visible_details = [
            detail
            for detail in model.world.ground_details_for_chunks(visible_query.chunk_ids)
            if self.ground_detail_is_visible(detail, camera, margin)
        ]
        for detail in visible_details:
            anchor = camera.project(Vec3(detail.x, 0.0, detail.z))
            if anchor is None:
                continue
            commands.append(
                DrawCommand(
                    depth=anchor.depth,
                    layer_bias=1,
                    stable_id=detail.id,
                    draw=lambda detail=detail: self.draw_ground_detail(
                        detail, camera, model.world_tick
                    ),
                )
            )
        for obj in visible_objects:
            anchor = camera.project(Vec3(obj.x, 0.0, obj.z))
            if anchor is None:
                continue
            commands.append(
                DrawCommand(
                    depth=anchor.depth,
                    layer_bias=0,
                    stable_id=obj.id,
                    draw=lambda obj=obj: self.draw_object(obj, camera),
                )
            )
        for enemy in model.enemies:
            anchor = camera.project(Vec3(enemy.x, 0.0, enemy.z))
            if anchor is None:
                continue
            commands.append(
                DrawCommand(
                    depth=anchor.depth,
                    layer_bias=0,
                    stable_id=enemy.id,
                    draw=lambda enemy=enemy: self.draw_enemy(enemy, camera),
                )
            )
        if model.bubble is not None:
            bubble_anchor = camera.project(Vec3(model.bubble.x, 4.0, model.bubble.z))
            if bubble_anchor is not None:
                commands.append(
                    DrawCommand(
                        depth=bubble_anchor.depth,
                        layer_bias=-1,
                        stable_id="bubble",
                        draw=lambda: self.draw_bubble(model, camera),
                    )
                )
        buddy_anchor = camera.project(Vec3(model.buddy.x, model.buddy.y, model.buddy.z))
        if buddy_anchor is not None:
            commands.append(
                DrawCommand(
                    depth=buddy_anchor.depth,
                    layer_bias=0,
                    stable_id="buddy",
                    draw=lambda: self.draw_buddy(model, camera, presentation_time),
                )
            )
        player_anchor = camera.project(Vec3(model.player.x, 0.0, model.player.z))
        if player_anchor is not None:
            commands.append(
                DrawCommand(
                    depth=player_anchor.depth,
                    layer_bias=0,
                    stable_id="player",
                    draw=lambda: self.draw_player(model, camera, presentation_time),
                )
            )
        self.last_stats = RenderStats(
            total_static_objects=len(model.world.objects),
            candidate_chunks=visible_query.candidate_chunk_count,
            candidate_static_objects=visible_query.candidate_object_count,
            visible_static_objects=len(visible_objects),
            visible_ground_details=len(visible_details),
            draw_commands=len(commands),
            active_enemies=model.debug.active_enemies,
            dormant_enemies=model.debug.dormant_enemies,
        )
        return commands

    def draw_object(self, obj: StaticObject, camera: CameraState) -> None:
        if obj.kind == "sprite_prop":
            self.draw_sprite_prop(obj, camera)
            return
        if obj.solid:
            height = obj.height if obj.height > 0 else 24.0
            color = 5 if obj.kind == "obstacle" else 4
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
        self, detail: GroundDetail, camera: CameraState, world_tick: int
    ) -> None:
        point = camera.project(Vec3(detail.x, 0.0, detail.z))
        if point is None:
            return
        x = int(point.x)
        y = int(point.y)
        phase = (world_tick // 8 + detail.phase) % 2
        self.pyxel.pset(x, y, detail.color)
        self.pyxel.line(x - 1, y, x - 1 + phase, y - 3, detail.color)

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

    def draw_enemy(self, enemy, camera: CameraState) -> None:
        if enemy.state == "DEFEATED":
            return
        point = camera.project(Vec3(enemy.x, 4.0, enemy.z))
        if point is None:
            return
        pyxel = self.pyxel
        radius = max(3, int(900 / max(point.depth, 1.0)))
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
                Vec3(enemy.x, 0.0, enemy.z),
                Vec3(enemy.x + enemy.dash_x * 56.0, 0.0, enemy.z + enemy.dash_z * 56.0),
                8,
            )
            pyxel.circb(x, y, radius + 5, 8)
        elif enemy.state == "DASH":
            pyxel.circb(x, y, radius + 5, 2)
        elif enemy.state == "CAPTURED":
            self.draw_world_circle(camera, enemy.x, enemy.z, 16.0, 12)
            pyxel.circb(x, y, radius + 5, 12)

    def draw_bubble(self, model: GameModel, camera: CameraState) -> None:
        bubble = model.bubble
        if bubble is None:
            return
        point = camera.project(Vec3(bubble.x, 5.0, bubble.z))
        if point is None:
            return
        radius = max(3, int(600 / max(point.depth, 1.0)))
        x = int(point.x)
        y = int(point.y)
        self.pyxel.circb(x, y, radius, 12)
        self.pyxel.pset(x, y, 7)

    def draw_player(self, model: GameModel, camera: CameraState, presentation_time: float) -> None:
        hover = self.player_visual_hover(model, presentation_time)
        shadow = camera.project(Vec3(model.player.x, 0.0, model.player.z))
        if shadow is not None:
            radius = max(3, int(1200 / max(shadow.depth, 1.0)))
            self.pyxel.elli(
                int(shadow.x - radius),
                int(shadow.y - radius // 3),
                radius * 2,
                max(2, radius // 2),
                0,
            )
        if self.draw_player_sprite(model, camera, presentation_time):
            return
        half = model.player_cube_size / 2.0
        self.draw_box(
            camera, model.player.x, model.player.z, half, half, model.player_cube_size, hover, 11
        )

    def player_visual_hover(self, model: GameModel, presentation_time: float) -> float:
        hover = float(model.config["player"]["visual_hover_base"])
        hover += math.sin(
            presentation_time / float(model.config["player"]["visual_hover_period_sec"]) * math.tau
        )
        return hover * float(model.config["player"]["visual_hover_amplitude"]) / 2.0

    def player_sprite_asset(self, model: GameModel) -> LoadedSpriteAsset | None:
        if not self.sprite_assets.enabled:
            return None
        asset_config = model.config.get("assets", {})
        asset_id = str(asset_config.get("player_idle_asset", ""))
        if not asset_id:
            return None
        return self.sprite_assets.get(asset_id)

    def player_sprite_placement(
        self, model: GameModel, camera: CameraState, presentation_time: float
    ):
        asset = self.player_sprite_asset(model)
        if asset is None:
            return None
        anchor = Vec3(
            model.player.x,
            self.player_visual_hover(model, presentation_time),
            model.player.z,
        )
        return placement_for_upright_height_billboard(camera, asset.definition, anchor)

    def draw_player_sprite(
        self, model: GameModel, camera: CameraState, presentation_time: float
    ) -> bool:
        asset = self.player_sprite_asset(model)
        if asset is None:
            return False
        placement = self.player_sprite_placement(model, camera, presentation_time)
        if placement is None:
            return False
        draw_scaled_sprite(self.pyxel, asset.frame(), asset.definition, placement)
        return True

    def draw_buddy(self, model: GameModel, camera: CameraState, presentation_time: float) -> None:
        buddy = model.buddy
        shadow = camera.project(Vec3(buddy.x, 0.0, buddy.z))
        if shadow is not None:
            radius = max(2, int(700 / max(shadow.depth, 1.0)))
            self.pyxel.elli(
                int(shadow.x - radius),
                int(shadow.y - max(1, radius // 4)),
                radius * 2,
                max(1, radius // 2),
                0,
            )
        bob = math.sin(presentation_time * math.tau / 1.3) * 2.0
        half = model.buddy_cube_size / 2.0
        self.draw_box(
            camera,
            buddy.x,
            buddy.z,
            half,
            half,
            model.buddy_cube_size,
            buddy.y + bob,
            10,
        )

    def draw_barrier(self, model: GameModel, camera: CameraState) -> None:
        if not model.player.barrier_active:
            return
        radius = float(model.config["barrier"]["radius"])
        self.draw_world_circle(camera, model.player.x, model.player.z, radius, 12)

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
        for _depth, _name, points, face_color in sorted(projected_faces, key=lambda item: -item[0]):
            p0, p1, p2, p3 = points
            self.pyxel.tri(
                int(p0.x), int(p0.y), int(p1.x), int(p1.y), int(p2.x), int(p2.y), face_color
            )
            self.pyxel.tri(
                int(p0.x), int(p0.y), int(p2.x), int(p2.y), int(p3.x), int(p3.y), face_color
            )
            for start, end in ((p0, p1), (p1, p2), (p2, p3), (p3, p0)):
                self.pyxel.line(int(start.x), int(start.y), int(end.x), int(end.y), 0)

    def draw_world_circle(
        self, camera: CameraState, x: float, z: float, radius: float, color: int
    ) -> None:
        last = None
        for index in range(33):
            angle = index * math.tau / 32.0
            point = camera.project(
                Vec3(x + math.cos(angle) * radius, 0.0, z + math.sin(angle) * radius)
            )
            if point is not None and last is not None:
                self.pyxel.line(int(last.x), int(last.y), int(point.x), int(point.y), color)
            last = point

    def draw_world_line(self, camera: CameraState, start: Vec3, end: Vec3, color: int) -> None:
        a = camera.project(start)
        b = camera.project(end)
        if a is None or b is None:
            return
        self.pyxel.line(int(a.x), int(a.y), int(b.x), int(b.y), color)

    def draw_debug_world(self, model: GameModel, camera: CameraState) -> None:
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
        self.draw_world_particles(camera, effects)
        self.draw_actor_emotes(model, camera, effects)
        self.draw_screen_cues(camera, effects)

    def draw_world_particles(self, camera: CameraState, effects: EffectSystem) -> None:
        for particle in effects.particles:
            point = camera.project(Vec3(particle.x, max(0.0, particle.y), particle.z))
            if point is None:
                continue
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

    def object_screen_bounds(self, obj: StaticObject, camera: CameraState) -> ScreenRect | None:
        if obj.kind == "sprite_prop":
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
            if not obj.occludes_player:
                continue
            obj_anchor = camera.project(Vec3(obj.x, 0.0, obj.z))
            if obj_anchor is None or obj_anchor.depth >= player_anchor.depth:
                continue
            obj_bounds = self.sprite_prop_bounds(obj, camera)
            if obj_bounds is not None and obj_bounds.overlaps(player_bounds):
                return True
        return False

    def draw_player_outline(
        self, model: GameModel, camera: CameraState, presentation_time: float | None = None
    ) -> None:
        bounds = self.player_screen_bounds(model, camera, presentation_time)
        if bounds is None:
            return
        self.pyxel.rectb(bounds.x - 2, bounds.y - 2, bounds.width + 4, bounds.height + 4, 7)
        self.pyxel.rectb(bounds.x - 1, bounds.y - 1, bounds.width + 2, bounds.height + 2, 12)
