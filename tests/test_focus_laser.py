from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.focus_laser import (
    BEAM_BEGIN,
    BIT_FADE_END,
    BUBBLE_BEGIN,
    BUBBLE_FLIGHT,
    BUBBLE_STAGGER,
    BURN_BEGIN,
    BURN_STEPS,
    CONTACT_HOLD,
    DURATION,
    FocusLaserAction,
    burn_pixels,
    burn_thresholds,
    draw_focus_laser,
)
from drift_with_me.math3d import ProjectedPoint, Vec2, Vec3
from drift_with_me.nudibranch_preview import DIRECTIONS, preview_assets
from drift_with_me.save_state import SAVE_KEY, encode
from test_nudibranch_preview import Image
from test_save_state import Storage, payload
from test_week_debug_safety import debug_app


def action():
    return FocusLaserAction.create(
        Vec3(0, 12, 0),
        Vec3(24, 12, 22),
        Vec3(66, 6.5, 10),
        Vec2(1, 0),
        "abnormal",
        "N_00",
    )


def test_six_jack_bits_surround_target_above_and_fuse_paths_end_at_the_bit():
    a = action()
    assert len(a.relays) == 6
    assert sum(r.bit.x for r in a.relays) / 6 == pytest.approx(a.target.x)
    for r in a.relays:
        assert r.bit.y > a.target.y + 18
        assert r.bit.z == a.target.z
        assert r.spawn_path[0] == a.jack
        assert r.spawn_path[-1] == r.bit
        assert r.laser_path[0] == a.fuse
        assert r.laser_path[-1] == r.bit
        assert len(r.laser_path) == 33
        # Curves have an actual arch rather than merely many collinear samples.
        assert r.laser_path[16].y > (a.fuse.y + r.bit.y) / 2


def test_deployment_arrival_contact_then_acceleration_and_burn_order():
    a = action()
    assert BUBBLE_BEGIN > 0.48
    assert BUBBLE_BEGIN + 5 * BUBBLE_STAGGER + BUBBLE_FLIGHT < BEAM_BEGIN
    arrivals = [r.arrival for r in a.relays]
    impacts = [r.impact for r in a.relays]
    assert arrivals == sorted(arrivals) and len(set(arrivals)) == 6
    assert impacts == sorted(impacts) and len(set(impacts)) == 6
    for r in a.relays:
        assert r.straight_start - r.arrival == pytest.approx(CONTACT_HOLD)
        assert r.impact > r.straight_start
    assert a.relays[0].straight_start < a.relays[-1].arrival
    assert impacts[0] < BURN_BEGIN
    assert BIT_FADE_END < DURATION


@pytest.mark.parametrize("kind", ["normal", "abnormal"])
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_every_direction_and_phase_dissolves_all_body_and_tentacle_pixels(kind, direction):
    root = Path(__file__).resolve().parents[1] / "src/drift_with_me/assets/electric_nudibranch"
    thresholds = burn_thresholds(64, 64)
    for f in range(4):
        source = bytes(
            int(c, 16)
            for c in (
                root / kind / f"electric_nudibranch_{kind}_{direction}_{f:02d}.hex"
            ).read_text()
            if c != "\n"
        )
        assert burn_pixels(source, thresholds, 0, 8) == source
        before = {i for i, p in enumerate(source) if p != 8}
        for step in range(1, BURN_STEPS + 1):
            pixels = burn_pixels(source, thresholds, step / BURN_STEPS, 8)
            alive = {i for i, p in enumerate(pixels) if p != 8}
            assert alive <= before  # No pixels ever grow back during the burn.
            before = alive
        assert not before


def test_geometry_and_burn_images_prepared_once_and_done_draws_nothing():
    a = action()
    calls = []
    camera = SimpleNamespace(project=lambda p: calls.append(p) or ProjectedPoint(p.x, -p.y, 500))
    paths = a.ensure_projection(camera)
    count = len(calls)
    for _ in range(30):
        assert a.ensure_projection(camera) is paths
    assert len(calls) == count and a.geometry_projection_count == 1
    pyxel = SimpleNamespace(Image=Image)
    asset = preview_assets(pyxel).get("electric_nudibranch_abnormal")
    frames = a.ensure_burn_frames(pyxel, asset.frame("N_00"), 8)
    assert len(frames) == BURN_STEPS + 1
    assert a.ensure_burn_frames(pyxel, asset.frame("N_00"), 8) is frames
    assert a.burn_preparation_count == 1
    a.elapsed = DURATION
    assert a.complete and a.phase == "DONE"
    draw_focus_laser(None, a, None)


