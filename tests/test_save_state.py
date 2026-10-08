import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.east_site import SITE_FACTS
from drift_with_me.office import CaseState
from drift_with_me.save_state import SAVE_KEY, ProgressStore, decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek
from field_transition_helpers import finish_travel
from test_field_visit import drain, inspect
from test_week2_loop import hero_app, resolve


def payload():
    app = hero_app()
    app.week_office_history = {WorkWeek(6, 2): app.office}
    app.first_sight_seen = set()
    return app, snapshot(app)


class Storage:
    def __init__(self):
        self.items = {}
        self.fail = False

    def getItem(self, key):
        return self.items.get(key)

    def setItem(self, key, value):
        if self.fail and key == SAVE_KEY:
            raise RuntimeError("QuotaExceededError")
        self.items[key] = value


def test_native_and_browser_round_trip_partial_dialog_and_facts(tmp_path):
    app, _ = payload()
    inspect(app, "jun_w2_old_hatch")
    app.advance_field_conversation()
    app.process_events(app.model.cancel_interaction())
    inspect(app, "jun_w2_canal_bank")
    app.advance_field_conversation()
    app.advance_field_conversation()
    app.first_sight_seen = {"normal"}
    p = snapshot(app)
    for store in [
        ProgressStore(path=tmp_path / "save.json"),
        ProgressStore(browser_storage=Storage()),
    ]:
        assert store.write(p)
        week, offices, sites, seen, resources, defeated = store.load()
        assert week == WorkWeek(6, 2)
        assert sites.facts == {"bank_unsafe"} and sites.positions == {"jun_w2_old_hatch": 1}
        assert sites.pending_completion is None
        assert seen == {"normal"}
        assert offices[week].active_field_task.case_id == "OFF-JUN-W2-HERO"
        assert offices[week].current_session.field_result is None
        assert sites.begin("jun_w2_old_hatch")[1] == 1


def test_reported_checkpoint_cannot_repeat_report_or_advance_unwritten_week():
    app, _ = payload()
    app.east_site_progress.facts = set(SITE_FACTS.values())
    assert app.complete_office_field_task()
    finish_travel(app)
    drain(app.office)
    assert app.office.advance_case()
    resolve(app.office)
    assert app.office.advance_case()
    p = snapshot(app)
    w, offices, sites, _, _, _ = decode(encode(p))
    assert offices[w].complete and not offices[w].advance_case()
    assert p["reported"] and sites.facts == set(SITE_FACTS.values())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(version=0),
        lambda p: p.update(version=3),
        lambda p: p.update(version=True),
        lambda p: p.update(week=[6, 3]),
        lambda p: p.update(week=[6, True]),
        lambda p: p.update(week=[float("nan"), 2]),
        lambda p: p.update(facts=["imaginary"]),
        lambda p: p.update(facts=["bank_unsafe", "bank_unsafe"]),
        lambda p: p.update(positions={"jun_w2_canal_bank": 99}),
        lambda p: p.update(reported=True),
        lambda p: p.update(seen=["enemy_that_does_not_exist"]),
        lambda p: p["offices"]["6:2"].update(index=-1),
        lambda p: p["offices"]["6:2"].update(index=999),
        lambda p: p["offices"]["6:2"]["sessions"]["OFF-JUN-W2-HERO"].update(state="FIELD_RETURNED"),
        lambda p: p["offices"]["6:2"]["sessions"]["OFF-JUN-W2-CONSTRUCTION"].update(
            state="CLOSED_COUNTER"
        ),
    ],
)
def test_corrupt_unknown_and_future_records_are_not_silently_cleared(mutation):
    _, p = payload()
    mutation(p)
    storage = Storage()
    storage.items[SAVE_KEY] = encode(p)
    before = storage.items.copy()
    store = ProgressStore(browser_storage=storage)
    assert store.load() is None and store.message
    assert storage.items == before and store.has_record


def test_checksum_and_incomplete_writes_keep_last_good_backup():
    _, p = payload()
    storage = Storage()
    store = ProgressStore(browser_storage=storage)
    assert store.write(p)
    modified = deepcopy(p)
    modified["seen"] = ["normal"]
    assert store.write(modified)
    storage.items[SAVE_KEY] = '{"payload":'
    assert store.load()[3] == set() and "前の保存" in store.message
    assert storage.items[SAVE_KEY] == '{"payload":'
    storage.items[SAVE_KEY] = encode(p).replace("bank_unsafe", "hatch_present")
    assert store.load() is not None


