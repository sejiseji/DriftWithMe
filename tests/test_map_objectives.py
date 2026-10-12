from dataclasses import replace

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.map_objectives import map_goals
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week4 import FLOWER_IDS
from test_office_jack_portrait import OfficeFont
from test_ui_layout import overlaps
from test_week4 import app4


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_button_and_panel_clear_existing_controls_and_dialogue(profile):
    app = app4()
    app.runtime = load_runtime_config(profile)
    button = app.map_objective_button_rect()
    panel = app.map_objective_panel_rect()
    for rect in (
        app.field_return_button_rect(),
        app.pause_button_rect(),
        app.sound_button_rect(),
        app.action_button_rect(),
        app.interact_button_rect(),
    ):
        assert not overlaps(button, rect)
        assert not overlaps(panel, rect)
    assert button.width >= 59 and button.height >= 26


def test_drawer_preserves_selection_without_mutating_progress_or_save():
    app = app4()
    saved = snapshot(app)

    def click(rect):
        app.mouse_pressed_in = lambda target: target == rect
        assert app.update_map_objectives()
        assert snapshot(app) == saved

    assert not getattr(app, "map_objective_open", False)
    click(app.map_objective_button_rect())
    assert app.map_objective_open
    click(app.map_objective_mode_rect(1))
    click(app.map_objective_button_rect())
    assert not app.map_objective_open and app.map_objective_mode == 1
    app.mouse_pressed_in = lambda target: target == app.map_objective_panel_rect()
    assert not app.update_map_objectives()  # No transparent panel hit area while folded.
    click(app.map_objective_button_rect())
    assert app.map_objective_open and app.map_objective_mode == 1
    app.model.combat_session = object()
    assert not app.update_map_objectives()
    app.model.combat_session = None
    app.first_sight_conversation = object()
    assert not app.update_map_objectives()
    app.first_sight_conversation = None
    app.field_conversation = object()
    # The actual map dialogue always has an inspection interaction.
    from test_field_visit import inspect

    inspect(app, "jun_w4_fuji")
    assert not app.update_map_objectives()


def test_progress_comes_from_instructed_collected_and_delivered_separately():
    app = app4()
    major, rows = map_goals(app)
    assert not major.done and [row.done for row in rows] == [False, False, False]
    p = app.office.plant_progress
    p.instructed = True
    p.carried = set(FLOWER_IDS)
    major, rows = map_goals(app)
    assert not major.done and [row.done for row in rows] == [True, True, False]
    p.delivered, p.carried = p.carried, set()
    major, rows = map_goals(app)
    assert major.done and all(row.done for row in rows)
    _, offices, *_ = decode(encode(snapshot(app)))
    app.office = offices[app.work_week]
    assert map_goals(app)[0].done
    app.office.active_field_task = None
    assert map_goals(app) == (None, ())


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_long_objective_pages_preserve_all_text_and_reset_on_task_change(profile):
    app = app4()
    app.runtime = load_runtime_config(profile)
    app.ui_text = OfficeFont()
    original = app.office.active_field_task
    app.office.active_field_task = replace(original, objective="確認する。" * 40)
    pages, done = app.map_objective_pages()
    assert len(pages) > 1 and not done
    assert "".join(line for page in pages for line in page) == "未 " + "確認する。" * 40
    rect = app.map_objective_content_rect()
    assert all(len(page) * 12 <= rect.height for page in pages)
    assert all(
        OfficeFont.text_width(line, "office_japanese") <= int(rect.width)
        for page in pages
        for line in page
    )
    app.map_objective_page = 1
    app.office.active_field_task = replace(original, task_id="other")
    app.map_objective_pages()
    assert app.map_objective_page == 0


def test_folded_and_modal_render_never_leaves_a_blank_panel_or_forces_open():
    app = app4()
    frames = []
    app.draw_office_button = lambda *a: None
    app.draw_panel_frame = lambda *a, **k: frames.append(True)
    app.draw_map_objectives()
    assert not frames
    app.office.plant_progress.instructed = True
    app.draw_map_objectives()
    assert not frames and not getattr(app, "map_objective_open", False)
    app.map_objective_open = True
    app.model.combat_session = object()
    app.draw_map_objectives()
    assert not frames and app.map_objective_open


def test_new_task_folds_without_losing_selected_size():
    app = app4()
    app.sync_map_objective_context()
    app.map_objective_open = True
    app.map_objective_mode = 1
    app.office.active_field_task = replace(app.office.active_field_task, task_id="next-task")
    app.sync_map_objective_context()
    assert not app.map_objective_open and app.map_objective_mode == 1
