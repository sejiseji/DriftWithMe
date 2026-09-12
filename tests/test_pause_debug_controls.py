from __future__ import annotations

from drift_with_me.app import DriftWithMeApp
from drift_with_me.audio import AudioEngine
from drift_with_me.camera import CameraController
from drift_with_me.config import load_runtime_config
from drift_with_me.effects import EffectSystem
from drift_with_me.input import PointerInput
from drift_with_me.math3d import Vec3
from drift_with_me.model import GameModel
from drift_with_me.world import load_world_data


def make_pause_app() -> DriftWithMeApp:
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config("medium")
    app.world = load_world_data()
    app.model = GameModel(app.runtime.raw, app.world)
    app.audio = AudioEngine(app.runtime.raw)
    app.effects = EffectSystem(app.runtime.raw)
    app.camera_controller = CameraController(
        app.runtime.raw,
        app.world,
        app.runtime.screen_width,
        app.runtime.screen_height,
        Vec3(app.model.player.x, 0.0, app.model.player.z),
    )
    input_config = app.runtime.raw["input"]
    app.pointer = PointerInput(
        hold_sec=float(input_config["hold_sec"]),
        drag_threshold_px=float(input_config["drag_threshold_ref_px"]),
        deadzone_px=float(input_config["stick_deadzone_ref_px"]),
        radius_px=float(input_config["stick_radius_ref_px"]),
    )
    app.pending_action_pressed = True
    app.pending_interact_pressed = True
    app.last_denied_reason = "no_target"
    app.previous_time = 1.0
    app.accumulator = 1.0
    return app


def test_pause_debug_resource_controls_are_explicit_model_changes() -> None:
    app = make_pause_app()

    app.model.water = 1.0
    app.model.energy = 2.0
    app.fill_resources_for_debug()

    assert app.model.water == app.model.water_max
    assert app.model.energy == app.model.energy_max
    assert app.last_denied_reason == ""

    app.zero_resources_for_debug()

    assert app.model.water == 0.0
    assert app.model.energy == 0.0
    assert not app.model.player.barrier_active


def test_pause_debug_reset_clears_pending_state() -> None:
    app = make_pause_app()
    app.model.water = 0.0
    app.model.energy = 0.0
    app.model.bubble_cooldown_remaining = 9.0

    app.reset_scene_for_debug()

    assert app.model.water == app.runtime.raw["resources"]["water_start"]
    assert app.model.energy == app.runtime.raw["resources"]["energy_start"]
    assert app.model.bubble is None
    assert app.pending_action_pressed is False
    assert app.pending_interact_pressed is False
    assert app.last_denied_reason == ""
    assert app.previous_time is None
    assert app.accumulator == 0.0


def test_pause_debug_culling_toggle_refreshes_active_set() -> None:
    app = make_pause_app()

    assert app.model.culling_enabled is True
    app.toggle_culling_for_debug()

    assert app.model.culling_enabled is False
    assert app.model.active_enemy_ids == {enemy.id for enemy in app.model.enemies}

    app.toggle_culling_for_debug()

    assert app.model.culling_enabled is True
