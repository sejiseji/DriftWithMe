from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.july_week3 import (
    DURATIONS,
    PARENT,
    PARENT_POSITION,
    SMALL,
    Week3Progress,
    install_week3_world,
)
from drift_with_me.save_state import ProgressStore, decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek
from test_save_state import Storage
from test_week_debug_safety import debug_app


def app3(debug=False):
    storage = Storage()
    app = debug_app(storage)
    assert app.jump_to_debug_week(WorkWeek(7, 3))
    app.office.prepare_debug_field_task()
    app.screen = AppScreen.PLAY
    app.week_debug_active = debug
    app.progress_store = ProgressStore(browser_storage=storage)
    app.key_pressed = lambda *keys: False
    app.mouse_pressed_in = lambda rect: False
    app.travel_input_held = lambda: False
    return app, storage


def begin_scene(app, ident):
    assert app.begin_week3_target(ident)
    while app.week3_dialogue is not None:
        assert app.advance_week3_dialogue()
    assert app.office.week3_progress.active_scene == ident


@pytest.mark.parametrize("ident", SMALL)
def test_small_terminal_zero_power_atomic_resume_and_no_duplicate_collection(ident):
    app, _ = app3()
    app.model.energy = 0
    pose = (deepcopy(app.model.player), deepcopy(app.model.buddy), app.camera())
    enemies = deepcopy(app.model.enemies)
    begin_scene(app, ident)
    for stage in range(2):
        assert app.update_july_week3(DURATIONS[stage])
    saved = snapshot(app)
    progress = decode(encode(saved))[1][WorkWeek(7, 3)].week3_progress
    assert progress.active_scene == ident and progress.scene_step == 2
    app.office.week3_progress = progress
    app.week3_scene_elapsed = 0
    for seconds in DURATIONS[2:]:
        assert app.update_july_week3(seconds)
    p = app.office.week3_progress
    assert p.recovered == {ident} and p.active_scene is None
    assert app.world.object_by_id(ident) is None
    assert app.model.energy == 0
    assert (app.model.player, app.model.buddy, app.camera()) == pose
    assert app.model.enemies == enemies
    assert app.model.week2_scenery_enabled
    assert not app.begin_week3_target(ident)
    restored = decode(encode(snapshot(app)))[1][WorkWeek(7, 3)].week3_progress
    assert restored.recovered == {ident}


def test_interrupted_discovery_dialogue_resumes_at_same_line_and_debug_is_separate():
    app, storage = app3(debug=True)
    before = deepcopy(storage.items)
    ident = next(iter(SMALL))
    assert app.begin_week3_target(ident)
    assert app.advance_week3_dialogue()
    p = Week3Progress.restore(app.office.week3_progress.snapshot())
    app.office.week3_progress = p
    app.week3_dialogue = None
    app.week3_wait_release = False
    app.update_july_week3(0)
    assert app.week3_dialogue.index == 1 and len(app.week3_dialogue.lines) == 2
    assert storage.items == before


def test_parent_early_visit_is_observation_only_and_positions_do_not_block_access():
    app, _ = app3()
    assert app.begin_week3_target(PARENT)
    while app.week3_dialogue is not None:
        app.advance_week3_dialogue()
    assert app.office.week3_progress.parent_seen
    assert not app.office.week3_progress.parent_recovered
    assert app.office.week3_progress.active_scene is None
    assert not app.office.complete and not app.can_begin_next_week()
    assert app.world.object_by_id("jun_w3_old_key") is None
    for ident, (x, z) in {**SMALL, PARENT: PARENT_POSITION}.items():
        obj = app.world.object_by_id(ident)
        assert obj is not None and not obj.solid
        assert not app.world.collides_player(x + 18, z + 10, 1, 1)


def test_save_failure_does_not_start_scene_or_mark_collection():
    app, storage = app3()
    before = app.office.week3_progress.snapshot()
    storage.fail = True
    assert not app.begin_week3_target(next(iter(SMALL)))
    assert app.office.week3_progress.snapshot() == before
    assert getattr(app, "week3_dialogue", None) is None


