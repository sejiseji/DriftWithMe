"""Prelude timing/input/save isolation, independent of an actual player record."""

from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.ending_prelude import AUTOMATIC_SECONDS, LINES, TIMED, Prelude
from drift_with_me.save_state import snapshot
from test_ending_playback import final_app


def test_reading_waits_indefinitely_then_every_authored_cut_runs():
    p = Prelude()
    p.advance(3600)
    assert p.phase == "dialogue" and p.line == 0 and p.elapsed == 0
    for i in range(len(LINES)):
        assert p.next_line()
        assert p.line == min(i + 1, len(LINES) - 1)
    assert p.phase == "water_hold"
    for phase, seconds in TIMED:
        assert p.phase == phase
        p.advance(seconds - 1e-5)
        assert p.phase == phase
        p.advance(1e-5)
    assert p.complete and not p.next_line()


def test_invalid_time_split_updates_and_carry_are_deterministic():
    a = Prelude()
    b = Prelude()
    for p in (a, b):
        for _ in LINES:
            p.next_line()
    for value in (0, -1, float("nan"), float("inf")):
        assert a.advance(value) == 0
    a.advance(14.25)
    for _ in range(57):
        b.advance(0.25)
    assert a.phase == b.phase
    assert (a.elapsed, a.white, a.pan) == pytest.approx((b.elapsed, b.white, b.pan), abs=1e-10)
    assert a.advance(AUTOMATIC_SECONDS + 1 - 14.25) == pytest.approx(1)


def test_fade_and_pan_endpoints_have_no_premature_cut():
    for phase, duration in TIMED:
        p = Prelude(phase=phase)
        assert 0 <= p.white <= 1
        if phase.endswith("_in"):
            assert p.white == 1
        if phase.endswith("_out"):
            assert p.white == 0
        if phase.endswith("_pan"):
            assert p.pan == 0
            p.elapsed = duration
            assert p.pan == 1
        p.elapsed = duration
        if phase.endswith("_out"):
            assert p.white == 1
        if phase.endswith("_in"):
            assert p.white == 0


def test_enter_hold_input_advance_cancel_and_replay_never_write_progress():
    app, storage = final_app(True)
    before = snapshot(app)
    saved = deepcopy(storage.items)
    app.travel_input_held = lambda: True
    app.key_pressed = lambda *keys: "KEY_RETURN" in keys
    app.mouse_pressed_in = lambda _: False
    assert app.begin_ending()
    first = app.ending_playback
    app.update_ending(60)
    assert first.prelude.line == 0 and first.elapsed == 0
    app.travel_input_held = lambda: False
    app.update_ending(0.01)
    assert first.prelude.line == 1
    app.travel_input_held = lambda: True
    app.update_ending(1)
    assert first.prelude.line == 1  # repeat/held press cannot consume another line
    app.travel_input_held = lambda: False
    app.key_pressed = lambda *keys: "KEY_ESCAPE" in keys
    app.update_ending(0.01)
    assert app.screen == AppScreen.OFFICE and app.ending_playback is None
    assert snapshot(app) == before and storage.items == saved
    assert app.begin_ending() and app.ending_playback is not first
    assert app.ending_playback.prelude.line == 0


@pytest.mark.parametrize("complete", [False, True])
def test_all_cuts_connect_to_unchanged_credits_then_persistent_owned_room(complete):
    app, storage = final_app(complete)
    before = snapshot(app)
    saved = deepcopy(storage.items)
    app.travel_input_held = lambda: False
    app.key_pressed = lambda *_: False
    app.mouse_pressed_in = lambda _: False
    assert app.begin_ending()
    state = app.ending_playback
    for _ in LINES:
        state.prelude.next_line()
    app.update_ending(AUTOMATIC_SECONDS)
    assert state.prelude is None and state.elapsed == 0
    app.update_ending(111.31)
    assert app.screen == AppScreen.COLLECTION_ROOM and app.ending_playback is None
    assert snapshot(app) == before and storage.items == saved


