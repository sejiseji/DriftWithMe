from __future__ import annotations

import pytest

from drift_with_me.app import DriftWithMeApp
from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import ProjectedPoint
from drift_with_me.swarm_water import (
    MAX_ROWS,
    MAX_SPRAY,
    MAX_STREAMS,
    SPRAY_LIFETIME_MAX,
    STREAM_PIXELS,
    WATER_COLORS,
    draw_water_spear,
    spray_samples,
    surface_samples,
)
from test_swarm_field import enter, setup_field


class Pixels:
    def __init__(self):
        self.calls = []

    def rect(self, *args):
        self.calls.append(("rect", args))

    def pset(self, *args):
        self.calls.append(("pset", args))


def test_group_only_camera_framing_keeps_shared_zoom_and_real_actor_positions():
    model, camera, field = setup_field()
    enter(model, camera, field)
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.model, app.runtime = model, load_runtime_config()
    app.combat_camera_snapshot_zoom = None
    app.projection_mode = "perspective"
    app.camera = lambda: camera
    app.presentation_camera = lambda c: c
    before = (model.player.x, model.player.z, model.buddy.x, model.buddy.y, model.buddy.z)
    field.battle.phase, field.battle.total_elapsed = "ready", 4
    session = field.presentation_session()
    group = app.swarm_scene_camera(session)
    standard = app.combat_camera_for_session(camera, session, camera.target)
    assert group.distance == standard.distance
    assert group.anchor_y == pytest.approx(0.70) and group.anchor_y > standard.anchor_y
    assert app.combat_scene_camera(camera) is camera  # Ordinary field/single route is untouched.
    field.battle.phase, field.battle.total_elapsed = "entry", 0
    first = app.swarm_scene_camera(field.presentation_session())
    assert first.anchor_y == camera.anchor_y
    field.battle.phase, field.battle.elapsed = "victory", 10
    end = app.swarm_scene_camera(field.presentation_session())
    assert end.anchor_y == camera.anchor_y
    assert before == (model.player.x, model.player.z, model.buddy.x, model.buddy.y, model.buddy.z)


def test_group_entry_offset_interpolates_without_a_frame_step():
    model, camera, field = setup_field()
    enter(model, camera, field)
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.model, app.runtime = model, load_runtime_config()
    app.combat_camera_snapshot_zoom = None
    app.projection_mode = "perspective"
    app.camera = lambda: camera
    app.presentation_camera = lambda c: c
    field.battle.phase = "entry"
    positions = []
    for i in range(31):
        field.battle.total_elapsed = i / 60
        c = app.swarm_scene_camera(field.presentation_session())
        positions.append(c.anchor_y * c.viewport_height)
    assert positions == sorted(positions)
    assert max(b - a for a, b in zip(positions, positions[1:], strict=False)) < 2


def test_diagonal_surface_clusters_move_up_and_sideways_coherently():
    a = surface_samples(100, 150, 14, 48, 0.05)
    b = surface_samples(100, 150, 14, 48, 0.15)
    assert len(a) == len(b) == MAX_STREAMS
    # Track one unwrapped cluster: upward motion is accompanied by lateral flow.
    assert b[0][1] < a[0][1] and b[0][0] != a[0][0]
    assert a == surface_samples(100, 150, 14, 48, 0.05)
    assert all(color in WATER_COLORS for _, _, color in a)


def test_spray_has_ballistic_up_then_down_motion_and_finite_lifetime():
    samples = [spray_samples(100, 150, 14, 48, t)[0] for t in (0.05, 0.15, 0.25)]
    assert samples[1].y < samples[0].y
    # Follow the same first droplet analytically past its peak while still alive.
    at_peak = spray_samples(100, 150, 14, 48, 0.19)[0]
    falling = spray_samples(100, 150, 14, 48, 0.265)[0]
    assert falling.y > at_peak.y
    for step in range(61):
        dots = spray_samples(100, 150, 14, 48, step / 100)
        assert len(dots) <= MAX_SPRAY
        assert all(0 <= d.age <= d.lifetime <= SPRAY_LIFETIME_MAX + 1e-9 for d in dots)
    assert spray_samples(100, 150, 14, 48, 1) == ()


@pytest.mark.parametrize("elapsed", [0, 0.08, 0.16, 0.30, 0.45, 0.59])
def test_native_pixel_spear_has_bounded_work_and_existing_water_palette(elapsed):
    p = Pixels()
    stats = draw_water_spear(
        p,
        ProjectedPoint(80, 150, 1),
        ProjectedPoint(120, 150, 1),
        ProjectedPoint(100, -1000, 1),
        ProjectedPoint(100, 150, 1),
        elapsed,
    )
    assert stats["rows"] <= MAX_ROWS and stats["stream_clusters"] <= MAX_STREAMS
    assert stats["spray_particles"] <= MAX_SPRAY
    assert len(p.calls) <= MAX_ROWS * 3 + MAX_STREAMS * STREAM_PIXELS + MAX_SPRAY * 2
    assert all(args[-1] in WATER_COLORS for _, args in p.calls)
    assert {kind for kind, _ in p.calls} <= {"pset", "rect"}
