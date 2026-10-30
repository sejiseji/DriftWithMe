"""Save-isolated ending conversation and three native-rendered landscape cuts."""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field, replace

from drift_with_me.ending_sprites import place_sprite, snap_placement
from drift_with_me.hex_assets import draw_scaled_sprite, placement_for_upright_height_billboard
from drift_with_me.math3d import Vec3, screen_to_ground_affine, screen_to_ground_point
from drift_with_me.render import DrawCommand, Renderer

LINES = (
    ("ジャック", "今日の報告は、少し落ち着いて話せたよ。"),
    ("ヒューズ", "ええ。ちゃんと、自分の言葉になってたわ。"),
    ("ジャック", "こうしてると、急に力が抜けるね。"),
    ("ヒューズ", "もう、急いで戻らなくていいもの。"),
    ("ジャック", "そっか。明日から夏休みだ。"),
    ("ヒューズ", "のんびりしましょう。お互いにね。"),
)
TIMED = (
    ("water_hold", 2.5),
    ("water_out", 1.2),
    ("nw_in", 1.2),
    ("nw_pan", 8.0),
    ("nw_out", 1.2),
    ("ne_in", 1.2),
    ("ne_pan", 8.0),
    ("ne_out", 1.2),
)
AUTOMATIC_SECONDS = sum(seconds for _, seconds in TIMED)
CENTERS = {"water": (460.0, 550.0), "nw": (236.0, 718.0), "ne": (800.0, 850.0)}


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


@dataclass
class Prelude:
    phase: str = "dialogue"
    elapsed: float = 0.0
    ambient_time: float = 0.0
    line: int = 0
    wait_release: bool = True
    actor_hold_time: float = 0.0
    scene: object = field(default=None, repr=False)

    @property
    def complete(self):
        return self.phase == "done"

    @property
    def cut(self):
        return (
            "nw"
            if self.phase.startswith("nw")
            else "ne"
            if self.phase.startswith("ne")
            else "water"
        )

    @property
    def pan(self):
        if self.phase.endswith("_pan"):
            return smooth(self.elapsed / 8)
        return 1.0 if self.phase.endswith("_out") else 0.0

    @property
    def white(self):
        if self.phase.endswith("_in"):
            return 1 - smooth(self.elapsed / 1.2)
        if self.phase.endswith("_out"):
            return smooth(self.elapsed / 1.2)
        return 0.0

    def next_line(self):
        if self.phase != "dialogue":
            return False
        if self.line + 1 < len(LINES):
            self.line += 1
        else:
            self.phase, self.elapsed = TIMED[0][0], 0.0
            self.actor_hold_time = self.ambient_time
        return True

    def advance(self, seconds):
        if not math.isfinite(seconds) or seconds <= 0:
            return 0.0
        self.ambient_time += seconds
        if self.phase == "dialogue":
            return 0.0  # Reading is never timed out.
        remaining = seconds
        while not self.complete:
            index = next(i for i, (phase, _) in enumerate(TIMED) if phase == self.phase)
            duration = TIMED[index][1]
            step = min(remaining, duration - self.elapsed)
            self.elapsed += step
            remaining -= step
            if self.elapsed + 1e-9 < duration:
                break
            self.phase = TIMED[index + 1][0] if index + 1 < len(TIMED) else "done"
            self.elapsed = 0.0
            if remaining <= 1e-9:
                break
        return remaining if self.complete and remaining > 1e-9 else 0.0