def test_invalid_terminal_and_completion_states_are_rejected():
    p = Week3Progress()
    raw = p.snapshot()
    raw["recovered"] = [next(iter(SMALL))]
    with pytest.raises(ValueError):
        Week3Progress.restore(raw)
    raw = p.snapshot()
    raw["parent_recovered"] = True
    with pytest.raises(ValueError):
        Week3Progress.restore(raw)


def test_completed_week2_next_button_dispatches_authored_week3():
    from drift_with_me.july_week2 import SITES
    from test_july_week2 import app2

    app, _ = app2(True)
    app.office.week2_progress.checked = set(SITES)
    app.office.finish_week()
    app.screen = AppScreen.OFFICE
    app.mouse_pressed_in = lambda rect: rect == app.office_next_week_rect()
    app.update_office_screen(0)
    assert app.week_transition is not None
    assert app.week_transition.target == WorkWeek(7, 3)


def parent_ready(app):
    p = app.office.week3_progress
    p.found = p.recovered = set(SMALL)
    p.parent_seen = True
    install_week3_world(app)
    app.presentation_time = 0


@pytest.mark.parametrize("assisted", [False, True])
def test_story_parent_ring_clear_disconnect_collection_and_single_default_reward(assisted):
    from drift_with_me.ring_linkage import solution_counts

    app, _ = app3()
    app.model.energy = 0
    parent_ready(app)
    assert app.open_story_ring()
    puzzle = app.ring_preview
    if assisted:
        assert puzzle.assist()
        assert app.ring_preview_store.save_progress(puzzle)
    for i, c in enumerate(solution_counts(puzzle.angles, puzzle.disabled_links)):
        for _ in range(min(c, 12 - c)):
            puzzle.selected = i
            assert puzzle.rotate(1 if c <= 6 else -1)
            puzzle.tick(0.16)
    assert app.ring_preview_store.save_progress(puzzle)
    p = app.office.week3_progress
    assert p.ring_unlocked and p.rewards.sunglasses_received
    assert puzzle.special_praise_earned is (not assisted)
    for dt in (0.35, 1.4, 3.2):
        puzzle.tick(dt)
    assert not p.rewards.claim(puzzle)
    assert app.close_story_ring()
    for dt in DURATIONS:
        assert app.update_july_week3(dt)
    p = app.office.week3_progress
    assert p.parent_stopped and p.parent_recovered and p.rewards.sunglasses_received
    assert app.model.energy == 0 and app.world.object_by_id(PARENT) is None
    assert not app.begin_week3_target(PARENT)
    restored = decode(encode(snapshot(app)))[1][WorkWeek(7, 3)].week3_progress
    assert restored.parent_recovered and restored.rewards.sunglasses_received
    assert not app.office.complete and not app.can_begin_next_week()


def test_story_exit_resets_board_keeps_help_and_never_uses_debug_namespace():
    app, storage = app3()
    parent_ready(app)
    assert app.open_story_ring()
    puzzle = app.ring_preview
    puzzle.assist()
    assert app.ring_preview_store.save_progress(puzzle)
    puzzle.rotate(1)
    puzzle.tick(0.16)
    assert app.close_story_ring()
    assert not app.office.week3_progress.rewards.sunglasses_received
    assert app.open_story_ring()
    assert app.ring_preview.angles == [1, 0, 5, 0, 11]
    assert app.ring_preview.disabled_links == app.ring_preview.help_history == [4]
    assert app.ring_preview.eligibility_forfeited
    assert not app.ring_preview.undo_history
    assert all("debug." not in key for key in storage.items)
    assert (
        not {"angles", "undo_history", "selected", "turn"}
        & app.office.week3_progress.snapshot().keys()
    )


def test_story_help_save_failure_rolls_back_both_puzzle_and_permanent_facts():
    from types import SimpleNamespace

    app, storage = app3()
    parent_ready(app)
    app.open_story_ring()
    app.pointer_snapshot = SimpleNamespace(pressed=True, down=False, x=0, y=0)
    app.mouse_pressed_in = lambda rect: rect == app.ring_preview_rects()["help"]
    storage.fail = True
    app.update_ring_preview()
    assert app.ring_preview.help_history == []
    assert app.office.week3_progress.ring_help == []


