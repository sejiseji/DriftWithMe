from __future__ import annotations

import copy
import math

import pytest

from drift_with_me.app import DriftWithMeApp
from drift_with_me.camera import CameraController
from drift_with_me.config import load_runtime_config
from drift_with_me.effects import EffectSystem
from drift_with_me.events import GameEvent
from drift_with_me.math3d import AffineCameraState, AffineProjectionProfile, CameraState, Vec3
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.world import load_world_data


def make_runtime_raw(shake: bool = False, pulse: bool = False) -> dict:
    runtime = load_runtime_config("medium")
    raw = copy.deepcopy(runtime.raw)
    raw["effects"]["shake_enabled"] = shake
    raw["effects"]["combat_camera_pulse_enabled"] = pulse
    return raw


def make_model(raw: dict) -> GameModel:
    return GameModel(raw, load_world_data())


def make_event(model: GameModel, kind: str) -> GameEvent:
    return model.event_queue.emit(
        world_tick=model.world_tick,
        kind=kind,
        actor_id="test",
        target_id="urchin_normal_01",
        world_position=(model.player.x + 16.0, 0.0, model.player.z),
    )


def camera_for_model(raw: dict, model: GameModel) -> CameraState:
    runtime = load_runtime_config("medium")
    return CameraState.from_config(
        raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )


def camera_zoom(raw: dict, camera: CameraState | AffineCameraState) -> float:
    return float(raw["camera"]["base_distance"]) / camera.distance


def make_app(raw: dict, model: GameModel) -> DriftWithMeApp:
    runtime = load_runtime_config("medium")
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = type(runtime)(raw=raw, profile=runtime.profile)
    app.world = model.world
    app.model = model
    app.effects = EffectSystem(raw)
    app.audio = SilentAudio()
    app.hitstop_remaining = 0.0
    app.accumulator = 0.0
    app._processed_hitstop_event_ids = set()
    app.last_combat_scene_camera = None
    app.combat_camera_restore = None
    app.combat_camera_snapshot_zoom = None
    app.camera_controller = CameraController(
        raw,
        model.world,
        runtime.screen_width,
        runtime.screen_height,
        Vec3(model.player.x, 0.0, model.player.z),
    )
    return app


class SilentAudio:
    def play_events(self, events) -> None:
        self.last_events = list(events)


def start_contact_combat(model: GameModel, raw: dict) -> CameraState:
    model.player.x = 300.0
    model.player.z = 192.0
    enemy = model.enemy_by_id("urchin_normal_01")
    assert enemy is not None
    enemy.x = 307.0
    enemy.z = 192.0
    camera = camera_for_model(raw, model)

    events = model.step(InputIntent(), camera, 1.0 / 60.0)

    assert [event.kind for event in events] == ["combat_started"]
    assert model.combat_session is not None
    return camera


def test_camera_reactions_default_off_do_not_create_impulses() -> None:
    raw = make_runtime_raw(shake=False, pulse=False)
    model = make_model(raw)
    effects = EffectSystem(raw)

    effects.process_events([make_event(model, "discharge_succeeded")], model)

    assert effects.camera_impulses == []
    assert effects.camera_transform(512, 236).zoom_multiplier == 1.0


def test_camera_reactions_create_delayed_non_additive_transform() -> None:
    raw = make_runtime_raw(shake=True, pulse=True)
    model = make_model(raw)
    effects = EffectSystem(raw)
    zap = make_event(model, "discharge_succeeded")

    effects.process_events([zap, zap], model, camera_reaction_delay=0.05)

    assert len(effects.camera_impulses) == 1
    assert effects.camera_transform(512, 236).zoom_multiplier == 1.0

    effects.update(0.06, model)
    transform = effects.camera_transform(512, 236)

    assert transform.zoom_multiplier > 1.0
    assert transform.zoom_multiplier <= 1.04
    assert abs(transform.offset_x) <= 2.0
    assert abs(transform.offset_y) <= 2.0


def test_bat006_combat_camera_reaction_uses_existing_gates() -> None:
    raw = make_runtime_raw(shake=True, pulse=True)
    model = make_model(raw)
    effects = EffectSystem(raw)
    perfect = make_event(model, "combat_perfect_started")

    effects.process_events([perfect], model)
    effects.update(0.04, model)
    transform = effects.camera_transform(512, 236)

    assert len(effects.camera_impulses) == 1
    assert transform.zoom_multiplier > 1.0
    assert transform.zoom_multiplier <= 1.035
    assert abs(transform.offset_x) <= 2.0
    assert abs(transform.offset_y) <= 2.0


