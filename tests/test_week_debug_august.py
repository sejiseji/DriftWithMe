"""Debug entry, real save gates and return/transition paths; synthetic production slots only."""

import json
from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.august import REPORTS, SITES
from drift_with_me.august_patrol import BY_ID
from drift_with_me.flowerbed import FLOWER_IDS, FlowerbedLayoutStore
from drift_with_me.save_state import ProgressStore, decode, snapshot
from drift_with_me.week_cycle import WorkWeek
from drift_with_me.week_debug import TemporaryProgressStore
from test_august_wave1 import dispatch
from test_august_wave2 import sight
from test_office_week_picker import app_and_storage, tap


def jump(app, week):
    tap(app, app.office_calendar_rect())
    tap(app, app.week_debug_rects()[f"month{week.month}"])
    tap(app, app.week_debug_rects()[f"week{week.number}"])
    tap(app, app.week_debug_rects()["start"])


@pytest.mark.parametrize("number", range(1, 5))
def test_august_entry_save_gate_return_report_next_and_rejump_preserve_normal_slots(number):
    app, storage = app_and_storage()
    before = deepcopy(storage.items)
    jump(app, WorkWeek(8, number))
    assert app.office.august_progress.phase == "counter"
    assert not app.office.august_progress.sites
    assert app.screen == AppScreen.OFFICE
    office = app.office
    tap(app, app.office_calendar_rect())
    tap(app, app.week_debug_rects()["cancel"])
    assert app.office is office and app.office.august_progress.phase == "counter"
    # Save acknowledgements are backed by validated, detached in-memory records.
    assert app.progress_store.write(snapshot(app))
    with pytest.raises(ValueError, match="completed previous week"):
        decode(app.progress_store.session)  # Ordinary save validation remains strict.
    restored = app.progress_store.load()
    assert restored[0] == WorkWeek(8, number)
    assert restored[1][restored[0]] is not app.office
    dispatch(app)
    if number == 1:
        for site in sorted(SITES):
            sight(app, site)  # Actual proximity claim and sighting dialogue save gates.
    elif number in (2, 3):
        for site in sorted(SITES):
            assert app.record_august_site(site, "swarm")
    else:
        assert not app.model.enemies
        assert all(app.world.object_by_id(ident) is not None for ident in BY_ID)
    assert app.return_august()
    app.field_transition = None
    app.screen = AppScreen.OFFICE
    if number == 4:
        assert app.office.august_progress.phase == "office"
        app.key_pressed = lambda *keys: "KEY_F" in keys
        app.mouse_pressed_in = lambda _: False
        assert app.update_patrol(0)
    for _ in REPORTS[number]:
        assert app.advance_august_report()
    assert app.office.august_progress.phase == "done"
    if number < 4:
        assert app.begin_next_week()
        app.update_week_transition(0.56)
        app.update_week_transition(4)
        app.week_input_wait_for_release = False
        assert app.work_week == WorkWeek(8, number + 1)
        assert app.office.august_progress.phase == "counter"
    else:
        assert not app.can_begin_next_week()  # Existing ending boundary is unchanged.
    assert storage.items == before
    jump(app, WorkWeek(6, 1))
    jump(app, WorkWeek(8, number))
    assert app.office.august_progress.phase == "counter"
    assert app.progress_store.load() is None
    assert getattr(app, "patrol_dialogue", None) is None
    temp = app.progress_store
    app.return_from_week_debug()
    assert app.progress_store is app.normal_progress_store
    assert app.saved_progress is not None and temp.load() is None
    assert storage.items == before


def test_temporary_store_validates_copies_and_discards_without_serializing_external_objects():
    app, _ = app_and_storage()
    jump(app, WorkWeek(8, 1))
    store = TemporaryProgressStore(entry_week=WorkWeek(8, 1))
    data = snapshot(app)
    assert store.write(data)
    data["resources"]["water"] = -1
    assert not store.write(data)
    assert not store.write(object())
    assert store.load()[4]["water"] >= 0
    restored = store.load()
    restored[4]["water"] = -1
    assert store.load()[4]["water"] >= 0
    store.authorize_new_game()
    assert store.load() is None and not store.has_record


def test_debug_flowerbed_memory_survives_rejump_but_not_session_and_restores_original_store():
    app, storage = app_and_storage()
    original = FlowerbedLayoutStore(ProgressStore(browser_storage=storage))
    app.flowerbed_layout_store = original
    storage.items[original.key] = json.dumps({"version": 1, "order": list(reversed(FLOWER_IDS))})
    before = deepcopy(storage.items)
    jump(app, WorkWeek(7, 2))
    assert app.flowerbed_layout_store is not original
    assert app.east_site_progress.flowerbed_order == ()
    app.office.prepare_debug_field_task()
    app.screen = AppScreen.PLAY
    assert app.start_flowerbed_editor()
    for ident in FLOWER_IDS:
        app.flowerbed_editor.choose(ident)
    assert app.confirm_flowerbed()
    assert app.flowerbed_layout_store.load() == FLOWER_IDS
    assert original.load() == tuple(reversed(FLOWER_IDS))
    assert storage.items == before
    app.jump_to_debug_week(WorkWeek(8, 4))
    assert app.jump_to_debug_week(WorkWeek(7, 2))
    assert app.east_site_progress.flowerbed_order == FLOWER_IDS
    app.return_from_week_debug()
    assert app.flowerbed_layout_store is original
    assert original.load() == tuple(reversed(FLOWER_IDS))
    app.start_game()
    app.week_debug_wait_release = False
    jump(app, WorkWeek(7, 2))
    assert app.east_site_progress.flowerbed_order == ()
    assert storage.items == before
