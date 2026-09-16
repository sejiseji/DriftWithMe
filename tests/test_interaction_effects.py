from __future__ import annotations

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.effects import (
    EffectSystem,
    ReactiveEnvironmentState,
    presentation_cue_for_event,
)
from drift_with_me.events import GameEvent
from drift_with_me.hex_assets import LoadedSpriteAsset, LoadedSpriteFrame, SpriteDefinition
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import BubbleState, GameModel, InputIntent
from drift_with_me.render import Renderer
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


def abnormal_enemy(model: GameModel):
    enemy = model.enemy_by_id("urchin_abnormal_01")
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


def test_inspection_target_direction_overrides_idle_sprite_facing_until_closed() -> None:
    model, _camera = make_model()
    model.player.x = 160.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    renderer = Renderer(None)
    sign = model.world.object_by_id("sign_start")
    assert sign is not None

    events = model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)
    delta = renderer.actor_screen_facing_delta(model, camera, model.player.x, model.player.z)

    assert [event.kind for event in events] == ["interaction_started"]
    assert model.actor_facing_target() == pytest.approx((sign.x, sign.z))
    assert delta is not None
    assert renderer.player_sprite_direction_view(
        model, camera
    ) == renderer.screen_direction_view_name(*delta)

    model.actor_facing_target_remaining = 0.0
    model.update_paused(3.0)
    assert model.actor_facing_target() == pytest.approx((sign.x, sign.z))

    model.complete_interaction()
    assert model.actor_facing_target() is None


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


def test_enemy_can_be_inspected_as_check_target_and_freezes_world() -> None:
    model, _camera = make_model()
    model.player.x = 288.0
    model.player.z = 192.0
    enemy = normal_enemy(model)
    enemy.x = 320.0
    enemy.z = 192.0
    camera = camera_for_model(model)

    events = model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)

    assert [item.kind for item in events] == ["interaction_started"]
    assert events[0].target_id == enemy.id
    assert events[0].payload["interaction_kind"] == "inspect"
    assert model.interaction is not None
    assert model.interaction.object_id == enemy.id
    assert model.interaction.title == "ENEMY NORMAL"
    assert model.interaction.lines == ("ENEMY NORMAL APPROACH", "ENEMY NORMAL GUARD")
    assert model.world_paused

    before_state = enemy.state
    before_timer = enemy.state_timer
    assert model.update_paused(10.0) == []
    assert model.interaction is not None
    assert model.step(InputIntent(), camera, 1.0) == []
    assert enemy.state == before_state
    assert enemy.state_timer == pytest.approx(before_timer)

    finished = model.complete_interaction()

    assert [item.kind for item in finished] == ["inspection_completed"]
    assert finished[0].target_id == enemy.id
    assert finished[0].world_position == pytest.approx((enemy.x, 0.0, enemy.z))
    assert finished[0].payload["first_read"] is True
    assert enemy.id in model.inspected_object_ids


def test_enemy_inspection_range_matches_barrier_reaction_distance() -> None:
    model, _camera = make_model()
    model.player.x = 288.0
    model.player.z = 192.0
    enemy = normal_enemy(model)
    enemy.z = model.player.z
    camera = camera_for_model(model)
    guard_distance = model.enemy_interaction_range(enemy)

    enemy.x = model.player.x + guard_distance
    started = model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)
    model.cancel_interaction()

    enemy.x = model.player.x + guard_distance + 0.1
    outside = model.step(InputIntent(interact_pressed=True), camera, 1.0 / 60.0)

    assert [item.kind for item in started] == ["interaction_started"]
    assert started[0].target_id == enemy.id
    assert [item.kind for item in outside] == ["action_denied"]
    assert outside[0].payload["reason"] == "no_target"


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
    assert len(effects.rings) <= effects.max_particles
    assert len(effects.strokes) <= effects.max_particles
    assert len(effects.emotes) <= effects.max_emotes
    assert snapshot_model(model) == before


def test_reactive_environment_query_filters_by_world_distance() -> None:
    model, _camera = make_model()
    grass = model.world.object_by_id("grass_01")
    assert grass is not None

    near = model.world.query_reactive_environment(grass.x, grass.z)
    far = model.world.query_reactive_environment(0.0, 0.0)

    assert [obj.id for obj in near.objects] == ["grass_01"]
    assert near.candidate_chunk_count > 0
    assert far.objects == ()


