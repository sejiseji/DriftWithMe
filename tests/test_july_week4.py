from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.july_week3 import REPORT as W3_REPORT
from drift_with_me.july_week4 import FOLLOW, PARK, REPORT, SENIOR, TASK, JulyWeek4Office
from drift_with_me.office import Classification
from drift_with_me.save_state import ProgressStore, decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek, load_week_office
from test_july_week3 import recovered_app, start_report


def app4():
    app, storage = recovered_app()
    start_report(app)
    for _ in W3_REPORT:
        assert app.advance_week3_dialogue()
    old = app.office
    app.work_week = app.map_work_week = WorkWeek(7, 4)
    app.office = JulyWeek4Office()
    app.office.begin_current_case()
    app.week_office_history = {WorkWeek(7, 3): old, WorkWeek(7, 4): app.office}
    app.week4_dialogue = None
    app.week4_wait_release = False
    app.screen = AppScreen.OFFICE
    return app, storage


def drain(office):
    while office.has_pending_dialogue_step():
        office.advance_dialogue_step()


def close_case(app):
    office = app.office
    drain(office)
    for q in office.current_case.questions:
        assert office.ask_question(q.question_id)
        drain(office)
        office.complete_pending_question()
    assert office.classify(office.current_case.expected_classification)
    drain(office)


def field_app():
    app, storage = app4()
    for _ in range(2):
        close_case(app)
        assert app.advance_week4_case()
    close_case(app)
    app.office.prepare_field_task()
    app.office.week4_progress.phase = "field"
    app.screen = AppScreen.PLAY
    return app, storage


def test_handoff_is_atomic_once_and_old_inventory_and_reward_history_survive():
    app, _ = app4()
    assert load_week_office(WorkWeek(7, 4)) is not None
    assert load_week_office(WorkWeek(8, 1)) is not None
    assert not app.advance_week4_case()
    close_case(app)
    assert app.advance_week4_case()
    old = app.week_office_history[WorkWeek(7, 3)].week3_progress
    assert not old.professor_handoff_pending and old.professor_handoff_completed
    assert old.rewards.sunglasses_received and old.parent_recovered
    assert app.office.current_case.case_id == SENIOR and app.office.week4_progress.handoff_received
    assert not app.advance_week4_case()
    week, offices, *_ = decode(encode(snapshot(app)))
    assert week == WorkWeek(7, 4) and offices[week].week4_progress.handoff_received


def test_handoff_save_failure_rolls_back_both_offices():
    app, storage = app4()
    close_case(app)
    before = encode(snapshot(app))
    storage.fail = True
    assert not app.advance_week4_case()
    assert encode(snapshot(app)) == before
    storage.fail = False
    app.progress_store = ProgressStore(browser_storage=storage)
    assert app.advance_week4_case()


@pytest.mark.parametrize("read_follow", [False, True])
def test_senior_requires_plan_and_concern_and_follow_is_optional_and_persisted(read_follow):
    from test_office import make_office_dialogue_app

    app, _ = app4()
    app.ui_text = make_office_dialogue_app().ui_text
    close_case(app)
    app.advance_week4_case()
    drain(app.office)
    assert not app.office.classify(Classification.COUNTER_COMPLETE)
    close_case(app)
    app.update_office_dialogue_playback(60)
    assert app.week4_follow_available()
    if read_follow:
        assert app.begin_office_consultation()
        for i in range(len(FOLLOW)):
            assert app.office.week4_progress.follow_index == i
            app.office = decode(encode(snapshot(app)))[1][WorkWeek(7, 4)]
            app.office_consultation = None
            # Start-game initialization must retain a saved follow-up.
            app.end_office_consultation()
            assert app.office.week4_progress.follow_index == i
            from drift_with_me.app import OfficeDialoguePlayback

            app.office_dialogue_playback = OfficeDialoguePlayback()
            app.update_july_week4(0)
            assert app.office_consultation.page_index == i
            app.update_office_dialogue_playback(60)
            assert app.advance_office_dialogue_page()
        assert app.office_consultation is None
        assert not app.office_dialogue_requires_advance()
    assert app.advance_week4_case()
    assert app.office.current_case.case_id == TASK
    assert not app.week4_follow_available()


def test_small_field_task_can_return_unfinished_and_dialogue_resume_and_complete_once():
    app, _ = field_app()
    before_resources = (app.model.water, app.model.energy)
    order = deepcopy(app.east_site_progress.flowerbed_order)
    assert app.return_week4()
    assert app.office.week4_progress.phase == "office"
    assert not app.office.complete
    assert app.cancel_week4_return()
    app.field_transition = None
    for target in (PARK, "fuji"):
        assert app.begin_week4_target(target)
        assert (
            decode(encode(snapshot(app)))[1][WorkWeek(7, 4)].week4_progress.dialogue_target
            == target
        )
        while app.week4_dialogue:
            app.advance_week4_dialogue()
    assert app.office.week4_progress.ready
    assert (app.model.water, app.model.energy) == before_resources
    assert app.east_site_progress.flowerbed_order == order
    assert app.return_week4()
    app.field_transition = None
    app.screen = AppScreen.OFFICE
    for i in range(len(REPORT)):
        app.week4_dialogue = None
        app.office = decode(encode(snapshot(app)))[1][WorkWeek(7, 4)]
        app.update_july_week4(0)
        assert app.week4_dialogue.index == i
        app.advance_week4_dialogue()
    assert app.office.complete and app.can_begin_next_week()
    assert not app.return_week4()
    assert decode(encode(snapshot(app)))[1][WorkWeek(7, 4)].week4_progress.phase == "done"


def test_iwama_identity_and_no_unapproved_promises_or_mechanical_conclusions():
    office = JulyWeek4Office()
    elder = office.cases[1]
    assert elder.visitor.portrait_id == "iwama_bust_normal"
    assert elder.visitor.name == "イワマ"
    assert elder.visitor.kind == "来庁"
    assert len(elder.questions) == 2
    assert all(q.memo_updates == () for q in elder.questions)