@pytest.mark.parametrize("width,height", [(426, 196), (512, 236), (640, 294)])
def test_private_scene_camera_directions_and_world_bounds_do_not_change_saved_model(width, height):
    from types import SimpleNamespace

    from drift_with_me.ending_prelude import Scene
    from drift_with_me.hex_assets import SpriteAssetLibrary
    from drift_with_me.math3d import Vec3, screen_to_ground_affine

    class Image:
        def __init__(self, w, h):
            pass

        def set(self, x, y, rows):
            self.rows = rows

        def pget(self, x, y):
            return int(self.rows[y][x], 16)

    app, storage = final_app(True)
    app.pyxel = SimpleNamespace(Image=Image, width=width, height=height)
    app.sprite_assets = SpriteAssetLibrary.empty()
    before = snapshot(app)
    raw = deepcopy(app.world.raw)
    config = deepcopy(app.model.config)
    p = Prelude()
    scene = Scene(app, p)
    for cut in ("nw", "ne"):
        projected = []
        for t in (0, 4, 8):
            p.phase = cut + "_pan"
            p.elapsed = t
            cam = scene.camera(app, p)
            point = cam.project(Vec3(*({"nw": (236, 0, 718), "ne": (800, 0, 850)}[cut])))
            projected.append(point)
            for x, y in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
                ground = screen_to_ground_affine(cam, x, y)
                assert scene.model.world.visual_ground_rect.contains_point(ground.x, ground.y)
        if cut == "nw":
            assert projected[0].x > projected[-1].x
            assert projected[0].y == pytest.approx(projected[-1].y)
        else:
            assert projected[0].y > projected[-1].y
            assert projected[0].x == pytest.approx(projected[-1].x)
    assert scene.model is not app.model and scene.model.world is not app.world
    assert app.world.raw == raw and app.model.config == config and snapshot(app) == before


def test_hidden_update_does_not_advance_reading_or_pan_then_resume_continues():
    app, _ = final_app()
    assert app.begin_ending()
    p = app.ending_playback.prelude
    p.phase = "nw_pan"
    p.elapsed = 2.0
    app.lifecycle_update_blocked = lambda: True
    app.consume_elapsed = lambda: pytest.fail("hidden update consumed elapsed time")
    app.update()
    assert p.elapsed == 2.0
    app.travel_input_held = lambda: False
    app.key_pressed = lambda *_: False
    app.mouse_pressed_in = lambda _: False
    app.update_ending(0.5)
    assert p.elapsed == 2.5


def test_post_dialogue_actors_freeze_while_ambient_clock_continues(monkeypatch):
    from types import SimpleNamespace

    from drift_with_me.ending_prelude import SceneRenderer
    from drift_with_me.render import Renderer

    p = Prelude(ambient_time=10)
    for _ in LINES:
        p.next_line()
    p.advance(1)
    assert p.ambient_time == 11 and p.actor_hold_time == 10
    calls = []
    monkeypatch.setattr(Renderer, "draw_player", lambda self, m, c, t, a: calls.append(t))
    monkeypatch.setattr(Renderer, "draw_buddy", lambda self, m, c, t, a: calls.append(t))
    r = SceneRenderer(SimpleNamespace())
    r.prelude = p
    r.draw_player(None, None, 11, None)
    r.draw_buddy(None, None, 12, None)
    assert calls == [10, 10]


def test_touch_back_target_cancels_and_releases_private_scene_without_saving():
    app, storage = final_app()
    before = snapshot(app)
    saved = deepcopy(storage.items)
    assert app.begin_ending()
    p = app.ending_playback.prelude
    p.scene = object()
    app.travel_input_held = lambda: False
    app.key_pressed = lambda *_: False
    back = app.office_rect(46, 0, 64, 44)
    app.mouse_pressed_in = lambda rect: rect == back
    app.update_ending(0.01)
    assert app.screen == AppScreen.OFFICE and app.ending_playback is None and p.scene is None
    assert snapshot(app) == before and storage.items == saved


