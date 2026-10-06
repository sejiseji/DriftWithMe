from copy import deepcopy
from itertools import permutations

import pytest

from drift_with_me import config
from drift_with_me.app import DriftWithMeApp
from drift_with_me.office import OfficePrototype


class Font:
    @staticmethod
    def text_width(text, style):
        return sum(6 if ord(c) < 128 else 12 for c in text)

    @staticmethod
    def visual_vertical_metrics(style):
        return 0, 12


def finish(office):
    while office.has_pending_dialogue_step():
        office.advance_dialogue_step()
    office.complete_pending_question()


def app_for(office, profile="medium"):
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = config.load_runtime_config(profile)
    app.office = office
    app.ui_text = Font()
    app.office_focus = "classifications"
    app.office_question_index = 1
    app.office_classification_index = 2
    app.office_answer_case_id = office.current_case.case_id
    app.office_answer_question_id = None
    app.presentation_time = 7.38
    p = app.sync_office_dialogue_playback()
    p.page_index = len(p.pages) - 1
    p.revealed_chars = 9999
    return app


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_every_question_order_advice_and_consultation_restore(profile):
    data = config.load_data_json("office_supervisor_advice.json")
    for idx, case in enumerate(OfficePrototype.load().cases):
        for order in permutations(case.questions):
            office = OfficePrototype.load()
            office.current_index = idx
            office.begin_current_case()
            finish(office)
            for question in (*order, None):
                app = app_for(office, profile)
                session = deepcopy(office.current_session)
                saved = deepcopy(app.current_office_dialogue_playback())
                focus = (
                    app.office_focus,
                    app.office_question_index,
                    app.office_classification_index,
                    app.office_answer_question_id,
                )
                rows = data["cases"][case.case_id]
                expected = next(
                    (
                        text
                        for qid, text in rows["checks"]
                        if qid not in office.current_session.asked_question_ids
                    ),
                    rows["ready"],
                )
                assert office.supervisor_advice() == expected
                assert app.begin_office_consultation()
                assert not app.begin_office_consultation()
                p = app.sync_office_dialogue_playback()
                content = app.office_dialogue_content_rect()
                assert (
                    "".join(line.text for page in p.pages for line in page) == "上司: " + expected
                )
                assert all(line.speaker == "上司" for page in p.pages for line in page)
                assert all(len(page) <= 5 for page in p.pages)
                assert all(
                    app.ui_text.text_width(line.text, "office_japanese")
                    <= int(content.width) - line.indent_px
                    for page in p.pages
                    for line in page
                )
                app.update_office_dialogue_playback(60)
                while app.office_consultation is not None:
                    assert app.advance_office_dialogue_page()
                assert app.sync_office_dialogue_playback() == saved
                assert office.current_session == session
                assert (
                    app.office_focus,
                    app.office_question_index,
                    app.office_classification_index,
                    app.office_answer_question_id,
                ) == focus
                assert app.begin_office_consultation()
                app.end_office_consultation()
                app.end_office_consultation()
                assert app.sync_office_dialogue_playback() == saved
                if question is not None:
                    assert office.ask_question(question.question_id)
                    assert not app.begin_office_consultation()
                    finish(office)


@pytest.mark.parametrize(
    "profile,size", [("low", (95, 120)), ("medium", (116, 149)), ("high", (145, 186))]
)
def test_supervisor_rect_and_button_do_not_overlap_ui(profile, size):
    office = OfficePrototype.load()
    office.begin_current_case()
    finish(office)
    app = app_for(office, profile)
    image = app.office_supervisor_portrait_rect()
    assert (image.width, image.height) == size
    panel = app.office_visitor_rect()
    assert (
        image.x >= int(panel.x) + 4
        and image.y
        >= round(panel.y + 2 + max(0, (app.office_rect(0, 0, 0, 20).height - 12) / 2)) + 14
    )
    assert image.x + image.width < int(panel.x) + int(panel.width)
    assert image.y + image.height < int(panel.y) + int(panel.height)
    button = app.office_consultation_button_rect()
    debug = app.office_field_debug_rect()
    assert button.x + button.width < debug.x
    assert app.ui_text.text_width("上司に相談", "office_japanese") <= int(button.width) - 4
    assert button.y + button.height < app.office_dialog_rect().y