def test_bat007_guard_failure_camera_reaction_uses_existing_gates() -> None:
    raw = make_runtime_raw(shake=True, pulse=True)
    model = make_model(raw)
    effects = EffectSystem(raw)
    failed = make_event(model, "combat_guard_failed")

    effects.process_events([failed], model)
    effects.update(0.05, model)
    transform = effects.camera_transform(512, 236)

    assert len(effects.camera_impulses) == 1
    assert transform.zoom_multiplier == pytest.approx(1.0)
    assert abs(transform.offset_x) <= 2.0
    assert abs(transform.offset_y) <= 2.0
    assert abs(transform.offset_x) > 0.0 or abs(transform.offset_y) > 0.0


def test_presentation_camera_changes_render_only_and_respects_focus_mode() -> None:
    raw = make_runtime_raw(shake=True, pulse=True)
    model = make_model(raw)
    app = make_app(raw, model)
    base_camera = camera_for_model(raw, model)
    app.effects.process_events([make_event(model, "discharge_succeeded")], model)
    app.effects.update(0.05, model)

    render_camera = app.presentation_camera(base_camera)

    assert render_camera is not base_camera
    assert render_camera.distance < base_camera.distance
    assert base_camera.anchor_x == pytest.approx(0.5)

    app.camera_controller.start_focus_point(Vec3(model.player.x, 8.0, model.player.z))

    assert app.presentation_camera(base_camera) is base_camera


def test_combat_scene_camera_zooms_to_battle_pair_without_moving_world() -> None:
    raw = make_runtime_raw()
    model = make_model(raw)
    app = make_app(raw, model)
    app.projection_mode = "perspective"
    base_camera = start_contact_combat(model, raw)
    assert model.combat_session is not None
    model.combat_session.elapsed_sec = float(raw["combat_v1"]["entry"]["camera_transition_sec"])
    model.combat_session.phase_elapsed_sec = float(
        raw["combat_v1"]["entry"]["camera_transition_sec"]
    )

    scene_camera = app.scene_camera(base_camera)

    assert isinstance(scene_camera, CameraState)
    assert scene_camera.distance < base_camera.distance
    assert scene_camera.distance == pytest.approx(
        float(raw["camera"]["base_distance"]) / float(raw["combat_v1"]["entry"]["combat_zoom"])
    )
    assert scene_camera.target.x == pytest.approx(303.5)
    assert scene_camera.target.z == pytest.approx(192.0)


def test_combat_restored_camera_smoothly_zooms_back_to_follow() -> None:
    raw = make_runtime_raw()
    model = make_model(raw)
    app = make_app(raw, model)
    app.projection_mode = "perspective"
    base_camera = start_contact_combat(model, raw)
    assert model.combat_session is not None
    model.combat_session.elapsed_sec = float(raw["combat_v1"]["entry"]["camera_transition_sec"])
    model.combat_session.phase_elapsed_sec = float(
        raw["combat_v1"]["entry"]["camera_transition_sec"]
    )
    combat_camera = app.scene_camera(base_camera)
    assert isinstance(combat_camera, CameraState)

    model.combat_session = None
    restored = model.event_queue.emit(
        world_tick=model.world_tick,
        kind="combat_restored",
        actor_id="urchin_normal_01",
        target_id="player",
        world_position=(model.player.x, 0.0, model.player.z),
    )
    app.process_events([restored])

    restore_start = app.scene_camera(base_camera)
    assert isinstance(restore_start, CameraState)
    assert restore_start.distance == pytest.approx(combat_camera.distance)
    assert restore_start.target.x == pytest.approx(combat_camera.target.x)

    duration = float(raw["combat_v1"]["exit"]["camera_restore_sec"])
    app.update_combat_camera_restore(duration * 0.5)
    restore_mid = app.scene_camera(base_camera)
    assert isinstance(restore_mid, CameraState)
    assert combat_camera.distance < restore_mid.distance < base_camera.distance
    assert base_camera.target.x < restore_mid.target.x < combat_camera.target.x

    app.update_combat_camera_restore(duration)
    restore_done = app.scene_camera(base_camera)
    assert isinstance(restore_done, CameraState)
    assert restore_done.distance == pytest.approx(base_camera.distance)
    assert restore_done.target.x == pytest.approx(base_camera.target.x)
    assert app.combat_camera_restore is None


