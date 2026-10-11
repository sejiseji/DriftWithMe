import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.garden_props_preview import (
    ASSET_IDS,
    GardenProp,
    GardenPropsPreview,
    garden_preview_draw_commands,
)
from drift_with_me.hex_assets import load_sprite_manifest, placement_for_upright_height_billboard
from drift_with_me.math3d import (
    AffineProjectionProfile,
    CameraState,
    Vec3,
    affine_camera_from_perspective,
)
from drift_with_me.model import InputIntent
from drift_with_me.render import DrawCommand, Renderer
from drift_with_me.save_state import SAVE_KEY, encode, snapshot
from drift_with_me.week_cycle import WorkWeek
from test_hex_assets import RecordingPyxel
from test_nudibranch_preview import Image
from test_save_state import Storage, payload
from test_week_debug_safety import debug_app

ASSETS = Path(__file__).resolve().parents[1] / "src/drift_with_me/assets"


def library():
    manifest = json.loads((ASSETS / "jack_sprite.json").read_text())
    definitions = [a for a in manifest["source_assets"] if a["id"] in ASSET_IDS]
    return load_sprite_manifest(
        SimpleNamespace(Image=Image),
        {"schema_version": 1, "assets": definitions},
        lambda name: (ASSETS / name).read_text(),
        enabled=True,
    )


def camera():
    runtime = load_runtime_config("medium")
    perspective = CameraState.from_config(runtime.raw, Vec3(400, 0, 600), 512, 236)
    return affine_camera_from_perspective(
        perspective, AffineProjectionProfile.from_config(runtime.raw), base_distance=480
    )


def test_all18_approved_assets_are_registered_and_raw_ground_is_not_billboard():
    loaded = library()
    assert set(loaded.assets) == set(ASSET_IDS)
    assert len(loaded.assets) == 18
    for asset in loaded.assets.values():
        assert asset.definition.colkey == 0
        assert set(asset.frame().source.pixels) <= set(range(16))
    ground = loaded.get("jlp1_string_ground_source")
    assert ground.definition.projection_mode == "ground_decal_source_v1"
    assert (
        placement_for_upright_height_billboard(camera(), ground.definition, Vec3(400, 0, 600))
        is None
    )


def test_normal_world_emits_no_preview_and_modular_layout_is_not_registered_as_collision():
    renderer = Renderer(RecordingPyxel(), library())
    assert garden_preview_draw_commands(renderer, SimpleNamespace(), camera()) == []
    state = GardenPropsPreview.for_camera(camera())
    assert len([p for p in state.props if p.asset_id.startswith("jlp1_stake_")]) == 6
    assert len([p for p in state.props if p.asset_id.startswith("jlp1_tray_")]) == 5
    rectangle = state.links
    state.layout = 1
    state.rebuild()
    assert state.links != rectangle
    assert all(a.y == b.y == 4 for a, b in state.links)
    for amount in range(4):
        state.amount = amount
        state.rebuild()
        assert (
            len([p for p in state.props if p.asset_id.startswith("jlp1_material_")]) == 3 - amount
        )


def test_sprite_extents_cull_offscreen_objects_but_keep_partial_overlap():
    cam = camera()
    renderer = Renderer(RecordingPyxel(), library())
    state = GardenPropsPreview.for_camera(cam)
    state.links = ()
    # Center just outside the viewport; part of the upright sprite remains visible.
    from drift_with_me.math3d import screen_to_ground_affine

    p = screen_to_ground_affine(cam, -4, 120)
    state.props = (GardenProp("jlp1_tray_white", p.x, p.y, "garden:partial"),)
    model = SimpleNamespace(garden_props_preview=state)
    commands = garden_preview_draw_commands(renderer, model, cam)
    assert [c.stable_id for c in commands] == ["garden:partial"]
    state.props = (replace(state.props[0], x=p.x - 10000),)
    assert garden_preview_draw_commands(renderer, model, cam) == []


def test_actor_and_props_share_depth_sort_and_use_equal_xy_scaling():
    cam = camera()
    recorder = RecordingPyxel()
    renderer = Renderer(recorder, library())
    state = GardenPropsPreview.for_camera(cam)
    state.links = ()
    state.props = (GardenProp("jlp1_tray_white", 400, 600, "garden:tray:white"),)
    commands = garden_preview_draw_commands(
        renderer, SimpleNamespace(garden_props_preview=state), cam
    )
    prop = commands[0]
    for dz, order in ((8, ["player", prop.stable_id]), (-8, [prop.stable_id, "player"])):
        actor = cam.project(Vec3(400, 0, 600 + dz))
        player = DrawCommand(actor.depth, 0, "player", lambda: None)
        assert [
            c.stable_id
            for c in sorted([player, prop], key=lambda c: (-c.depth, c.layer_bias, c.stable_id))
        ] == order
    prop.draw()
    _, options = recorder.blt_calls[0]
    assert options["scale"] == pytest.approx(abs(cam.profile.basis_y.y) * cam.effective_scale / 2)
    assert options["colkey"] == 0


@pytest.mark.parametrize("record_kind", ["valid", "corrupt", "absent"])
def test_controls_exit_week_jump_reload_preserve_scenario_and_both_save_slots(record_kind):
    _, valid = payload()
    storage = Storage()
    storage.items = {SAVE_KEY: encode(valid), SAVE_KEY + ".backup": encode(valid)}
    if record_kind == "corrupt":
        storage.items[SAVE_KEY] = "broken normal record"
    elif record_kind == "absent":
        storage.items.pop(SAVE_KEY)
    before = deepcopy(storage.items)
    for _ in range(2):
        app = debug_app(storage)
        app.presentation_time = 0
        assert app.start_garden_props_preview()
        assert app.model.garden_props_preview is app.garden_props_preview
        scenario = deepcopy(snapshot(app))
        enemies = [(e.id, e.state, e.x, e.z) for e in app.model.enemies]
        for action in ("layout", "less", "less", "less", "parts", "parts", "overlap", "overlap"):
            target = app.garden_props_preview_rects()[action]
            app.mouse_pressed_in = lambda rect, target=target: rect == target
            app.update_garden_props_preview()
        assert snapshot(app) == scenario
        assert [(e.id, e.state, e.x, e.z) for e in app.model.enemies] == enemies
        assert not app.checkpoint_progress()
        assert storage.items == before
        app.jump_to_debug_week(WorkWeek(6, 4))
        assert app.garden_props_preview is None
        assert not hasattr(app.model, "garden_props_preview")
        app.return_from_week_debug()
        assert not app.checkpoint_progress()
        assert storage.items == before


def test_preview_movement_never_steps_gameplay_and_normal_session_cannot_enter():
    app = debug_app(Storage(), enabled=False)
    assert not app.start_garden_props_preview()
    app = debug_app(Storage())
    app.presentation_time = 0
    assert app.start_garden_props_preview()
    before = deepcopy(snapshot(app))
    app.mouse_pressed_in = lambda _rect: False
    app.keyboard_intent = lambda: InputIntent(screen_x=1, strength=1)
    app.model.step = lambda *_args, **_kwargs: pytest.fail("gameplay advanced in preview")
    x = app.model.player.x
    app.presentation_time = 0.05
    app.update_garden_props_preview()
    assert app.model.player.x != x
    assert snapshot(app) == before
