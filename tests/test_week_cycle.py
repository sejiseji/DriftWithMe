from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.app import AppScreen, DriftWithMeApp
from drift_with_me.office import CaseState, Classification, OfficePrototype
from drift_with_me.week_cycle import WeekTransition, WorkWeek, load_week_office


def drain(office):
    while office.has_pending_dialogue_step():
        office.advance_dialogue_step()
    office.complete_pending_question()


def completed_app():
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.office = OfficePrototype.load()
    # Completion gating is separately checked for every unresolved/field state.
    for session in app.office.sessions.values():
        session.state = CaseState.RESOLVED
    app.office.current_index = len(app.office.cases)
    app.work_week = WorkWeek()
    app.map_work_week = app.work_week
    app.week_office_history = {app.work_week: app.office}
    app.week_transition = None
    app.week_input_wait_for_release = False
    app.screen = AppScreen.OFFICE
    app.runtime = SimpleNamespace(raw={})
    app.pointer = SimpleNamespace(cancel=lambda: None)
    app.clear_world_input_latches = lambda: None
    app.end_office_consultation = lambda: None
    app.pointer_snapshot = SimpleNamespace(down=False)
    app.pyxel = SimpleNamespace(btn=lambda key: False, KEY_RETURN=1, KEY_Z=2, KEY_ESCAPE=3, KEY_X=4)
    return app


def test_twelve_workdays_and_month_end_without_invented_vacation():
    week = WorkWeek()
    weeks = []
    while week is not None:
        weeks.append(week)
        week = week.following()
    assert len(weeks) == 12
    assert weeks[3].following() == WorkWeek(7, 1)
    assert weeks[7].following() == WorkWeek(8, 1)
    assert weeks[-1].following() is None
    assert WorkWeek(6, 2).label == "6月 第2週"
    for args in [(5, 1), (9, 1), (6, 0), (6, 5)]:
        with pytest.raises(ValueError):
            WorkWeek(*args)
    assert load_week_office(WorkWeek(6, 3)) is None
    assert load_week_office(WorkWeek(8, 4)) is None


@pytest.mark.parametrize("dt", [1 / 30, 1 / 60, 1 / 120, 100])
def test_commit_is_once_and_only_at_full_black_even_with_large_elapsed(dt):
    transition = WeekTransition(WorkWeek(6, 2))
    events = []
    for _ in range(400):
        transition.advance(
            dt, lambda: events.append((transition.darkness, transition.showing_title))
        )
    assert transition.complete
    assert transition.darkness == 0
    assert events == [(1, True)]


def test_pause_resume_before_and_after_black_keeps_one_commit():
    t = WeekTransition(WorkWeek(6, 2))
    calls = []

    def apply():
        calls.append("applied")

    t.advance(0.3, apply)
    for _ in range(20):
        t.advance(0, apply)
    assert not calls
    t.advance(0.4, apply)
    for _ in range(20):
        t.advance(0, apply)
    assert calls == ["applied"]
    t.advance(9, apply)
    assert calls == ["applied"] and t.complete
    with pytest.raises(ValueError):
        t.advance(-1, apply)
    with pytest.raises(ValueError):
        WeekTransition(WorkWeek(6, 2), fade_out=0)


@pytest.mark.parametrize("state", [s for s in CaseState if s != CaseState.RESOLVED])
def test_unreported_or_unfinished_case_cannot_be_skipped(state):
    app = completed_app()
    app.office.sessions["OFF-PROT-003"].state = state
    assert not app.begin_next_week()
    assert app.work_week == WorkWeek()


def test_active_field_task_blocks_transition_even_if_case_index_is_complete():
    app = completed_app()
    app.office.active_field_task = object()
    assert not app.begin_next_week()


def test_week_office_map_binding_and_history_change_once_under_black():
    app = completed_app()
    previous = app.office
    before = deepcopy(previous.sessions)
    assert app.begin_next_week()
    for _ in range(20):
        assert not app.begin_next_week()
    app.update_week_transition(0.3)
    assert app.office is previous and app.work_week == WorkWeek()
    app.update_week_transition(0.3)
    current = app.office
    assert app.work_week == app.map_work_week == WorkWeek(6, 2)
    assert current.current_case.case_id == "OFF-JUN-W2-GROW"
    assert len(current.cases) == 4
    assert previous.sessions == before
    assert app.week_office_history[WorkWeek()] is previous
    app.update_week_transition(10)
    assert app.office is current and app.week_input_wait_for_release
    app.pointer_snapshot.down = True
    for _ in range(20):
        assert app.update_week_transition(0.1)
    assert app.week_input_wait_for_release
    app.pointer_snapshot.down = False
    assert app.update_week_transition(0.1)
    assert not app.week_input_wait_for_release
    assert not app.update_week_transition(0.1)
    assert not app.begin_next_week()
    assert previous.sessions == before


def test_return_visit_accepts_documents_without_repeating_hearing_or_granting_relief():
    office = load_week_office(WorkWeek(6, 2))
    assert office is not None
    assert [q.question_id for q in office.current_case.questions] == ["supplement"]
    drain(office)
    assert not office.classify(Classification.COUNTER_COMPLETE)
    assert office.ask_question("supplement")
    assert not office.advance_case()
    drain(office)
    assert office.classify(Classification.COUNTER_COMPLETE)
    drain(office)
    session = office.current_session
    assert session.state == CaseState.CLOSED_COUNTER
    assert any("担当へ渡します" in line.text for line in session.dialogue)
    assert office.advance_case() and office.current_case.case_id == "OFF-JUN-W2-RECEIPT"
    assert not office.advance_case()
    assert (
        OfficePrototype.load().cases[1].expected_classification == Classification.MISSING_DOCUMENTS
    )


def test_actual_update_blocks_held_confirm_and_reentry_until_release():
    app = completed_app()
    app.consume_elapsed = lambda: 0.25
    app.presentation_time = 0
    app.frame = 0
    app.read_pointer_snapshot = lambda: app.pointer_snapshot
    app.pyxel.btn = lambda key: True
    assert app.begin_next_week()
    for _ in range(24):
        app.update()
        assert not app.begin_next_week()
    assert app.work_week == WorkWeek(6, 2)
    assert app.week_transition is None and app.week_input_wait_for_release
    session = app.office.current_session
    assert not session.asked_question_ids
    assert session.selected_classification is None
    assert session.state == CaseState.HEARING
    app.pyxel.btn = lambda key: False
    app.update()
    assert not app.week_input_wait_for_release