def test_affine_scene_camera_applies_reactions_as_zoom_and_fx_offset() -> None:
    raw = make_runtime_raw(shake=True, pulse=True)
    model = make_model(raw)
    app = make_app(raw, model)
    app.projection_mode = "affine"
    app.affine_projection_profile = AffineProjectionProfile.from_config(raw)
    base_camera = camera_for_model(raw, model)
    app.effects.process_events([make_event(model, "discharge_succeeded")], model)
    app.effects.update(0.06, model)

    scene_camera = app.scene_camera(base_camera)

    assert isinstance(scene_camera, AffineCameraState)
    assert scene_camera.zoom > 1.0
    assert abs(scene_camera.fx_offset_x) > 0.0 or abs(scene_camera.fx_offset_y) > 0.0
    assert scene_camera.anchor_x == pytest.approx(base_camera.anchor_x)
    assert scene_camera.anchor_y == pytest.approx(base_camera.anchor_y)
    assert scene_camera.yaw_deg == pytest.approx(float(raw["camera"]["yaw_deg"]))
    assert scene_camera.pitch_deg == pytest.approx(float(raw["camera"]["pitch_deg"]))


def test_affine_combat_scene_camera_uses_combat_zoom() -> None:
    raw = make_runtime_raw()
    model = make_model(raw)
    app = make_app(raw, model)
    app.projection_mode = "affine"
    app.affine_projection_profile = AffineProjectionProfile.from_config(raw)
    base_camera = start_contact_combat(model, raw)
    assert model.combat_session is not None
    model.combat_session.elapsed_sec = float(raw["combat_v1"]["entry"]["camera_transition_sec"])
    model.combat_session.phase_elapsed_sec = float(
        raw["combat_v1"]["entry"]["camera_transition_sec"]
    )

    scene_camera = app.scene_camera(base_camera)

    assert isinstance(scene_camera, AffineCameraState)
    assert scene_camera.zoom == pytest.approx(float(raw["combat_v1"]["entry"]["combat_zoom"]))
    assert scene_camera.target.x == pytest.approx(303.5)
    assert scene_camera.target.z == pytest.approx(192.0)


def test_combat_scene_camera_uses_battle_anchor_y() -> None:
    raw = make_runtime_raw()
    model = make_model(raw)
    app = make_app(raw, model)
    base_camera = start_contact_combat(model, raw)

    combat_camera = app.combat_scene_camera(base_camera)

    assert combat_camera.anchor_y == pytest.approx(
        raw["combat_v1"]["dynamic_camera"]["screen_anchor_y"]
    )
    assert combat_camera.anchor_y < base_camera.anchor_y


def test_bat006a_parry_timing_holds_camera_zoom_static() -> None:
    raw = make_runtime_raw()
    model = make_model(raw)
    app = make_app(raw, model)
    app.projection_mode = "affine"
    app.affine_projection_profile = AffineProjectionProfile.from_config(raw)
    base_camera = start_contact_combat(model, raw)
    session = model.combat_session
    assert session is not None
    session.phase = "PARRY_TIMING"
    session.phase_elapsed_sec = 0.0
    start_camera = app.scene_camera(base_camera)
    assert isinstance(start_camera, AffineCameraState)

    session.phase_elapsed_sec = 0.8
    later_camera = app.scene_camera(base_camera)
    assert isinstance(later_camera, AffineCameraState)

    assert start_camera.zoom == pytest.approx(1.6)
    assert later_camera.zoom == pytest.approx(start_camera.zoom)


def test_bat006a_perfect_reaches_snapshot_relative_peak_above_follow_zoom_max() -> None:
    raw = make_runtime_raw()
    model = make_model(raw)
    app = make_app(raw, model)
    app.projection_mode = "affine"
    app.affine_projection_profile = AffineProjectionProfile.from_config(raw)
    base_camera = start_contact_combat(model, raw)
    session = model.combat_session
    assert session is not None
    session.phase = "PARRY_RESOLVE"
    session.result = "perfect"
    session.phase_elapsed_sec = float(
        raw["combat_v1"]["dynamic_camera"]["durations_sec"]["perfect_push"]
    )

    scene_camera = app.scene_camera(base_camera)

    assert isinstance(scene_camera, AffineCameraState)
    assert scene_camera.zoom == pytest.approx(1.8)
    assert scene_camera.zoom > float(raw["camera"]["zoom_max"])