class SceneRenderer(Renderer):
    def player_is_occluded(self, *args):
        return False  # Cinematic keeps ordinary depth occlusion, without exploration outline.

    def draw_shallow_water_tiles(self, model, camera):
        pass

    def draw_shallow_water_shoreline_tiles(self, model, camera):
        pass

    def draw_shallow_water_symbols(self, *args):
        return 0

    def draw_ground_surfaces(self, model, camera):
        pass  # Omit flat material planes; the ending is a flowering grassland.

    def draw_baked_ground_patches(self, model, camera):
        return ()  # These contain XZ-projected bitmap decor; draw original props below.

    def draw_atmospheric_scaled_sprite(self, asset, placement, frame=None):
        super().draw_atmospheric_scaled_sprite(
            asset, snap_placement(asset.definition, placement), frame
        )

    def draw_ground_source_asset(self, asset, camera, x, z):
        if asset is None:
            return False
        definition = asset.definition
        if self.prelude.cut == "water" and any(
            (x - ax) ** 2 + (z - az) ** 2 < 18**2 for ax, az in ((455, 548), (473, 553))
        ):
            return True
        point = camera.project(Vec3(x, 0, z))
        if point is None:
            return True
        # Ground artwork previously mapped each source pixel into a skewed XZ basis.
        # Keep the source bitmap intact, with one scalar and its lower opaque edge at ground.
        frame = asset.frame()
        source = frame.source
        if source is not None:
            rows = source.rows
            bottom = max(
                (
                    y + 1
                    for y, row in enumerate(rows)
                    if any(int(c, 16) != definition.colkey for c in row)
                ),
                default=definition.hex_height,
            )
            definition = replace(definition, anchor_px=(definition.anchor_px[0], bottom))
        scale = camera.effective_scale * min(
            definition.world_size[0] / definition.hex_width,
            definition.world_size[1] / definition.hex_height,
        )
        placement = place_sprite(definition, point, scale)
        draw_scaled_sprite(self.pyxel, frame, definition, placement)
        return True

    def world_commands(self, model, camera, presentation_time, effects=None):
        commands = super().world_commands(model, camera, presentation_time, effects)
        if self.prelude.cut != "water":
            commands = [c for c in commands if c.stable_id not in {"player", "buddy"}]
        commands.extend(self.scenery(model, camera))
        return commands

    def draw_player(self, model, camera, presentation_time, presentation=None):
        time = (
            presentation_time if self.prelude.phase == "dialogue" else self.prelude.actor_hold_time
        )
        return super().draw_player(model, camera, time, presentation)

    def draw_buddy(self, model, camera, presentation_time, presentation=None):
        time = (
            presentation_time if self.prelude.phase == "dialogue" else self.prelude.actor_hold_time
        )
        return super().draw_buddy(model, camera, time, presentation)

    def scenery(self, model, camera):
        p = self.prelude
        commands = []
        for i, (x, z, red) in enumerate(self.flower_positions[p.cut]):
            asset = self.sprite_assets.get("jun_w4_south" if red else "jun_w4_tree")
            if asset is None:
                raise RuntimeError("Missing approved flower sprite")
            point = camera.project(Vec3(x, 0, z))
            if point is None:
                continue
            # One-pixel lateral breeze preserves every source pixel and its proportions.
            sway = round(math.sin(p.ambient_time * 1.1 + i * 0.618))
            point = replace(point, x=point.x + sway)
            placement = place_sprite(asset.definition, point, 1.0)
            if placement.right < 0 or placement.left > camera.viewport_width:
                continue

            def flower_draw(a=asset, place=placement, red=red):
                if red:
                    self.pyxel.pal(9, 8)
                    self.pyxel.pal(10, 14)
                try:
                    draw_scaled_sprite(self.pyxel, a.frame(), a.definition, place)
                finally:
                    if red:
                        self.pyxel.pal(9, 9)
                        self.pyxel.pal(10, 10)

            commands.append(
                DrawCommand(
                    depth=point.depth,
                    layer_bias=0,
                    stable_id=f"ending_flower:{i}",
                    draw=flower_draw,
                    atmosphere_strength=0.0,
                )
            )
        if p.cut == "water":
            return commands
        from drift_with_me.nudibranch_preview import preview_assets

        if not hasattr(self, "babies"):
            self.babies = preview_assets(self.pyxel)
        t = p.ambient_time
        for i in range(2):
            kind = "urchin" if p.cut == "nw" else "slug"
            asset = (
                self.configured_sprite_asset(model, "normal_urchin_idle_asset")
                if kind == "urchin"
                else self.babies.get("electric_nudibranch_normal")
            )
            if asset is None:
                raise RuntimeError("Missing approved juvenile sprite")
            if kind == "urchin":
                # Small continuous routes around the same woodland clearing.
                ground = Vec3(
                    246 - i * 18 + 6 * math.sin(t * 0.45 + i),
                    0,
                    674 + i * 7 + 2 * math.sin(t * 0.90 + i),
                )
                frame = asset.frame()
            else:
                ground = Vec3(800 + i * 13, 0, 852 - i * 6)
                direction = ("E", "NE", "N", "NE")[int(t / 1.5 + i) % 4]
                frame = asset.frame(f"{direction}_{int(t * 3) % 4:02d}")
            definition = replace(
                asset.definition, world_size=tuple(v * 0.55 for v in asset.definition.world_size)
            )
            placement = placement_for_upright_height_billboard(camera, definition, ground)
            anchor = camera.project(ground)
            if placement is not None and anchor is not None:
                commands.append(
                    DrawCommand(
                        depth=anchor.depth,
                        layer_bias=0,
                        stable_id=f"ending_baby:{i}",
                        draw=lambda a=asset, d=definition, f=frame, place=placement: (
                            self.draw_atmospheric_scaled_sprite(a, place, f)
                        ),
                        atmosphere_strength=0.0,
                    )
                )
        return commands


