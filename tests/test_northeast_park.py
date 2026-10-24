"""Scenery lifecycle must preserve authored progress and playable access."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.flowerbed import FLOWER_IDS, install_flowerbed_world
from drift_with_me.model import GameModel
from drift_with_me.northeast_park import (
    BENCH,
    PREFIX,
    PREVIEW_WEEKS,
    install_park_world,
    park_ground_covers,
    park_stage,
)
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek, load_week_office
from drift_with_me.world import load_world_data
from test_flowerbed import garden_app


def scenery_app(week):
    world = load_world_data()
    return SimpleNamespace(
        world=world, model=GameModel(load_runtime_config().raw, world), work_week=week
    )


def test_stages_are_week_derived_and_idempotent_and_reverse_to_authored_tree():
    app = scenery_app(WorkWeek())
    original = deepcopy(app.world.raw)
    bounds = deepcopy(original["bounds"])
    other = {o["id"]: o for o in original["objects"] if o["id"] != "tree_33"}
    for week in [*PREVIEW_WEEKS, *reversed(PREVIEW_WEEKS), WorkWeek()]:
        app.work_week = week
        install_park_world(app)
        first = deepcopy(app.world.raw)
        install_park_world(app)
        assert app.world.raw == first
        assert app.world.raw["bounds"] == bounds
        assert {
            o["id"]: o
            for o in app.world.raw["objects"]
            if not o["id"].startswith(PREFIX) and o["id"] != "tree_33"
        } == other
        if park_stage(week):
            assert app.world.object_by_id("tree_33") is None
            assert app.world.object_by_id(PREFIX + "stump").half_x == 6
        else:
            assert app.world.object_by_id("tree_33") == load_world_data().object_by_id("tree_33")
            assert not any(o.id.startswith(PREFIX) for o in app.world.objects)


@pytest.mark.parametrize("week", PREVIEW_WEEKS)
def test_each_stage_accesses_supplies_investigations_and_gate_without_moving_enemy_homes(week):
    app = scenery_app(week)
    enemies = deepcopy(app.model.enemies)
    install_park_world(app)
    assert app.model.enemies == enemies
    app.model.player.x, app.model.player.z = 632, 592
    for p in [
        (288, 440),
        (240, 744),
        (936, 904),
        (904, 884),
        (888, 876),
        (128, 192),
        (192, 128),
        (816, 256),
        (848, 256),
        (928, 144),
        (160, 160),
    ]:
        assert not app.world.collides_player(*p, 12, 12), p
        assert app.model.find_auto_move_path(*p) is not None, p
    assert app.model.nav_segment_clear(888, 876, 920, 876)
    for enemy in app.model.enemies:
        assert not app.world.collides_player(enemy.home_x, enemy.home_z, 10, 10), enemy.id
    if park_stage(week) >= 4:
        assert app.world.collides_player(*BENCH, 12, 12)
        assert not app.world.collides_player(840, 900, 12, 12)


def test_overlay_preserves_combat_resources_and_all_progress_and_east_access():
    app, _ = garden_app()
    app.east_site_progress.flowerbed_order = FLOWER_IDS
    app.east_site_progress.flowerbed_visit = {"stage": "thanks", "index": 1}
    app.east_site_progress.positions = {"jun_w2_old_hatch": 1}
    app.model.water, app.model.energy = 17.5, 8
    app.world.east_site_access_ready = True
    enemy = app.model.enemies[0]
    app.model.start_contact_combat(enemy, [])
    combat = app.model.combat_session
    assert combat is not None
    before = snapshot(app)
    for week in PREVIEW_WEEKS:
        install_park_world(app, week)
        assert snapshot(app) == before
        assert app.model.combat_session is combat
        assert (app.model.water, app.model.energy) == (17.5, 8)
        assert app.world.east_site_access_ready


def test_real_save_resume_reconstructs_week_two_without_new_save_fields():
    app, _ = garden_app()
    app.east_site_progress.flowerbed_order = FLOWER_IDS
    app.east_site_progress.flowerbed_visit = {"stage": "thanks", "index": 1}
    app.model.water, app.model.energy = 19, 11
    app.model.enemies[0].state = "DEFEATED"
    saved = snapshot(app)
    app.saved_progress = decode(encode(saved))
    install_park_world(app, WorkWeek(8, 1))
    app.start_game()
    assert app.model.northeast_park.stage == 2
    assert app.model.enemies[0].state == "DEFEATED"
    assert snapshot(app) == saved
    assert app.east_site_progress.flowerbed_order == FLOWER_IDS
    assert app.flowerbed_dialogue.index == 1


def test_debug_scenery_does_not_unlock_future_offices_or_write_storage():
    app, storage = garden_app()
    before = deepcopy(storage.items)
    assert app.start_park_preview()
    for week in PREVIEW_WEEKS:
        app.set_park_preview(week)
        assert app.work_week == WorkWeek(7, 2)
        assert app.model.northeast_park.stage == park_stage(week)
        assert not app.checkpoint_progress()
    for week in PREVIEW_WEEKS[4:]:
        assert (load_week_office(week) is None) == (week == WorkWeek(8, 4))
        assert not app.jump_to_debug_week(week)
    assert storage.items == before
    app.jump_to_debug_week(WorkWeek(6, 1))
    assert app.park_preview_week is None and app.model.northeast_park is None


def test_park_ground_filter_does_not_cover_magenta_investigation_sites():
    app = scenery_app(WorkWeek(7, 4))
    install_park_world(app)
    assert park_ground_covers(app.model.northeast_park, 854, 880)
    for p in [(288, 416), (252, 758), (648, 600), (912, 888)]:
        assert not park_ground_covers(app.model.northeast_park, *p)
    # Existing player flowerbed is still the same order, at its authored location.
    app.east_site_progress = SimpleNamespace(flowerbed_order=FLOWER_IDS)
    install_flowerbed_world(app)
    assert app.model.flowerbed_order == FLOWER_IDS


def test_august_construction_finishes_in_week_two_without_replacing_assets():
    assert park_stage(WorkWeek(8, 1)) == 4
    assert park_stage(WorkWeek(8, 2)) == 5
    assert park_stage(WorkWeek(8, 3)) == 5
