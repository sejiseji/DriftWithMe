"""Default affine camera can start and finish the existing July counter attack."""

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import (
    AffineProjectionProfile,
    CameraState,
    Vec3,
    affine_camera_from_perspective,
)
from drift_with_me.model import InputIntent
from test_july_combat import make_model


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
@pytest.mark.parametrize("index", [0, 2])
def test_affine_counter_focus_finishes_once_without_electric_energy(profile, index):
    model, _ = make_model()
    enemy = model.enemies[index]
    runtime = load_runtime_config(profile)
    perspective = CameraState.from_config(
        runtime.raw, Vec3(enemy.x, 0, enemy.z), runtime.screen_width, runtime.screen_height
    )
    camera = affine_camera_from_perspective(
        perspective,
        AffineProjectionProfile.from_config(runtime.raw),
        base_distance=float(runtime.raw["camera"]["base_distance"]),
    )
    events = []
    model.start_contact_combat(enemy, events)
    session = model.combat_session
    session.phase = "PERFECT_BUBBLE_WINDOW"
    model.energy = 0
    model._july_combat_camera = camera
    model.try_combat_counter_bubble(session, events)
    model.try_combat_counter_zap(session, events)
    assert session.phase == "FOCUS_LASER"
    for _ in range(1800):
        events.extend(model.step(InputIntent(action_pressed=True), camera, 1 / 60))
        if model.combat_session is None:
            break
    assert model.combat_session is None
    assert enemy.state == "DEFEATED" and model.energy == 0
    assert sum(e.kind == "focus_laser_started" for e in events) == 1
    assert sum(e.kind == "enemy_defeated" for e in events) == 1
    assert not any(e.kind == "discharge_succeeded" for e in events)
