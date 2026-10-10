"""Synthetic storage only: week testing never modifies either ordinary slot."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.save_state import SAVE_KEY, ProgressStore, encode
from drift_with_me.week_cycle import WorkWeek
from drift_with_me.week_debug import TemporaryProgressStore
from test_field_visit import make_visit
from test_save_state import Storage, payload


def debug_app(storage, enabled=True):
    app = make_visit()
    app.progress_store = ProgressStore(browser_storage=storage)
    app.saved_progress = app.progress_store.load()
    app.session_started = False
    app.last_checkpoint = None
    app.week_transition = None
    app._processed_hitstop_event_ids = set()
    app.pointer_snapshot = SimpleNamespace(down=False)
    app.initialize_week_debug(enabled)
    return app


@pytest.fixture
def records():
    _, valid = payload()
    storage = Storage()
    storage.items = {
        SAVE_KEY: encode(valid),
        SAVE_KEY + ".backup": encode(valid),
        "other": "untouched",
    }
    return storage


def test_temporary_store_never_serializes_or_authorizes_persistent_state():
    store = TemporaryProgressStore()
    store.authorize_new_game()
    assert not store.write(object())  # An unserializable object is harmless too.
    assert store.load() is None
    assert not store.enabled and not store.has_record


@pytest.mark.parametrize("record_kind", ["valid", "corrupt", "absent"])
def test_start_jump_cancel_return_reload_keeps_normal_and_backup(records, record_kind):
    if record_kind == "corrupt":
        records.items[SAVE_KEY] = "broken normal record"
    elif record_kind == "absent":
        records.items.pop(SAVE_KEY)
    before = deepcopy(records.items)
    for _ in range(2):  # A fresh instance represents a reload, not resumed test progress.
        app = debug_app(records)
        assert app.saved_progress is None
        assert isinstance(app.progress_store, TemporaryProgressStore)
        for number in (1, 4, 2, 3, 4, 1):
            assert app.jump_to_debug_week(WorkWeek(6, number))
            assert app.work_week == WorkWeek(6, number)
            assert app.office.current_case is not None
            assert not app.checkpoint_progress()
            app.week_debug_menu_open = True
            cancel = app.week_debug_rects()["cancel"]
            app.mouse_pressed_in = lambda rect, target=cancel: rect == target
            app.week_debug_wait_release = False
            assert app.update_week_debug()
            assert not app.week_debug_menu_open
            assert records.items == before
        app.return_from_week_debug()
        assert app.screen == AppScreen.START and not app.session_started
        assert app.progress_store is app.normal_progress_store
        assert not app.checkpoint_progress()
        assert records.items == before


def test_checkpoint_second_guard_protects_even_if_real_store_is_attached(records):
    before = deepcopy(records.items)
    app = debug_app(records)
    app.jump_to_debug_week(WorkWeek(6, 4))
    app.progress_store = app.normal_progress_store  # Fault injection: bypass first guard.
    app.progress_store.write = lambda _: pytest.fail("normal write reached")
    assert not app.checkpoint_progress()
    assert records.items == before


def test_held_pointer_cannot_retrigger_start_or_return(records):
    app = debug_app(records)
    before = deepcopy(records.items)
    app.pointer_snapshot.down = True
    start = app.week_debug_rects()["start"]
    app.mouse_pressed_in = lambda rect: rect == start
    assert app.update_week_debug()
    first_model = app.model
    for _ in range(12):
        assert app.update_week_debug()
        assert app.model is first_model
    assert records.items == before
    app.pointer_snapshot.down = False
    app.update_week_debug()
    app.week_debug_menu_open = True
    normal = app.week_debug_rects()["normal"]
    app.mouse_pressed_in = lambda rect: rect == normal
    assert app.update_week_debug()
    app.pointer_snapshot.down = True
    for _ in range(12):
        assert app.update_week_debug()
        assert not app.session_started
        assert not app.checkpoint_progress()
    assert records.items == before


@pytest.mark.parametrize("month", [7, 8])
def test_unimplemented_month_cannot_jump_or_write(records, month):
    app = debug_app(records)
    before = deepcopy(records.items)
    model = app.model
    assert not app.jump_to_debug_week(WorkWeek(month, 1))
    app.week_debug_month = month
    start = app.week_debug_rects()["start"]
    app.mouse_pressed_in = lambda rect: rect == start
    assert app.update_week_debug()
    assert app.model is model
    assert records.items == before


def test_normal_launch_keeps_normal_store_and_resume(records):
    app = debug_app(records, enabled=False)
    assert not app.week_debug_active and not app.week_debug_menu_open
    assert app.progress_store is app.normal_progress_store
    assert app.saved_progress is not None
    assert not app.jump_to_debug_week(WorkWeek(6, 2))


@pytest.mark.parametrize("number", [3, 4])
def test_return_discards_debug_world_flags_enemies_and_field_residue(records, number):
    from drift_with_me.week4 import TARGET_IDS

    app = debug_app(records)
    before = deepcopy(records.items)
    app.jump_to_debug_week(WorkWeek(6, number))
    debug_model = app.model
    app.world.east_site_access_ready = True
    app.model.enemies[0].state = "DEFEATED"
    app.field_transition = app.week_transition = app.field_conversation = object()
    app.pending_week_office = object()
    app.first_sight_conversation = object()
    app.week_input_wait_for_release = app.field_input_wait_for_release = True
    app.return_from_week_debug()
    assert app.model is not debug_model
    assert not app.world.east_site_access_ready
    assert not any(obj.id in TARGET_IDS for obj in app.world.objects)
    assert all(enemy.state != "DEFEATED" for enemy in app.model.enemies)
    assert app.field_transition is app.week_transition is app.field_conversation is None
    assert app.pending_week_office is None
    assert app.first_sight_conversation is None
    assert not app.week_input_wait_for_release and not app.field_input_wait_for_release
    assert not app.session_started and app.screen == AppScreen.START
    assert records.items == before
    app.start_game()  # Resume the synthetic normal W2 record only after explicit entry.
    assert app.work_week == WorkWeek(6, 2)
    assert not app.world.east_site_access_ready
    assert records.items == before
