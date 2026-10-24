from __future__ import annotations

from types import SimpleNamespace

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.model import InputIntent
from drift_with_me.save_state import ProgressStore, decode, encode, snapshot
from drift_with_me.swarm_battle import CENTER, RADII, STARTS
from drift_with_me.swarm_field import SITE_IDS, SwarmField, validate_progress
from test_combat_resources import make_model, normal_enemy, start_fast_combat
from test_week2_loop import hero_app


def setup_field():
    model, camera = make_model()
    model.swarm_field = field = SwarmField(model, "6:2", {})
    return model, camera, field


def step(m, camera, dt=1 / 60, pressed=False):
    return m.step(InputIntent(action_pressed=pressed), camera, dt)


def enter(m, camera, f, site="northwest"):
    m.player.x, m.player.z = f.config["sites"][site]
    events = step(m, camera)
    assert [e.kind for e in events] == ["swarm_started"]
    step(m, camera)  # Entry release; never counts as capture.
    while f.battle.phase in {"entry", "ready"}:
        step(m, camera)
    return f.battle


def hit(m, camera, f):
    b = f.battle
    step(m, camera, max(0, b.settings.target * b.settings.sweep - b.elapsed))
    step(m, camera, 0, True)


def until(m, camera, f, phase=None):
    events = []
    for _ in range(1200):
        if (phase and f.battle and f.battle.phase == phase) or (not phase and not f.battle):
            return events
        events.extend(step(m, camera))
    pytest.fail(f"stuck at {f.battle.phase if f.battle else None}")


def win(m, camera, f):
    hit(m, camera, f)
    until(m, camera, f, "finish_wait")
    return until(m, camera, f)


def test_encirclement_is_one_ellipse_with_outward_middle_and_shared_inward_motion():
    # Left/right middle actors are furthest from Jack, with upper/lower arcs.
    assert STARTS[1][0] < STARTS[0][0] == pytest.approx(STARTS[2][0])
    assert STARTS[4][0] > STARTS[3][0] == pytest.approx(STARTS[5][0])
    for x, y in STARTS:
        assert ((x - CENTER[0]) / RADII[0]) ** 2 + (
            (y - CENTER[1]) / RADII[1]
        ) ** 2 == pytest.approx(1)
    assert min(y for _, y in STARTS) < CENTER[1] < max(y for _, y in STARTS)


def test_all_test_sites_are_walkable_and_opposite_southwest_spawn():
    m, _, f = setup_field()
    assert (m.world.spawn_x, m.world.spawn_z) == (160, 160)
    for x, z in f.config["sites"].values():
        assert not m.world.collides_player(x, z, m.player_solid_half_x, m.player_solid_half_z)


def test_model_locks_movement_actions_buddy_enemies_and_world_tick_during_battle():
    m, camera, f = setup_field()
    enter(m, camera, f)
    positions = [(e.x, e.z, e.state) for e in m.enemies]
    actor = (m.player.x, m.player.z, m.buddy.x, m.buddy.z, m.world_tick)
    intent = InputIntent(
        screen_x=1,
        strength=1,
        barrier=True,
        interact_pressed=True,
        auto_move_goal_x=300,
        auto_move_goal_z=300,
    )
    for _ in range(30):
        m.step(intent, camera, 1 / 60)
    assert positions == [(e.x, e.z, e.state) for e in m.enemies]
    assert actor == (m.player.x, m.player.z, m.buddy.x, m.buddy.z, m.world_tick)
    assert not m.player.barrier_active and not m.auto_move_path and m.interaction is None
    assert not m.can_start_contact_combat(normal_enemy(m))
    assert (m.water, m.energy) == (100, 100)


def test_victory_returns_to_real_field_prevents_reentry_and_movement_resumes():
    m, camera, f = setup_field()
    enter(m, camera, f)
    events = win(m, camera, f)
    assert f.battle is None and f.cleared == {"northwest"}
    assert [e.kind for e in events] == ["swarm_site_cleared", "swarm_restored"]
    assert (m.player.x, m.player.z) == tuple(f.config["sites"]["northwest"])
    assert (m.water, m.energy) == (76, 80)
    step(m, camera, 4)
    assert f.battle is None
    before = (m.player.x, m.player.z)
    m.step(InputIntent(screen_x=1, strength=1), camera, 0.1)
    assert (m.player.x, m.player.z) != before


