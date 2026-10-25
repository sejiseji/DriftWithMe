from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.august import REPORTS, SITES, AugustProgress
from drift_with_me.july_week4 import REPORT as JULY_REPORT
from drift_with_me.save_state import (
    SAVE_KEY,
    decode,
    encode,
    office_snapshot,
    restore_office,
    snapshot,
)
from drift_with_me.week_cycle import WorkWeek, load_week_office
from test_july_week4 import close_case, field_app


def finished_july():
    app, storage = field_app()
    p = app.office.week4_progress
    p.fuji_seen = p.park_seen = True
    assert app.return_week4()
    app.field_transition = None
    app.screen = AppScreen.OFFICE
    for _ in JULY_REPORT:
        app.update_july_week4(0)
        assert app.advance_week4_dialogue()
    return app, storage


def august_app():
    app, storage = finished_july()
    assert app.begin_next_week()
    app.update_week_transition(0.56)
    app.update_week_transition(4)
    app.week_input_wait_for_release = False
    assert app.work_week == WorkWeek(8, 1)
    app.office.begin_current_case()
    return app, storage


def dispatch(app):
    close_case(app)
    assert app.office.prepare_field_task()
    app.enter_exploration_from_office()
    app.field_transition = None
    app.screen = AppScreen.PLAY
    assert app.office.august_progress.phase == "field"


def complete_week(app):
    dispatch(app)
    for site in sorted(SITES):
        assert app.record_august_site(site, "sighting" if app.work_week.number == 1 else "swarm")
    assert app.return_august()
    app.field_transition = None
    app.screen = AppScreen.OFFICE
    for _ in REPORTS[app.work_week.number]:
        assert app.advance_august_report()


def test_native_july_bridge_and_three_august_weeks_offer_optional_w4():
    app, storage = august_app()
    for n in (1, 2, 3):
        assert app.work_week == WorkWeek(8, n)
        complete_week(app)
        restored = decode(encode(snapshot(app)))
        assert restored[1][WorkWeek(8, n)].august_progress.phase == "done"
        if n < 3:
            assert app.begin_next_week()
            app.update_week_transition(0.56)
            app.update_week_transition(4)
            app.week_input_wait_for_release = False
            app.office.begin_current_case()
        else:
            assert app.can_begin_next_week()
            assert load_week_office(WorkWeek(8, 4)) is not None
            assert app.last_checkpoint == snapshot(app)
            stored = decode(storage.items[SAVE_KEY])
            assert stored[0] == WorkWeek(8, 3)
            assert stored[1][stored[0]].august_progress.phase == "done"


def test_missing_field_producers_never_auto_complete_and_partial_resume_is_idempotent():
    app, _ = august_app()
    dispatch(app)
    assert not app.office.august_progress.ready
    assert not app.record_august_site("northwest", "swarm")
    assert app.record_august_site("northwest", "sighting")
    assert not app.record_august_site("northwest", "sighting")
    saved = decode(encode(snapshot(app)))
    app.office = saved[1][app.work_week]
    assert app.office.august_progress.sites == ["northwest"]
    assert app.return_august()
    assert app.office.august_progress.phase == "office"
    assert not app.office.complete
    assert not app.advance_august_report()
    app.field_transition = None
    app.screen = AppScreen.OFFICE
    app.enter_exploration_from_office()
    assert app.office.august_progress.sites == ["northwest"]


def test_save_failure_rolls_back_site_and_completion():
    app, _ = august_app()
    dispatch(app)
    old = deepcopy(app.office.august_progress.snapshot())
    original = app.progress_store.write
    app.progress_store.write = lambda _: False
    assert not app.record_august_site("northwest", "sighting")
    assert app.office.august_progress.snapshot() == old
    app.progress_store.write = original
    for site in SITES:
        assert app.record_august_site(site, "sighting")
    assert app.return_august()
    app.field_transition = None
    app.screen = AppScreen.OFFICE
    while app.office.august_progress.report_index < len(REPORTS[1]) - 1:
        assert app.advance_august_report()
    app.progress_store.write = lambda _: False
    assert not app.advance_august_report()
    assert app.office.august_progress.phase == "report" and not app.office.complete


@pytest.mark.parametrize(
    "bad",
    [
        {},
        None,
        {"phase": "done", "sites": [], "report_index": 0},
        {"phase": "field", "sites": ["northwest"] * 2, "report_index": 0},
        {"phase": "counter", "sites": [], "report_index": True},
    ],
)
def test_corrupt_august_state_rejected(bad):
    with pytest.raises(ValueError):
        AugustProgress.restore(bad, 1)


def test_missing_new_state_and_broken_history_are_rejected_without_changing_old_july():
    app, _ = august_app()
    data = snapshot(app)
    old = deepcopy(data)
    old["offices"]["8:1"].pop("august")
    with pytest.raises(ValueError):
        decode(encode(old))
    old = deepcopy(data)
    old["offices"].pop("7:4")
    with pytest.raises(ValueError):
        decode(encode(old))
    office = load_week_office(WorkWeek(8, 1))
    office.begin_current_case()
    raw = office_snapshot(office)
    raw["august"]["phase"] = "field"
    with pytest.raises(ValueError):
        restore_office(raw, WorkWeek(8, 1))
