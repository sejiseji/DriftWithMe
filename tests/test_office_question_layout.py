from types import SimpleNamespace

import pytest

from drift_with_me.app import DriftWithMeApp
from drift_with_me.config import load_runtime_config
from drift_with_me.office import OfficePrototype
from drift_with_me.week_cycle import WorkWeek, load_week_office
from test_office import finish_app_office_dialogue, make_office_dialogue_app


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_question_buttons_clear_frame_and_keep_full_labels(profile):
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config(profile)
    panel = app.office_questions_panel_rect()
    inner = 4 if profile == "high" else 3
    for office in (OfficePrototype.load(), load_week_office(WorkWeek(6, 2))):
        for case in office.cases:
            for i, question in enumerate(case.questions):
                rect = app.office_question_rect(i, len(case.questions))
                assert all(int(v) == v for v in (rect.x, rect.y, rect.width, rect.height))
                assert rect.x > int(panel.x) + inner
                assert rect.x + rect.width < int(panel.x) + int(panel.width) - inner
                assert rect.y + rect.height < int(panel.y) + int(panel.height) - inner
                assert rect.height >= 14  # Existing 12px font plus breathing room.
                label = f"{app.office_question_number(i)} 済 {question.button_label}"
                assert sum(6 if ord(c) < 128 else 12 for c in label) <= rect.width - 6
    assert int(panel.y) > int(app.office_dialog_rect().y) + int(app.office_dialog_rect().height)
    assert int(panel.y) + int(panel.height) < int(app.office_footer_rect().y)


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_last_question_accepts_visible_bottom_pixel_but_not_frame_margin(profile):
    app = make_office_dialogue_app()
    app.runtime = load_runtime_config(profile)
    app.office.current_index = 2
    app.office.begin_current_case()
    app.office_dialogue_playback = None
    finish_app_office_dialogue(app)
    app.clear_world_input_latches = lambda: None
    app.key_pressed = lambda *keys: False
    case = app.office.current_case
    for index, question in enumerate(case.questions):
        rect = app.office_question_rect(index, len(case.questions))
        app.pointer_snapshot = SimpleNamespace(
            pressed=True, x=rect.x + rect.width / 2, y=rect.y + rect.height - 0.5
        )
        app.update_office_screen(0)
        assert app.office.current_session.pending_question_id == question.question_id
        finish_app_office_dialogue(app)
        assert question.question_id in app.office.current_session.asked_question_ids
        assert app.office_visible_question_count() == min(index + 2, len(case.questions))
    last = app.office_question_rect(4, 5)
    panel = app.office_questions_panel_rect()
    for y in (last.y + last.height, int(panel.y) + int(panel.height) - 2):
        app.office_question_index = 0
        app.pointer_snapshot = SimpleNamespace(pressed=True, x=last.x + 2, y=y)
        app.update_office_screen(0)
        assert app.office_question_index == 0
        assert app.office.current_session.pending_question_id is None