def test_real_retreat_spawn_no_refund_rematch_restores_assist():
    m, camera, f = setup_field()
    enter(m, camera, f)
    step(m, camera, 0, True)
    until(m, camera, f, "assist")
    until(m, camera, f, "approach")
    step(m, camera, 0, True)
    until(m, camera, f)
    assert (m.player.x, m.player.z) == (160, 160)
    assert (m.water, m.energy) == (100, 100) and not f.cleared
    step(m, camera, 3)
    b = enter(m, camera, f)
    assert b.assists == 1


@pytest.mark.parametrize(
    ("water", "energy", "remaining"),
    [(0, 100, (0, 100)), (12, 100, (0, 100)), (100, 0, (88, 0)), (12, 0, (0, 0))],
)
def test_resource_shortage_retreat_preserves_actual_model_resources(water, energy, remaining):
    m, camera, f = setup_field()
    m.water, m.energy = water, energy
    b = enter(m, camera, f)
    hit(m, camera, f)
    if water:
        until(m, camera, f, "retreat_line")
    assert b.phase == "retreat_line" and not b.defeated
    until(m, camera, f)
    assert (m.water, m.energy) == remaining and not f.cleared
    assert (m.player.x, m.player.z) == (160, 160)


def test_three_sites_complete_week_without_story_or_week_advance_retreat_keeps_clear():
    m, camera, f = setup_field()
    enter(m, camera, f)
    win(m, camera, f)
    step(m, camera, 3)
    enter(m, camera, f, "northeast")
    step(m, camera, 0, True)
    until(m, camera, f, "assist")
    until(m, camera, f, "approach")
    step(m, camera, 0, True)
    until(m, camera, f)
    assert f.cleared == {"northwest"}
    for site in ("northeast", "southeast"):
        step(m, camera, 3)
        enter(m, camera, f, site)
        events = win(m, camera, f)
    assert f.complete and f.cleared == SITE_IDS
    assert [e.kind for e in events] == [
        "swarm_site_cleared",
        "swarm_week_completed",
        "swarm_restored",
    ]
    assert f.week_key == "6:2" and (m.water, m.energy) == (28, 40)
    other = SwarmField(m, "6:3", f.progress)
    assert not other.cleared


def test_normal_contact_combat_remains_available_outside_swarm_sites():
    m, camera, f = setup_field()
    enemy = start_fast_combat(m, camera)
    assert m.combat_session is not None and f.battle is None
    assert not f.start("northwest", camera, [])
    assert enemy.id == m.combat_session.enemy_id


def test_existing_interaction_blocks_swarm_entry():
    m, camera, f = setup_field()
    m.interaction = SimpleNamespace()
    m.player.x, m.player.z = f.config["sites"]["northwest"]
    assert not f.start("northwest", camera, [])
    assert not f.battle


def test_optional_progress_roundtrip_old_save_compatibility_and_native_store(tmp_path):
    app = hero_app()
    app.week_office_history = {app.work_week: app.office}
    app.first_sight_seen = set()
    old = snapshot(app)
    assert "swarm" not in old
    assert not decode(encode(old))[2].swarm_progress
    app.east_site_progress.swarm_progress = {"6:2": ["northwest"]}
    app.model.water, app.model.energy = 64, 80
    data = snapshot(app)
    store = ProgressStore(path=tmp_path / "isolated-save.json")
    assert store.write(data)
    week, offices, sites, seen, resources, defeated = store.load()
    assert sites.swarm_progress == {"6:2": ["northwest"]}
    assert resources == {"water": 64, "energy": 80}
    restored = SwarmField(app.model, "6:2", sites.swarm_progress)
    assert restored.cleared == {"northwest"} and restored.battle is None
    # The new optional key changes neither the existing offices nor legacy fields.
    assert {k: v for k, v in data.items() if k not in {"swarm", "resources"}} == {
        k: v for k, v in old.items() if k != "resources"
    }
    assert week == app.work_week and offices.keys() == app.week_office_history.keys()


