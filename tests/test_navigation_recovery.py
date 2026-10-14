"""Contact starts, exact swept bodies, bounded recovery and target correction."""

from copy import deepcopy

import pytest

from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import InputIntent
from drift_with_me.world import WorldData
from test_july_story import july_app


def run(model, seconds=12):
    for _ in range(round(seconds * 60)):
        model.update_auto_move([], 1 / 60)
        assert not model.world.collides_player(
            model.player.x, model.player.z, model.player_solid_half_x, model.player_solid_half_z
        )
        if model.auto_move_goal is None:
            return
    pytest.fail("navigation did not stop")


def test_contact_start_can_detour_without_manual_backstep():
    app = july_app()
    m = app.model
    m.player.x, m.player.z = 126.594927, 365.591088
    m.request_auto_move_goal(180, 380, [])
    assert m.auto_move_goal == (180, 380)
    run(m)
    assert (m.player.x, m.player.z) == pytest.approx((180, 380), abs=2)


def test_stock_goal_is_corrected_to_reachable_edge_without_entering_pile():
    m = july_app().model
    m.player.x, m.player.z = 288, 384
    m.request_auto_move_goal(236, 432, [])
    assert m.auto_move_goal is not None and m.auto_move_goal != (236, 432)
    goal = m.auto_move_goal
    assert abs(goal[0] - 236) + abs(goal[1] - 432) < 48
    run(m)
    assert (m.player.x, m.player.z) == pytest.approx(goal, abs=2)


def isolated(boxes, start):
    app = july_app()
    raw = deepcopy(app.world.raw)
    raw["objects"] = [
        {
            "id": f"box_{i}",
            "kind": "wall",
            "position": [x, 0, z],
            "solid": True,
            "half_extents_xz": [hx, hz],
        }
        for i, (x, z, hx, hz) in enumerate(boxes)
    ]
    app.model.world = WorldData(
        raw,
        app.world.chunk_size,
        app.world.static_visual_max_height,
        app.world.visual_detail_per_chunk,
    )
    app.model.player.x, app.model.player.z = start
    return app.model


def test_corner_detour_never_clips_the_actual_rectangle():
    m = isolated([(200, 200, 20, 20)], (150, 200))
    m.request_auto_move_goal(250, 200, [])
    assert len(m.auto_move_path) > 1
    run(m)
    assert (m.player.x, m.player.z) == pytest.approx((250, 200), abs=2)


def test_narrow_corridor_uses_body_extents_rather_than_extra_clearance():
    m = isolated([(200, 150, 80, 40), (200, 260, 80, 40)], (90, 205))
    m.request_auto_move_goal(310, 205, [])
    assert m.auto_move_goal is not None
    run(m)
    assert (m.player.x, m.player.z) == pytest.approx((310, 205), abs=2)


def test_locked_landing_cannot_be_cut_by_smoothing():
    m = july_app().model
    landing = m.world.east_site_landing_rect
    assert landing is not None
    m.world.east_site_access_ready = False
    a = (landing.min_x - 30, (landing.min_z + landing.max_z) / 2)
    b = (landing.max_x + 30, a[1])
    assert m.smooth_auto_move_path([a, b]) is None


def test_unreachable_goal_cancels_previous_goal_and_stops():
    m = isolated([(400, 512, 10, 512)], (200, 200))
    m.request_auto_move_goal(220, 200, [])
    assert m.auto_move_goal is not None
    m.request_auto_move_goal(600, 200, [])
    assert m.auto_move_goal is None
    before = (m.player.x, m.player.z)
    for _ in range(120):
        m.update_auto_move([], 1 / 60)
    assert (m.player.x, m.player.z) == before


def test_stuck_replans_once_then_stops_instead_of_oscillating(monkeypatch):
    m = isolated([], (100, 100))
    m.request_auto_move_goal(200, 100, [])
    attempts = []
    original = m.plan_auto_move_goal
    monkeypatch.setattr(
        m, "plan_auto_move_goal", lambda *goal: (attempts.append(goal), original(*goal))[1]
    )
    monkeypatch.setattr(m, "move_player_by_delta", lambda x, z: 0)
    for _ in range(180):
        m.update_auto_move([], 1 / 60)
    assert len(attempts) == 1
    assert m.auto_move_goal is None


def test_world_replacement_invalidates_path_once_and_replans(monkeypatch):
    m = isolated([], (100, 100))
    m.request_auto_move_goal(250, 100, [])
    m.world = isolated([(180, 100, 8, 40)], (100, 100)).world
    attempts = []
    original = m.plan_auto_move_goal
    monkeypatch.setattr(
        m, "plan_auto_move_goal", lambda *goal: (attempts.append(goal), original(*goal))[1]
    )
    run(m)
    assert len(attempts) == 1
    assert (m.player.x, m.player.z) == pytest.approx((250, 100), abs=2)


def test_new_request_and_manual_input_reset_recovery_and_cancel_movement():
    m = isolated([], (100, 100))
    camera = CameraState.from_config(m.config, Vec3(100, 0, 100), 512, 236)
    m.request_auto_move_goal(200, 100, [])
    m.request_auto_move_goal(100, 200, [])
    assert m.auto_move_goal == (100, 200) and m.auto_move_replans_remaining == 1
    m.step(InputIntent(screen_x=1, strength=1), camera, 1 / 60)
    assert m.auto_move_goal is None


def test_unreachable_blocked_target_has_bounded_correction_radius():
    m = isolated([(400, 400, 120, 120)], (100, 100))
    m.request_auto_move_goal(400, 400, [])
    assert m.auto_move_goal is None


def test_speed_resources_and_save_resume_keep_navigation_transient():
    from drift_with_me.july_week1 import install_july_world
    from drift_with_me.save_state import decode, encode, snapshot

    app = july_app()
    m = app.model
    m.player.x, m.player.z = 126.594927, 365.591088
    resources = m.water, m.energy
    m.request_auto_move_goal(180, 380, [])
    saved = snapshot(app)
    _, offices, *_ = decode(encode(saved))
    app.office = offices[app.work_week]
    install_july_world(app, combat=True)
    run(m)
    assert (m.water, m.energy) == resources
    assert snapshot(app) == saved
    straight = isolated([], (100, 100))
    straight.request_auto_move_goal(200, 100, [])
    straight.update_auto_move([], 1 / 60)
    assert straight.player.x - 100 == pytest.approx(straight.config["player"]["move_speed"] / 60)


def test_construction_collision_is_not_a_foreground_box_pick(monkeypatch):
    from types import SimpleNamespace

    from drift_with_me.app import DriftWithMeApp

    app = july_app()
    body = next(o for o in app.world.objects if o.kind == "construction_collision")
    app.world = SimpleNamespace(objects=[body])
    app.renderer = SimpleNamespace(
        object_occlusion_depth=lambda *args: 0,
        object_ground_pick_block_bounds=lambda *args: pytest.fail(
            "invisible collider was rendered"
        ),
    )
    app.foreground_pick_margin_px = lambda: 0
    camera = SimpleNamespace(project=lambda point: SimpleNamespace(depth=1))
    assert not DriftWithMeApp.foreground_object_blocks_ground_pick(app, camera, 10, 10, 180, 380)
