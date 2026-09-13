from __future__ import annotations

import pytest

from drift_with_me.camera import CameraController, camera_ground_axes
from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import Vec3
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.world import load_world_data


def make_controller() -> tuple[CameraController, GameModel]:
    runtime = load_runtime_config()
    world = load_world_data()
    model = GameModel(runtime.raw, world)
    controller = CameraController(
        runtime.raw,
        world,
        runtime.screen_width,
        runtime.screen_height,
        Vec3(model.player.x, 0.0, model.player.z),
    )
    model.snap_buddy(controller.current)
    return controller, model


def test_overview_zone_uses_player_position_and_exit_margin() -> None:
    controller, model = make_controller()

    model.player.x = 700.0
    model.player.z = 700.0
    controller.update(0.1, model.player.x, model.player.z)

    assert controller.active_zone_id == "overview_north"
    assert controller.mode_name == "OVERVIEW"

    model.player.x = 620.0
    model.player.z = 620.0
    controller.update(0.1, model.player.x, model.player.z)

    assert controller.active_zone_id == "overview_north"

    model.player.x = 600.0
    model.player.z = 600.0
    controller.update(0.1, model.player.x, model.player.z)

    assert controller.active_zone_id is None


def test_pan_demo_sequence_freezes_world_and_returns_to_base() -> None:
    controller, _model = make_controller()

    assert controller.start_pan_demo()
    assert controller.mode_name == "EVENT_PAN"
    assert controller.freezes_world

    for _ in range(220):
        controller.update(1.0 / 60.0, 160.0, 160.0)

    assert controller.sequence is None
    assert not controller.freezes_world
    assert controller.mode_name == "FOLLOW"


def test_actor_focus_point_frames_target_slightly_below_center() -> None:
    controller, model = make_controller()
    target = Vec3(model.player.x, model.player_cube_size * 0.5, model.player.z)

    controller.start_focus_point(target, hold_sec=1.0)
    camera = controller.update(1.0, model.player.x, model.player.z)
    projected = camera.project(target)

    assert projected is not None
    assert projected.x == pytest.approx(controller.viewport_width * 0.5)
    assert projected.y == pytest.approx(controller.viewport_height * 0.56)
    assert camera.distance == pytest.approx(
        float(controller.camera_config["base_distance"])
        / float(controller.camera_config["zoom_max"])
    )


def test_buddy_follows_camera_relative_goal_without_affecting_movement() -> None:
    controller, model = make_controller()
    start_x = model.player.x

    for _ in range(30):
        model.step(InputIntent(screen_x=1.0, strength=1.0), controller.current, 1.0 / 60.0)
        controller.update(1.0 / 60.0, model.player.x, model.player.z)

    assert model.player.x != start_x
    assert model.buddy.distance_to_goal() < 24.0
    assert model.buddy.distance_to_goal() > 0.0


def test_buddy_repositions_behind_jack_for_side_facing() -> None:
    controller, model = make_controller()
    screen_right, ground_forward = camera_ground_axes(controller.current)

    model.player.last_move_x = screen_right.x
    model.player.last_move_z = screen_right.y
    right_facing_goal = model.buddy_goal(controller.current)
    right_dx = right_facing_goal[0] - model.player.x
    right_dz = right_facing_goal[2] - model.player.z

    assert right_dx * screen_right.x + right_dz * screen_right.y == pytest.approx(-20.0)
    assert right_dx * ground_forward.x + right_dz * ground_forward.y == pytest.approx(-12.0)
    assert model.buddy_side_reposition_active(controller.current)
    assert model.buddy_follow_tau(controller.current) == pytest.approx(0.08)

    model.player.last_move_x = -screen_right.x
    model.player.last_move_z = -screen_right.y
    left_facing_goal = model.buddy_goal(controller.current)
    left_dx = left_facing_goal[0] - model.player.x
    left_dz = left_facing_goal[2] - model.player.z

    assert left_dx * screen_right.x + left_dz * screen_right.y == pytest.approx(20.0)
    assert left_dx * ground_forward.x + left_dz * ground_forward.y == pytest.approx(-12.0)
    assert model.buddy_side_reposition_active(controller.current)


def test_buddy_keeps_camera_relative_goal_when_jack_faces_front_or_back() -> None:
    controller, model = make_controller()
    screen_right, ground_forward = camera_ground_axes(controller.current)

    model.player.last_move_x = ground_forward.x
    model.player.last_move_z = ground_forward.y
    goal = model.buddy_goal(controller.current)
    dx = goal[0] - model.player.x
    dz = goal[2] - model.player.z

    assert dx * screen_right.x + dz * screen_right.y == pytest.approx(-20.0)
    assert dx * ground_forward.x + dz * ground_forward.y == pytest.approx(-12.0)
    assert not model.buddy_side_reposition_active(controller.current)
    assert model.buddy_follow_tau(controller.current) == pytest.approx(0.18)
