from __future__ import annotations

from copy import copy
from types import SimpleNamespace

import pytest

from drift_with_me.app import DriftWithMeApp, PointerSnapshot
from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import Vec3
from drift_with_me.model import InputIntent
from drift_with_me.render import Renderer
from test_swarm_field import enter, setup_field
from test_swarm_render import scene_setup
from test_week2_loop import hero_app


def test_main_capture_timing_and_wait_use_individual_configuration():
    m, _, f = setup_field()
    assert f.settings.entry == m.combat_duration_sec()
    assert f.settings.ready == m.combat_ready_total_sec()
    assert f.settings.sweep == m.combat_parry_sweep_sec()
    assert f.settings.radius == m.combat_parry_hit_radius_normalized(enemy_kind="normal")
    assert f.settings.finish_wait == m.combat_zap_window_sec()


def test_countdown_uses_the_exact_normal_game_cue_function():
    m, camera, f = setup_field()
    enter(m, camera, f)
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config()
    b = f.battle
    b.phase = "ready"
    for elapsed, expected in (
        (0, "READY!"),
        (m.combat_ready_ready_sec(), "3"),
        (m.combat_ready_ready_sec() + m.combat_ready_count_step_sec() * 1.1, "2"),
        (m.combat_ready_ready_sec() + m.combat_ready_count_step_sec() * 2.1, "1"),
    ):
        b.elapsed = elapsed
        session = f.presentation_session()
        assert app.combat_countdown_cue_text(session) == expected
        assert app.combat_countdown_cue_text(copy(session)) == expected
    b.phase, b.elapsed = "approach", 0
    assert app.combat_countdown_cue_text(f.presentation_session()) == "GO!"
    b.phase = "finish_wait"
    assert app.combat_countdown_cue_text(f.presentation_session()) is None


@pytest.mark.parametrize(
    "phase", ["entry", "ready", "approach", "bound", "finish_wait", "electric", "victory"]
)
def test_swarm_and_individual_share_zoom_function_and_limits(phase):
    m, camera, f = setup_field()
    enter(m, camera, f)
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime, app.model = load_runtime_config(), m
    app.combat_camera_snapshot_zoom = None
    f.battle.phase, f.battle.elapsed, f.battle.total_elapsed = phase, 0.2, 4
    normal = f.presentation_session()
    swarm = copy(normal)
    a = app.combat_camera_for_session(camera, normal, Vec3(m.player.x, 0, m.player.z))
    b = app.combat_camera_for_session(camera, swarm, Vec3(m.player.x, 0, m.player.z))
    assert a == b
    expected = app.clamp_combat_zoom(
        app.combat_snapshot_zoom(camera) * app.combat_camera_zoom_multiplier(normal),
        app.combat_snapshot_zoom(camera),
    )
    assert app.camera_zoom(a) == pytest.approx(expected)


def test_real_normal_button_hitbox_captures_but_background_tap_does_not():
    app = hero_app()
    app.swarm_field_enabled = True
    field = app.ensure_swarm_field()
    enter(app.model, app.camera(), field)
    app.key_pressed = lambda *_: False
    app.keyboard_intent = lambda: InputIntent()
    app.travel_input_held = lambda: False
    app.effects.update = lambda *_: None
    app.pointer_snapshot = PointerSnapshot(True, True, 0, 110)
    b = field.battle
    assert app.update_swarm_frame(0)
    assert b.phase == "approach" and b.failures == 0
    b.tick(max(0, b.settings.sweep * b.settings.target - b.elapsed))
    rect = app.action_button_rect()
    app.pointer_snapshot = PointerSnapshot(
        True, True, rect.x + rect.width / 2, rect.y + rect.height / 2
    )
    assert app.update_swarm_frame(0)
    assert b.phase == "bound" and app.model.water == 88
    app.pointer_snapshot = PointerSnapshot(True, False, rect.x + 1, rect.y + 1)
    for _ in range(10):
        app.update_swarm_frame(0.01)
    assert app.model.water == 88 and b.failures == 0


def test_all_capture_sprites_bubbles_and_shadows_share_knockback_height_and_depth():
    model, camera, field, renderer, scene = scene_setup()
    b = field.battle
    b.captured, b.capture_progress, b.capture_elapsed = True, 0.72, 0
    scene.prepare(1)
    before = [(e.x, e.z) for e in scene.enemies]
    b.capture_elapsed = 0.9
    scene.prepare(2)
    for index, enemy in enumerate(scene.enemies):
        old_x, old_z = before[index]
        old_distance = ((old_x - model.player.x) ** 2 + (old_z - model.player.z) ** 2) ** 0.5
        new_distance = ((enemy.x - model.player.x) ** 2 + (enemy.z - model.player.z) ** 2) ** 0.5
        assert new_distance > old_distance and enemy.capture_y > 0
        pose = Renderer.enemy_actor_presentation(SimpleNamespace(), scene.model_view, enemy, camera)
        assert pose.jump_y == enemy.capture_y
        visual = camera.project(Vec3(enemy.x, enemy.capture_y, enemy.z))
        ground = camera.project(Vec3(enemy.x, 0, enemy.z))
        assert visual.y < ground.y
        renderer.calls.clear()
        scene.draw_enemy_fx(renderer, enemy, index)
        bubble = next(args[0] for name, args in renderer.calls if name == "draw_combat_bubble_wrap")
        expected = camera.project(Vec3(enemy.x, 8 + enemy.capture_y, enemy.z))
        assert bubble == expected
    commands = scene.draw_commands(renderer, scene.model_view, camera)
    assert len([c for c in commands if c.stable_id.startswith("swarm-shadow:")]) == 6
    for index, enemy in enumerate(scene.enemies):
        fx = next(c for c in commands if c.stable_id == f"swarm-fx:{index}")
        assert fx.depth == camera.project(Vec3(enemy.x, enemy.capture_y, enemy.z)).depth
