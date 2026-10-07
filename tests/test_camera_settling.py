import math

import pytest

from drift_with_me.camera import CameraController
from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import Vec3
from drift_with_me.world import load_world_data


def make_controller():
    runtime = load_runtime_config()
    return CameraController(runtime.raw, load_world_data(), 512, 236, Vec3(520, 0, 520))


@pytest.mark.parametrize("hz", (30, 60, 120))
def test_stop_settles_without_drift_or_snap_at_render_rates(hz):
    c = make_controller()
    x = 520.0
    point = Vec3(520, 0, 560)
    for _ in range(2 * hz):
        x += 18 / hz
        c.update(1 / hz, x, 520, 1, 0)
    positions = []
    for _ in range(4 * hz):
        positions.append(c.update(1 / hz, x, 520, 1, 0).project(point))
    final = positions[-1]
    residual = [math.hypot(p.x - final.x, p.y - final.y) for p in positions]
    assert residual[hz] < 0.06
    assert residual[2 * hz] < 0.001
    assert all(a >= b - 1e-8 for a, b in zip(residual, residual[1:], strict=False))
    assert (
        max(
            math.hypot(a.x - b.x, a.y - b.y) for a, b in zip(positions, positions[1:], strict=False)
        )
        < 4
    )


def test_turn_reverse_and_restart_remain_continuous_without_overshoot():
    c = make_controller()
    x, z = 520.0, 520.0
    point = Vec3(520, 0, 560)
    positions = []
    for direction in ((1, 0), (0, 1), (-1, 0), (-1, 0)):
        for _ in range(120):
            x += direction[0] * 0.3
            z += direction[1] * 0.3
            positions.append(c.update(1 / 60, x, z, *direction).project(point))
        for _ in range(90):
            positions.append(c.update(1 / 60, x, z, *direction).project(point))
        desired = c.directional_lookahead_offset(*direction)
        assert math.hypot(c.lookahead_offset.x - desired.x, c.lookahead_offset.y - desired.y) < 0.02
    assert (
        max(
            math.hypot(a.x - b.x, a.y - b.y) for a, b in zip(positions, positions[1:], strict=False)
        )
        < 4
    )


def test_tiny_input_does_not_reverse_last_real_movement_lookahead():
    c = make_controller()
    x = 520.0
    for _ in range(120):
        x += 0.3
        c.update(1 / 60, x, 520, 1, 0)
    for _ in range(180):
        c.update(1 / 60, x, 520, 1, 0)
    before = c.follow_target.x
    for frame in range(180):
        noise = 0.001 if frame % 2 else -0.001
        c.update(1 / 60, x + noise, 520, 1 if noise > 0 else -1, 0)
    assert not c.player_moving
    assert c.lookahead_offset.x > 0
    assert abs(c.follow_target.x - before) < 0.01
    c.reset(Vec3(x, 0, 520))
    assert not c.has_player_moved
    assert c.last_moving_direction == (None, None)


def test_motion_hysteresis_avoids_threshold_chatter():
    c = make_controller()
    x = 520.0
    x += 0.6 / 60
    c.update(1 / 60, x, 520, 1, 0)
    assert c.player_moving
    for speed in (0.3, 0.49, 0.21, 0.4):
        x += speed / 60
        c.update(1 / 60, x, 520, 1, 0)
        assert c.player_moving
    c.update(1 / 60, x, 520, 1, 0)
    assert not c.player_moving
    for speed in (0.21, 0.49, 0.3):
        x += speed / 60
        c.update(1 / 60, x, 520, -1, 0)
        assert not c.player_moving
