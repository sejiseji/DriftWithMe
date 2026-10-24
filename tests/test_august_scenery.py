"""Weather/scenery are presentation only; the existing checkpoint is authoritative."""

import random
from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.august import AugustProgress
from drift_with_me.august_scenery import (
    MAX_RAIN,
    ROUTES,
    TREE_RING,
    environment,
    flowers,
    planks,
    rain_segments,
)
from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import CameraState, Vec3


@pytest.mark.parametrize(
    "number,phase,rain,recovered",
    [
        (1, "field", False, False),
        (2, "field", False, False),
        (3, "field", True, False),
        (3, "report", True, False),
        (3, "done", False, True),
    ],
)
def test_weather_and_recovery_only_follow_saved_week_phase(number, phase, rain, recovered):
    progress = AugustProgress(phase=phase)
    app = SimpleNamespace(
        august_active=lambda: True,
        work_week=SimpleNamespace(number=number),
        office=SimpleNamespace(august_progress=progress),
    )
    before = deepcopy(progress)
    assert environment(app) == (rain, recovered)
    assert progress == before
    app.august_active = lambda: False
    assert environment(app) == (False, False)


def test_rain_is_bounded_deterministic_and_does_not_use_game_random():
    camera = CameraState.from_config(load_runtime_config().raw, Vec3(500, 0, 500), 512, 236)
    before = random.getstate()
    a = list(rain_segments(camera, 4.25))
    b = list(rain_segments(camera, 4.25))
    assert a == b and 0 < len(a) <= MAX_RAIN
    assert random.getstate() == before
    assert list(rain_segments(camera, 4.35)) != a


def test_paths_are_cached_ground_geometry_without_world_mutation():
    assert len(ROUTES) == 4 and TREE_RING[0] == pytest.approx(TREE_RING[-1])
    assert planks() is planks() and len(planks()) < 600
    assert flowers() is flowers()
    assert all(v.y == 0.2 for _, _, corners, _ in planks() for v in corners)
    assert len(flowers().props) < 80
    assert ROUTES[0][0][1] < 0


def test_draw_rain_keeps_primitive_budget_and_restores_dither():
    from drift_with_me.august_scenery import MAX_SPLASHES, draw_rain

    class Pixels:
        def __init__(self):
            self.calls = []

        def __getattr__(self, name):
            return lambda *args: self.calls.append((name, args))

    camera = CameraState.from_config(load_runtime_config().raw, Vec3(500, 0, 500), 512, 236)
    p = Pixels()
    renderer = SimpleNamespace(pyxel=p)
    model = SimpleNamespace(august_rain=False, water=12, energy=20)
    draw_rain(renderer, model, camera, 3)
    assert not p.calls
    model.august_rain = True
    before = deepcopy(vars(model))
    draw_rain(renderer, model, camera, 3)
    assert vars(model) == before
    assert sum(name == "line" for name, _ in p.calls) <= MAX_RAIN
    assert sum(name == "pset" for name, _ in p.calls) <= MAX_SPLASHES * 2
    assert [args for name, args in p.calls if name == "dither"][-1] == (1,)


def test_boardwalk_centerline_avoids_existing_solids():
    from drift_with_me.world import load_world_data

    world = load_world_data()
    for x, z, _, _ in planks():
        if 12 < x < 1012 and 12 < z < 1012:
            assert not world.collides_player(x, z, 8, 8), (x, z)
