"""Production swarm presentation through Renderer.draw_scene and normal assets.

Only transient enemy actors and new water effects are added. Player, buddy,
world, camera and the ordinary sprite loader remain the main-game instances.
"""

from __future__ import annotations

import math

from drift_with_me.hex_assets import placement_for_upright_height_billboard
from drift_with_me.math3d import (
    AffineCameraState,
    Vec3,
    screen_to_ground_affine,
    screen_to_ground_point,
)
from drift_with_me.model import EnemyState
from drift_with_me.nudibranch_preview import preview_assets
from drift_with_me.swarm_battle import ANGLES, KINDS
from drift_with_me.swarm_column import WINDUP, attack_view, column_frame, load_column_assets
from drift_with_me.swarm_guard import follow, guard_sample


class SwarmModelView:
    def __init__(self, model, presentation):
        self.model = model
        self.enemies = presentation.enemies
        self.swarm_presentation = presentation

    def __getattr__(self, name):
        return getattr(self.model, name)

    def enemy_by_id(self, enemy_id):
        return next((e for e in self.enemies if e.id == enemy_id), self.model.enemy_by_id(enemy_id))


class SwarmScene:
    def __init__(self, field, renderer, camera):
        self.field, self.battle = field, field.battle
        self.camera = camera
        self.elapsed = 0.0
        model = field.model
        self.enemies = []
        self.model_view = SwarmModelView(model, self)
        for index, kind in enumerate(KINDS):
            enemy = EnemyState(
                f"swarm:{index}",
                "normal",
                model.player.x,
                model.player.z,
                model.player.x,
                model.player.z,
            )
            enemy.focus_action = None
            enemy.zigzag_path = ()
            if kind == "slug":
                enemy.species = "electric_nudibranch"
            self.enemies.append(enemy)
        # Missing production art is a hard error, never a primitive replacement.
        for key in (
            "player_idle_asset",
            "buddy_idle_asset",
            "normal_urchin_idle_asset",
            "jun_w4_fuji_asset",
        ):
            if renderer.configured_sprite_asset(model, key) is None:
                raise RuntimeError(f"Missing production swarm sprite: {key}")
        library = getattr(renderer, "_nudibranch_preview_assets", None)
        if library is None:
            library = renderer._nudibranch_preview_assets = preview_assets(renderer.pyxel)
        if library.errors or library.get("electric_nudibranch_normal") is None:
            raise RuntimeError(f"Missing production nudibranch sprites: {library.errors}")
        self.library = library
        self.column_assets = load_column_assets(renderer.pyxel)
        self.fuji = renderer.configured_sprite_asset(model, "jun_w4_fuji_asset")
        self.anchor = camera.project(Vec3(model.player.x, 0, model.player.z))
        if self.anchor is None:
            raise RuntimeError("Swarm player anchor is outside the main camera")
        self.starts = []
        for angle in ANGLES:
            a = math.radians(angle)
            self.starts.append(
                self.ground(
                    self.anchor.x + camera.viewport_width * 0.23 * math.cos(a),
                    self.anchor.y
                    + camera.viewport_height
                    * field.config.get("formation_radius_y_ratio", 0.14)
                    * math.sin(a),
                )
            )
        self.fuji_ground = self.ground(
            self.anchor.x - camera.viewport_width * 0.34, self.anchor.y + 22
        )
        self.guard_ground = (model.buddy.x, model.buddy.z)
        self.guard_clock = None
        self.guard_views = None
        self.guard_rest_views = (
            getattr(renderer, "player_sprite_view_name", "front_left"),
            getattr(renderer, "buddy_sprite_view_name", "front_right"),
        )
        self.guard_rest_views = tuple(
            ("front_left" if i == 0 else "front_right") if v == "idle" else v
            for i, v in enumerate(self.guard_rest_views)
        )
        self.guard_facing = list(self.guard_rest_views)
        self.guard_turn_time = 0.0
        self.started_at = None
        self.obscuring_objects = set()

    def attack_view(self, actor, views):
        return attack_view(self.battle.phase, self.battle.elapsed, actor, views)

    def attack_asset(self, renderer, model, actor, view):
        if self.attack_view(actor, renderer.SPIN_DIRECTION_VIEWS) is None:
            return None
        if actor == "player":
            return self.column_assets.get(f"jack_{view}_squint")
        return self.column_assets.get(f"fuse_{view}_squint")

    def guard_view(self, actor):
        if self.guard_views is None:
            return None
        return self.guard_views[0 if actor == "player" else 1]

    def prepare_guard(self, time):
        dt = 0 if self.guard_clock is None else min(0.1, max(0, time - self.guard_clock))
        self.guard_clock = time
        model = self.field.model
        target = (model.buddy.x, model.buddy.z)
        if self.battle.phase == "approach":
            jack, buddy, (dx, dy) = guard_sample(self.battle.elapsed)
            target_views = (jack, buddy)
            anchor = self.camera.project(Vec3(model.player.x, 0, model.player.z))
            scale = self.camera.viewport_width / 512
            target = self.ground(anchor.x + dx * scale, anchor.y + dy * scale)
        else:
            target_views = self.guard_rest_views
        self.guard_turn_time += dt
        views = (
            "right",
            "front_right",
            "front",
            "front_left",
            "left",
            "back_left",
            "back",
            "back_right",
        )
        while self.guard_turn_time >= 0.045:
            self.guard_turn_time -= 0.045
            for i, desired in enumerate(target_views):
                a, b = views.index(self.guard_facing[i]), views.index(desired)
                if a != b:
                    delta = (b - a) % 8
                    self.guard_facing[i] = views[(a + (1 if delta < 4 else -1)) % 8]
        self.guard_views = tuple(self.guard_facing)
        if self.battle.phase != "approach" and self.guard_views == self.guard_rest_views:
            self.guard_views = None
        self.guard_ground = follow(self.guard_ground, target, dt)

    def ground(self, x, y):
        result = (
            screen_to_ground_affine(self.camera, x, y)
            if isinstance(self.camera, AffineCameraState)
            else screen_to_ground_point(self.camera, x, y)
        )
        if result is None:
            raise RuntimeError("Cannot place swarm on the main-game ground plane")
        return result.x, result.y

    def prepare(self, time):
        self.prepare_guard(time)
        self.elapsed = time
        self.anchor = self.camera.project(
            Vec3(self.field.model.player.x, 0, self.field.model.player.z)
        )
        if self.started_at is None:
            self.started_at = time
        b, model = self.battle, self.field.model
        progress = b.capture_progress if b.captured else b.progress
        for index, enemy in enumerate(self.enemies):
            x, z = self.starts[index]
            enemy.x = x + (model.player.x - x) * progress * 0.78
            enemy.z = z + (model.player.z - z) * progress * 0.78
            enemy.capture_y = 0.0
            if b.captured:
                t = min(1, b.capture_elapsed / 0.8)
                eased = t * t * (3 - 2 * t)
                dx, dz = enemy.x - model.player.x, enemy.z - model.player.z
                length = max(1e-6, math.hypot(dx, dz))
                enemy.x += dx / length * b.settings.knockback * eased
                enemy.z += dz / length * b.settings.knockback * eased
                enemy.capture_y = eased * (
                    b.settings.float_height + 1.5 * math.sin(b.capture_elapsed * 3 + index * 0.7)
                )
                point = self.camera.project(Vec3(enemy.x, 0, enemy.z))
                margin_x = self.camera.viewport_width * 32 / 512
                sx = max(margin_x, min(self.camera.viewport_width - margin_x, point.x))
                sy = max(
                    self.camera.viewport_height * 90 / 236,
                    min(self.camera.viewport_height * 188 / 236, point.y),
                )
                enemy.x, enemy.z = self.ground(sx, sy)
            if b.phase == "shake":
                point = self.camera.project(Vec3(enemy.x, 0, enemy.z))
                enemy.x, enemy.z = self.ground(
                    point.x + math.sin(b.elapsed * 100 + index) * 3, point.y
                )
            enemy.state = (
                "DEFEATED" if index in b.defeated else "CAPTURED" if b.captured else "IDLE"
            )
            dx, dz = model.player.x - enemy.x, model.player.z - enemy.z
            length = max(1e-6, math.hypot(dx, dz))
            enemy.dash_x, enemy.dash_z = dx / length, dz / length
            enemy.sprite_heading = (enemy.dash_x, enemy.dash_z)
            enemy.animation_time = time

    def draw(self, app):
        self.prepare(app.presentation_time)
        p, b = app.pyxel, self.battle
        # Camera offsets affect the real scene only, never the resource/dialogue UI.
        p.camera(round(math.sin(b.elapsed * 120) * 2) if b.phase == "shake" else 0, 0)
        app.renderer.draw_scene(
            self.model_view,
            self.camera,
            app.presentation_time,
            app.debug_enabled,
            app.effects,
            exploration_markers=False,
        )
        p.camera()
        self.draw_hud(app)
        if b.phase == "fade":
            p.dither(min(1, b.elapsed / b.settings.fade))
            p.rect(0, 0, app.runtime.screen_width, app.runtime.screen_height, 0)
            p.dither(1)

    def command_opacity(self, renderer, command):
        # The ordinary contact battle removes foreground blockers. For a swarm,
        # fade the same production props instead, then restore them gradually.
        # Neither the world objects nor the camera moves to make an arena.
        obj = self.field.model.world.object_by_id(command.stable_id)
        if obj is None or not (obj.occludes_player or obj.kind in {"sprite_prop", "reactive_prop"}):
            return 1.0
        bounds = renderer.object_screen_bounds(obj, self.camera)
        if bounds is None:
            return 1.0
        farthest = max(self.camera.project(Vec3(x, 0, z)).depth for x, z in self.starts)
        x0, x1 = (
            self.anchor.x - self.camera.viewport_width * 0.28,
            self.anchor.x + self.camera.viewport_width * 0.28,
        )
        if command.depth >= farthest or bounds.max_x < x0 or bounds.x > x1:
            return 1.0
        self.obscuring_objects.add(obj.id)
        entered = min(1, max(0, (self.elapsed - self.started_at) / 0.35))
        strength = entered
        if self.battle.phase == "victory":
            strength *= max(0, 1 - self.battle.elapsed / self.field.config["victory_hold"])
        return 1 - 0.90 * strength

    def draw_commands(self, renderer, model, camera):
        from drift_with_me.render import DrawCommand

        commands = []
        for index, enemy in enumerate(self.enemies):
            if enemy.state == "DEFEATED":
                continue
            ground = camera.project(Vec3(enemy.x, 0, enemy.z))
            point = camera.project(Vec3(enemy.x, getattr(enemy, "capture_y", 0), enemy.z))
            if getattr(enemy, "capture_y", 0) > 0:
                commands.append(
                    DrawCommand(
                        ground.depth,
                        -1,
                        f"swarm-shadow:{index}",
                        lambda g=ground: renderer.draw_shadow_ellipse(
                            int(g.x - 7), int(g.y - 2), 14, 4, 7
                        ),
                        0,
                    )
                )
            commands.append(
                DrawCommand(
                    point.depth,
                    1,
                    f"swarm-fx:{index}",
                    lambda e=enemy, i=index: self.draw_enemy_fx(renderer, e, i),
                    0,
                )
            )
        b = self.battle
        if b.phase == "assist" or b.phase == "retreat_line" and b.failures > 1:
            x, z = self.fuji_ground
            placement = placement_for_upright_height_billboard(
                camera, self.fuji.definition, Vec3(x, 0, z)
            )
            if placement is not None:
                commands.append(
                    DrawCommand(
                        placement.depth,
                        0,
                        "swarm-fuji",
                        lambda: renderer.draw_atmospheric_scaled_sprite(self.fuji, placement),
                        1,
                    )
                )
        return commands

    def draw_enemy_fx(self, renderer, enemy, index):
        b, camera, model = self.battle, self.camera, self.field.model
        target = camera.project(Vec3(enemy.x, 8 + getattr(enemy, "capture_y", 0), enemy.z))
        if b.captured:
            progress = min(1, b.elapsed / b.settings.bound_hold) if b.phase == "bound" else 1
            if b.phase == "bound":
                source = camera.project(Vec3(model.player.x, 12, model.player.z))
                renderer.draw_combat_bubble_spray(source, target, progress, b.elapsed)
            renderer.draw_combat_bubble_wrap(target, progress, 1, self.elapsed)
        if b.phase == "electric" and KINDS[index] == "urchin":
            source = camera.project(
                Vec3(self.guard_ground[0], model.buddy.y + 5, self.guard_ground[1])
            )
            t = max(0, min(1, (b.elapsed - WINDUP) / (b.settings.electric - WINDUP)))
            if b.elapsed >= WINDUP:
                renderer.draw_combat_homing_zaps(source, target, t)
            renderer.draw_combat_enemy_disappear(target, t, enemy.kind)
        if KINDS[index] != "slug" or b.phase not in {"circle", "converge", "spear"}:
            return
        renderer.draw_world_circle(camera, enemy.x, enemy.z, 12, 12)
        renderer.draw_world_circle(camera, enemy.x, enemy.z, 10, 6)
        if b.phase == "converge":
            t = min(1, b.elapsed / b.settings.converge)
            for index in range(8):
                a = index * math.tau / 8 + b.elapsed * 5
                r = 24 * (1 - t)
                renderer.draw_world_line(
                    camera,
                    Vec3(enemy.x + math.cos(a) * r, 1, enemy.z + math.sin(a) * r),
                    Vec3(enemy.x, 1, enemy.z),
                    12,
                )
        if b.phase == "spear":
            frame_index = column_frame(b.elapsed - WINDUP) if b.elapsed >= WINDUP else None
            asset = self.column_assets.get("water_tornado_v3")
            placement = placement_for_upright_height_billboard(
                camera, asset.definition, Vec3(enemy.x, 0, enemy.z)
            )
            if frame_index is not None and placement is not None:
                renderer.draw_atmospheric_scaled_sprite(
                    asset, placement, asset.frame(f"f{frame_index:02d}")
                )
            self.water_stats = {"column_frame": frame_index, "cycle_ms": 270}
            if b.elapsed > b.settings.spear * 0.6:
                renderer.draw_combat_enemy_disappear(
                    target, b.elapsed / b.settings.spear, enemy.kind
                )

    def draw_hud(self, app):
        app.draw_resource_panel()
        app.draw_system_button(app.sound_button_rect(), app.sound_visual_rect(), "sound")
        app.draw_system_button(app.pause_button_rect(), app.pause_visual_rect(), "pause")
        app.draw_combat_timing_bar(self.field.presentation_session())
        token = self.field.action_mode
        app.draw_action_button(
            app.action_button_visual_rect(), token, slot="primary", enabled=token != "NONE"
        )
        app.draw_combat_chance_cues()
