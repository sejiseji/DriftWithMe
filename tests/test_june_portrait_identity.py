"""June portrait identity and legacy synthetic-save regressions."""

from copy import deepcopy

import pytest

from drift_with_me.app import OFFICE_STATIC_PORTRAIT_IDS
from drift_with_me.east_site import EastSiteProgress
from drift_with_me.office import DialogueLine
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek, load_week_office
from test_field_visit import drain, make_visit
from test_week2_loop import resolve


def june_app(number):
    app = make_visit()
    app.work_week = app.map_work_week = WorkWeek(6, number)
    app.office = load_week_office(app.work_week)
    app.week_office_history = {app.work_week: app.office}
    app.east_site_progress = EastSiteProgress()
    app.first_sight_seen = set()
    return app


def test_new_portraits_keep_case_visitor_and_question_identifiers():
    app = june_app(3)
    resolve(app.office)
    assert app.office.advance_case()
    case = app.office.current_case
    assert case.case_id == "OFF-JUN-W3-HALL"
    assert case.visitor.visitor_id == "hall"
    assert case.visitor.name == "メリル"
    assert case.visitor.portrait_id == "merrill_matte"
    assert [q.question_id for q in case.questions] == ["talk"]
    app = june_app(4)
    case = app.office.current_case
    assert case.case_id == "OFF-JUN-W4-CLEANER"
    assert case.visitor.visitor_id == "cleaner"
    assert case.visitor.name == "ミズノ"
    assert case.visitor.portrait_id == "mizuno_matte"
    assert [q.question_id for q in case.questions] == ["talk"]
    assert {"merrill_matte", "mizuno_matte"} <= OFFICE_STATIC_PORTRAIT_IDS


def test_merrill_identity_survives_existing_week3_progress_format():
    app = june_app(3)
    resolve(app.office)
    app.office.advance_case()
    before = snapshot(app)
    week, offices, *_ = decode(encode(before))
    restored = offices[week]
    assert restored.current_case.case_id == "OFF-JUN-W3-HALL"
    assert restored.current_case.visitor.name == "メリル"
    assert restored.current_case.visitor.portrait_id == "merrill_matte"
    assert restored.sessions.keys() == app.office.sessions.keys()


@pytest.mark.parametrize("point", ["opening", "ura_reply", "cleaner_reply"])
def test_legacy_cleaner_speaker_save_loads_without_losing_cursor(point):
    app = june_app(4)
    if point != "opening":
        drain(app.office)
        assert app.office.ask_question("talk")
        if point == "cleaner_reply":
            drain(app.office)
    current = snapshot(app)
    old = deepcopy(current)
    counter = old["offices"]["6:4"]["counter"]
    for line in counter["lines"]:
        if line[0] == "ミズノ":
            line[0] = "清掃業者"
    week, offices, *_ = decode(encode(old))
    restored = offices[week].current_session
    assert restored.active_dialogue_line_count == counter["count"]
    assert [step.step_id for step in restored.pending_dialogue_steps] == counter["pending"]
    assert restored.completed_dialogue_turn_ids == set(counter["completed"])
    assert restored.pending_question_id == counter["question"]
    expected = [
        ["ミズノ" if line[0] == "清掃業者" else line[0], *line[1:]] for line in counter["lines"]
    ]
    assert [[line.speaker, line.text, line.visual_action] for line in restored.dialogue] == expected


def test_week4_ura_mizuno_and_siblings_switch_only_current_speaker_portrait():
    app = june_app(4)
    session = app.office.current_session
    for speaker, expected in [
        ("ミズノ", "mizuno_matte"),
        ("ウラ", "ura_matte"),
        ("ミズノ", "mizuno_matte"),
    ]:
        session.dialogue.append(DialogueLine(speaker, "確認"))
        assert app.office_current_visitor_identity(app.office.current_case) == (expected, speaker)
        session.dialogue.append(DialogueLine("ジャック", "承知しました"))
        assert app.office_current_visitor_identity(app.office.current_case) == (expected, speaker)
    resolve(app.office)
    assert app.office.advance_case()
    assert app.office.current_case.case_id == "OFF-JUN-W4-SIBLINGS"
    session = app.office.current_session
    for speaker, expected in [
        ("ルビィ", "ruby_matte"),
        ("モリス", "morris_matte"),
        ("ルビィ", "ruby_matte"),
    ]:
        session.dialogue.append(DialogueLine(speaker, "確認"))
        assert app.office_current_visitor_identity(app.office.current_case) == (expected, speaker)


@pytest.mark.parametrize("mutation", ["text", "action", "foreign_case"])
def test_legacy_alias_does_not_accept_unknown_dialogue(mutation):
    app = june_app(4)
    if mutation == "foreign_case":
        resolve(app.office)
        app.office.advance_case()
    old = snapshot(app)
    line = old["offices"]["6:4"]["counter"]["lines"][0]
    line[0] = "清掃業者"
    if mutation == "text":
        line[1] = "保存に存在しない台詞"
    elif mutation == "action":
        line[2] = "unexpected_action"
    with pytest.raises(ValueError, match="unknown counter dialogue"):
        decode(encode(old))


def test_actual_legacy_cleaner_texts_and_speaker_restore_to_current_identity():
    app = june_app(4)
    drain(app.office)
    assert app.office.ask_question("talk")
    current = snapshot(app)
    legacy = deepcopy(current)
    old_texts = {
        "おはようございます。清掃のミズノです。エアコンの作業予定を確認したくて": (
            "おはようございます。エアコン清掃の件で伺いました。作業の予定を確認したくて"
        ),
        "ウラさん、清掃のミズノさんがお見えです。作業予定を確認したいとのことです": (
            "ウラさん、エアコン清掃の方がお見えです。作業予定を確認したいとのことです"
        ),
    }
    counter = legacy["offices"]["6:4"]["counter"]
    replaced = set()
    for line in counter["lines"]:
        if line[0] == "ミズノ":
            line[0] = "清掃業者"
        if line[1] in old_texts:
            replaced.add(line[1])
            line[1] = old_texts[line[1]]
    assert replaced == set(old_texts)  # Both real pre-integration utterances exist.
    week, offices, *_ = decode(encode(legacy))
    session = offices[week].current_session
    assert [[line.speaker, line.text, line.visual_action] for line in session.dialogue] == current[
        "offices"
    ]["6:4"]["counter"]["lines"]
    assert session.active_dialogue_line_count == counter["count"]
    assert session.pending_question_id == "talk"
    assert [step.step_id for step in session.pending_dialogue_steps] == counter["pending"]
    assert session.completed_dialogue_turn_ids == set(counter["completed"])
    app.office = offices[week]
    assert app.office_current_visitor_identity(app.office.current_case) == ("ura_matte", "ウラ")
