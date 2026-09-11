from __future__ import annotations

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.effects import EffectSystem
from drift_with_me.events import GameEvent
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


def normal_enemy(model: GameModel):
    enemy = model.enemy_by_id("urchin_normal_01")
    assert enemy is not None
    return enemy


def snapshot_model(model: GameModel) -> tuple:
    return (
        model.player.x,
        model.player.z,
        model.water,
        model.energy,
        tuple(
            (enemy.id, enemy.x, enemy.z, enemy.state, enemy.state_timer) for enemy in model.enemies
        ),
    )


def event(
    model: GameModel,
    kind: str,
    x: float,
    z: float,
    target_id: str | None = None,
    payload: dict | None = None,
) -> GameEvent:
    return model.event_queue.emit(
        world_tick=model.world_tick,
        kind=kind,
        actor_id="test",
        target_id=target_id,
        world_position=(x, 0.0, z),
        payload=payload,
    )


def test_inspection_records_read_id_and_emits_first_read_once() -> None:
    model, _camera = make_model()
    model.player.x = 192.0
    model.player.z = 192.0
    camera = camera_for_model(model)

    started = model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)
    first_finished = model.complete_interaction()
    second_started = model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)
    second_finished = model.complete_interaction()

    assert [item.kind for item in started] == ["interaction_started"]
    assert started[0].payload["interaction_kind"] == "inspect"
    assert [item.kind for item in first_finished] == ["inspection_completed"]
    assert first_finished[0].target_id == "sign_start"
    assert first_finished[0].payload["first_read"] is True
    assert [item.kind for item in second_started] == ["interaction_started"]
    assert [item.kind for item in second_finished] == ["inspection_completed"]
    assert second_finished[0].payload["first_read"] is False
    assert model.inspected_object_ids == {"sign_start"}
    assert model.debug.inspected_count == 1


def test_world_stays_stopped_during_inspection() -> None:
    model, _camera = make_model()
    model.player.x = 192.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    enemy = normal_enemy(model)
    enemy.state = "CAPTURED"
    enemy.state_timer = 0.2
    model.bubble = BubbleState(x=192.0, z=192.0, dir_x=1.0, dir_z=0.0)

    model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)
    before_tick = model.world_tick
    before_state = enemy.state
    before_timer = enemy.state_timer
    before_bubble_x = model.bubble.x
    before_water = model.water
    events = model.step(InputIntent(action_pressed=True, barrier=True), camera, 1.0)

    assert model.world_paused
    assert events == []
    assert model.world_tick == before_tick
    assert enemy.state == before_state
    assert enemy.state_timer == pytest.approx(before_timer)
    assert model.bubble is not None
    assert model.bubble.x == pytest.approx(before_bubble_x)
    assert model.water == pytest.approx(before_water)


def test_captured_enemy_blocks_interaction_outside_safe_zone() -> None:
    model, _camera = make_model()
    model.player.x = 400.0
    model.player.z = 256.0
    enemy = normal_enemy(model)
    enemy.x = 450.0
    enemy.z = 256.0
    enemy.state = "CAPTURED"
    enemy.state_timer = 4.0
    camera = camera_for_model(model)

    events = model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)

    assert model.interaction is None
    assert [item.kind for item in events] == ["action_denied"]
    assert events[0].payload["reason"] == "blocked"


def test_effects_capacity_and_model_invariance() -> None:
    model, _camera = make_model()
    effects = EffectSystem(model.config)
    before = snapshot_model(model)
    events = [
        event(model, "barrier_repelled", model.player.x, model.player.z, "urchin_normal_01")
        for _ in range(20)
    ]

    effects.process_events(events, model)
    effects.update(1.0 / 60.0, model)

    assert len(effects.particles) <= effects.max_particles
    assert len(effects.emotes) <= effects.max_emotes
    assert snapshot_model(model) == before


def test_grass_reaction_uses_cooldown() -> None:
    model, _camera = make_model()
    effects = EffectSystem(model.config)
    model.player.x = 224.0
    model.player.z = 352.0

    effects.update(0.0, model)
    first_count = len(effects.particles)
    effects.update(0.1, model)
    second_count = len(effects.particles)
    effects.update(0.8, model)

    assert first_count > 0
    assert second_count == first_count
    assert len(effects.particles) == first_count
    assert max(particle.age for particle in effects.particles) == pytest.approx(0.0)