def test_bat006a_victory_cue_restores_to_snapshot_zoom_before_restore() -> None:
    raw = make_runtime_raw()
    model = make_model(raw)
    app = make_app(raw, model)
    app.projection_mode = "affine"
    app.affine_projection_profile = AffineProjectionProfile.from_config(raw)
    base_camera = start_contact_combat(model, raw)
    session = model.combat_session
    assert session is not None
    session.phase = "VICTORY_CUE"
    session.phase_elapsed_sec = 0.0
    early_camera = app.scene_camera(base_camera)
    assert isinstance(early_camera, AffineCameraState)

    session.phase_elapsed_sec = float(
        raw["combat_v1"]["dynamic_camera"]["durations_sec"]["victory_restore_delay"]
    ) + float(raw["combat_v1"]["dynamic_camera"]["durations_sec"]["victory_restore"])
    restored_camera = app.scene_camera(base_camera)
    assert isinstance(restored_camera, AffineCameraState)

    assert early_camera.zoom == pytest.approx(1.36)
    assert restored_camera.zoom == pytest.approx(camera_zoom(raw, base_camera))


def test_affine_combat_restore_camera_blends_zoom_back_to_follow() -> None:
    raw = make_runtime_raw()
    model = make_model(raw)
    app = make_app(raw, model)
    app.projection_mode = "affine"
    app.affine_projection_profile = AffineProjectionProfile.from_config(raw)
    base_camera = start_contact_combat(model, raw)
    assert model.combat_session is not None
    model.combat_session.elapsed_sec = float(raw["combat_v1"]["entry"]["camera_transition_sec"])
    model.combat_session.phase_elapsed_sec = float(
        raw["combat_v1"]["entry"]["camera_transition_sec"]
    )
    combat_camera = app.scene_camera(base_camera)
    assert isinstance(combat_camera, AffineCameraState)

    model.combat_session = None
    restored = model.event_queue.emit(
        world_tick=model.world_tick,
        kind="combat_restored",
        actor_id="urchin_normal_01",
        target_id="player",
        world_position=(model.player.x, 0.0, model.player.z),
    )
    app.process_events([restored])

    restore_start = app.scene_camera(base_camera)
    assert isinstance(restore_start, AffineCameraState)
    assert restore_start.zoom == pytest.approx(float(raw["combat_v1"]["entry"]["combat_zoom"]))

    app.update_combat_camera_restore(float(raw["combat_v1"]["exit"]["camera_restore_sec"]))
    restore_done = app.scene_camera(base_camera)
    assert isinstance(restore_done, AffineCameraState)
    assert restore_done.zoom == pytest.approx(
        float(raw["camera"]["base_distance"]) / base_camera.distance
    )


def test_affine_scene_camera_keeps_projection_fixed_for_overview_like_camera() -> None:
    raw = make_runtime_raw()
    model = make_model(raw)
    app = make_app(raw, model)
    app.projection_mode = "affine"
    app.affine_projection_profile = AffineProjectionProfile.from_config(raw)
    runtime = load_runtime_config("medium")
    base_distance = float(raw["camera"]["base_distance"])
    overview_like = CameraState(
        target=Vec3(768.0, 0.0, 768.0),
        yaw_deg=35.0,
        pitch_deg=25.0,
        horizontal_fov_deg=float(raw["camera"]["horizontal_fov_deg"]),
        distance=base_distance / 0.7,
        near=float(raw["camera"]["near"]),
        far=float(raw["camera"]["far"]),
        anchor_x=float(raw["camera"]["screen_anchor"][0]),
        anchor_y=float(raw["camera"]["screen_anchor"][1]),
        viewport_width=runtime.screen_width,
        viewport_height=runtime.screen_height,
    )

    scene_camera = app.scene_camera(overview_like)

    assert isinstance(scene_camera, AffineCameraState)
    assert scene_camera.target == overview_like.target
    assert scene_camera.zoom == pytest.approx(0.7)
    assert scene_camera.yaw_deg == pytest.approx(float(raw["camera"]["yaw_deg"]))
    assert scene_camera.pitch_deg == pytest.approx(float(raw["camera"]["pitch_deg"]))


def test_enemy_inspection_event_starts_focus_on_enemy_position() -> None:
    raw = make_runtime_raw()
    model = make_model(raw)
    app = make_app(raw, model)
    enemy = model.enemy_by_id("urchin_normal_01")
    assert enemy is not None
    enemy.x = model.player.x + 32.0
    enemy.z = model.player.z
    event = model.event_queue.emit(
        world_tick=model.world_tick,
        kind="interaction_started",
        actor_id="player",
        target_id=enemy.id,
        world_position=(enemy.x, 0.0, enemy.z),
        payload={"interaction_kind": "inspect", "duration_sec": 0.8},
    )

    app.process_events([event])

    assert app.camera_controller.focus is not None
    assert math.isinf(app.camera_controller.focus.hold_sec)
    target = app.camera_controller.focus.target_point
    assert target.x == pytest.approx(enemy.x)
    assert target.y == pytest.approx(max(6.0, model.enemy_radius(enemy)))
    assert target.z == pytest.approx(enemy.z)
