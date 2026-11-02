import math
from dataclasses import asdict

import pytest

from drift_with_me.camera import CameraController
from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import (
    AffineProjectionProfile,
    Vec3,
    affine_camera_from_perspective,
    screen_to_ground_affine,
)
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.world import load_world_data


def trace(mode, start=(520, 480), frames=360, pattern=None):
    raw = load_runtime_config().raw
    world = load_world_data()
    m = GameModel(raw, world)
    m.enemies.clear()
    m.player.x, m.player.z = start
    c = CameraController(raw, world, 512, 236, Vec3(start[0], 0, start[1]))
    c.stop_settle_mode = mode
    p = AffineProjectionProfile.from_config(raw)
    rows = []
    for frame in range(frames):
        a = affine_camera_from_perspective(c.current, p, base_distance=480)
        dx, dy = pattern(frame) if pattern else ((1, 0) if frame < 60 else (0, 0))
        m.step(
            InputIntent(screen_x=dx, screen_y=dy, strength=1 if dx or dy else 0),
            c.current,
            1 / 60,
            movement_camera=a,
        )
        c.update(1 / 60, m.player.x, m.player.z, m.player.last_move_x, m.player.last_move_z)
        a = affine_camera_from_perspective(c.current, p, base_distance=480)
        q = a.project(Vec3(start[0] + 48, 0, start[1] + 40))
        # Same camera used by display/picking: round trip ground coordinates.
        back = screen_to_ground_affine(a, q.x, q.y)
        assert back.x == pytest.approx(start[0] + 48, abs=1e-9)
        assert back.y == pytest.approx(start[1] + 40, abs=1e-9)
        rows.append(
            (
                asdict(m.player),
                asdict(m.buddy),
                q.x,
                q.y,
                a.zoom,
                (c.current).target,
                m.water,
                m.energy,
            )
        )
    return rows, c


@pytest.mark.parametrize("start", [(520, 480), (160, 240)])
@pytest.mark.parametrize("mode", ["threshold", "finite"])
def test_stop_settles_and_keeps_world_state(start, mode):
    off, _ = trace("off", start)
    on, c = trace(mode, start)
    for a, b in zip(off, on, strict=False):
        for state in (0, 1):
            for key in a[state]:
                x, y = a[state][key], b[state][key]
                if isinstance(x, float):
                    assert x == pytest.approx(y, abs=1e-9)
                else:
                    assert x == y
        assert a[6:] == b[6:]
    assert on[-1][2:6] == on[-20][2:6]
    if mode == "finite":
        for axis in (2, 3):
            dif = [
                b[axis] - a[axis]
                for a, b in zip(on[60:100], on[61:101], strict=False)
                if abs(b[axis] - a[axis]) > 1e-8
            ]
            assert not dif or all(d * dif[0] > 0 for d in dif)


def test_reacceleration_reverse_keeps_logic():
    def pattern(f):
        if f < 60 or 92 <= f < 120 or 180 <= f < 215:
            return (1, 0)
        if 120 <= f < 150:
            return (-1, 0)
        return (0, 0)

    off, _ = trace("off", pattern=pattern)
    on, _ = trace("finite", pattern=pattern)
    for a, b in zip(off, on, strict=False):
        for state in (0, 1):
            for k, v in a[state].items():
                assert (
                    b[state][k] == pytest.approx(v, abs=1e-9)
                    if isinstance(v, float)
                    else b[state][k] == v
                )


def test_disabled_reset_and_camera_control_exit():
    _, c = trace("finite", frames=80)
    assert c.stop_settle is not None
    c.stop_settle_mode = "off"
    c.update(1 / 60, c.last_player_position.x, c.last_player_position.y, 1, 0)
    assert c.stop_settle is None
    c.stop_settle_mode = "finite"
    c.update(1 / 60, c.last_player_position.x, c.last_player_position.y, 1, 0)
    assert c.stop_settle is not None
    c.start_focus_point(Vec3(400, 0, 400))
    c.update(1 / 60, c.last_player_position.x, c.last_player_position.y, 1, 0)
    assert c.stop_settle is None
    c.reset(Vec3(520, 0, 480))
    assert c.stop_settle is None


@pytest.mark.parametrize(
    "degrees", [0, 44.9, 45, 45.1, 89.9, 90, 134.9, 135, 135.1, 180, 225, 270, 315]
)
def test_diagonal_boundary_restarts_keep_player_and_buddy(degrees):
    angle = math.radians(degrees)

    def pattern(f):
        return (math.cos(angle), math.sin(angle)) if f < 45 or 69 <= f < 110 else (0, 0)

    off, _ = trace("off", frames=150, pattern=pattern)
    on, _ = trace("finite", frames=150, pattern=pattern)
    for a, b in zip(off, on, strict=True):
        for state in (0, 1):
            for key, v in a[state].items():
                assert (
                    b[state][key] == pytest.approx(v, abs=1e-9)
                    if isinstance(v, float)
                    else b[state][key] == v
                )


