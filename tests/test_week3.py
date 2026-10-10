from copy import deepcopy
from itertools import combinations, permutations

import pytest

from drift_with_me.east_site import EastSiteProgress
from drift_with_me.events import GameEvent
from drift_with_me.office import CaseState, Classification, FieldResult
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week3 import FACTS, LABELS, LINES, SITE_FACTS
from drift_with_me.week_cycle import WorkWeek, load_week_office
from field_transition_helpers import finish_travel
from test_field_visit import drain, inspect, make_visit
from test_week2_loop import resolve


def app3():
    app = make_visit()
    app.office = load_week_office(WorkWeek(6, 3))
    app.work_week = app.map_work_week = WorkWeek(6, 3)
    app.week_office_history = {app.work_week: app.office}
    app.east_site_progress = EastSiteProgress({"bank_unsafe", "shade_no_seat", "hatch_present"})
    app.first_sight_seen = set()
    for _ in range(3):
        resolve(app.office)
        assert app.office.active_field_task is None
        app.office.advance_case()
    resolve(app.office)
    assert app.office.prepare_field_task()
    app.enter_exploration_from_office()
    finish_travel(app)
    return app


def read_site(app, target):
    inspect(app, target)
    while app.field_conversation:
        app.advance_field_conversation()


def restored(app):
    w, offices, sites, *_ = decode(encode(snapshot(app)))
    app.office = offices[w]
    app.week_office_history = offices
    app.east_site_progress = sites
    return app


def report(app):
    assert app.complete_office_field_task()
    assert not app.complete_office_field_task()
    finish_travel(app)
    while app.office.current_index in (4, 5):
        resolve(app.office)
        assert app.office.advance_case()


@pytest.mark.parametrize("order", list(permutations(SITE_FACTS)))
def test_free_order_only_full_read_records_then_both_reports_complete(order):
    app = app3()
    assert not app.office.site_progress.facts
    for target in order:
        inspect(app, target)
        assert app.field_conversation.lines == LINES[target]
        while app.field_conversation.index < len(LINES[target]) - 1:
            app.advance_field_conversation()
            assert SITE_FACTS[target] not in app.office.site_progress.facts
        app.advance_field_conversation()
        assert SITE_FACTS[target] in app.office.site_progress.facts
        restored(app)
    assert not app.office.complete and not app.office.site_progress.reported
    app.complete_office_field_task()
    finish_travel(app)
    assert app.office.current_index == 4
    resolve(app.office)
    assert not app.office.complete
    app.office.advance_case()
    assert app.office.site_progress.reported == {"hatch_matched"}
    restored(app)
    resolve(app.office)
    app.office.advance_case()
    assert app.office.complete and app.office.site_progress.reported == FACTS
    restored(app)
    assert app.office.complete and load_week_office(WorkWeek(6, 4)) is not None


SUBSETS = [set(c) for n in range(4) for c in combinations(SITE_FACTS, n)]


@pytest.mark.parametrize("targets", SUBSETS)
def test_every_partial_return_reports_only_known_then_redeploy(targets):
    app = app3()
    for target in targets:
        read_site(app, target)
    facts = set(app.office.site_progress.facts)
    lines = app.office.site_progress.travel_lines("back")
    if not facts:
        assert "まだ確認できていない" in lines[0][1]
    elif facts != FACTS:
        for t in SITE_FACTS:
            assert LABELS[t] in lines[0][1]
    app.complete_office_field_task()
    finish_travel(app)
    restored(app)
    if "hatch_matched" not in facts:
        assert app.office.current_index == 5
    while app.office.current_index in (4, 5):
        case = app.office.current_case
        if case.visitor.name == "サガン":
            text = case.questions[0].jack_text
            assert ("通りにくそう" in text) == ("route_bank" in facts)
            assert ("石が出てる" in text) == ("route_stone" in facts)
            if facts != FACTS:
                assert case.questions[0].visitor_reply == "了解。残りも、見られたら教えてくれ"
        resolve(app.office)
        app.office.advance_case()
        restored(app)
    if facts != FACTS:
        assert not app.office.complete and app.office.active_field_task
        assert app.office.current_session.state == CaseState.FIELD_ACTIVE
        app.activate_office_footer_action()
        finish_travel(app)
        for t in set(SITE_FACTS) - targets:
            read_site(app, t)
        report(app)
    assert app.office.complete and app.office.site_progress.reported == FACTS


@pytest.mark.parametrize("target", SITE_FACTS)
def test_cancel_resume_repeat_and_forged_inspection_do_not_add_facts(target):
    app = app3()
    inspect(app, target)
    app.advance_field_conversation()
    app.process_events(app.model.cancel_interaction())
    assert not app.office.site_progress.facts
    restored(app)
    inspect(app, target)
    assert app.field_conversation.index == 1
    while app.field_conversation:
        app.advance_field_conversation()
    before = deepcopy(app.office.site_progress.facts)
    inspect(app, target)
    assert len(app.field_conversation.lines) == 1
    app.advance_field_conversation()
    assert app.office.site_progress.facts == before
    app.process_events(
        [GameEvent(900, 0, "inspection_completed", "player", "jun_w2_shade", (0, 0, 0))]
    )
    assert app.office.site_progress.facts == before


