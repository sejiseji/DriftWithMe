from __future__ import annotations

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.world import load_world_data


def make_model() -> tuple[GameModel, CameraState]:
    runtime = load_runtime_config()
    world = load_world_data()
    model = GameModel(runtime.raw, world)
    camera = camera_for_model(model)
    return model, camera


def camera_for_model(model: GameModel) -> CameraState:
    runtime = load_runtime_config()
    return CameraState.from_config(
        runtime.raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )


def normal_enemy(model: GameModel):
    enemy = model.enemy_by_id("urchin_normal_01")
    assert enemy is not None
    return enemy


def test_normal_urchin_approaches_slowly_outside_safe_zone() -> None:
    model, camera = make_model()
    model.player.x = 260.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    enemy = normal_enemy(model)
    dt = 1.0 / 60.0

    for _ in range(60):
        model.step(InputIntent(), camera, dt)

    assert enemy.state == "APPROACH"
    assert enemy.x < enemy.home_x
    assert enemy.home_x - enemy.x == pytest.approx(6.0, rel=0.05, abs=0.1)


def test_barrier_consumes_water_and_repels_a_normal_enemy_once() -> None:
    model, camera = make_model()
    model.player.x = 300.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    enemy = normal_enemy(model)
    dt = 1.0 / 60.0

    first_events = model.step(InputIntent(barrier=True), camera, dt)
    later_events = []
    for _ in range(10):
        later_events.extend(model.step(InputIntent(barrier=True), camera, dt))

    assert model.water == pytest.approx(100.0 - 11.0 * 10.0 / 60.0)
    assert model.player.barrier_active
    assert enemy.state in {"REPELLED", "REST"}
    assert [event.kind for event in first_events] == ["barrier_repelled"]
    assert not [event for event in later_events if event.kind == "barrier_repelled"]


def test_guard_threat_only_tracks_normal_enemy_at_barrier_range() -> None:
    model, _camera = make_model()
    model.player.x = 300.0
    model.player.z = 192.0
    enemy = normal_enemy(model)
    enemy.x = model.player.x + float(model.config["barrier"]["radius"]) + model.enemy_radius(enemy)
    enemy.z = model.player.z

    assert model.guard_threat() is enemy

    enemy.state = "REPELLED"
    assert model.guard_threat() is None

    abnormal = model.enemy_by_id("urchin_abnormal_01")
    assert abnormal is not None
    abnormal.x = model.player.x + 4.0
    abnormal.z = model.player.z
    abnormal.state = "APPROACH"

    assert model.guard_threat() is None


def test_barrier_depletion_requires_release_before_redeploy() -> None:
    model, camera = make_model()
    dt = 1.0 / 60.0
    model.water = float(model.config["resources"]["barrier_water_per_sec"]) * dt * 0.5

    first = model.step(InputIntent(barrier=True), camera, dt)
    second = model.step(InputIntent(barrier=True), camera, dt)
    model.water = model.water_max
    still_held = model.step(InputIntent(barrier=True), camera, dt)
    model.step(InputIntent(), camera, dt)
    after_release = model.step(InputIntent(barrier=True), camera, dt)

    assert model.water == pytest.approx(model.water_max - 10.0 / 60.0)
    assert [event.payload["reason"] for event in first if event.kind == "action_denied"] == [
        "insufficient_water"
    ]
    assert second == []
    assert still_held == []
    assert after_release == []
    assert model.player.barrier_active


def test_unprotected_contact_knocks_player_once_during_invulnerability() -> None:
    model, camera = make_model()
    model.player.x = 300.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    enemy = normal_enemy(model)
    enemy.x = 307.0
    enemy.z = 192.0
    start_x = model.player.x

    first_events = model.step(InputIntent(), camera, 1.0 / 60.0)
    second_events = model.step(InputIntent(), camera, 1.0 / 60.0)

    assert model.debug.player_contacts == 1
    assert model.player.x != start_x
    assert model.player.invulnerable_remaining > 0.0
    assert [event.kind for event in first_events] == ["player_contacted"]
    assert second_events == []


def test_safe_zone_blocks_contact_and_enemy_entry() -> None:
    model, camera = make_model()
    enemy = normal_enemy(model)
    enemy.x = model.player.x
    enemy.z = model.player.z

    events = model.step(InputIntent(), camera, 1.0 / 60.0)
    moved_x, moved_z = model.world.move_enemy_circle_sliding(260.0, 160.0, -80.0, 0.0, 10.0)

    assert events == []
    assert model.debug.player_contacts == 0
    assert moved_x >= 250.0
    assert moved_z == 160.0


def test_working_tap_refills_water_only_on_completion() -> None:
    model, _camera = make_model()
    model.player.x = 128.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    model.water = 20.0

    started = model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)
    halfway = model.update_paused(0.4)
    completed = model.update_paused(0.4)

    assert [event.kind for event in started] == ["interaction_started"]
    assert halfway == []
    assert model.water == model.water_max
    assert [event.kind for event in completed] == ["resource_refilled"]


def test_refill_cancel_does_not_change_water() -> None:
    model, _camera = make_model()
    model.player.x = 128.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    model.water = 20.0

    model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)
    model.update_paused(0.3)
    cancelled = model.cancel_interaction()

    assert model.water == 20.0
    assert model.interaction is None
    assert [event.kind for event in cancelled] == ["interaction_cancelled"]


def test_stopped_tap_does_not_refill_water() -> None:
    model, _camera = make_model()
    model.player.x = 400.0
    model.player.z = 256.0
    camera = camera_for_model(model)
    model.water = 20.0

    started = model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)
    finished = model.update_paused(0.8)

    assert model.interaction is None
    assert model.water == 20.0
    assert [event.kind for event in started] == ["interaction_started"]
    assert [event.kind for event in finished] == ["inspection_completed"]
    assert "tap_stopped" in model.inspected_object_ids


def test_nearby_enemy_blocks_interaction_outside_safe_zone() -> None:
    model, _camera = make_model()
    model.player.x = 400.0
    model.player.z = 256.0
    enemy = normal_enemy(model)
    enemy.x = 450.0
    enemy.z = 256.0
    camera = camera_for_model(model)

    events = model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)

    assert model.interaction is None
    assert [event.kind for event in events] == ["action_denied"]
    assert events[0].payload["reason"] == "blocked"