def test_common_camera_pick_and_no_app_coordinate_path_changes():
    # The public controller camera itself is the settled view; no hidden legacy
    # input camera. Affine source and inverse use this exact snapshot.
    rows, c = trace("finite", start=(160, 240), frames=90)
    profile = AffineProjectionProfile.from_config(c.raw_config)
    a = affine_camera_from_perspective(c.current, profile, base_distance=480)
    for x, z in [(c.follow_target.x, c.follow_target.z), (160, 240), (200, 300)]:
        p = a.project(Vec3(x, 0, z))
        back = screen_to_ground_affine(a, p.x, p.y)
        assert (back.x, back.y) == pytest.approx((x, z), abs=1e-9)


@pytest.mark.parametrize(
    "x,z,frame", [(128, 232, 80), (192, 232, 90), (400, 296, 80), (816, 296, 80), (848, 296, 80)]
)
@pytest.mark.parametrize("mode", ["off", "finite"])
def test_five_regressions_display_and_actual_action_agree(x, z, frame, mode):
    raw = load_runtime_config().raw
    world = load_world_data()
    m = GameModel(raw, world)
    m.enemies.clear()
    profile = AffineProjectionProfile.from_config(raw)
    c = CameraController(raw, world, 512, 236, Vec3(x, 0, z - 70))
    c.stop_settle_mode = mode
    for f in range(frame + 1):
        c.update(1 / 60, x, z - 70 + 70 * min(1, (f + 1) / 60), 0, 1)
    m.player.x, m.player.z = x, z
    scene = affine_camera_from_perspective(c.current, profile, base_distance=480)
    visible = m.interaction_candidate(scene)
    assert visible is not None
    events = m.step(InputIntent(interact_pressed=True), c.current, 1 / 60, selection_camera=scene)
    assert m.interaction is not None
    assert m.interaction.object_id == visible.id
    assert any(e.target_id == visible.id and e.kind == "interaction_started" for e in events)


def test_hud_and_selection_share_display_camera_without_moving_buddy_axes():
    from test_field_visit import make_visit

    app = make_visit()
    app.projection_mode = "affine"
    raw = app.runtime.raw
    c = CameraController(raw, app.world, 512, 236, Vec3(128, 0, 162))
    c.stop_settle_mode = "finite"
    for f in range(81):
        c.update(1 / 60, 128, 162 + 70 * min(1, (f + 1) / 60), 0, 1)
    app.camera_controller = c
    app.model.enemies.clear()
    app.model.player.x, app.model.player.z = 128, 232
    app.scene_camera = lambda camera: affine_camera_from_perspective(
        camera, AffineProjectionProfile.from_config(raw), base_distance=480
    )
    assert app.interact_button_token() == "REFILL"
    assert app.selection_camera().target == app.camera().target
    assert app.model.interaction_candidate(app.selection_camera()).id == "tap_start"
    app.projection_mode = "perspective"
    assert app.selection_camera() is app.camera()
    app.projection_mode = "affine"
    app.model.combat_session = object()
    assert app.selection_camera() is app.camera()


@pytest.mark.parametrize("x,z", [(128, 241), (192, 79), (192, 241)])
def test_selection_preserves_world_interaction_range(x, z):
    raw = load_runtime_config().raw
    m = GameModel(raw, load_world_data())
    m.enemies.clear()
    m.player.x, m.player.z = x, z
    c = CameraController(raw, m.world, 512, 236, Vec3(x, 0, z))
    scene = affine_camera_from_perspective(
        c.current, AffineProjectionProfile.from_config(raw), base_distance=480
    )
    before = (m.player.x, m.player.z, m.water, m.energy)
    events = m.step(InputIntent(interact_pressed=True), c.current, 1 / 60, selection_camera=scene)
    assert m.interaction is None
    assert any(e.kind == "action_denied" and e.payload.get("reason") == "no_target" for e in events)
    assert (m.player.x, m.player.z, m.water, m.energy) == before


def test_camera_settle_does_not_enter_saved_payload():
    from drift_with_me.save_state import snapshot
    from test_save_state import payload

    app, before = payload()
    c = CameraController(app.runtime.raw, app.world, 512, 236, Vec3(128, 0, 162))
    app.camera_controller = c
    c.stop_settle_mode = "finite"
    for f in range(100):
        c.update(1 / 60, 128, 162 + 70 * min(1, (f + 1) / 60), 0, 1)
    assert c.stop_settle is not None
    assert snapshot(app) == before
