import math

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.focus_laser import DURATION
from drift_with_me.july_combat import (
    JULY_ENEMY_IDS,
    clear_july_enemies,
    configure_july_enemies,
    defeated_july_ids,
    freeze_zigzag,
    update_zigzag,
)
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.world import load_world_data


def make_model():
    runtime = load_runtime_config()
    model = GameModel(runtime.raw, load_world_data())
    camera = CameraState.from_config(
        runtime.raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    configure_july_enemies(model)
    return model, camera


def test_four_finite_and_reentry_preserves_defeats_and_june_restore():
    model, _ = make_model()
    june = model._pre_july_enemies
    assert [e.kind for e in model.enemies] == ["normal", "normal", "abnormal", "abnormal"]
    assert tuple(e.id for e in model.enemies) == JULY_ENEMY_IDS
    model.enemies[0].state = "DEFEATED"
    ids = defeated_july_ids(model)
    configure_july_enemies(model, ids)
    assert defeated_july_ids(model) == ids
    assert len(model.enemies) == 4
    clear_july_enemies(model)
    assert model.enemies is june


@pytest.mark.parametrize("index", range(4))
def test_capture_then_focus_reuses_action_without_electric_damage(index):
    model, camera = make_model()
    enemy = model.enemies[index]
    events = []
    model.capture_enemy(enemy, events)
    model.player.x, model.player.z = enemy.x + 5.0, enemy.z
    model.enemy_visible = lambda e, c: True
    energy = model.energy
    model.try_discharge(enemy, events, camera)
    assert enemy.state == "FOCUS"
    action = enemy.focus_action
    assert len(action.relays) == 6
    model.try_discharge(enemy, events, camera)
    assert enemy.focus_action is action
    assert model.energy == energy
    assert not any(e.kind == "discharge_succeeded" for e in events)
    model.update_enemies(DURATION + 0.1, events)
    assert enemy.state == "DEFEATED"
    assert enemy.id in defeated_july_ids(model)
    model.update_enemies(100.0, events)
    assert sum(e.kind == "enemy_defeated" for e in events) == 1


def test_bubble_accepts_normal_nudibranch_and_immune_without_capture():
    model, camera = make_model()
    enemy = model.enemies[0]
    model.enemies = [enemy]
    # Visibility is independently covered in existing bubble targeting tests.
    model.enemy_visible = lambda e, c: True
    model.has_line_of_sight = lambda *a: True
    model.player.x, model.player.z = enemy.x + 20.0, enemy.z
    assert model.bubble_target(camera) is enemy
    events = []
    model.try_discharge(enemy, events, camera)
    assert enemy.state != "DEFEATED"
    assert enemy.focus_action is None


def test_zigzag_no_retarget_and_recover():
    model, _ = make_model()
    enemy = model.enemies[2]
    enemy.x, enemy.z = 0.0, 0.0
    enemy.dash_x, enemy.dash_z = 1.0, 0.0
    freeze_zigzag(enemy)
    path = enemy.zigzag_path
    enemy.state = "DASH"
    model.move_enemy = lambda e, dx, dz: (
        setattr(e, "x", e.x + dx),
        setattr(e, "z", e.z + dz),
        math.hypot(dx, dz),
    )[-1]
    for _ in range(100):
        model.player.x, model.player.z = -500.0, 500.0
        update_zigzag(model, enemy, 0.02)
        if enemy.state == "RECOVER":
            break
    assert enemy.zigzag_path == path
    assert (enemy.x, enemy.z) == pytest.approx(path[-1])
    assert enemy.state == "RECOVER"


def test_combat_counter_focus_duration_and_completion():
    model, camera = make_model()
    enemy = model.enemies[0]
    model.config["combat_v1"]["enabled"] = True
    events = []
    model.start_contact_combat(enemy, events)
    session = model.combat_session
    model._july_combat_camera = camera
    session.phase = "PERFECT_BUBBLE_WINDOW"
    model.try_combat_counter_bubble(session, events)
    assert session.phase == "PERFECT_ZAP_WINDOW"
    model.energy = 0.0
    assert model.combat_zap_counter_available(session)
    model.try_combat_counter_zap(session, events)
    assert session.phase == "FOCUS_LASER"
    model.update_combat_session(InputIntent(action_pressed=True), camera, DURATION / 2, events)
    assert enemy.state == "FOCUS"
    model.update_combat_session(
        InputIntent(action_pressed=True), camera, DURATION / 2 + 0.1, events
    )
    assert enemy.state == "DEFEATED"
    assert session.phase == "VICTORY_CUE"
    assert not any(e.kind == "discharge_succeeded" for e in events)


def test_focus_not_cancelled_by_barrier_or_contact():
    model, camera = make_model()
    enemy = model.enemies[0]
    model.enemies = [enemy]
    model.player.x, model.player.z = enemy.x + 5.0, enemy.z
    model.enemy_visible = lambda e, c: True
    model.capture_enemy(enemy, [])
    model.try_discharge(enemy, [], camera)
    model.player.barrier_active = True
    model.resolve_barrier_contacts([])
    assert enemy.state == "FOCUS"
    model.player.barrier_active = False
    model.resolve_player_contacts([])
    assert model.combat_session is None


def test_combat_zigzag_snapshot_does_not_follow_moved_player():
    from drift_with_me.july_combat import combat_zigzag_position, prepare_combat_zigzag

    model, camera = make_model()
    enemy = model.enemies[2]
    model.start_contact_combat(enemy, [])
    session = model.combat_session
    prepare_combat_zigzag(model, enemy, session, camera)
    path = session.july_charge_path
    model.player.x += 500.0
    prepare_combat_zigzag(model, enemy, session, camera)
    assert session.july_charge_path == path
    assert combat_zigzag_position(session, 0.0) == path[0]
    assert combat_zigzag_position(session, 1.0) == pytest.approx(path[-1])


@pytest.mark.parametrize("width,height", [(256, 118), (512, 236), (768, 354)])
@pytest.mark.parametrize("index", [0, 2])
def test_sprite_frame_and_dissolve_draw_three_sizes(width, height, index):
    from types import SimpleNamespace

    from drift_with_me.focus_laser import BURN_BEGIN
    from drift_with_me.july_combat import draw_sprite, focus_draw_commands, start_focus
    from drift_with_me.nudibranch_preview import preview_assets

    class Image:
        def __init__(self, width, height):
            self.width, self.height = width, height

        def set(self, x, y, rows):
            self.rows = rows

        def pget(self, x, y):
            return int(self.rows[y][x], 16)

    blits, atmospheres = [], []
    pyxel = SimpleNamespace(Image=Image, blt=lambda *a, **k: blits.append((a, k)))
    renderer = SimpleNamespace(
        pyxel=pyxel,
        _nudibranch_preview_assets=preview_assets(pyxel),
        draw_atmospheric_scaled_sprite=lambda *a: atmospheres.append(a),
    )
    model, _ = make_model()
    enemy = model.enemies[index]
    runtime = load_runtime_config()
    camera = CameraState.from_config(runtime.raw, Vec3(enemy.x, 0.0, enemy.z), width, height)
    assert draw_sprite(renderer, model, enemy, camera, enemy.x, enemy.z, 0.0) is not None
    assert atmospheres[-1][2].frame_id.endswith("_00")
    start_focus(model, enemy, camera, [])
    enemy.focus_action.elapsed = BURN_BEGIN + 0.4
    assert draw_sprite(renderer, model, enemy, camera, enemy.x, enemy.z, 0.0) is not None
    assert blits[-1][1]["colkey"] == 8
    assert len(focus_draw_commands(renderer, model, camera)) == 7
