from __future__ import annotations

import math

from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.world import WorldData, load_world_data


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


def test_screen_right_input_moves_projection_right() -> None:
    model, camera = make_model()
    before = camera.project(Vec3(model.player.x, 0.0, model.player.z))

    model.step(InputIntent(screen_x=1.0, strength=1.0), camera, 1.0 / 60.0)
    after_camera = CameraState(
        target=camera.target,
        yaw_deg=camera.yaw_deg,
        pitch_deg=camera.pitch_deg,
        horizontal_fov_deg=camera.horizontal_fov_deg,
        distance=camera.distance,
        near=camera.near,
        far=camera.far,
        anchor_x=camera.anchor_x,
        anchor_y=camera.anchor_y,
        viewport_width=camera.viewport_width,
        viewport_height=camera.viewport_height,
    )
    after = after_camera.project(Vec3(model.player.x, 0.0, model.player.z))

    assert before is not None and after is not None
    assert after.x > before.x


def test_diagonal_movement_is_not_faster_than_axis_movement() -> None:
    axis_model, axis_camera = make_model()
    diagonal_model, diagonal_camera = make_model()
    dt = 1.0 / 60.0
    diagonal = 1.0 / math.sqrt(2.0)

    for _ in range(60):
        axis_model.step(InputIntent(screen_y=-1.0, strength=1.0), axis_camera, dt)
        diagonal_model.step(
            InputIntent(screen_x=diagonal, screen_y=-diagonal, strength=1.0),
            diagonal_camera,
            dt,
        )

    assert axis_model.player.moved_distance == pytest_approx(diagonal_model.player.moved_distance)


def test_released_input_stops_on_next_step() -> None:
    model, camera = make_model()

    model.step(InputIntent(screen_x=1.0, strength=1.0), camera, 1.0 / 60.0)
    moved_x = model.player.x
    moved_z = model.player.z
    model.step(InputIntent(), camera, 1.0 / 60.0)

    assert model.player.x == moved_x
    assert model.player.z == moved_z


def test_world_bounds_include_player_half_extent() -> None:
    runtime = load_runtime_config()
    world = load_world_data()
    half_x = runtime.raw["player"]["collider_half_x"]
    half_z = runtime.raw["player"]["collider_half_z"]

    x, z = world.move_player_sliding(half_x, half_z, -999.0, -999.0, half_x, half_z)

    assert x == half_x
    assert z == half_z


def test_world_loads_split_bounds_and_legacy_fallback() -> None:
    world = load_world_data()

    assert world.walkable_rect.min_x == 0.0
    assert world.walkable_rect.max_x == 1024.0
    assert world.camera_target_rect == world.walkable_rect
    assert world.visual_ground_rect.min_x == -256.0
    assert world.visual_ground_rect.max_z == 1280.0
    assert world.content_rect.min_x == -256.0
    assert world.minimap_rect == world.walkable_rect

    legacy_raw = dict(world.raw)
    legacy_raw.pop("bounds", None)
    legacy_world = WorldData(legacy_raw, visual_detail_per_chunk=0)

    assert legacy_world.walkable_rect.min_x == 0.0
    assert legacy_world.walkable_rect.max_x == legacy_world.width
    assert legacy_world.visual_ground_rect == legacy_world.walkable_rect
    assert legacy_world.minimap_rect == legacy_world.walkable_rect


def test_player_collision_uses_walkable_bounds_not_visual_ground() -> None:
    runtime = load_runtime_config()
    world = load_world_data()
    half_x = runtime.raw["player"]["collider_half_x"]
    half_z = runtime.raw["player"]["collider_half_z"]

    assert not world.collides_player(
        world.walkable_rect.min_x + half_x,
        world.walkable_rect.min_z + half_z,
        half_x,
        half_z,
    )
    assert world.visual_ground_rect.contains_point(-32.0, 160.0)
    assert world.collides_player(-32.0, 160.0, half_x, half_z)


def test_wall_collision_slides_along_tangent_axis() -> None:
    runtime = load_runtime_config()
    world = load_world_data()
    half_x = runtime.raw["player"]["collider_half_x"]
    half_z = runtime.raw["player"]["collider_half_z"]

    x, z = world.move_player_sliding(296.0, 300.0, 32.0, 32.0, half_x, half_z)

    assert x <= 296.0
    assert z > 300.0


def test_player_solid_collision_margin_keeps_sprite_clear_of_box() -> None:
    model, _camera = make_model()
    margin = float(model.config["player"]["solid_collision_margin"])
    wall = model.world.object_by_id("wall_01")
    assert wall is not None
    assert margin > 0.0

    model.player.x = wall.min_x - model.player_solid_half_x - 24.0
    model.player.z = wall.z
    model.move_player_by_delta(96.0, 0.0)

    assert model.player.x <= wall.min_x - model.player_solid_half_x


def pytest_approx(value: float):
    import pytest

    return pytest.approx(value, rel=0.01, abs=0.01)
