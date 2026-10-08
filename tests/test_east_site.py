import json
from copy import deepcopy
from itertools import permutations
from pathlib import Path

import pytest

from drift_with_me.config import load_data_json
from drift_with_me.east_site import SITE_FACTS, SITE_LINES
from drift_with_me.events import GameEvent
from drift_with_me.model import InputIntent
from drift_with_me.office import CaseState
from drift_with_me.world import load_world_data
from field_transition_helpers import finish_travel
from test_field_visit import inspect, make_visit


@pytest.mark.parametrize("order", list(permutations(SITE_FACTS)))
def test_free_order_records_only_completed_exchanges_and_never_lamel_facts(order):
    app = make_visit()
    original = deepcopy(app.office.current_session.field_progress)
    for target in order:
        inspect(app, target)
        assert app.field_conversation.lines == SITE_LINES[target]
        app.advance_field_conversation()
        assert SITE_FACTS[target] not in app.east_site_progress.facts
        app.advance_field_conversation()
        assert SITE_FACTS[target] in app.east_site_progress.facts
        assert app.model.interaction is None and app.field_conversation is None
    assert app.east_site_progress.facts == set(SITE_FACTS.values())
    assert app.office.current_session.field_progress == original
    assert app.complete_office_field_task()
    finish_travel(app)
    assert app.office.current_session.field_result is None
    assert app.office.current_session.state == CaseState.FIELD_ACTIVE
    app.activate_office_footer_action()
    finish_travel(app)
    for target in order:
        inspect(app, target)
        assert len(app.field_conversation.lines) == 1
        app.advance_field_conversation()
    assert app.east_site_progress.facts == set(SITE_FACTS.values())
    assert not app.world.east_site_access_ready


def test_partial_cancel_resume_and_external_completion_cannot_invent_a_fact():
    app = make_visit()
    target = "jun_w2_old_hatch"
    inspect(app, target)
    app.advance_field_conversation()
    app.process_events(app.model.cancel_interaction())
    assert not app.east_site_progress.facts
    assert app.east_site_progress.positions[target] == 1
    app.process_events([GameEvent(999, 0, "inspection_completed", "player", target, (928, 0, 144))])
    assert not app.east_site_progress.facts
    assert app.complete_office_field_task()
    finish_travel(app)
    app.activate_office_footer_action()
    finish_travel(app)
    inspect(app, target)
    assert app.field_conversation.index == 1
    app.advance_field_conversation()
    assert app.east_site_progress.facts == {"hatch_present"}
    app.process_events([GameEvent(999, 0, "inspection_completed", "player", target, (928, 0, 144))])
    assert app.east_site_progress.facts == {"hatch_present"}


def test_normal_exploration_does_not_require_a_hero_or_office_task():
    app = make_visit()
    app.office.active_field_task = None
    for target in SITE_FACTS:
        inspect(app, target)
        while app.field_conversation:
            app.advance_field_conversation()
    assert app.east_site_progress.facts == set(SITE_FACTS.values())
    assert app.office.current_case.case_id == "OFF-PROT-003"
    assert app.office.current_session.field_result is None


def test_lamel_report_contains_only_her_observations_after_site_visit():
    app = make_visit()
    inspect(app, "jun_w2_canal_bank")
    while app.field_conversation:
        app.advance_field_conversation()
    inspect(app, "tap_stopped")
    while app.field_conversation:
        app.advance_field_conversation()
    assert app.complete_office_field_task()
    finish_travel(app)
    result = app.office.current_session.field_result
    assert result.discovered_fact_ids == ("supply_stopped",)
    assert all(f not in result.discovered_fact_ids for f in SITE_FACTS.values())
    assert app.east_site_progress.facts == {"bank_unsafe"}


def test_small_landing_is_blocked_from_every_side_but_water_is_walkable():
    world = load_world_data()
    for point in ((960, 250), (1000, 250), (990, 184), (990, 319), (1020, 250)):
        assert world.collides_player(*point, 4, 4)
    for point in ((924, 250), (944, 256), (952, 250), (928, 144), (884, 40)):
        assert not world.collides_player(*point, 4, 4)
    # All possible approaches stop at the footing region, rather than a thin wall.
    for point in ((956, 240), (990, 180), (990, 324)):
        assert not world.collides_player(*point, 3, 3)
    world.east_site_access_ready = True
    assert not world.collides_player(990, 250, 4, 4)
    # No date advance or observation toggles this future integration boundary.
    assert world.walkable_rect.max_x == 1024


def test_overlay_preserves_old_objects_enemies_camera_and_has_matching_spec():
    base = load_data_json("prototype_world.json")
    world = load_world_data()
    assert world.raw["objects"][: len(base["objects"])] == base["objects"]
    for key in ("enemies", "camera_zones", "camera_sequences", "safe_zones", "bounds"):
        assert world.raw[key] == base[key]
    addon = load_data_json("east_site.json")
    spec = Path(__file__).resolve().parents[1] / "docs/prototype_spec/data/east_site.json"
    assert addon == json.loads(spec.read_text())
    assert {o["id"] for o in addon["objects"]} == set(SITE_FACTS)
    assert all(o["inspectable"] and not o["solid"] for o in addon["objects"])


def test_real_enemy_danger_denies_start_and_existing_conversation_freezes_contact():
    app = make_visit()
    model = app.model
    model.player.x, model.player.z = 924, 256
    enemy = model.enemies[0]
    enemy.x, enemy.z = 924, 326
    events = []
    model.try_start_interaction(events, None)
    assert model.interaction is None
    assert any(e.kind == "action_denied" for e in events)
    enemy.x, enemy.z = 600, 500
    model.try_start_interaction(events, None)
    app.process_events(events)
    assert app.field_conversation.target_id == "jun_w2_canal_bank"
    enemy.x, enemy.z = model.player.x, model.player.z
    before = model.world_tick
    for _ in range(60):
        model.step(InputIntent(screen_x=1, strength=1), app.camera(), 1 / 60)
    assert model.world_tick == before
    assert model.combat_session is None
    while app.field_conversation:
        app.advance_field_conversation()
    enemy.x, enemy.z = 600, 500
    model.step(InputIntent(), app.camera(), 1 / 60)
    assert model.world_tick > before


def test_navigation_does_not_cut_across_closed_footing_and_water_stays_clear():
    app = make_visit()
    m = app.model
    assert not m.nav_segment_clear(924, 160, 1000, 340, 4)
    assert m.nav_segment_clear(900, 256, 952, 256, 4)
    m.world.east_site_access_ready = True
    assert m.nav_segment_clear(924, 160, 1000, 340, 4)


def test_different_active_interaction_cannot_start_a_site_exchange():
    app = make_visit()
    inspect(app, "tap_stopped")
    app.begin_field_conversation("jun_w2_canal_bank")
    assert app.field_conversation is None
    assert app.model.interaction.object_id == "tap_stopped"
