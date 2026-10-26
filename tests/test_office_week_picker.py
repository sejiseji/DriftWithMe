"""Office entry uses synthetic storage; opening/closing preserves the live conversation."""

from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.save_state import SAVE_KEY, encode
from drift_with_me.week_cycle import WorkWeek
from drift_with_me.week_debug import IMPLEMENTED_DEBUG_WEEKS, TemporaryProgressStore
from test_save_state import Storage, payload
from test_week_debug_safety import debug_app


def app_and_storage():
    _, valid = payload()
    storage = Storage()
    storage.items = {SAVE_KEY: encode(valid), SAVE_KEY + ".backup": encode(valid)}
    app = debug_app(storage, enabled=False)
    app.work_week = WorkWeek(6, 2)
    app.session_started = True
    app.screen = AppScreen.OFFICE
    return app, storage


def tap(app, rect):
    app.mouse_pressed_in = lambda candidate: candidate == rect
    app.pointer_snapshot.down = True
    assert app.update_week_debug()
    # Holding the same touch may not dispatch the action again.
    model = app.model
    for _ in range(4):
        assert app.update_week_debug()
        assert app.model is model
    app.pointer_snapshot.down = False
    assert app.update_week_debug()


def test_open_close_preserves_normal_store_conversation_and_progress():
    app, storage = app_and_storage()
    before = deepcopy(storage.items)
    office, model, store, saved = app.office, app.model, app.progress_store, app.saved_progress
    conversation = object()
    app.week2_dialogue = conversation
    for _ in range(3):
        tap(app, app.office_calendar_rect())
        assert app.week_debug_menu_open and not app.week_debug_active
        assert set(app.week_debug_rects()) == {
            "month6",
            "month7",
            "month8",
            "week1",
            "week2",
            "week3",
            "week4",
            "start",
            "cancel",
        }
        tap(app, app.week_debug_rects()["month7"])
        tap(app, app.week_debug_rects()["week4"])
        tap(app, app.week_debug_rects()["cancel"])
        assert not app.week_debug_menu_open
        assert app.office is office and app.model is model
        assert app.week2_dialogue is conversation
        assert app.progress_store is store and app.saved_progress is saved
        assert storage.items == before


@pytest.mark.parametrize("week", sorted(IMPLEMENTED_DEBUG_WEEKS, key=lambda w: (w.month, w.number)))
def test_calendar_jumps_and_rejumps_only_in_temporary_session(week):
    app, storage = app_and_storage()
    before = deepcopy(storage.items)
    for target in (week, WorkWeek(6, 1), week):
        tap(app, app.office_calendar_rect())
        tap(app, app.week_debug_rects()[f"month{target.month}"])
        tap(app, app.week_debug_rects()[f"week{target.number}"])
        tap(app, app.week_debug_rects()["start"])
        assert app.work_week == target
        assert isinstance(app.progress_store, TemporaryProgressStore)
        assert not app.checkpoint_progress()
        assert not app.week_debug_menu_open
        assert app.office.current_case is not None
        assert storage.items == before
    app.return_from_week_debug()
    assert app.saved_progress is not None
    assert storage.items == before


def test_picker_draw_and_update_take_priority_over_story_overlays():
    app, _ = app_and_storage()
    tap(app, app.office_calendar_rect())
    calls = []
    app.draw_week_debug_menu = lambda: calls.append("picker")
    app.draw_august_overlay = lambda: pytest.fail("story overlay covered picker")
    app.draw_active_scene()
    assert calls == ["picker"]
    app.lifecycle_update_blocked = lambda: False
    app.consume_elapsed = lambda: 0.1
    app.presentation_time = 0
    app.frame = 0
    app.read_pointer_snapshot = lambda: app.pointer_snapshot
    app.sync_august_sighting_lock = lambda: pytest.fail("story advanced while picker open")
    app.mouse_pressed_in = lambda _: False
    for _ in range(12):
        app.update()
    assert app.week_debug_menu_open
