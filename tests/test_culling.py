from __future__ import annotations

from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.world import load_world_data


def make_model(culling_enabled: bool = True) -> tuple[GameModel, CameraState]:
    runtime = load_runtime_config()
    world = load_world_data()
    model = GameModel(runtime.raw, world, culling_enabled=culling_enabled)
    return model, camera_for_model(model)


def camera_for_model(model: GameModel) -> CameraState:
    runtime = load_runtime_config()
    return CameraState.from_config(
        runtime.raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )


def enemy_by_id(model: GameModel, enemy_id: str):
    enemy = model.enemy_by_id(enemy_id)
    assert enemy is not None
    return enemy


def major_state(model: GameModel) -> tuple:
    return (
        round(model.player.x, 4),
        round(model.player.z, 4),
        round(model.water, 4),
        round(model.energy, 4),
        tuple(
            (
                enemy.id,
                round(enemy.x, 4),
                round(enemy.z, 4),
                enemy.state,
                round(enemy.state_timer, 4),
            )
            for enemy in model.enemies
        ),
        tuple(event.kind for event in model.last_events),
    )


def test_active_enemy_hysteresis_uses_enter_and_exit_radii() -> None:
    model, _camera = make_model(culling_enabled=True)
    enemy = enemy_by_id(model, "urchin_normal_01")

    model.player.x = enemy.x - 255.0
    model.player.z = enemy.z
    model.refresh_active_enemies()
    assert enemy.id in model.active_enemy_ids

    model.player.x = enemy.x - 319.0
    model.refresh_active_enemies()
    assert enemy.id in model.active_enemy_ids

    model.player.x = enemy.x - 321.0
    model.refresh_active_enemies()
    assert enemy.id not in model.active_enemy_ids


def test_captured_enemy_is_pinned_until_timer_advances_offscreen() -> None:
    model, camera = make_model(culling_enabled=True)
    enemy = enemy_by_id(model, "urchin_abnormal_01")
    model.player.x = 32.0
    model.player.z = 32.0
    enemy.x = 900.0
    enemy.z = 900.0
    enemy.state = "CAPTURED"
    enemy.state_timer = 0.5

    model.refresh_active_enemies()
    model.step(InputIntent(), camera, 0.2)

    assert enemy.id in model.active_enemy_ids
    assert enemy.state == "CAPTURED"
    assert enemy.state_timer == 0.3


def test_culling_on_off_keeps_model_results_for_same_inputs() -> None:
    enabled, enabled_camera = make_model(culling_enabled=True)
    disabled, disabled_camera = make_model(culling_enabled=False)
    dt = 1.0 / 60.0
    inputs = [
        InputIntent(screen_x=1.0, strength=1.0),
        InputIntent(screen_x=1.0, strength=1.0),
        InputIntent(screen_y=1.0, strength=1.0),
        InputIntent(screen_y=1.0, strength=1.0),
        InputIntent(),
    ]

    for frame in range(240):
        intent = inputs[(frame // 48) % len(inputs)]
        enabled.step(intent, enabled_camera, dt)
        disabled.step(intent, disabled_camera, dt)

    assert major_state(enabled) == major_state(disabled)
