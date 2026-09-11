from __future__ import annotations

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import BubbleState, GameModel, InputIntent
from drift_with_me.world import load_world_data


def make_model() -> tuple[GameModel, CameraState]:
    runtime = load_runtime_config()
    world = load_world_data()
    model = GameModel(runtime.raw, world)
    return model, camera_for_model(model)


def camera_for_model(model: GameModel) -> CameraState:
    runtime = load_runtime_config()
    return CameraState.from_config(
        runtime.raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )


def abnormal_enemy(model: GameModel):
    enemy = model.enemy_by_id("urchin_abnormal_01")
    assert enemy is not None
    return enemy


def place_action_scene(model: GameModel) -> tuple[CameraState, object]:
    model.player.x = 650.0
    model.player.z = 420.0
    model.buddy.x = model.player.x
    model.buddy.z = model.player.z
    enemy = abnormal_enemy(model)
    enemy.x = 730.0
    enemy.z = 420.0
    enemy.state = "WINDUP"
    enemy.state_timer = 10.0
    enemy.dash_x = -1.0
    enemy.dash_z = 0.0
    return camera_for_model(model), enemy


def test_abnormal_windup_fixes_dash_direction_before_dash() -> None:
    model, _camera = make_model()
    model.player.x = 650.0
    model.player.z = 420.0
    camera = camera_for_model(model)
    enemy = abnormal_enemy(model)
    enemy.x = 730.0
    enemy.z = 420.0
    dt = 1.0 / 60.0

    model.step(InputIntent(), camera, dt)
    model.step(InputIntent(), camera, dt)
    assert enemy.state == "WINDUP"
    dash_x = enemy.dash_x
    dash_z = enemy.dash_z

    model.player.x = 730.0
    model.player.z = 500.0
    for _ in range(46):
        model.step(InputIntent(), camera, dt)

    assert enemy.state == "DASH"
    assert enemy.dash_x == pytest.approx(dash_x)
    assert enemy.dash_z == pytest.approx(dash_z)


def test_bubble_fire_costs_water_and_capture_needs_second_press_for_discharge() -> None:
    model, _camera = make_model()
    camera, enemy = place_action_scene(model)
    dt = 1.0 / 60.0

    fired = model.step(InputIntent(action_pressed=True), camera, dt)
    capture_events = []
    for _ in range(30):
        capture_events.extend(model.step(InputIntent(), camera, dt))
        if enemy.state == "CAPTURED":
            break

    assert [event.kind for event in fired] == ["bubble_fired"]
    assert model.water == pytest.approx(88.0)
    assert enemy.state == "CAPTURED"
    assert [event.kind for event in capture_events] == ["enemy_captured"]
    assert model.energy == 60.0

    discharged = model.step(InputIntent(action_pressed=True), camera, dt)

    assert enemy.state == "DEFEATED"
    assert model.energy == pytest.approx(40.0)
    assert [event.kind for event in discharged] == ["discharge_succeeded"]


def test_bubble_failure_does_not_spend_water() -> None:
    model, camera = make_model()
    model.player.x = 650.0
    model.player.z = 420.0
    camera = camera_for_model(model)
    enemy = abnormal_enemy(model)
    enemy.x = 730.0
    enemy.z = 420.0
    model.water = 5.0

    events = model.step(InputIntent(action_pressed=True), camera, 1.0 / 60.0)

    assert model.bubble is None
    assert model.water == 5.0
    assert [event.kind for event in events] == ["action_denied"]
    assert events[0].payload["reason"] == "insufficient_water"


def test_active_bubble_blocks_second_shot_without_extra_cost() -> None:
    model, _camera = make_model()
    camera, _enemy = place_action_scene(model)
    dt = 1.0 / 60.0

    model.step(InputIntent(action_pressed=True), camera, dt)
    water_after_first = model.water
    events = model.step(InputIntent(action_pressed=True), camera, dt)

    assert model.bubble is not None
    assert model.water == water_after_first
    assert [event.kind for event in events] == ["action_denied"]
    assert events[0].payload["reason"] == "busy"


def test_wall_collision_stops_bubble_before_capture() -> None:
    model, _camera = make_model()
    enemy = abnormal_enemy(model)
    enemy.x = 650.0
    enemy.z = 352.0
    enemy.state = "WINDUP"
    enemy.state_timer = 10.0
    model.bubble = BubbleState(x=600.0, z=352.0, dir_x=1.0, dir_z=0.0)
    events = []

    model.update_bubble(0.2, events)

    assert model.bubble is None
    assert enemy.state == "WINDUP"
    assert events == []


def test_captured_enemy_expires_to_recover_without_discharge() -> None:
    model, camera = make_model()
    enemy = abnormal_enemy(model)
    enemy.state = "CAPTURED"
    enemy.state_timer = 0.1

    events = model.step(InputIntent(), camera, 0.2)

    assert events == []
    assert enemy.state == "RECOVER"
    assert enemy.state_timer == pytest.approx(model.config["bubble"]["release_grace_sec"])


def test_discharge_failure_does_not_spend_energy_or_defeat() -> None:
    model, _camera = make_model()
    camera, enemy = place_action_scene(model)
    enemy.state = "CAPTURED"
    enemy.state_timer = 4.0
    model.energy = 10.0

    events = model.step(InputIntent(action_pressed=True), camera, 1.0 / 60.0)

    assert enemy.state == "CAPTURED"
    assert model.energy == 10.0
    assert [event.kind for event in events] == ["action_denied"]
    assert events[0].payload["reason"] == "insufficient_energy"
