from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.hex_assets import SpriteDefinition
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.render import ScreenRect
from drift_with_me.swarm_field import SwarmField
from drift_with_me.swarm_render import SwarmScene
from test_combat_resources import make_model
from test_swarm_field import enter, win
from test_week2_loop import hero_app

ASSETS = Path(__file__).resolve().parents[1] / "src/drift_with_me/assets"


def production_definitions():
    manifest = json.loads((ASSETS / "jack_sprite.json").read_text())
    wanted = ("jack_idle_32", "fuse_front_right_neutral_48", "normal_urchin_idle_64")
    result = {}
    for name in wanted:
        raw = manifest["assets"][name]
        frame = raw["frames"][0]
        result[name] = SimpleNamespace(
            definition=SpriteDefinition(
                name,
                "pyxel_default_16",
                frame["w"],
                frame["h"],
                raw["colkey"],
                tuple(raw["anchor_px"]),
                tuple(raw["world_size"]),
                raw["projection_mode"],
                "none",
                "static",
                (),
                frame["source_hash"],
            )
        )
    for raw in manifest["source_assets"]:
        if raw["id"] == "jun_w4_fuji":
            assert (ASSETS / raw["frames"][0]["path"]).is_file()
            result[raw["id"]] = SimpleNamespace(
                definition=SpriteDefinition(
                    raw["id"],
                    raw["palette_id"],
                    raw["hex_width"],
                    raw["hex_height"],
                    raw["colkey"],
                    tuple(raw["anchor_px"]),
                    tuple(raw["world_size"]),
                    raw["projection_mode"],
                    raw["flip_policy"],
                    raw["animation"],
                    (),
                    raw["source_hash"],
                )
            )
    slug = json.loads((ASSETS / "electric_nudibranch/sprites.json").read_text())["assets"][0]
    assert len(slug["frames"]) == 32
    assert all((ASSETS / "electric_nudibranch" / f["path"]).is_file() for f in slug["frames"])
    result[slug["id"]] = SimpleNamespace(definition=SimpleNamespace(**slug))
    return result


class AssetsRenderer:
    def __init__(self):
        import pyxel

        self.pyxel = pyxel
        self.assets = production_definitions()
        self._nudibranch_preview_assets = SimpleNamespace(errors=(), get=self.assets.get)
        self.calls = []

    def configured_sprite_asset(self, model, key):
        return self.assets.get(model.config["assets"][key])

    def draw_atmospheric_scaled_sprite(self, asset, placement):
        self.calls.append((asset.definition.asset_id, placement))

    def __getattr__(self, name):
        if name.startswith("draw_"):
            return lambda *args: self.calls.append((name, args))
        raise AttributeError(name)


def scene_setup():
    model, _ = make_model()
    model.player.x, model.player.z = 200, 800
    camera = CameraState.from_config(model.config, Vec3(200, 0, 800), 512, 236)
    field = model.swarm_field = SwarmField(model, "6:2", {})
    assert field.start("northwest", camera, [])
    renderer = AssetsRenderer()
    scene = SwarmScene(field, renderer, camera)
    return model, camera, field, renderer, scene


def test_production_metadata_transparency_and_feet_are_used_without_reauthoring():
    assets = production_definitions()
    assert assets["jack_idle_32"].definition.anchor_px == (16, 32)
    assert assets["fuse_front_right_neutral_48"].definition.colkey == 2
    assert assets["normal_urchin_idle_64"].definition.colkey == 3
    assert assets["normal_urchin_idle_64"].definition.anchor_px == (32, 60)
    assert assets["electric_nudibranch_normal"].definition.colkey == 8


def test_render_view_preserves_real_actors_world_and_enemy_roster():
    model, camera, field, _, scene = scene_setup()
    actors = deepcopy((model.player, model.buddy))
    enemies = deepcopy(model.enemies)
    assert scene.model_view.player is model.player and scene.model_view.buddy is model.buddy
    assert scene.model_view.world is model.world
    assert len(scene.model_view.enemies) == 6 and scene.model_view.enemies is not model.enemies
    scene.prepare(1)
    field.battle.progress = 0.72
    scene.prepare(2)
    assert (model.player, model.buddy) == actors and model.enemies == enemies
    assert scene.camera is camera
    assert sum(getattr(e, "species", "") == "electric_nudibranch" for e in scene.enemies) == 3


def test_real_camera_ellipse_remains_outward_and_capture_positions_are_stable():
    _, camera, field, _, scene = scene_setup()
    projected = [camera.project(Vec3(x, 0, z)) for x, z in scene.starts]
    assert projected[1].x < projected[0].x == pytest.approx(projected[2].x)
    assert projected[4].x > projected[3].x == pytest.approx(projected[5].x)
    field.battle.progress = 0.5
    scene.prepare(1)
    for enemy, (x, z) in zip(scene.enemies, scene.starts, strict=True):
        assert (enemy.x, enemy.z) == pytest.approx(
            (x + (200 - x) * 0.5 * 0.78, z + (800 - z) * 0.5 * 0.78)
        )
    field.battle.captured = True
    field.battle.capture_progress = 0.5
    field.battle.progress = 0
    before = [(e.x, e.z) for e in scene.enemies]
    scene.prepare(2)
    for original, enemy in zip(before, scene.enemies, strict=True):
        assert original == pytest.approx((enemy.x, enemy.z))
    assert all(e.state == "CAPTURED" for e in scene.enemies)