def test_storage_denied_retains_primary_and_uses_visible_session_fallback():
    _, p = payload()
    storage = Storage()
    store = ProgressStore(browser_storage=storage)
    assert store.write(p)
    old = storage.items[SAVE_KEY]
    storage.fail = True
    p["seen"] = ["normal"]
    assert not store.write(p) and not store.available and "この間だけ" in store.message
    assert storage.items[SAVE_KEY] == old
    assert store.load()[3] == {"normal"}


def test_replace_failure_keeps_native_last_good_file(tmp_path, monkeypatch):
    _, p = payload()
    store = ProgressStore(path=tmp_path / "save.json")
    assert store.write(p)
    old = store.path.read_bytes()
    monkeypatch.setattr(
        "drift_with_me.save_state.os.replace",
        lambda *a: (_ for _ in ()).throw(OSError("write denied")),
    )
    p["seen"] = ["normal"]
    assert not store.write(p)
    assert store.path.read_bytes() == old


def test_no_checkpoint_in_battle_fade_or_unfinished_inspection():
    app, _ = payload()
    app.progress_store = ProgressStore(enabled=False)
    app.session_started = True
    app.last_checkpoint = None
    app.week_transition = None
    assert not app.progress_store.enabled
    inspect(app, "jun_w2_canal_bank")
    app.advance_field_conversation()
    assert not app.checkpoint_progress() and not app.east_site_progress.facts
    app.process_events(app.model.cancel_interaction())
    assert not app.checkpoint_progress()
    # Disabled native capture storage still holds a session checkpoint, with no disk write.
    assert app.progress_store.session is not None
    app.field_transition = SimpleNamespace(phase="fade_out")
    before = app.last_checkpoint
    assert not app.checkpoint_progress() and app.last_checkpoint == before


def test_snapshot_does_not_share_live_conversation_positions():
    app, _ = payload()
    before = snapshot(app)
    app.office.current_session.field_progress.conversation_positions["tap_stopped"] = 1
    assert before["offices"]["6:2"]["sessions"]["OFF-JUN-W2-HERO"]["field"]["positions"] == {}


def test_invalid_checkpoint_does_not_crash_or_replace_a_good_record():
    _, p = payload()
    storage = Storage()
    store = ProgressStore(browser_storage=storage)
    assert store.write(p)
    before = storage.items.copy()
    p["offices"]["6:2"]["index"] = 999
    assert not store.write(p) and storage.items == before and store.message


@pytest.mark.parametrize("bad_record", ["{broken", encode({"version": 99}), "x" * 70000])
def test_bad_primary_and_good_backup_cannot_be_overwritten_by_continue(bad_record):
    _, p = payload()
    storage = Storage()
    storage.items[SAVE_KEY] = bad_record
    storage.items[SAVE_KEY + ".backup"] = encode(p)
    store = ProgressStore(browser_storage=storage)
    assert store.load() is not None
    assert store.write_protected
    old = storage.items.copy()
    p["seen"] = ["normal"]
    assert not store.write(p)
    assert storage.items == old and "この間だけ" in store.message
    assert store.load()[3] == {"normal"}
    store.authorize_new_game()
    assert store.write(p)
    assert storage.items[SAVE_KEY] != bad_record