@pytest.mark.parametrize("record_kind", ["valid", "corrupt", "absent"])
def test_repeat_cancel_kind_terrain_exit_and_reentry_preserve_storage(record_kind):
    _, valid = payload()
    storage = Storage()
    storage.items = {SAVE_KEY: encode(valid), SAVE_KEY + ".backup": encode(valid)}
    if record_kind == "corrupt":
        storage.items[SAVE_KEY] = "broken"
    elif record_kind == "absent":
        storage.items.pop(SAVE_KEY)
    before = deepcopy(storage.items)
    app = debug_app(storage)
    app.scene_camera = lambda camera: None  # Ground axes use the base camera in affine mode.
    app.presentation_time = 0
    app.start_nudibranch_preview()

    def click(name):
        rects = {**app.nudibranch_preview_rects(), **app.focus_laser_rects()}
        app.mouse_pressed_in = lambda rect: rect == rects[name]
        app.update_nudibranch_preview()

    assert not app.start_focus_laser()
    click("mode")
    assert app.nudibranch_preview.terrain == "grass"
    enemies = [(e.id, e.kind, e.state) for e in app.model.enemies]
    for _ in range(3):
        assert app.start_focus_laser()
        previous = app.nudibranch_preview.focus_action
        assert app.start_focus_laser()
        assert app.nudibranch_preview.focus_action is not previous
        click("cancel")
        assert app.nudibranch_preview.focus_action is None
        click("kind")
        click("terrain")
        assert not app.checkpoint_progress()
        assert storage.items == before
    assert [(e.id, e.kind, e.state) for e in app.model.enemies] == enemies
    app.start_focus_laser()
    click("menu")
    assert app.nudibranch_preview is None
    assert not hasattr(app.model, "nudibranch_preview")
    app.start_nudibranch_preview()
    assert app.nudibranch_preview.focus_action is None
    app.return_from_week_debug()
    assert storage.items == before and app.nudibranch_preview is None


def test_normal_session_cannot_start_finish():
    app = debug_app(Storage(), enabled=False)
    assert not app.start_focus_laser()


@pytest.mark.parametrize("kind", ["normal", "abnormal"])
def test_attack_se_sprite_selection_and_facing_does_not_leak_after_lifecycle(kind):
    from drift_with_me.nudibranch_preview import preview_attack_direction
    from drift_with_me.render import Renderer

    app = debug_app(Storage())
    app.presentation_time = 0
    app.start_nudibranch_preview()
    app.nudibranch_preview.mode = "laser"
    app.nudibranch_preview.target_kind = kind
    app.place_nudibranch_preview_actors()
    renderer = Renderer(SimpleNamespace())
    camera = app.camera()
    renderer.buddy_sprite_view_name = "back_left"
    assert preview_attack_direction(app.model) is None
    ordinary = (
        renderer.player_sprite_direction_view(app.model, camera),
        renderer.buddy_sprite_direction_view(app.model, camera),
    )
    cached = (renderer.player_sprite_view_name, renderer.buddy_sprite_view_name)
    for elapsed in (0, 0.8, 1.8, 2.4, 3.5):
        assert app.start_focus_laser()
        app.nudibranch_preview.focus_action.elapsed = elapsed
        assert renderer.player_sprite_direction_view(app.model, camera) == "front_right"
        assert renderer.buddy_sprite_direction_view(app.model, camera) == "front_right"
        assert (renderer.player_sprite_view_name, renderer.buddy_sprite_view_name) == cached
    app.nudibranch_preview.focus_action.elapsed = DURATION
    assert preview_attack_direction(app.model) is None
    assert (
        renderer.player_sprite_direction_view(app.model, camera),
        renderer.buddy_sprite_direction_view(app.model, camera),
    ) == ordinary
    app.start_focus_laser()
    app.nudibranch_preview.focus_action = None
    assert preview_attack_direction(app.model) is None
    app.start_focus_laser()
    app.return_from_week_debug()
    assert preview_attack_direction(app.model) is None
    app.initialize_week_debug(True)
    assert app.start_nudibranch_preview()
    assert preview_attack_direction(app.model) is None