@pytest.mark.parametrize(
    "missing",
    [
        "jack_idle_32",
        "fuse_front_right_neutral_48",
        "normal_urchin_idle_64",
        "jun_w4_fuji",
        "electric_nudibranch_normal",
    ],
)
def test_missing_production_art_fails_instead_of_drawing_primitives(missing):
    _, camera, field, renderer, _ = scene_setup()
    del renderer.assets[missing]
    with pytest.raises(RuntimeError, match="Missing production"):
        SwarmScene(field, renderer, camera)


def test_fuji_uses_existing_field_sprite_in_the_world_depth_sort():
    _, _, field, renderer, scene = scene_setup()
    field.battle.phase = "assist"
    scene.prepare(1)
    commands = scene.draw_commands(renderer, scene.model_view, scene.camera)
    fuji = next(c for c in commands if c.stable_id == "swarm-fuji")
    fuji.draw()
    name, placement = renderer.calls[-1]
    assert name == "jun_w4_fuji" and fuji.layer_bias == 0
    assert fuji.depth == placement.depth


def test_capture_and_electric_effects_dispatch_to_existing_game_rendering():
    _, _, field, renderer, scene = scene_setup()
    b = field.battle
    b.captured, b.phase, b.elapsed = True, "bound", 0.5
    scene.prepare(1)
    scene.draw_enemy_fx(renderer, scene.enemies[0], 0)
    assert [c[0] for c in renderer.calls] == ["draw_combat_bubble_spray", "draw_combat_bubble_wrap"]
    renderer.calls.clear()
    b.phase, b.elapsed = "electric", 0.6
    scene.draw_enemy_fx(renderer, scene.enemies[0], 0)
    assert [c[0] for c in renderer.calls] == [
        "draw_combat_bubble_wrap",
        "draw_combat_homing_zaps",
        "draw_combat_enemy_disappear",
    ]


def test_foreground_assets_fade_back_before_victory_without_moving_world():
    model, _, field, renderer, scene = scene_setup()
    obj = next(o for o in model.world.objects if o.kind == "sprite_prop")
    renderer.object_screen_bounds = lambda *_: ScreenRect(120, 0, 300, 236)
    command = SimpleNamespace(stable_id=obj.id, depth=-1e9)
    original = deepcopy(model.world.objects)
    scene.prepare(1)
    assert scene.command_opacity(renderer, command) == 1
    scene.prepare(2)
    assert scene.command_opacity(renderer, command) == pytest.approx(0.1)
    field.battle.phase = "victory"
    field.battle.elapsed = field.config["victory_hold"]
    assert scene.command_opacity(renderer, command) == 1
    assert model.world.objects == original


def test_victory_never_snaps_buddy_and_app_never_resets_camera():
    model, camera = make_model()
    model.buddy.x, model.buddy.z = 231.25, 740.75
    before = (model.buddy.x, model.buddy.y, model.buddy.z)
    field = model.swarm_field = SwarmField(model, "6:2", {})
    enter(model, camera, field)
    assert (model.buddy.x, model.buddy.y, model.buddy.z) == before
    win(model, camera, field)
    assert (model.buddy.x, model.buddy.y, model.buddy.z) == before
    app = hero_app()
    app.camera_controller.reset = lambda *_: pytest.fail("victory camera jumped")
    app.model.snap_buddy = lambda *_: pytest.fail("victory buddy jumped")
    app.process_swarm_event(SimpleNamespace(kind="swarm_restored", payload={"won": True}))


def test_swarm_hud_has_only_common_controls_without_commentary_windows():
    _, _, field, _, scene = scene_setup()
    calls = []

    class App:
        def __getattr__(self, name):
            if name in {
                "draw_panel_frame",
                "draw_office_text_in_rect",
                "draw_office_wrapped_lines",
            }:
                raise AssertionError("Removed swarm commentary window was drawn")
            return lambda *args, **kwargs: calls.append(name)

    app = App()
    for phase in [
        "ready",
        "approach",
        "assist",
        "retreat_line",
        "fade",
        "electric",
        "spear",
        "victory",
    ]:
        field.battle.phase = phase
        scene.draw_hud(app)
    assert calls.count("draw_resource_panel") == 8
    assert calls.count("draw_combat_timing_bar") == 8
    assert calls.count("draw_action_button") == 8
    assert calls.count("draw_combat_chance_cues") == 8