def test_consultation_blocks_all_other_input_and_escape_restores():
    office = OfficePrototype.load()
    office.begin_current_case()
    finish(office)
    app = app_for(office)
    assert app.begin_office_consultation()
    before = deepcopy(office.current_session)
    app.clear_world_input_latches = lambda: None
    app.mouse_pressed_in = lambda rect: rect == app.office_field_debug_rect()
    app.key_pressed = lambda *keys: False
    app.update_office_screen(1)
    assert office.current_session == before
    app.key_pressed = lambda *keys: "KEY_ESCAPE" in keys
    app.update_office_screen(1)
    assert app.office_consultation is None and office.current_session == before


def test_pending_answer_is_not_known_to_advice_and_consult_has_no_world_effects():
    office = OfficePrototype.load()
    office.begin_current_case()
    finish(office)
    assert office.ask_question("identity")
    assert (
        office.supervisor_advice()
        == config.load_data_json("office_supervisor_advice.json")["cases"]["OFF-PROT-001"][
            "checks"
        ][0][1]
    )


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_supervisor_scaled_blt_uses_source_center_and_stays_inside(profile):
    from types import SimpleNamespace

    office = OfficePrototype.load()
    office.begin_current_case()
    finish(office)
    app = app_for(office, profile)
    calls = []
    frame = SimpleNamespace(width=116, height=149, image=object(), u=0, v=0)
    asset = SimpleNamespace(frame=lambda: frame, definition=SimpleNamespace(colkey=8))
    app.sprite_assets = SimpleNamespace(
        get=lambda name: asset if name == "office_supervisor" else None
    )
    app.pyxel = SimpleNamespace(
        rect=lambda *a: None, rectb=lambda *a: None, blt=lambda *a, **kw: calls.append((a, kw))
    )
    rect = app.office_supervisor_portrait_rect()
    app.draw_office_portrait(rect, "office_supervisor")
    assert len(calls) == 1
    args, kwargs = calls[0]
    scale = kwargs["scale"]
    assert kwargs["colkey"] == 8
    left = args[0] + 116 * (1 - scale) / 2
    top = args[1] + 149 * (1 - scale) / 2
    assert abs(left - (rect.x + (rect.width - 116 * scale) / 2)) <= 0.5 + 1e-9
    assert abs(top - (rect.y + (rect.height - 149 * scale) / 2)) <= 0.5 + 1e-9
    assert left >= rect.x - 0.5 - 1e-9 and top >= rect.y - 0.5 - 1e-9
    assert left + 116 * scale <= rect.x + rect.width + 0.5 + 1e-9
    assert top + 149 * scale <= rect.y + rect.height + 0.5 + 1e-9


def test_advice_after_action_and_field_uses_no_unobserved_facts():
    from drift_with_me.office import FieldResult

    data = config.load_data_json("office_supervisor_advice.json")
    for idx, case in enumerate(OfficePrototype.load().cases):
        office = OfficePrototype.load()
        office.current_index = idx
        office.begin_current_case()
        finish(office)
        for q in case.questions:
            assert office.ask_question(q.question_id)
            finish(office)
        assert office.classify(case.expected_classification)
        finish(office)
        assert office.supervisor_advice() == data["after_action"]
        if case.field_task:
            task = office.prepare_field_task()
            assert task
            assert office.complete_field_task(
                FieldResult(task.task_id, task.case_id, "REVIEW", (), ("確認済み",))
            )
            assert office.supervisor_advice() == data["after_field"]
