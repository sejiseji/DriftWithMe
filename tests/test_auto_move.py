from __future__ import annotations

import pytest

from drift_with_me.app import DriftWithMeApp
from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import CameraState, Vec3, screen_to_ground_point
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.render import Renderer
from drift_with_me.world import load_world_data


def make_model() -> tuple[GameModel, CameraState]:
    runtime = load_runtime_config()
    world = load_world_data()
    model = GameModel(runtime.raw, world)
    camera = CameraState.from_config(
        runtime.raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    return model, camera


def make_app_shell() -> tuple[DriftWithMeApp, CameraState]:
    runtime = load_runtime_config()
    world = load_world_data()
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = runtime
    app.world = world
    app.model = GameModel(runtime.raw, world)
    app.renderer = Renderer(None)
    camera = CameraState.from_config(
        runtime.raw,
        Vec3(app.model.player.x, 0.0, app.model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    return app, camera


def test_screen_to_ground_point_round_trips_projected_ground_point() -> None:
    _model, camera = make_model()
    projected = camera.project(Vec3(220.0, 0.0, 240.0))
    assert projected is not None

    picked = screen_to_ground_point(camera, projected.x, projected.y)

    assert picked is not None
    assert picked.x == pytest.approx(220.0, abs=1e-6)
    assert picked.y == pytest.approx(240.0, abs=1e-6)


def test_foreground_object_blocks_auto_move_pick() -> None:
    app, camera = make_app_shell()
    obj = app.world.object_by_id("wall_01")
    assert obj is not None
    assert app.renderer is not None
    bounds = app.renderer.object_screen_bounds(obj, camera)
    assert bounds is not None
    screen_x = bounds.x + bounds.width / 2.0
    screen_y = bounds.y + bounds.height / 2.0
    picked = screen_to_ground_point(camera, screen_x, screen_y)
    assert picked is not None

    assert app.foreground_object_blocks_ground_pick(camera, screen_x, screen_y, picked.x, picked.y)


def test_free_ground_does_not_block_auto_move_pick() -> None:
    app, camera = make_app_shell()
    projected = camera.project(Vec3(220.0, 0.0, 240.0))
    assert projected is not None

    assert not app.foreground_object_blocks_ground_pick(
        camera, projected.x, projected.y, 220.0, 240.0
    )


def test_auto_move_reaches_clear_goal_at_walk_speed() -> None:
    model, camera = make_model()
    goal_x = model.player.x + 48.0
    goal_z = model.player.z

    model.step(InputIntent(auto_move_goal_x=goal_x, auto_move_goal_z=goal_z), camera, 1.0 / 60.0)
    for _ in range(60):
        model.step(InputIntent(), camera, 1.0 / 60.0)

    assert model.auto_move_goal is None
    assert model.player.x == pytest.approx(goal_x, abs=2.0)
    assert model.player.z == pytest.approx(goal_z, abs=2.0)
    assert model.auto_move_path == []


def test_manual_input_cancels_auto_move_without_resuming() -> None:
    model, camera = make_model()

    model.step(
        InputIntent(auto_move_goal_x=model.player.x + 64.0, auto_move_goal_z=model.player.z),
        camera,
        1.0 / 60.0,
    )
    assert model.auto_move_goal is not None

    model.step(InputIntent(screen_x=1.0, strength=1.0), camera, 1.0 / 60.0)
    model.step(InputIntent(), camera, 1.0 / 60.0)

    assert model.auto_move_goal is None
    assert model.auto_move_path == []


def test_auto_move_rejects_goal_inside_solid_object() -> None:
    model, camera = make_model()

    events = model.step(
        InputIntent(auto_move_goal_x=320.0, auto_move_goal_z=320.0), camera, 1.0 / 60.0
    )

    assert model.auto_move_goal is None
    assert [event.payload["reason"] for event in events if event.kind == "action_denied"] == [
        "auto_move_blocked"
    ]


def test_auto_move_paths_around_static_wall() -> None:
    model, camera = make_model()
    model.player.x = 256.0
    model.player.z = 320.0

    first_events = model.step(
        InputIntent(auto_move_goal_x=384.0, auto_move_goal_z=320.0), camera, 1.0 / 60.0
    )

    assert [event.kind for event in first_events] == []
    assert model.auto_move_goal == (384.0, 320.0)
    assert len(model.auto_move_path) >= 2

    for _ in range(240):
        model.step(InputIntent(), camera, 1.0 / 60.0)
        if model.auto_move_goal is None:
            break

    assert model.auto_move_goal is None
    assert model.auto_move_path == []
    assert model.player.x == pytest.approx(384.0, abs=3.0)
    assert model.player.z == pytest.approx(320.0, abs=3.0)