def test_reactive_environment_state_uses_nearby_query_and_recovers() -> None:
    model, _camera = make_model()
    effects = EffectSystem(model.config)
    grass = model.world.object_by_id("grass_01")
    assert grass is not None
    model.player.x = grass.x
    model.player.z = grass.z
    model.player.last_move_x = 1.0
    model.player.last_move_z = 0.0

    effects.update(1.0 / 60.0, model)
    first_particle_count = len(effects.particles)

    assert effects.reactive_environment_last_query_count == 1
    assert first_particle_count == 3
    assert set(effects.reactive_environment_states) == {"grass_01"}
    state = effects.reactive_environment_states["grass_01"]
    assert state.kind == "reactive_grass_tall"
    assert state.direction_x == pytest.approx(1.0)
    assert state.direction_z == pytest.approx(0.0)
    assert 0.0 <= state.strength <= 1.0

    model.player.last_move_x = 0.0
    model.player.last_move_z = 1.0
    effects.update(1.0 / 60.0, model)
    assert len(effects.particles) == first_particle_count
    refreshed = effects.reactive_environment_states["grass_01"]
    assert refreshed.direction_x == pytest.approx(0.0)
    assert refreshed.direction_z == pytest.approx(1.0)
    assert refreshed.age == pytest.approx(0.0)

    model.player.x = 0.0
    model.player.z = 0.0
    effects.update(1.1, model)
    assert effects.reactive_environment_states == {}


def test_reactive_environment_keeps_minimum_strength_at_trigger_edge() -> None:
    model, _camera = make_model()
    effects = EffectSystem(model.config)
    grass = model.world.object_by_id("grass_01")
    assert grass is not None
    model.player.x = grass.x + grass.reaction_radius
    model.player.z = grass.z

    effects.update(1.0 / 60.0, model)

    state = effects.reactive_environment_states["grass_01"]
    assert state.strength == pytest.approx(model.config["reactive_environment"]["min_strength"])


def test_reactive_grass_render_helpers_use_active_state_until_recovered() -> None:
    model, camera = make_model()
    effects = EffectSystem(model.config)
    renderer = Renderer(None)
    grass = model.world.object_by_id("grass_01")
    assert grass is not None
    state = ReactiveEnvironmentState(
        object_id=grass.id,
        kind=grass.visual,
        x=grass.x,
        z=grass.z,
        trigger_radius=grass.reaction_radius,
        visual_radius=24.0,
        strength=0.8,
        direction_x=1.0,
        direction_z=0.0,
        recovery_sec=1.0,
    )
    effects.reactive_environment_states[grass.id] = state

    direction = renderer.reactive_environment_screen_direction(camera, grass, state)

    assert renderer.reactive_environment_state(effects, grass.id) is state
    assert renderer.reactive_environment_intensity(state) == pytest.approx(0.8)
    assert direction is not None
    assert direction[0] > 0.0
    assert abs((direction[0] ** 2 + direction[1] ** 2) ** 0.5 - 1.0) < 1e-6

    state.age = state.recovery_sec
    assert renderer.reactive_environment_state(effects, grass.id) is None
    assert renderer.reactive_environment_intensity(state) == pytest.approx(0.0)


def test_reactive_upright_grass_deformation_is_disabled_by_default() -> None:
    model, _camera = make_model()
    renderer = Renderer(None)

    assert renderer.reactive_upright_deform_enabled(model) is False


