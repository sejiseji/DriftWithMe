from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.field_transition import travel_lines
from drift_with_me.field_visit import ANOMALY_ID, FieldProgress
from drift_with_me.office import CaseState
from field_transition_helpers import finish_travel
from test_field_visit import make_visit


@pytest.mark.parametrize("dt", (1 / 60, 1 / 30, 10))
def test_departure_is_black_once_then_both_lines_before_world_resumes(dt):
    app = make_visit()
    app.screen = AppScreen.OFFICE
    app.enter_exploration_from_office()
    original = app.field_transition
    app.enter_exploration_from_office()
    assert app.field_transition is original
    calls = []
    app.show_location_label = lambda: calls.append(app.field_transition.darkness)
    for _ in range(100):
        app.update_field_transition(dt)
        if original.phase == "dialogue":
            break
    assert app.screen == AppScreen.PLAY and calls == [1]
    assert original.index == 0
    original.wait_release = False
    app.update_field_transition(0)
    assert original.index == 1 and original.phase == "dialogue"
    app.update_field_transition(0)  # release frame cannot advance again
    assert original.index == 1
    finish_travel(app)
    assert calls == [1]


def test_unconfirmed_return_redeparture_and_cancel_preserve_facts_and_week():
    app = make_visit()
    progress = app.office.current_session.field_progress
    before = deepcopy(progress)
    assert app.complete_office_field_task()
    assert app.field_transition.report is None
    app.field_transition.wait_release = False
    app.key_pressed = lambda *names: "KEY_ESCAPE" in names
    app.update_field_transition(0)
    assert app.screen == AppScreen.PLAY and progress == before
    assert app.complete_office_field_task()
    finish_travel(app)
    assert app.screen == AppScreen.OFFICE
    assert app.office.current_session.state == CaseState.FIELD_ACTIVE
    assert app.office.current_session.field_result is None
    assert not app.office.advance_case()
    app.activate_office_footer_action()
    assert app.field_transition.lines == travel_lines("out", progress)
    finish_travel(app)
    assert progress == before


def test_return_report_waits_for_both_lines_and_black_and_commits_once():
    app = make_visit()
    session = app.office.current_session
    session.field_progress.observe("tap_stopped")
    assert app.complete_office_field_task()
    assert not app.complete_office_field_task()
    assert session.field_result is None
    t = app.field_transition
    t.wait_release = False
    app.update_field_transition(0)
    assert t.index == 1 and session.field_result is None
    finish_travel(app)
    result = session.field_result
    assert result.discovered_fact_ids == ("supply_stopped",)
    assert result.result_code == "OBSERVED"
    assert not app.complete_office_field_task()
    assert session.field_result is result


def test_whole_update_freezes_enemy_world_and_latched_input_until_release():
    app = make_visit()
    app.screen = AppScreen.OFFICE
    app.enter_exploration_from_office()
    app.frame = 0
    app.presentation_time = 0
    app.consume_elapsed = lambda: 1 / 30
    app.read_pointer_snapshot = lambda: SimpleNamespace(down=True)
    app.pyxel.btn = lambda _: True
    app.model.enemies[0].x = app.model.player.x
    app.model.enemies[0].z = app.model.player.z
    world = app.model.world_tick
    enemy = [(e.x, e.z, e.state) for e in app.model.enemies]
    for _ in range(100):
        app.update()
    assert app.field_transition.phase == "dialogue"
    assert app.field_transition.index == 0
    assert app.model.world_tick == world
    assert enemy == [(e.x, e.z, e.state) for e in app.model.enemies]
    assert app.frame == 100  # presentation advances while simulation is frozen
    assert app.model.combat_session is None
    assert not app.pending_action_pressed and not app.pending_interact_pressed


@pytest.mark.parametrize("kind", ("none", "partial", "all", "enemy", "interrupted", "dealt"))
def test_result_dialogue_does_not_turn_observation_into_success(kind):
    p = FieldProgress()
    if kind in {"partial", "all"}:
        p.observe("tap_stopped")
    if kind == "all":
        p.observe("maintenance_unit")
        p.observe("observation_post")
    if kind == "enemy":
        p.observe(ANOMALY_ID)
    if kind == "interrupted":
        p.interrupted = True
    if kind == "dealt":
        p.dealt_target_ids.add(ANOMALY_ID)
    before = deepcopy(p)
    text = "".join(line for _, line in travel_lines("back", p))
    assert len(travel_lines("back", p)) == 2 and p == before
    assert ("対処できた" in text) == (kind == "dealt")
    assert "勇者" not in text
    assert "危ない" in "".join(
        line for _, line in travel_lines("back", FieldProgress(), interrupted=True)
    )


def test_other_case_cannot_inherit_lamel_place_or_cause_dialogue():
    p = FieldProgress()
    p.dealt_target_ids.add(ANOMALY_ID)
    for direction in ("out", "back"):
        text = "".join(t for _, t in travel_lines(direction, p, case_id="future-case"))
        assert "北側" not in text and "音の原因" not in text and "個体" not in text


def test_pointer_cancel_keeps_observed_facts_and_uncommitted_report():
    app = make_visit()
    session = app.office.current_session
    session.field_progress.observe("tap_stopped")
    before = deepcopy(session.field_progress)
    assert app.complete_office_field_task()
    app.field_transition.wait_release = False
    app.key_pressed = lambda *names: False
    app.mouse_pressed_in = lambda rect: rect == app.field_travel_cancel_rect()
    app.update_field_transition(0)
    assert app.field_transition is None and app.screen == AppScreen.PLAY
    assert session.field_progress == before and session.field_result is None
    assert session.state == CaseState.FIELD_ACTIVE
