from __future__ import annotations

import math

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import (
    AffineProjectionProfile,
    CameraState,
    Vec3,
    affine_camera_from_perspective,
    screen_to_ground_affine,
)
from drift_with_me.world import load_world_data


def make_affine_camera():
    runtime = load_runtime_config()
    world = load_world_data()
    target = Vec3(world.spawn_x, 0.0, world.spawn_z)
    perspective = CameraState.from_config(
        runtime.raw,
        target,
        runtime.screen_width,
        runtime.screen_height,
    )
    profile = AffineProjectionProfile.from_config(runtime.raw)
    affine = affine_camera_from_perspective(
        perspective,
        profile,
        base_distance=float(runtime.raw["camera"]["base_distance"]),
    )
    return runtime, world, perspective, profile, affine


def test_affine_profile_matches_current_follow_projection_measurement() -> None:
    _runtime, world, perspective, profile, _affine = make_affine_camera()
    step = 32.0
    origin = Vec3(world.spawn_x, 0.0, world.spawn_z)
    p0 = perspective.project(origin)
    px = perspective.project(Vec3(origin.x + step, origin.y, origin.z))
    py = perspective.project(Vec3(origin.x, origin.y + step, origin.z))
    pz = perspective.project(Vec3(origin.x, origin.y, origin.z + step))
    assert p0 is not None and px is not None and py is not None and pz is not None

    assert profile.basis_x.x == pytest.approx((px.x - p0.x) / step)
    assert profile.basis_x.y == pytest.approx((px.y - p0.y) / step)
    assert profile.basis_y.x == pytest.approx((py.x - p0.x) / step)
    assert profile.basis_y.y == pytest.approx((py.y - p0.y) / step)
    assert profile.basis_z.x == pytest.approx((pz.x - p0.x) / step)
    assert profile.basis_z.y == pytest.approx((pz.y - p0.y) / step)


def test_affine_ground_basis_is_invertible() -> None:
    _runtime, _world, _perspective, profile, _affine = make_affine_camera()

    assert math.isfinite(profile.ground_determinant)
    assert abs(profile.ground_determinant) > 1e-6


def test_affine_world_to_screen_to_ground_round_trip() -> None:
    _runtime, _world, _perspective, _profile, affine = make_affine_camera()
    max_error = 0.0

    for point in (
        Vec3(160.0, 0.0, 160.0),
        Vec3(220.0, 0.0, 240.0),
        Vec3(96.0, 0.0, 288.0),
        Vec3(320.0, 0.0, 128.0),
    ):
        projected = affine.project(point)
        assert projected is not None
        picked = screen_to_ground_affine(affine, projected.x, projected.y)
        assert picked is not None
        max_error = max(max_error, abs(picked.x - point.x), abs(picked.y - point.z))

    assert max_error <= 1e-9


def test_affine_screen_to_ground_to_screen_round_trip() -> None:
    _runtime, _world, _perspective, _profile, affine = make_affine_camera()
    max_error = 0.0

    for screen_x, screen_y in (
        (256.0, 136.88),
        (300.0, 120.0),
        (180.0, 180.0),
        (420.0, 92.0),
    ):
        picked = screen_to_ground_affine(affine, screen_x, screen_y)
        assert picked is not None
        projected = affine.project(Vec3(picked.x, 0.0, picked.y))
        assert projected is not None
        max_error = max(max_error, abs(projected.x - screen_x), abs(projected.y - screen_y))

    assert max_error <= 1e-9


def test_affine_xz_screen_vectors_are_position_invariant() -> None:
    _runtime, _world, _perspective, _profile, affine = make_affine_camera()
    base = Vec3(96.0, 0.0, 128.0)
    comparison = Vec3(352.0, 0.0, 416.0)

    base_root = affine.project(base)
    base_x = affine.project(Vec3(base.x + 32.0, base.y, base.z))
    base_z = affine.project(Vec3(base.x, base.y, base.z + 32.0))
    comparison_root = affine.project(comparison)
    comparison_x = affine.project(Vec3(comparison.x + 32.0, comparison.y, comparison.z))
    comparison_z = affine.project(Vec3(comparison.x, comparison.y, comparison.z + 32.0))
    assert (
        base_root is not None
        and base_x is not None
        and base_z is not None
        and comparison_root is not None
        and comparison_x is not None
        and comparison_z is not None
    )

    assert comparison_x.x - comparison_root.x == pytest.approx(base_x.x - base_root.x)
    assert comparison_x.y - comparison_root.y == pytest.approx(base_x.y - base_root.y)
    assert comparison_z.x - comparison_root.x == pytest.approx(base_z.x - base_root.x)
    assert comparison_z.y - comparison_root.y == pytest.approx(base_z.y - base_root.y)