class Scene:
    def __init__(self, app, prelude):
        # Never bind the snapshot back into the game, office, garden or save store.
        self.model = deepcopy(app.model)
        self.model.enemies = []
        self.model.combat_session = None
        self.model.interaction = None
        self.model.bubble = None
        self.model.auto_move_goal = None
        self.model.player.barrier_active = False
        self.model.last_events = []
        self.model.august_sighting_view = None
        self.model.swarm_presentation = None
        self.model.nudibranch_preview = None
        self.model.garden_props_preview = None
        self.model.august_rain = False
        self.model.august_recovered = True
        self.model.config["world_debug"]["show_walkable_boundary"] = False
        from drift_with_me.world import WorldData

        raw = deepcopy(self.model.world.raw)
        raw["objects"] = [
            o for o in raw["objects"] if not o["id"].startswith(("aug_patrol_", "collectible_"))
        ]
        self.model.world = WorldData(raw)
        self.model.player.x, self.model.player.z = 455, 548
        self.model.buddy.x, self.model.buddy.z, self.model.buddy.y = 473, 553, 10
        self.model.player.last_move_x, self.model.player.last_move_z = -1, -1
        self.model.buddy.goal_x, self.model.buddy.goal_z = 455, 548
        self.model.config["shallow_water"]["enabled"] = False
        self.model.config["shallow_water"]["surface_tiles_enabled"] = False
        self.model.config["shallow_water"]["shoreline_tiles_enabled"] = False
        self.renderer = SceneRenderer(app.pyxel, app.sprite_assets)
        self.renderer.prelude = prelude
        self.renderer.flower_positions = {}
        from drift_with_me.august_scenery import planks
        from drift_with_me.northeast_park import PAVING

        plank_centers = tuple((x, z) for x, z, _, _ in planks())
        for cut in ("water", "nw", "ne"):
            reference = Prelude(phase="dialogue" if cut == "water" else cut + "_pan", elapsed=4)
            camera = self.camera(app, reference)
            positions = []
            # Rectangles live in the reference screen plane; only their anchors
            # are mapped to world ground. The camera never warps flower pixels.
            plots = {
                "water": (
                    (80, 34, 152, 82, True),
                    (320, 30, 392, 78, False),
                    (94, 132, 166, 180, False),
                    (344, 134, 416, 182, True),
                ),
                "nw": (
                    (112, 40, 184, 88, False),
                    (300, 42, 372, 90, True),
                    (270, 158, 342, 206, False),
                ),
                "ne": (
                    (116, 36, 188, 84, True),
                    (334, 40, 406, 88, False),
                    (300, 164, 372, 212, True),
                ),
            }[cut]
            self.renderer.flower_plots = getattr(self.renderer, "flower_plots", {})
            self.renderer.flower_plots[cut] = plots
            for x0, y0, x1, y1, red in plots:
                for sy in range(y0, y1 + 1, 24):
                    for sx in range(x0, x1 + 1, 24):
                        ground = screen_to_ground_affine(
                            camera,
                            sx * camera.viewport_width / 512,
                            sy * camera.viewport_height / 236,
                        )
                        if ground is not None:
                            positions.append((ground.x, ground.y, red))
            candidates = positions
            positions = []
            for gx, gz, red in candidates:
                from drift_with_me.math3d import Vec2

                ground = Vec2(gx, gz)
                if ground is None or not self.model.world.visual_ground_rect.contains_point(
                    ground.x, ground.y
                ):
                    continue
                clear = (
                    ((455, 548, 21), (473, 553, 21))
                    if cut == "water"
                    else ((246, 674, 9), (228, 681, 9))
                    if cut == "nw"
                    else ((816, 900, 14), (800, 852, 9), (813, 846, 9))
                )
                if any(
                    (ground.x - x) ** 2 + (ground.y - z) ** 2 < radius**2 for x, z, radius in clear
                ):
                    continue
                if any((ground.x - x) ** 2 + (ground.y - z) ** 2 < 11**2 for x, z in plank_centers):
                    continue
                if cut == "ne" and any(
                    x0 <= ground.x <= x1 and z0 <= ground.y <= z1 for x0, z0, x1, z1 in PAVING
                ):
                    continue
                positions.append((ground.x, ground.y, red))
            self.renderer.flower_positions[cut] = tuple(positions)

    def camera(self, app, state):
        cx, cz = CENTERS[state.cut]
        from drift_with_me.math3d import (
            AffineProjectionProfile,
            CameraState,
            affine_camera_from_perspective,
        )

        # A fixed cinematic camera ignores the user's prior focus/shake/zoom.
        base = CameraState.from_config(
            self.model.config, Vec3(cx, 0, cz), app.pyxel.width, app.pyxel.height, zoom=2.0
        )
        camera = affine_camera_from_perspective(
            base,
            AffineProjectionProfile.from_config(self.model.config),
            base_distance=float(self.model.config["camera"]["base_distance"]),
        )
        # Pan in SCREEN coordinates; inverse projection makes the direction explicit.
        unproject = (
            screen_to_ground_affine
            if hasattr(camera, "effective_scale")
            else screen_to_ground_point
        )
        mx, my = camera.viewport_width / 2, camera.viewport_height / 2
        sx = (state.pan - 0.5) * 56 if state.cut == "nw" else 0
        sy = (state.pan - 0.5) * 40 if state.cut == "ne" else 0
        a, b = unproject(camera, mx, my), unproject(camera, mx + sx, my + sy)
        return replace(
            camera, target=Vec3(camera.target.x + b.x - a.x, 0, camera.target.z + b.y - a.y)
        )

    def draw(self, app, state):
        from drift_with_me.ending_playback import apply_palette, restore_palette

        restore_palette(app)
        self.model.world_tick = int(state.ambient_time * 60)
        self.renderer.draw_scene(
            self.model,
            self.camera(app, state),
            state.ambient_time,
            False,
            None,
            exploration_markers=False,
        )
        if state.phase == "dialogue":
            speaker, line = LINES[state.line]
            panel = app.office_rect(56, 157, 400, 69)
            app.draw_panel_frame(panel, fill=0, inner=12)
            app.draw_office_text_in_rect(app.office_rect(66, 163, 360, 17), speaker, 12)
            app.draw_office_wrapped_lines(app.office_rect(66, 184, 360, 32), (line,), 7)
            app.draw_office_text_in_rect(app.office_rect(402, 207, 48, 14), "次へ →", 10)
        app.draw_office_text_in_rect(app.office_rect(56, 8, 48, 18), "戻る", 7)
        # Match the already-approved credits/room viewport, including fade edges.
        apply_palette(app, list(app.pyxel.colors.to_list()), state.white)
        scale = min(app.pyxel.width / 512, app.pyxel.height / 236)
        width = 420 * scale
        left = (app.pyxel.width - width) / 2
        app.pyxel.rect(0, 0, left, app.pyxel.height, 255)
        app.pyxel.rect(left + width, 0, app.pyxel.width - left - width, app.pyxel.height, 255)