@pytest.mark.parametrize(
    "raw",
    [None, [], {"8:4": []}, {"6:2": ["bad"]}, {"6:2": ["northwest", "northwest"]}, {"6:2": [42]}],
)
def test_malformed_progress_is_rejected(raw):
    with pytest.raises(ValueError):
        validate_progress(raw)


def test_app_checkpoint_disallows_live_battle_and_saves_completed_site():
    app = hero_app()
    app.week_office_history = {app.work_week: app.office}
    app.first_sight_seen = set()
    app.week_transition = None
    app.session_started = True
    app.last_checkpoint = None
    writes = []
    app.progress_store = SimpleNamespace(write=lambda data: writes.append(data) or True)
    app.sync_july_progress = lambda: None
    app.model.swarm_field = f = SwarmField(app.model, "6:2", app.east_site_progress.swarm_progress)
    camera = app.camera()
    enter(app.model, camera, f)
    assert not app.checkpoint_progress() and not writes
    win(app.model, camera, f)
    assert app.checkpoint_progress() and writes[-1]["swarm"] == {"6:2": ["northwest"]}
    assert "battle" not in writes[-1]


def test_pause_route_freezes_live_swarm_and_cannot_open_water_study():
    app = hero_app()
    app.swarm_field_enabled = True
    app.model.swarm_field = f = SwarmField(app.model, "6:2", app.east_site_progress.swarm_progress)
    enter(app.model, app.camera(), f)
    elapsed = f.battle.elapsed
    app.key_pressed = lambda *keys: "KEY_ESCAPE" in keys
    assert app.update_swarm_frame(0.1)
    assert app.screen == AppScreen.PAUSE and f.battle.elapsed == elapsed


def test_app_field_click_capture_is_single_charge_and_held_input_cannot_leak_on_return():
    app = hero_app()
    app.swarm_field_enabled = True
    app.swarm_test_field_active = True
    app.model.swarm_field = f = SwarmField(app.model, "6:2", app.east_site_progress.swarm_progress)
    enter(app.model, app.camera(), f)
    app.key_pressed = lambda *_: False
    app.travel_input_held = lambda: False
    app.pointer_snapshot = SimpleNamespace(pressed=True, x=0, y=0)
    app.keyboard_intent = lambda: InputIntent()
    app.ui_button_intent = lambda: InputIntent(barrier=True)
    app.effects.update = lambda *_: None
    step(app.model, app.camera(), f.settings.target * f.settings.sweep - f.battle.elapsed)
    assert app.update_swarm_frame(1 / 60)
    assert f.battle.phase == "bound" and app.model.water == 88
    assert app.update_swarm_frame(1 / 60)
    assert app.model.water == 88
    # Simulate the real return input latch, after the active battle has ended.
    f.battle = None
    app.swarm_wait_release = True
    app.travel_input_held = lambda: True
    app.update_play_screen = lambda _: pytest.fail("held battle input leaked into field")
    assert app.update_swarm_frame(0.1) and app.swarm_wait_release
    app.travel_input_held = lambda: False
    assert app.update_swarm_frame(0.1) and not app.swarm_wait_release


def test_existing_pause_debug_resource_change_is_respected_without_automatic_refund():
    m, camera, f = setup_field()
    enter(m, camera, f)
    hit(m, camera, f)
    until(m, camera, f, "finish_wait")
    assert m.water == 88
    # Existing ZERO RES debug action deliberately changes the real resources.
    m.water = m.energy = 0
    step(m, camera, f.settings.finish_wait)
    assert f.battle.phase == "retreat_line" and not f.battle.defeated
    until(m, camera, f)
    assert (m.water, m.energy) == (0, 0)


def test_disabled_feature_does_not_bind_or_change_existing_app():
    app = hero_app()
    assert app.ensure_swarm_field() is None
    assert not app.update_swarm_frame(0.1)
    assert app.model.swarm_field is None
