"""Freeze AI and contact entry through the entire sighting dialogue, then resume safely."""

from copy import deepcopy

from drift_with_me.app import AppScreen
from drift_with_me.model import InputIntent
from drift_with_me.save_state import decode, encode, snapshot
from test_august_wave1 import august_app, dispatch


def scene():
    app, _ = august_app()
    dispatch(app)
    app.model.player.x, app.model.player.z = 200, 800
    enemy = app.model.enemies[0]
    enemy.x, enemy.z = 200, 800
    enemy.state = "DASH"
    enemy.state_timer = 0.01
    enemy.dash_x, enemy.dash_z = 1, 0
    return app, enemy


def test_entry_hook_claims_before_ai_dash_or_contact_and_freezes_model_calls():
    app, enemy = scene()
    before = deepcopy(app.model.enemies)
    resources = (app.model.water, app.model.energy)
    events = app.model.step(
        InputIntent(),
        app.camera(),
        1 / 60,
        before_enemy_update=lambda: app.update_august_sightings(0),
    )
    assert app.model.sighting_locked and app.model.world_paused
    assert app.model.enemies == before
    assert not any(e.kind == "combat_started" for e in events)
    tick = app.model.world_tick
    for _ in range(100):
        app.model.step(InputIntent(action_pressed=True), app.camera(), 0.1)
        app.model.update_enemies(0.1, events)
        app.model.resolve_player_contacts(events)
        app.model.start_contact_combat(enemy, events)
    assert app.model.enemies == before and app.model.world_tick == tick
    assert app.model.combat_session is None and not app.model.can_start_contact_combat(enemy)
    assert (app.model.water, app.model.energy) == resources


def test_dialogue_and_restored_pending_state_remain_locked_until_final_line():
    app, enemy = scene()
    assert app.update_august_sightings(0)
    for _ in range(14):
        app.update_august_sightings(0.1)
    app.office = decode(encode(snapshot(app)))[1][app.work_week]
    app.august_crossing = None
    app.model.sighting_locked = False
    assert app.sync_august_sighting_lock()
    before = deepcopy(app.model.enemies)
    assert app.advance_august_sighting()
    assert app.model.sighting_locked and app.model.enemies == before
    assert app.advance_august_sighting()
    assert not app.model.sighting_locked
    assert enemy.state == "IDLE" and enemy.dash_x == enemy.dash_z == 0
    events = []
    app.model.start_contact_combat(enemy, events)
    assert app.model.combat_session is None and not events
    assert app.model.sighting_resume_remaining > 0
    app.model.update_combat_reentry_cooldowns(app.model.sighting_resume_remaining + 0.01)
    assert app.model.can_start_contact_combat(enemy)
    assert not app.update_august_sightings(0.1)
    assert app.office.august_progress.sites == ["northwest"]


def test_pause_cancel_scene_and_new_scene_cannot_leave_a_permanent_lock():
    app, enemy = scene()
    assert app.update_august_sightings(0)
    app.screen = AppScreen.PAUSE
    assert app.sync_august_sighting_lock()
    app.screen = AppScreen.START
    assert not app.sync_august_sighting_lock()
    app.model.set_sighting_lock(True)
    app.model.reset_scene()
    assert not app.model.sighting_locked and app.model.sighting_resume_remaining == 0


def test_failed_sighting_save_never_locks_or_cancels_an_enemy():
    app, enemy = scene()
    app.progress_store.write = lambda *_: False
    before = deepcopy(app.model.enemies)
    assert app.update_august_sightings(0)
    assert not app.model.sighting_locked
    assert app.model.enemies == before
