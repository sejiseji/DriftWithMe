from __future__ import annotations

import math

from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import (
    AffineProjectionProfile,
    CameraState,
    Vec3,
    affine_camera_from_perspective,
)
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
    right_model, right_camera = make_model()
    diagonal_model, diagonal_camera = make_model()
    runtime = load_runtime_config()
    profile = AffineProjectionProfile.from_config(runtime.raw)
    affine_camera = affine_camera_from_perspective(
        axis_camera,
        profile,
        base_distance=float(runtime.raw["camera"]["base_distance"]),
    )
    axis_before = affine_camera.project(Vec3(axis_model.player.x, 0.0, axis_model.player.z))
    right_before = affine_camera.project(Vec3(right_model.player.x, 0.0, right_model.player.z))
    diagonal_before = affine_camera.project(
        Vec3(diagonal_model.player.x, 0.0, diagonal_model.player.z)
    )
    dt = 1.0 / 60.0
    diagonal = 1.0 / math.sqrt(2.0)

    for _ in range(60):
        axis_model.step(InputIntent(screen_y=-1.0, strength=1.0), axis_camera, dt)
        right_model.step(InputIntent(screen_x=1.0, strength=1.0), right_camera, dt)
        diagonal_model.step(
            InputIntent(screen_x=diagonal, screen_y=-diagonal, strength=1.0),
            diagonal_camera,
            dt,
        )

    axis_after = affine_camera.project(Vec3(axis_model.player.x, 0.0, axis_model.player.z))
    right_after = affine_camera.project(Vec3(right_model.player.x, 0.0, right_model.player.z))
    diagonal_after = affine_camera.project(
        Vec3(diagonal_model.player.x, 0.0, diagonal_model.player.z)
    )
    assert axis_before is not None and axis_after is not None
    assert right_before is not None and right_after is not None
    assert diagonal_before is not None and diagonal_after is not None
    axis_screen_distance = math.hypot(
        axis_after.x - axis_before.x,
        axis_after.y - axis_before.y,
    )
    right_screen_distance = math.hypot(
        right_after.x - right_before.x,
        right_after.y - right_before.y,
    )
    diagonal_screen_distance = math.hypot(
        diagonal_after.x - diagonal_before.x,
        diagonal_after.y - diagonal_before.y,
    )
    assert diagonal_screen_distance <= max(axis_screen_distance, right_screen_distance) + 0.5


def test_affine_manual_axis_input_moderately_boosts_vertical_screen_distance() -> None:
    right_model, base_camera = make_model()
    up_model, _ = make_model()
    baseline_up_model, _ = make_model()
    runtime = load_runtime_config()
    profile = AffineProjectionProfile.from_config(runtime.raw)
    camera = affine_camera_from_perspective(
        base_camera,
        profile,
        base_distance=float(runtime.raw["camera"]["base_distance"]),
    )
    right_before = camera.project(Vec3(right_model.player.x, 0.0, right_model.player.z))
    up_before = camera.project(Vec3(up_model.player.x, 0.0, up_model.player.z))
    baseline_up_before = camera.project(
        Vec3(baseline_up_model.player.x, 0.0, baseline_up_model.player.z)
    )

    right_model.step(InputIntent(screen_x=1.0, strength=1.0), base_camera, 1.0 / 60.0)
    up_model.step(InputIntent(screen_y=-1.0, strength=1.0), base_camera, 1.0 / 60.0)
    baseline_up_model.config["player"]["manual_affine_screen_speed_equalize"] = False
    baseline_up_model.step(InputIntent(screen_y=-1.0, strength=1.0), base_camera, 1.0 / 60.0)

    right_after = camera.project(Vec3(right_model.player.x, 0.0, right_model.player.z))
    up_after = camera.project(Vec3(up_model.player.x, 0.0, up_model.player.z))
    baseline_up_after = camera.project(
        Vec3(baseline_up_model.player.x, 0.0, baseline_up_model.player.z)
    )

    assert right_before is not None and right_after is not None
    assert up_before is not None and up_after is not None
    assert baseline_up_before is not None and baseline_up_after is not None
    right_screen_distance = math.hypot(
        right_after.x - right_before.x,
        right_after.y - right_before.y,
    )
    up_screen_distance = math.hypot(up_after.x - up_before.x, up_after.y - up_before.y)
    baseline_up_screen_distance = math.hypot(
        baseline_up_after.x - baseline_up_before.x,
        baseline_up_after.y - baseline_up_before.y,
    )
    assert up_screen_distance > baseline_up_screen_distance * 1.35
    assert up_screen_distance < right_screen_distance * 0.7


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
