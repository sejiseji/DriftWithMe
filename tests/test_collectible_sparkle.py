"""Synthetic rendering/storage only; never opens a player's saves."""

import math
from types import SimpleNamespace

import pytest

from drift_with_me import collectible_sparkle as fx
from drift_with_me.collectibles import BY_ID, PREFIX
from drift_with_me.math3d import Vec3
from drift_with_me.render import Renderer
from test_collectibles import week_app
from test_field_visit import inspect


def test_approved_marker_timing_shapes_and_bounded_pool():
    assert fx.PARTICLE_COUNT == 18
    assert (len(fx.MARKER[0]), len(fx.MARKER)) == (11, 15)
    assert (fx.DECAY, fx.OMEGA, fx.BLINK_HZ) == (1.1, 2.7, 0.7)
    assert 3.09 < fx.BURST_SECONDS < 3.10
    shapes = set()
    for tick in range(270):
        particles = fx.particles(tick / 60)
        assert len(particles) <= 18
        for x, y, shape, color in particles:
            assert math.isfinite(x) and math.isfinite(y) and math.hypot(x, y) <= 32.001
            shapes.add(shape)
            assert color in (7, 10, 15)
    assert shapes == {"point", "cross", "diamond"}


@pytest.mark.parametrize("width,height", [(426, 196), (512, 236), (640, 294)])
def test_all_profiles_edges_and_offscreen_are_clipped_without_changing_clip_state(width, height):
    for x, y in (
        (0, 0),
        (width - 1, 0),
        (0, height - 1),
        (width - 1, height - 1),
        (-20, 20),
        (width + 20, height // 2),
    ):
        for tick in range(270):
            points = fx.pixels(x, y, tick / 60, "collectible_herb_fine", width, height)
            assert len(points) < 400
            assert all(0 <= px < width and 0 <= py < height and 0 <= c < 16 for px, py, c in points)


def test_loop_has_quiet_gap_and_staggered_dim_birth_instead_of_pool_flash():
    assert fx.particles(fx.LOOP_SECONDS - 1 / 60) == ()
    assert len(fx.particles(0)) == 1
    assert fx.particles(0)[0][2:] == ("point", 15)
    assert len(fx.particles(1 / 60)) == 1
    assert len(fx.particles(0.1)) <= 5
    assert fx.particles(3.2) == ()
    for t in (0.01, 0.4, 1.2, 3.2):
        assert fx.pixels(256, 125, t, "", 512, 236) == fx.pixels(256, 125, t + 4.5, "", 512, 236)
    assert fx.particles(float("inf")) == ()
    assert fx.particles(float("nan")) == ()


def test_center_stays_readable_and_revisits_have_no_residual_state():
    for tick in range(540):
        points = fx.pixels(256, 125, tick / 60, "collectible_herb_fine", 512, 236)
        final = {(x, y): c for x, y, c in points}
        assert final[256, 125] == 7
        for row, line in enumerate(fx.MARKER):
            for col, value in enumerate(line):
                if value != ".":
                    assert final[251 + col, 118 + row] == int(value, 16)
    first = fx.pixels(256, 125, 1.2, "a", 512, 236)
    fx.pixels(-100, -100, 400, "b", 512, 236)
    assert fx.pixels(256, 125, 1.2, "a", 512, 236) == first


def test_renderer_uses_existing_ground_depth_and_expanded_visibility_bounds():
    app, _ = week_app(BY_ID["herb_fine"])
    camera = app.camera()
    r = Renderer(SimpleNamespace())
    obj = app.world.object_by_id(PREFIX + "herb_fine")
    commands = r.world_commands(app.model, camera, 0)
    command = next(c for c in commands if c.stable_id == obj.id)
    root = camera.project(Vec3(obj.x, 0, obj.z))
    assert command.depth == root.depth and command.layer_bias == 0
    bounds = r.object_screen_bounds(obj, camera)
    assert bounds.width == 73 and bounds.height == 73


def test_acquisition_removes_draw_command_immediately_and_failed_save_retains_it():
    app, _ = week_app(BY_ID["herb_fine"])
    r = Renderer(SimpleNamespace())
    camera = app.camera()

    def present():
        return any(
            c.stable_id == PREFIX + "herb_fine" for c in r.world_commands(app.model, camera, 0)
        )

    assert present()
    inspect(app, PREFIX + "herb_fine")
    write = app.progress_store.write
    app.progress_store.write = lambda _: False
    assert not app.claim_collectible("herb_fine")
    assert present()
    app.progress_store.write = write
    app.advance_field_conversation()
    app.advance_field_conversation()
    assert "herb_fine" in app.east_site_progress.collectibles
    assert not present()
    assert not hasattr(r, "collectible_particles")  # no detached emitter survives object removal