def test_legacy_version_one_migrates_without_losing_facts_and_keeps_original_backup():
    app, p = payload()
    app.east_site_progress.facts = {"bank_unsafe"}
    p = snapshot(app)
    p["version"] = 1
    p.pop("resources")
    p.pop("defeated")
    storage = Storage()
    storage.items[SAVE_KEY] = encode(p)
    original = storage.items[SAVE_KEY]
    store = ProgressStore(browser_storage=storage)
    week, offices, sites, seen, resources, defeated = store.load()
    assert sites.facts == {"bank_unsafe"} and offices[week].active_field_task is not None
    assert "初期量" in store.message
    assert resources == {"water": 100.0, "energy": 60.0}
    app.office = offices[week]
    app.east_site_progress = sites
    assert store.write(snapshot(app))
    assert storage.items[SAVE_KEY + ".backup"] == original
    assert json.loads(storage.items[SAVE_KEY])["payload"]["version"] == 2


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["resources"].update(water=-1),
        lambda p: p["resources"].update(energy=999),
        lambda p: p["resources"].update(water=float("nan")),
        lambda p: p["resources"].update(energy=float("inf")),
        lambda p: p["resources"].update(water=True),
        lambda p: p.update(defeated=["invented"]),
    ],
)
def test_invalid_resource_and_enemy_state_does_not_replace_a_good_slot(mutation):
    _, p = payload()
    storage = Storage()
    store = ProgressStore(browser_storage=storage)
    assert store.write(p)
    before = storage.items.copy()
    mutation(p)
    assert not store.write(p) and storage.items == before


def test_returned_hero_dialogue_is_replayed_at_safe_checkpoint_before_advancing():
    app, _ = payload()
    app.east_site_progress.facts = set(SITE_FACTS.values())
    assert app.complete_office_field_task()
    finish_travel(app)
    assert app.office.current_session.state == CaseState.FIELD_RETURNED
    app.week_office_history = {app.work_week: app.office}
    w, offices, _, _, _, _ = decode(encode(snapshot(app)))
    office = offices[w]
    assert office.current_session.state == CaseState.FIELD_RETURNED
    assert "建設課" in "".join(line.text for line in office.active_dialogue_lines())
    assert office.has_pending_dialogue_step() and not office.advance_case()
    assert office.active_field_task is None


def test_resources_and_permanently_defeated_enemy_survive_resume_without_mid_battle():
    from drift_with_me.app import AppScreen
    from drift_with_me.field_visit import ANOMALY_ID
    from drift_with_me.save_state import ProgressStore

    app, p = payload()
    app.model.water = 17.5
    app.model.energy = 8.0
    app.model.enemy_by_id(ANOMALY_ID).state = "DEFEATED"
    loaded = decode(encode(snapshot(app)))
    app.saved_progress = loaded
    app.progress_store = ProgressStore(enabled=False)
    app.model.water = 100
    app.model.energy = 60
    app.model.enemy_by_id(ANOMALY_ID).state = "IDLE"
    app.end_office_consultation = lambda: None
    app.pointer_snapshot = SimpleNamespace(down=False)
    app.camera_controller.reset = lambda target: None
    app.start_game()
    assert app.screen == AppScreen.OFFICE and app.model.combat_session is None
    assert (app.model.water, app.model.energy) == (17.5, 8)
    assert app.model.enemy_by_id(ANOMALY_ID).state == "DEFEATED"
    assert (app.model.player.x, app.model.player.z) == (app.world.spawn_x, app.world.spawn_z)


def test_real_contact_battle_restores_only_the_pre_battle_safe_checkpoint():
    app, _ = payload()
    app.progress_store = ProgressStore(enabled=False)
    app.session_started = True
    app.last_checkpoint = None
    app.week_transition = None
    app.first_sight_conversation = None
    app.model.water = 27
    app.model.energy = 14
    app.checkpoint_progress()
    saved = app.progress_store.session
    enemy = app.model.enemies[0]
    app.model.player.x, app.model.player.z = enemy.x, enemy.z
    app.model.start_contact_combat(enemy, [])
    assert app.model.combat_session is not None
    app.model.water = 7
    app.model.energy = 2
    assert not app.checkpoint_progress() and app.progress_store.session == saved
    app.saved_progress = decode(saved)
    app.end_office_consultation = lambda: None
    app.camera_controller.reset = lambda p: None
    app.start_game()
    assert app.model.combat_session is None
    assert (app.model.water, app.model.energy) == (27, 14)
    assert app.world.point_in_safe_zone(app.model.player.x, app.model.player.z)


def test_native_unreadable_primary_is_preserved_until_confirmed_new_game(tmp_path):
    _, p = payload()
    store = ProgressStore(path=tmp_path / "save.json")
    store.path.write_bytes(b"\xff\xfe")
    assert store.load() is None
    assert not store.write(p) and store.path.read_bytes() == b"\xff\xfe"
    store.authorize_new_game()
    assert store.write(p)
    assert store.load() is not None
