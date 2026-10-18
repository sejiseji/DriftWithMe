"""July checkpoints preserve finite patrol progress without changing June saves."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.east_site import EastSiteProgress
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek, load_week_office


def july_payload():
    week = WorkWeek(7, 1)
    office = load_week_office(week)
    app = SimpleNamespace(
        work_week=week,
        office=office,
        week_office_history={week: office},
        model=SimpleNamespace(water=80, energy=40, enemies=[]),
        east_site_progress=EastSiteProgress(),
        first_sight_seen=set(),
    )
    return app, snapshot(app)


def test_july_partial_progress_round_trip_keeps_enemy_and_conversation_flags():
    app, _ = july_payload()
    progress = app.office.july_progress
    progress.defeated = {"july_nudibranch_normal_1"}
    progress.materials_checked = True
    progress.souvenir_received = True
    progress.departed = True
    restored = decode(encode(snapshot(app)))[1][WorkWeek(7, 1)].july_progress
    assert restored.snapshot() == progress.snapshot()
    assert not restored.complete


def test_july_defeated_ids_do_not_pollute_legacy_general_enemy_record():
    app, _ = july_payload()
    app.model.enemies = [SimpleNamespace(id="july_nudibranch_normal_1", state="DEFEATED")]
    app.office.july_progress.defeated.add("july_nudibranch_normal_1")
    p = snapshot(app)
    assert p["defeated"] == []
    assert decode(encode(p))[1][WorkWeek(7, 1)].july_progress.defeated == {
        "july_nudibranch_normal_1"
    }


@pytest.mark.parametrize("week", [[7, 2], [7, 4], [8, 1], [True, 1]])
def test_unauthored_or_invalid_week_cannot_be_loaded(week):
    _, p = july_payload()
    p["week"] = week
    with pytest.raises(ValueError):
        decode(encode(p))


def test_unknown_july_fields_and_enemy_ids_rejected():
    _, original = july_payload()
    p = deepcopy(original)
    p["offices"]["7:1"]["july"]["invented"] = True
    with pytest.raises(ValueError):
        decode(encode(p))
    p = deepcopy(original)
    p["offices"]["7:1"]["july"]["defeated"] = ["invented"]
    with pytest.raises(ValueError):
        decode(encode(p))


def test_reported_june_enemy_remains_permanent_after_july_enemy_replacement():
    from test_save_state import payload

    app, _ = payload()
    from drift_with_me.office import OfficePrototype

    app.work_week = WorkWeek()
    app.office = OfficePrototype.load()
    app.week_office_history = {app.work_week: app.office}
    app.office.sessions["OFF-PROT-003"].field_progress.dealt_target_ids.add("urchin_abnormal_04")
    app.model.enemies = []
    p = snapshot(app)
    assert p["defeated"] == ["urchin_abnormal_04"]
    assert decode(encode(p))[-1] == {"urchin_abnormal_04"}


def test_finished_july_checkpoint_cannot_repeat_report_or_enter_unauthored_week():
    from drift_with_me.july_week1 import ENEMY_IDS, JULY_FACTS, TASK_CASE
    from drift_with_me.office import FieldResult

    app, _ = july_payload()
    office = app.office
    assert office.prepare_debug_field_task() is not None
    progress = office.july_progress
    progress.defeated = set(ENEMY_IDS)
    progress.materials_checked = progress.water_checked = True
    progress.researchers_arrived = progress.researchers_talked = True
    progress.souvenir_received = True
    result = FieldResult("FIELD-JUL-W1-PEST", TASK_CASE, "JULY1_COMPLETED", tuple(JULY_FACTS), ())
    assert office.complete_field_task(result)
    restored = decode(encode(snapshot(app)))[1][WorkWeek(7, 1)]
    assert restored.complete and restored.july_progress.souvenir_received
    assert not restored.complete_field_task(result)
    assert load_week_office(WorkWeek(7, 2)) is not None
    assert load_week_office(WorkWeek(7, 3)) is not None


def test_researchers_scene_cursor_resumes_without_repeating_arrival():
    from drift_with_me.july_week1 import ENEMY_IDS

    app, _ = july_payload()
    progress = app.office.july_progress
    progress.defeated = set(ENEMY_IDS)
    progress.researchers_arrived = True
    progress.stage = "researchers"
    progress.scene_index = 2
    restored = decode(encode(snapshot(app)))[1][WorkWeek(7, 1)].july_progress
    assert restored.stage == "researchers" and restored.scene_index == 2
    assert restored.researchers_arrived and not restored.researchers_talked


def test_june_general_enemy_state_retained_while_july_model_is_installed():
    app, _ = july_payload()
    app.model._pre_july_enemies = [SimpleNamespace(id="urchin_normal_01", state="DEFEATED")]
    p = snapshot(app)
    assert p["defeated"] == ["urchin_normal_01"]
    assert decode(encode(p))[-1] == {"urchin_normal_01"}