def test_order_visitor_first_and_generic_portrait():
    office = load_week_office(WorkWeek(6, 3))
    assert [line.speaker for line in office.active_dialogue_lines()] == ["ヨアケ", "Jack"]
    assert office.active_dialogue_lines()[1].visual_action == "read_document"
    assert office.cases[1].visitor.portrait_id == "generic_visitor"
    assert not office.advance_case()
    for expected in ["ヨアケ", "来訪者", "ウラ", "サガン"]:
        assert office.current_case.visitor.name == expected and not office.prepare_field_task()
        resolve(office)
        if expected != "サガン":
            assert office.advance_case() and office.active_field_task is None
    assert office.prepare_field_task()


def test_cannot_forge_unread_sites_or_report_without_return():
    app = app3()
    task = app.office.active_field_task
    assert not app.office.complete_field_task(
        FieldResult(task.task_id, task.case_id, "WEEK3_CONFIRMED", tuple(FACTS), ())
    )
    office = load_week_office(WorkWeek(6, 3))
    office.current_index = 4
    office.begin_current_case()
    drain(office)
    office.ask_question("talk")
    drain(office)
    assert not office.classify(Classification.COUNTER_COMPLETE)


@pytest.mark.parametrize("index", range(6))
def test_save_each_office_stage(index):
    app = app3()
    if index < 4:
        app.office = load_week_office(WorkWeek(6, 3))
        for _ in range(index):
            resolve(app.office)
            app.office.advance_case()
    else:
        for t in SITE_FACTS:
            read_site(app, t)
        app.complete_office_field_task()
        finish_travel(app)
        if index == 5:
            resolve(app.office)
            app.office.advance_case()
    w, offices, *_ = decode(encode(snapshot(app)))
    assert offices[w].current_index == index
    assert offices[w].current_case.visitor.name == app.office.current_case.visitor.name


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_question_labels_and_yoake_reading(profile):
    from test_document_reading import make_app

    app, _ = make_app(profile)
    app.office = load_week_office(WorkWeek(6, 3))
    app.office_dialogue_playback = None
    pages = app.sync_office_dialogue_playback().pages
    assert any(app.office_document_reading_active(page) for page in pages)
    for case in app.office.cases:
        rect = app.office_question_rect(0, 1)
        assert len(case.questions[0].button_label) * 12 + 30 <= rect.width - 6


def test_invalid_save_confirmation_and_report_order():
    app = app3()
    p = snapshot(app)
    p["offices"]["6:3"]["site"]["reported"] = ["hatch_matched"]
    with pytest.raises(ValueError):
        decode(encode(p))
    p = snapshot(app)
    p["offices"]["6:3"]["site"]["positions"] = {"jun_w2_old_hatch": 3}
    with pytest.raises(ValueError):
        decode(encode(p))
    p = snapshot(app)
    p["offices"]["6:3"]["index"] = 4
    with pytest.raises(ValueError):
        decode(encode(p))


def test_week2_to_week3_once_and_week4_available():
    from test_week_cycle import completed_app

    app = completed_app()
    app.work_week = app.map_work_week = WorkWeek(6, 2)
    app.office = load_week_office(app.work_week)
    for session in app.office.sessions.values():
        session.state = CaseState.RESOLVED
    app.office.current_index = len(app.office.cases)
    previous = app.office
    app.week_office_history[app.work_week] = previous
    assert app.begin_next_week()
    assert not app.begin_next_week()
    app.update_week_transition(0.6)
    assert app.work_week == app.map_work_week == WorkWeek(6, 3)
    current = app.office
    app.update_week_transition(10)
    assert app.office is current and app.week_office_history[WorkWeek(6, 2)] is previous
    assert not app.office.site_progress.facts
    assert not app.begin_next_week()


def test_inspection_freezes_world_and_checkpoint_keeps_unread_position():
    from drift_with_me.model import InputIntent
    from drift_with_me.save_state import ProgressStore

    app = app3()
    app.progress_store = ProgressStore(enabled=False)
    app.session_started = True
    app.last_checkpoint = None
    app.week_transition = None
    app.first_sight_conversation = None
    inspect(app, "jun_w2_old_hatch")
    before = app.model.world_tick
    for _ in range(20):
        app.model.step(InputIntent(), app.camera(), 1 / 60)
    assert app.model.world_tick == before
    app.advance_field_conversation()
    assert app.checkpoint_progress() is False  # session-only store still retains validated bytes.
    w, offices, *_ = decode(app.progress_store.session)
    assert offices[w].site_progress.positions == {"jun_w2_old_hatch": 1}
    assert not offices[w].site_progress.facts


def test_save_at_report_after_read_but_before_acknowledgement_is_not_complete():
    app = app3()
    for target in SITE_FACTS:
        read_site(app, target)
    app.complete_office_field_task()
    finish_travel(app)
    drain(app.office)
    app.office.ask_question("talk")
    drain(app.office)
    assert not app.office.site_progress.reported
    restored(app)
    assert not app.office.complete and not app.office.site_progress.reported
    assert app.office.classify(Classification.COUNTER_COMPLETE)
    drain(app.office)
    app.office.advance_case()
    assert app.office.site_progress.reported == {"hatch_matched"}