def test_env001_reactive_upright_grass_uses_static_billboard_when_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, camera = make_model()
    effects = EffectSystem(model.config)
    renderer = Renderer(None)
    grass = model.world.object_by_id("grass_01")
    assert grass is not None
    effects.reactive_environment_states[grass.id] = ReactiveEnvironmentState(
        object_id=grass.id,
        kind=grass.visual,
        x=grass.x,
        z=grass.z,
        trigger_radius=grass.reaction_radius,
        visual_radius=24.0,
        strength=1.0,
        direction_x=1.0,
        direction_z=0.0,
        recovery_sec=1.0,
    )
    asset = LoadedSpriteAsset(
        definition=SpriteDefinition(
            asset_id="test_reactive_grass",
            palette_id="pyxel_default_16",
            hex_width=64,
            hex_height=64,
            colkey=8,
            anchor_px=(32.0, 63.0),
            world_size=(28.0, 28.0),
            projection_mode="upright_height_billboard_v1",
            flip_policy="none",
            animation="static",
            frames=(),
            source_hash="0" * 64,
        ),
        frames={
            "idle_00": LoadedSpriteFrame(
                frame_id="idle_00",
                image=None,
                source=None,
                u=0,
                v=0,
                width=64,
                height=64,
                source_hash="0" * 64,
            )
        },
    )
    calls: list[str] = []

    def fail_deform(*_args, **_kwargs) -> bool:
        calls.append("deform")
        return True

    def record_static(*_args, **_kwargs) -> None:
        calls.append("static")

    monkeypatch.setattr(renderer, "draw_reactive_upright_prop", fail_deform)
    monkeypatch.setattr(renderer, "draw_atmospheric_scaled_sprite", record_static)

    assert renderer.draw_reactive_prop_sprite(model, grass, camera, asset, effects) is True
    assert calls == ["static"]


def test_presentation_cue_mapping_for_existing_events() -> None:
    model, _camera = make_model()

    assert (
        presentation_cue_for_event(
            event(
                model,
                "resource_refilled",
                model.player.x,
                model.player.z,
                payload={"resource": "water"},
            )
        )
        == "DWF_REFILL_DONE"
    )
    assert (
        presentation_cue_for_event(
            event(
                model,
                "resource_refilled",
                model.player.x,
                model.player.z,
                payload={"resource": "energy"},
            )
        )
        == "DWF_CHARGE_DONE"
    )
    assert (
        presentation_cue_for_event(event(model, "barrier_repelled", model.player.x, model.player.z))
        == "DWF_GUARD_REPEL"
    )
    assert (
        presentation_cue_for_event(event(model, "enemy_captured", model.player.x, model.player.z))
        == "DWF_BUBBLE_CAPTURE"
    )
    assert (
        presentation_cue_for_event(
            event(model, "discharge_succeeded", model.player.x, model.player.z)
        )
        == "DWF_ZAP_HIT"
    )
    assert (
        presentation_cue_for_event(
            event(model, "abnormal_windup_started", model.player.x, model.player.z)
        )
        == "DWF_ABNORMAL_WINDUP"
    )


def test_presentation_cues_create_local_fx_once_per_event() -> None:
    model, _camera = make_model()
    effects = EffectSystem(model.config)
    refill = event(
        model,
        "resource_refilled",
        model.player.x,
        model.player.z,
        payload={"resource": "water"},
    )
    zap = event(model, "discharge_succeeded", model.player.x + 32.0, model.player.z)

    effects.process_events([refill, refill, zap, zap], model)

    assert len(effects.rings) == 2
    assert len(effects.strokes) == 4
    assert len(effects.particles) == effects.max_particles_per_event * 2
    assert {particle.color for particle in effects.particles} >= {5, 7, 9, 10, 12}


def test_zap_cue_creates_draw_only_enemy_snapshot() -> None:
    model, camera = make_model()
    effects = EffectSystem(model.config)
    enemy = abnormal_enemy(model)
    enemy.state = "DEFEATED"
    before = snapshot_model(model)
    zap = event(model, "discharge_succeeded", enemy.x, enemy.z, target_id=enemy.id)

    effects.process_events([zap, zap], model)

    assert snapshot_model(model) == before
    assert len(effects.enemy_snapshots) == 1
    snapshot = effects.enemy_snapshots[0]
    assert snapshot.enemy_id == enemy.id
    assert snapshot.enemy_kind == "abnormal"
    assert snapshot.x == pytest.approx(enemy.x)
    assert snapshot.z == pytest.approx(enemy.z)
    assert snapshot.lifetime == pytest.approx(0.1)

    commands = Renderer(object()).world_commands(model, camera, 0.0, effects)
    assert f"enemy_snapshot:{enemy.id}" in {command.stable_id for command in commands}

    effects.update(0.11, model)

    assert effects.enemy_snapshots == []
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
    assert all(particle.age > 0.0 for particle in effects.particles)
    assert len(effects.particles) <= first_count
    assert "grass_01" in effects.reactive_environment_states