@pytest.mark.parametrize("width,height", [(32, 32), (64, 32), (32, 64), (256, 128)])
@pytest.mark.parametrize("scale", [0.25, 0.55, 1.0, 1.4, 2.2])
def test_ed_sprite_placement_preserves_source_aspect_and_square_sampling(width, height, scale):
    from types import SimpleNamespace

    from drift_with_me.ending_sprites import place_sprite, snap_placement
    from drift_with_me.math3d import ProjectedPoint

    definition = SimpleNamespace(hex_width=width, hex_height=height, anchor_px=(width / 2, height))
    point = ProjectedPoint(100, 150, 300)
    placement = place_sprite(definition, point, scale)
    assert (placement.right - placement.left) / width == pytest.approx(placement.scale)
    assert (placement.bottom - placement.top) / height == pytest.approx(placement.scale)
    assert (placement.right - placement.left) / (placement.bottom - placement.top) == pytest.approx(
        width / height
    )
    assert placement.bottom == 150
    assert placement.scale.is_integer() or (1 / placement.scale).is_integer()
    assert snap_placement(definition, placement) == placement


def test_ground_bitmap_projects_only_its_anchor_and_blits_the_original_frame():
    from types import SimpleNamespace

    from drift_with_me.ending_prelude import SceneRenderer
    from drift_with_me.math3d import ProjectedPoint

    projected = []
    drawn = []
    camera = SimpleNamespace(
        effective_scale=2, project=lambda p: projected.append(p) or ProjectedPoint(80, 80, 2)
    )
    definition = SimpleNamespace(
        hex_width=4, hex_height=8, world_size=(4, 8), anchor_px=(2, 4), colkey=0
    )
    # Real dataclass semantics are needed for the foot-anchor replacement.
    from dataclasses import make_dataclass

    Definition = make_dataclass(
        "Definition", [(k, type(v)) for k, v in vars(definition).items()], frozen=True
    )
    definition = Definition(**vars(definition))
    frame = SimpleNamespace(
        source=SimpleNamespace(
            rows=("0000", "0110", "0110", "0000", "0000", "0000", "0000", "0000")
        ),
        image=object(),
        u=0,
        v=0,
        width=4,
        height=8,
    )
    asset = SimpleNamespace(definition=definition, frame=lambda: frame)
    renderer = SceneRenderer(SimpleNamespace(blt=lambda *a, **kw: drawn.append((a, kw))))
    renderer.prelude = Prelude(phase="nw_pan")
    assert renderer.draw_ground_source_asset(asset, camera, 10, 20)
    assert len(projected) == 1  # no per-pixel XZ affine projection
    args, kw = drawn[0]
    assert args[2] is frame.image and args[5:7] == (4, 8) and kw["scale"] == 2


def test_flower_plots_leave_grass_gaps_clear_actor_feet_and_no_water_materials():
    from types import SimpleNamespace

    from drift_with_me.ending_prelude import Scene
    from drift_with_me.hex_assets import SpriteAssetLibrary

    app, _ = final_app(True)
    app.pyxel = SimpleNamespace(width=512, height=236)
    app.sprite_assets = SpriteAssetLibrary.empty()
    before = deepcopy(app.model.config)
    scene = Scene(app, Prelude())
    flowers = scene.renderer.flower_positions["water"]
    assert 12 <= len(flowers) <= 48
    assert len(scene.renderer.flower_plots["water"]) == 4
    for cut in ("nw", "ne"):
        assert len(scene.renderer.flower_plots[cut]) == 3
        assert 0 < len(scene.renderer.flower_positions[cut]) <= 36
    assert {red for x, z, red in flowers} == {False, True}
    for x, z, _red in flowers:
        assert all((x - ax) ** 2 + (z - az) ** 2 >= 21**2 for ax, az in ((455, 548), (473, 553)))
    assert not scene.model.config["shallow_water"]["enabled"]
    assert scene.renderer.sprite_assets is app.sprite_assets
    assert scene.renderer.draw_ground_surfaces(scene.model, None) is None
    assert scene.renderer.draw_baked_ground_patches(scene.model, None) == ()
    assert app.model.config == before


@pytest.mark.parametrize(
    "scale, expected", [(1.609251, 1), (1.819154, 1), (1.119479, 1), (2.099023, 2)]
)
def test_ed_pixel_scale_does_not_enlarge_scenery_above_its_world_size(scale, expected):
    from drift_with_me.ending_sprites import dot_scale

    assert dot_scale(scale) == expected
    assert dot_scale(scale) <= scale
    # Tall grass uses a 64px source, whereas the giant roots intentionally use 128px.
    assert 64 * dot_scale(1.819154) == 64
    assert 128 * dot_scale(2.099023) == 256
