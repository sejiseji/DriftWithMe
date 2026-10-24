from copy import deepcopy
from itertools import permutations

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.august import REPORTS, SITES, AugustProgress
from drift_with_me.model import InputIntent
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.swarm_battle import SwarmBattle
from drift_with_me.week_cycle import WorkWeek
from test_august_wave1 import august_app, dispatch


def sight(app, site):
    from drift_with_me.config import load_data_json

    app.model.player.x, app.model.player.z = load_data_json("swarm_config.json")["sites"][site]
    assert app.update_august_sightings(0.01)
    assert app.office.august_progress.pending_sighting == site
    for _ in range(14):
        app.update_august_sightings(0.1)
    assert app.august_crossing is None
    assert app.advance_august_sighting()
    assert app.advance_august_sighting()


def report_and_next(app):
    assert app.return_august()
    app.field_transition = None
    app.screen = AppScreen.OFFICE
    for _ in REPORTS[app.work_week.number]:
        assert app.advance_august_report()
    assert app.begin_next_week()
    app.update_week_transition(0.56)
    app.update_week_transition(4)
    app.week_input_wait_for_release = False
    app.office.begin_current_case()


@pytest.mark.parametrize("order", list(permutations(sorted(SITES))))
def test_real_proximity_sightings_any_order_and_only_once(order):
    app, _ = august_app()
    dispatch(app)
    enemies = deepcopy(app.model.enemies)
    for site in order:
        sight(app, site)
        assert site in app.office.august_progress.sites
        assert not app.update_august_sightings(0.1)
    assert app.office.august_progress.ready
    assert app.model.enemies == enemies and app.model.swarm_field is None
    assert decode(encode(snapshot(app)))[1][WorkWeek(8, 1)].august_progress.ready


def test_pending_sighting_save_resumes_dialogue_without_another_crossing():
    app, _ = august_app()
    dispatch(app)
    app.model.player.x, app.model.player.z = 200, 800
    assert app.update_august_sightings(0.1)
    assert app.august_crossing
    restored = decode(encode(snapshot(app)))[1][app.work_week]
    app.office = restored
    app.august_crossing = None
    app.update_august_sightings(0.1)
    assert app.august_crossing is None
    assert app.advance_august_sighting()
    index = decode(encode(snapshot(app)))[1][app.work_week].august_progress.sighting_index
    assert index == 1
    assert app.advance_august_sighting()
    assert not app.update_august_sightings(0.1)
    assert app.office.august_progress.sites == ["northwest"]


@pytest.mark.parametrize(
    "kinds,cost,phases",
    [
        (("urchin",) * 6, (12, 20), {"electric"}),
        (("slug",) * 6, (24, 0), {"circle", "converge", "spear"}),
        (("urchin", "slug") * 3, (24, 20), {"electric", "circle", "converge", "spear"}),
    ],
)
def test_species_attacks_charge_once_and_skip_irrelevant_actions(kinds, cost, phases):
    b = SwarmBattle(kinds=kinds)
    b.phase = "approach"
    b.progress = b.settings.target
    b.input()
    b.input()  # Held/spam capture cannot pay a second time.
    seen = set()
    for _ in range(1000):
        if b.phase == "finish_wait":
            b.input()
            b.finish()
            b.finish()
        b.tick(0.02)
        seen.add(b.phase)
        if b.phase == "victory":
            break
    assert b.phase == "victory" and b.defeated == set(range(6))
    assert (b.water, b.energy) == (100 - cost[0], 100 - cost[1])
    assert (seen & {"electric", "circle", "converge", "spear"}) == phases


def test_normal_story_dispatch_creates_site_specific_swarm_without_developer_flags():
    app, _ = august_app()
    dispatch(app)
    for site in sorted(SITES):
        sight(app, site)
    report_and_next(app)
    dispatch(app)
    assert app.work_week == WorkWeek(8, 2)
    assert not getattr(app, "swarm_field_enabled", False)
    field = app.ensure_swarm_field()
    assert field.config["compositions"]["northwest"] == ["urchin"] * 6
    assert field.config["compositions"]["northeast"] == ["slug"] * 6
    assert field.config["compositions"]["southeast"] == ["urchin", "slug"] * 3
    app.model.player.x, app.model.player.z = 200, 800
    events = []
    field.step(InputIntent(), app.camera(), 0.02, events)
    assert field.battle and field.battle.kinds == ("urchin",) * 6
    assert [e.kind for e in events] == ["swarm_started"]


@pytest.mark.parametrize(
    "kinds,water,energy,message",
    [
        (("urchin",) * 6, 12, 0, "電力"),
        (("slug",) * 6, 12, 100, "とどめ"),
        (("urchin", "slug") * 3, 12, 100, "混ざって"),
    ],
)
def test_shortages_keep_successful_capture_cost_without_partial_kills(
    kinds, water, energy, message
):
    b = SwarmBattle(water, energy, kinds=kinds)
    b.phase = "approach"
    b.progress = b.settings.target
    b.input()
    b.phase = "finish_wait"
    b.finish()
    assert b.phase == "retreat_line" and message in b.message
    assert not b.defeated and b.water == 0 and b.energy == energy


def test_wave1_progress_old_schema_accepted_and_pending_is_validated():
    p = AugustProgress.restore({"phase": "field", "sites": [], "report_index": 0}, 1)
    assert p.pending_sighting is None
    bad = p.snapshot()
    bad["pending_sighting"] = "northwest"
    with pytest.raises(ValueError):
        AugustProgress.restore(bad, 2)
    bad["pending_sighting"] = []
    with pytest.raises(ValueError):
        AugustProgress.restore(bad, 1)


def test_story_swarm_does_not_swallow_departure_or_week_fades():
    app, _ = august_app()
    dispatch(app)
    for site in sorted(SITES):
        sight(app, site)
    report_and_next(app)
    from test_july_week4 import close_case

    close_case(app)
    assert app.office.prepare_field_task()
    app.enter_exploration_from_office()
    app.screen = AppScreen.PLAY
    assert app.field_transition is not None
    assert not app.update_swarm_frame(0.1)
    assert app.model.swarm_field is None


def test_sighting_claim_and_dialogue_completion_rollback_on_write_failure():
    app, _ = august_app()
    dispatch(app)
    app.model.player.x, app.model.player.z = 200, 800
    original = app.progress_store.write
    app.progress_store.write = lambda _: False
    assert app.update_august_sightings(0.1)
    assert app.office.august_progress.pending_sighting is None
    assert not getattr(app, "august_crossing", None)
    app.progress_store.write = original
    assert app.update_august_sightings(0.1)
    for _ in range(14):
        app.update_august_sightings(0.1)
    assert app.advance_august_sighting()
    app.progress_store.write = lambda _: False
    assert not app.advance_august_sighting()
    assert app.office.august_progress.pending_sighting == "northwest"
    assert app.office.august_progress.sighting_index == 1
    assert not app.office.august_progress.sites