def test_parent_scene_resume_preserves_stop_and_does_not_grant_again():
    app, _ = app3()
    parent_ready(app)
    p = app.office.week3_progress
    p.ring_unlocked = True
    assert app.begin_parent_disconnect()
    for dt in DURATIONS[:2]:
        app.update_july_week3(dt)
    restored = decode(encode(snapshot(app)))[1][WorkWeek(7, 3)].week3_progress
    assert restored.parent_stopped and restored.active_scene == PARENT
    app.office.week3_progress = restored
    app.week3_scene_elapsed = 0
    for dt in DURATIONS[2:]:
        app.update_july_week3(dt)
    assert app.office.week3_progress.parent_recovered
    assert app.office.week3_progress.rewards.sunglasses_received


def test_story_preview_during_week_debug_never_changes_normal_save():
    app, storage = app3(debug=True)
    parent_ready(app)
    before = deepcopy(storage.items)
    app.open_story_ring()
    app.ring_preview.assist()
    assert app.ring_preview_store.save_progress(app.ring_preview)
    app.close_story_ring()
    assert storage.items == before


def test_device_scene_and_ring_do_not_start_during_existing_combat():
    app, _ = app3()
    app.model.combat_session = object()
    assert not app.begin_week3_target(next(iter(SMALL)))
    p = app.office.week3_progress
    p.found = p.recovered = set(SMALL)
    assert not app.open_story_ring()
    assert p.active_scene is None


@pytest.mark.parametrize("projection", ["affine", "perspective"])
def test_rotating_cube_culls_rear_faces_and_keeps_black_fill_white_edges(projection):
    from types import SimpleNamespace

    from drift_with_me.july_week3 import draw_cube
    from drift_with_me.math3d import Vec3
    from test_affine_projection import make_affine_camera

    _, _, perspective, _, affine = make_affine_camera()
    camera = affine if projection == "affine" else perspective
    calls = []
    painter = SimpleNamespace(
        tri=lambda *args: calls.append(("fill", args)),
        line=lambda *args: calls.append(("edge", args)),
    )
    frames = []
    for spin in (0.0, 2.0, 4.0, 8.0, 16.0):
        calls.clear()
        draw_cube(painter, camera, camera.target.x, camera.target.z, spin=spin)
        fills = [a for kind, a in calls if kind == "fill"]
        edges = [a for kind, a in calls if kind == "edge"]
        assert 2 <= len(fills) <= 6 and len(fills) % 2 == 0
        assert 4 <= len(edges) <= 9  # Never all twelve wireframe edges.
        assert all(a[-1] == 0 for a in fills) and all(a[-1] == 7 for a in edges)
        assert [kind for kind, _ in calls] == ["fill"] * len(fills) + ["edge"] * len(edges)
        for x0, y0, x1, y1, x2, y2, _ in fills:
            assert (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0) > 0
        frames.append(tuple(edges))
    assert len(set(frames)) == 5
    # Geometry is presentation only; projecting behind the near plane draws nothing.
    calls.clear()
    from dataclasses import replace

    draw_cube(painter, replace(perspective, target=Vec3(0, 0, 0)), 0, -10000)
    assert not calls


@pytest.mark.parametrize("ident", [*SMALL, PARENT])
def test_cube_spin_freezes_at_terminal_stop_without_save_fields(ident):
    app, _ = app3()
    p = app.office.week3_progress
    p.active_scene = ident
    app.week3_cube_spin_origin = (ident, 12.0)
    p.scene_step = 0
    app.week3_scene_elapsed = 0.1
    moving = app.week3_cube_scene_spin()
    app.week3_scene_elapsed = 0.2
    assert app.week3_cube_scene_spin() > moving
    p.scene_step = 2 if ident == PARENT else 3
    app.week3_scene_elapsed = 0.0
    stopped = app.week3_cube_scene_spin()
    p.scene_step = 3
    app.week3_scene_elapsed = 0.4
    assert app.week3_cube_scene_spin() == stopped
    assert not any("spin" in k for k in p.snapshot())
