from itertools import permutations

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.east_site import SITE_FACTS, SITE_LINES, EastSiteProgress
from drift_with_me.events import GameEvent
from drift_with_me.office import CaseState, Classification, FieldResult
from drift_with_me.week_cycle import WorkWeek, load_week_office
from field_transition_helpers import finish_travel
from test_field_visit import drain, inspect, make_visit


def resolve(office):
    drain(office)
    for q in office.current_case.questions:
        assert office.ask_question(q.question_id)
        drain(office)
    assert office.classify(office.current_case.expected_classification)
    drain(office)


def hero_app():
    app = make_visit()
    app.office = load_week_office(WorkWeek(6, 2))
    app.work_week = WorkWeek(6, 2)
    app.east_site_progress = EastSiteProgress()
    for expected in ("OFF-JUN-W2-GROW", "OFF-JUN-W2-RECEIPT"):
        assert app.office.current_case.case_id == expected
        resolve(app.office)
        assert app.office.advance_case()
    assert app.office.current_case.case_id == "OFF-JUN-W2-HERO"
    resolve(app.office)
    assert app.office.prepare_field_task()
    app.enter_exploration_from_office()
    finish_travel(app)
    return app


@pytest.mark.parametrize("order", list(permutations(SITE_FACTS)))
def test_week2_free_order_partial_return_and_construction_report(order):
    app = hero_app()
    assert app.screen == AppScreen.PLAY
    for i, target in enumerate(order):
        inspect(app, target)
        assert app.field_conversation.lines == SITE_LINES[target]
        app.advance_field_conversation()
        if i == 0:
            app.process_events(app.model.cancel_interaction())
            assert not app.east_site_progress.facts
            assert app.complete_office_field_task()
            finish_travel(app)
            assert app.office.current_session.state == CaseState.FIELD_ACTIVE
            assert app.office.current_session.field_result is None
            assert not app.office.advance_case()
            app.activate_office_footer_action()
            finish_travel(app)
            inspect(app, target)
            assert app.field_conversation.index == 1
        app.advance_field_conversation()
    assert app.east_site_progress.facts == set(SITE_FACTS.values())
    assert not app.office.current_session.field_progress.can_report
    assert app.complete_office_field_task()
    assert not app.complete_office_field_task()
    finish_travel(app)
    assert app.office.current_session.field_result.result_code == "EAST_SITE_CONFIRMED"
    drain(app.office)
    assert app.office.advance_case()
    assert app.office.current_case.case_id == "OFF-JUN-W2-CONSTRUCTION"
    resolve(app.office)
    assert app.office.advance_case() and app.office.complete
    assert not app.office.advance_case()
    assert app.work_week == WorkWeek(6, 2)
    assert load_week_office(WorkWeek(6, 3)) is None
    assert not app.world.east_site_access_ready
    assert "図面" in "".join(
        line.text for line in app.office.sessions["OFF-JUN-W2-CONSTRUCTION"].dialogue
    )


def test_lamel_observations_cannot_complete_hero_and_return_cannot_forge_missing_sites():
    app = hero_app()
    s = app.office.current_session
    app.process_events(
        [GameEvent(100, 0, "inspection_completed", "player", "tap_stopped", (0, 0, 0))]
    )
    assert not s.field_progress.can_report
    app.east_site_progress.facts.add("bank_unsafe")
    assert app.complete_office_field_task()
    finish_travel(app)
    assert s.field_result is None
    t = app.office.active_field_task
    assert not app.office.complete_field_task(
        FieldResult(t.task_id, t.case_id, "EAST_SITE_CONFIRMED", ("bank_unsafe",), ())
    )


def test_report_cannot_accept_without_confirmed_hero_result():
    office = load_week_office(WorkWeek(6, 2))
    office.current_index = 3
    office.begin_current_case()
    drain(office)
    assert office.ask_question("report")
    drain(office)
    assert not office.classify(Classification.COUNTER_COMPLETE)
