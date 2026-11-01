from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.office import OfficePrototype
from drift_with_me.office_header import publish_save_notice
from drift_with_me.save_state import ProgressStore
from drift_with_me.week_cycle import WorkWeek, load_week_office
from drift_with_me.week_debug import TemporaryProgressStore
from test_office_supervisor import app_for, finish
from test_save_state import Storage, payload


def test_actual_write_only_success_and_failure_notice(tmp_path):
    _, data = payload()
    store = ProgressStore(path=tmp_path / "progress.json")
    app = app_for(load_week_office(WorkWeek(6, 2)))
    app.progress_store = store
    app.week_debug_active = False
    assert store.write(data)
    assert app.office_save_notice() == ("進行をセーブしました", 10)
    revision = store.save_notice_revision
    app.presentation_time += 5
    assert store.write(data)  # Same content, no actual write, no renewed notification.
    assert store.save_notice_revision == revision
    assert app.office_save_notice()[0] == ""
    store.available = False
    assert not store.write(data)
    assert app.office_save_notice() == ("進行をセーブできません", 8)
    assert not store.write(data)
    assert store.save_notice_revision == revision + 1


def test_temporary_write_failure_and_normal_store_return_do_not_replay(tmp_path):
    _, data = payload()
    app = app_for(load_week_office(WorkWeek(6, 2)))
    normal = ProgressStore(path=tmp_path / "progress.json")
    assert normal.write(data)
    app.progress_store = normal
    app.week_debug_active = False
    app.office_save_notice()
    before = (tmp_path / "progress.json").read_bytes()
    app.presentation_time += 10
    app.week_debug_active = True
    app.progress_store = TemporaryProgressStore()
    assert app.office_save_notice()[0] == "デバッグ中・通常セーブは変更しません"
    assert app.progress_store.write(data)
    assert app.office_save_notice() == ("一時保存しました（デバッグ）", 12)
    assert not app.progress_store.write({})
    assert app.office_save_notice() == ("一時保存できません（デバッグ）", 8)
    app.progress_store = normal
    app.week_debug_active = False
    assert app.office_save_notice()[0] == ""
    assert (tmp_path / "progress.json").read_bytes() == before


def test_failed_browser_write_does_not_claim_success_or_change_main():
    _, data = payload()
    browser = Storage()
    store = ProgressStore(browser_storage=browser)
    assert store.write(data)
    before = deepcopy(browser.items)
    data = deepcopy(data)
    data["resources"]["water"] -= 1
    browser.fail = True
    assert not store.write(data)
    assert store.save_notice_kind == "failure"
    assert browser.items[next(k for k in before if not k.endswith(".backup"))] == next(
        iter(before.values())
    )


@pytest.mark.parametrize("month", [6, 7, 8])
@pytest.mark.parametrize("week", [1, 2, 3, 4])
@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_all_weeks_toolbar_rects_and_consultation_conditions(month, week, profile):
    office = load_week_office(WorkWeek(month, week)) or OfficePrototype.load()
    app = app_for(office, profile)
    app.work_week = WorkWeek(month, week)
    app.screen = AppScreen.OFFICE
    app.progress_store = ProgressStore(enabled=False)
    rects = [
        app.office_field_debug_rect(),
        app.office_consultation_button_rect(),
        app.office_calendar_rect(),
    ]
    assert all(r.width > 0 and r.height > 0 for r in rects)
    assert all(a.x + a.width <= b.x for a, b in zip(rects, rects[1:], strict=False))
    assert app.office_save_notice()[0] == ""
    # Initial dialogue must finish before the icon becomes available.
    if app.office_dialogue_requires_advance():
        assert not app.office_consultation_available()
    finish(office)
    playback = app.sync_office_dialogue_playback()
    playback.page_index = len(playback.pages) - 1
    playback.revealed_chars = 9999
    expected = app.week4_follow_available() or office.supervisor_advice() is not None
    assert app.office_consultation_available() == expected
    if expected:
        assert app.begin_office_consultation()
        if app.office_consultation is not None:
            assert app.office_consultation_available()
            app.end_office_consultation()


def test_notice_no_hitbox_and_revision_deduplication():
    store = Storage()
    publish_save_notice(store, "failure")
    publish_save_notice(store, "failure")
    assert store.save_notice_revision == 1
    publish_save_notice(store, "saved")
    assert store.save_notice_revision == 2
