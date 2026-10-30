"""Week wiring and persistence. The driver is handler-level, not a UI speedrun."""

from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.collectibles import owned_collectibles
from drift_with_me.flowerbed import FLOWER_IDS
from drift_with_me.flowerbed_visit import FlowerbedVisit
from drift_with_me.save_state import SAVE_KEY, ProgressStore, decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek
from twelve_week_driver import new_game, next_week, play_week, run_all, walk_to


def through_june4():
    app, storage, garden = new_game()
    for n in range(1, 5):
        play_week(app)
        app.checkpoint_progress()
        if n < 4:
            next_week(app)
    return app, storage, garden


@pytest.mark.parametrize("reload_each_boundary", [False, True])
def test_twelve_week_handler_path_without_debug_or_forced_completion(reload_each_boundary):
    app, storage, garden, records = run_all(reload_each_boundary)
    assert len(records) == 12 and all(r["complete"] for r in records)
    assert [r["collectibles"] for r in records] == list(range(1, 13))
    assert [r["history"] for r in records] == list(range(1, 13))
    assert not app.week_debug_active and not app.week_debug_menu_open
    assert app.screen == AppScreen.COLLECTION_ROOM
    assert len(owned_collectibles(app)) == 12
    assert app.east_site_progress.flowerbed_order == tuple(FLOWER_IDS)
    assert app.flowerbed_visit_state().complete
    assert decode(storage.items[SAVE_KEY])[0] == WorkWeek(8, 4)
    assert garden.items == {}


def test_june_boundary_preserves_inventory_resources_history_and_separate_garden():
    app, storage, garden = through_june4()
    assert app.flowerbed_layout_store.write_state(
        tuple(reversed(FLOWER_IDS)), FlowerbedVisit("complete")
    )
    garden_before = deepcopy(garden.items)
    owned = set(owned_collectibles(app))
    resources = app.model.water, app.model.energy
    history = deepcopy(snapshot(app)["offices"])
    assert app.can_begin_next_week()
    next_week(app)
    assert app.work_week == WorkWeek(7, 1)
    assert (app.model.water, app.model.energy) == resources
    assert owned_collectibles(app) == owned
    assert {k: v for k, v in snapshot(app)["offices"].items() if k in history} == history
    assert garden.items == garden_before
    assert app.progress_store.load()[0] == WorkWeek(7, 1)
    assert not app.can_begin_next_week()


@pytest.mark.parametrize("version", [1, 2])
def test_old_completed_june4_save_can_continue_into_july(version):
    app, _, _ = through_june4()
    old = snapshot(app)
    old.pop("collectibles", None)
    old["version"] = version
    if version == 1:
        old.pop("resources")
        old.pop("defeated")
    app.saved_progress = decode(encode(old))
    app.start_game()
    assert app.work_week == WorkWeek(6, 4) and app.office.complete
    assert not owned_collectibles(app)
    next_week(app)
    assert app.work_week == WorkWeek(7, 1)


def test_new_fence_moves_only_blocked_player_to_safe_spawn():
    app, _, _ = through_june4()
    walk_to(app, 176, 416, 6)
    before = app.model.water, app.model.energy, set(owned_collectibles(app))
    next_week(app)
    assert (app.model.player.x, app.model.player.z) == (app.world.spawn_x, app.world.spawn_z)
    assert not app.world.collides_player(
        app.model.player.x,
        app.model.player.z,
        app.model.player_solid_half_x,
        app.model.player_solid_half_z,
    )
    assert (app.model.water, app.model.energy, set(owned_collectibles(app))) == before


def test_failed_boundary_save_preserves_old_record_and_can_retry_after_backend_reopens():
    app, storage, _ = through_june4()
    old = storage.items[SAVE_KEY]
    last = deepcopy(app.last_checkpoint)
    storage.fail = True
    assert app.begin_next_week()
    app.update_week_transition(3)
    assert app.work_week == WorkWeek(7, 1)
    assert storage.items[SAVE_KEY] == old and app.last_checkpoint == last
    storage.fail = False
    app.progress_store = ProgressStore(browser_storage=storage)
    assert app.checkpoint_progress()
    assert app.progress_store.load()[0] == WorkWeek(7, 1)
    assert storage.items[SAVE_KEY + ".backup"] == old


def test_unfinished_june4_delivery_never_offers_next_week():
    app, _, _ = new_game()
    for _ in range(3):
        play_week(app)
        next_week(app)
    assert app.work_week == WorkWeek(6, 4) and not app.can_begin_next_week()
    for _ in range(10):
        assert not app.begin_next_week()


def test_partial_june4_delivery_stays_guarded():
    from drift_with_me.week4 import FLOWER_IDS, FUJI_ID
    from twelve_week_driver import close_case, dispatch, read

    app, _, _ = new_game()
    for _ in range(3):
        play_week(app)
        next_week(app)
    while app.office.current_case:
        close_case(app)
        if app.office.current_session.state.name == "FIELD_CHECK_REQUIRED":
            break
        assert app.office.advance_case()
    dispatch(app)
    read(app, FUJI_ID)
    read(app, sorted(FLOWER_IDS)[0])
    assert not app.can_begin_next_week()
    assert not app.office.plant_progress.complete
    assert not app.office.complete
    assert not app.begin_next_week()


@pytest.mark.parametrize("entry", [WorkWeek(6, 4), WorkWeek(8, 3)])
def test_debug_week_boundary_stays_in_temporary_storage(entry):
    from drift_with_me.week_debug import TemporaryProgressStore

    app, storage, garden = new_game()
    normal = deepcopy(storage.items), deepcopy(garden.items)
    app._processed_hitstop_event_ids = set()  # Hardware scaffold normally set by __init__.
    app.begin_temporary_week_session()
    assert app.jump_to_debug_week(entry)
    app.pointer_snapshot.down = False
    app.update_week_debug()  # Release the calendar Start tap before normal week input.
    assert isinstance(app.progress_store, TemporaryProgressStore)
    play_week(app)
    next_week(app)
    assert app.work_week == entry.following()
    assert not app.checkpoint_progress()  # Generic normal autosave stays disabled in debug.
    assert app.progress_store.write(snapshot(app))  # Week-specific save gates use this store.
    assert app.progress_store.load()[0] == app.work_week
    assert (storage.items, garden.items) == normal
    app.return_from_week_debug()
    assert (storage.items, garden.items) == normal
