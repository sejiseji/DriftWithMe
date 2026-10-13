"""Both patrol orders, one-time scenes and interrupted July return journeys."""

from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.east_site import EastSiteProgress
from drift_with_me.july_week1 import (
    FUJI_ID,
    PROFESSOR_ID,
    STUDENT_ID,
    WATER_ID,
    JulyWeek1Office,
    install_july_world,
)
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek
from field_transition_helpers import finish_travel
from test_field_visit import make_visit
from test_week4 import read
from test_week_debug_safety import debug_app, records  # noqa: F401


def july_app():
    app = make_visit()
    app.work_week = app.map_work_week = WorkWeek(7, 1)
    app.office = JulyWeek1Office()
    app.east_site_progress = EastSiteProgress()
    app.first_sight_seen = set()
    app.week_office_history = {app.work_week: app.office}
    app.office.prepare_debug_field_task()
    install_july_world(app, combat=True)
    app.field_transition = None
    app.week_transition = None
    app.screen = AppScreen.PLAY
    app.camera_controller.reset = lambda point: None
    app.key_pressed = lambda *keys: False
    app.mouse_pressed_in = lambda rect: False
    app.travel_input_held = lambda: False
    app.checkpoint_progress = lambda: False
    return app


def confirm(app):
    app.july_wait_release = False
    app.key_pressed = lambda *keys: True
    app.update_july_story(0)
    app.key_pressed = lambda *keys: False


def arrival_and_talk(app):
    for enemy in app.model.enemies:
        enemy.state = "DEFEATED"
    assert app.update_july_story(0)
    assert app.office.july_progress.stage == "after_clear"
    confirm(app)
    confirm(app)
    assert app.office.july_progress.stage == "arrival_fade"
    app.update_july_story(0.5)
    assert app.world.object_by_id(PROFESSOR_ID) is not None
    assert app.world.object_by_id(STUDENT_ID) is not None
    assert app.model.player.x == 520
    for _ in range(8):
        confirm(app)
    assert app.office.july_progress.researchers_talked


@pytest.mark.parametrize("checks_first", [True, False])
def test_both_orders_finish_and_report_once(checks_first):
    app = july_app()
    if checks_first:
        read(app, FUJI_ID)
        read(app, WATER_ID)
    arrival_and_talk(app)
    if not checks_first:
        assert not app.update_july_story(0)
        assert app.screen == AppScreen.PLAY
        read(app, WATER_ID)
        read(app, FUJI_ID)
    assert app.office.july_progress.complete
    assert app.office.july_progress.souvenir_received
    app.update_july_story(0)
    assert app.field_transition is not None
    finish_travel(app)
    assert app.screen == AppScreen.OFFICE
    assert app.office.complete
    result = app.office.sessions[app.office.cases[0].case_id].field_result
    assert not app.office.complete_field_task(result)
    assert not app.begin_next_week()


def test_partial_return_reentry_no_respawn_or_duplicate_gift():
    app = july_app()
    app.model.enemies[0].state = "DEFEATED"
    read(app, FUJI_ID)
    assert app.complete_office_field_task()
    finish_travel(app)
    assert not app.office.complete
    _, offices, _, _, _, _ = decode(encode(snapshot(app)))
    app.office = offices[WorkWeek(7, 1)]
    app.week_office_history = offices
    assert app.office.july_progress.souvenir_received
    app.enter_exploration_from_office()
    finish_travel(app)
    assert len(app.model.enemies) == 4
    assert app.model.enemies[0].state == "DEFEATED"
    assert sum(e.state != "DEFEATED" for e in app.model.enemies) == 3
    read(app, FUJI_ID)
    assert not any(
        "持っていって" in text for _, text in app.office.july_progress.lines_for(FUJI_ID)
    )


def test_held_advance_and_reload_preserve_one_time_arrival():
    app = july_app()
    for enemy in app.model.enemies:
        enemy.state = "DEFEATED"
    app.travel_input_held = lambda: True
    app.key_pressed = lambda *keys: True
    for _ in range(20):
        app.update_july_story(0)
    assert app.office.july_progress.scene_index == 0
    app.travel_input_held = lambda: False
    confirm(app)
    confirm(app)
    app.update_july_story(0.5)
    confirm(app)
    p = app.office.july_progress
    assert p.researchers_arrived and p.scene_index == 1
    _, offices, *_ = decode(encode(snapshot(app)))
    app.office = offices[WorkWeek(7, 1)]
    install_july_world(app, combat=True)
    assert len([o for o in app.world.objects if o.id in (PROFESSOR_ID, STUDENT_ID)]) == 2
    assert app.office.july_progress.stage == "researchers"
    assert app.office.july_progress.scene_index == 1


def test_july_debug_uses_july_office_without_normal_save(records):  # noqa: F811
    before = deepcopy(records.items)
    app = debug_app(records)
    assert app.jump_to_debug_week(WorkWeek(7, 1))
    assert isinstance(app.office, JulyWeek1Office)
    assert not app.checkpoint_progress()
    app.return_from_week_debug()
    assert records.items == before
