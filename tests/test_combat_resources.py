from __future__ import annotations

import math

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import AffineProjectionProfile, CameraState, ProjectedPoint, Vec3
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.render import Renderer, ScreenRect
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


def abnormal_enemy(model: GameModel):
    enemy = model.enemy_by_id("urchin_abnormal_01")
    assert enemy is not None
    return enemy


class RecordingPyxel:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def circ(self, *args) -> None:
        self.calls.append(("circ", *args))

    def circb(self, *args) -> None:
        self.calls.append(("circb", *args))

    def line(self, *args) -> None:
        self.calls.append(("line", *args))

    def pset(self, *args) -> None:
        self.calls.append(("pset", *args))


def enable_fast_combat(model: GameModel) -> None:
    model.config["combat_v1_enabled"] = True
    model.config["combat_v1"]["enemy_charge"].update(
        {
            "windup_sec": 0.03,
            "charge_sec": 0.05,
            "preimpact_slow_start_sec": 0.02,
            "round_gap_sec": 0.03,
        }
    )
    model.config["combat_v1"]["parry"]["sweep_sec"] = 0.3
    model.config["combat_v1"]["parry"]["input_debounce_sec"] = 0.0
    model.config["combat_v1"].setdefault("ready_sequence", {}).update(
        {"ready_sec": 0.03, "count_step_sec": 0.03, "go_sec": 0.02}
    )
    model.config["combat_v1"]["defense"]["failure_recovery_sec"] = 0.03
    model.config["combat_v1"].setdefault("victory", {})["cue_sec"] = 0.08


def start_fast_combat(model: GameModel, camera: CameraState):
    enable_fast_combat(model)
    model.player.x = 300.0
    model.player.z = 192.0
    enemy = normal_enemy(model)
    enemy.x = 307.0
    enemy.z = 192.0
    events = model.step(InputIntent(), camera, 1.0 / 60.0)
    assert [event.kind for event in events] == ["combat_started"]
    assert model.combat_session is not None
    return enemy


def test_contact_combat_starts_with_entry_settle_phase_before_windup() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    session = model.combat_session
    assert session is not None
    assert session.phase == "COMBAT_ENTRY"
    assert session.duration_sec == pytest.approx(model.combat_duration_sec())

    remaining = max(0.0, model.combat_duration_sec() - session.phase_elapsed_sec - 0.01)
    model.step(InputIntent(), camera, remaining)
    assert session.phase == "COMBAT_ENTRY"

    events = model.step(InputIntent(), camera, 0.02)
    assert session.phase == "COMBAT_READY"
    assert [event.kind for event in events] == ["combat_phase_changed"]
    assert events[0].payload["phase"] == "COMBAT_READY"


def test_combat_ready_sequence_holds_slider_before_first_parry() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    step_to_combat_phase(model, camera, "COMBAT_READY")
    session = model.combat_session
    assert session is not None

    assert model.combat_timing_slider_position(session) == pytest.approx(0.0)
    model.step(InputIntent(), camera, model.combat_ready_total_sec() * 0.5)
    assert session.phase == "COMBAT_READY"
    assert model.combat_timing_slider_position(session) == pytest.approx(0.0)

    model.step(InputIntent(), camera, model.combat_ready_total_sec())
    assert session.phase == "PARRY_TIMING"
    assert model.combat_timing_slider_position(session) == pytest.approx(0.0)


def test_combat_ready_sequence_repeats_before_later_parry() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    step_to_combat_phase(model, camera, "PARRY_TIMING")

    finish_current_parry_round(model, camera)
    advance_from_resolve(model, camera)
    step_to_combat_phase(model, camera, "COMBAT_READY")
    session = model.combat_session
    assert session is not None

    assert model.combat_timing_slider_position(session) == pytest.approx(0.0)
    model.step(InputIntent(), camera, model.combat_ready_total_sec() * 0.5)
    assert session.phase == "COMBAT_READY"
    assert model.combat_timing_slider_position(session) == pytest.approx(0.0)

    model.step(InputIntent(), camera, model.combat_ready_total_sec())
    assert session.phase == "PARRY_TIMING"
    assert model.combat_timing_slider_position(session) == pytest.approx(0.0)


def test_combat_entry_actor_presentation_moves_to_screen_anchors() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    session = model.combat_session
    assert session is not None
    renderer = Renderer(None)
    enemy = normal_enemy(model)

    session.phase_elapsed_sec = 0.0
    player_start = renderer.player_actor_presentation(model, camera)
    enemy_start = renderer.enemy_actor_presentation(model, enemy, camera)
    assert player_start.x == pytest.approx(session.snapshot.player.x)
    assert player_start.z == pytest.approx(session.snapshot.player.z)
    assert enemy_start.x == pytest.approx(session.snapshot.enemy.x)
    assert enemy_start.z == pytest.approx(session.snapshot.enemy.z)
    assert player_start.jump_y == pytest.approx(0.0)

    entry = model.combat_v1_config()["entry"]
    session.phase_elapsed_sec = (
        float(entry["isolation_sec"]) + float(entry["actor_settle_sec"]) * 0.5
    )
    player_mid = renderer.player_actor_presentation(model, camera)
    enemy_mid = renderer.enemy_actor_presentation(model, enemy, camera)
    assert player_mid.jump_y > 0.0
    assert enemy_mid.jump_y > 0.0
    assert (
        abs(player_mid.x - session.snapshot.player.x)
        + abs(player_mid.z - session.snapshot.player.z)
        > 1e-6
    )

    session.phase = "ENEMY_WINDUP"
    session.phase_elapsed_sec = 0.0
    player_settled = renderer.player_actor_presentation(model, camera)
    expected_player_screen = renderer.combat_actor_screen_anchor(model, camera, "player")
    assert expected_player_screen is not None
    projected_player = camera.project(Vec3(player_settled.x, 0.0, player_settled.z))
    assert projected_player is not None
    assert projected_player.x == pytest.approx(expected_player_screen[0], abs=1e-6)
    assert projected_player.y == pytest.approx(expected_player_screen[1], abs=1e-6)
    assert player_settled.jump_y == pytest.approx(0.0)


def test_combat_player_faces_enemy_presentation_after_settling() -> None:
    model, camera = make_model()
    enemy = start_fast_combat(model, camera)
    session = model.combat_session
    assert session is not None
    renderer = Renderer(None)

    model.player.moved_distance = 0.0
    session.phase = "ENEMY_WINDUP"
    session.phase_elapsed_sec = 0.0
    delta = renderer.combat_actor_screen_facing_delta(model, camera, "player")
    assert delta is not None

    assert renderer.player_sprite_direction_view(
        model, camera
    ) == renderer.screen_direction_view_name(*delta)
    enemy_delta = renderer.combat_actor_screen_facing_delta(model, camera, "enemy")
    assert enemy_delta is not None
    assert enemy_delta[0] == pytest.approx(-delta[0])
    assert enemy_delta[1] == pytest.approx(-delta[1])
    assert enemy is normal_enemy(model)


def step_to_combat_phase(model: GameModel, camera: CameraState, phase: str) -> list:
    events = []
    for _ in range(80):
        session = model.combat_session
        if session is not None and session.phase == phase:
            return events
        events.extend(model.step(InputIntent(), camera, 1.0 / 60.0))
    raise AssertionError(f"combat phase {phase} was not reached")


def step_until_combat_restored(model: GameModel, camera: CameraState) -> list:
    events = []
    for _ in range(240):
        if model.combat_session is None:
            return events
        events.extend(model.step(InputIntent(), camera, 1.0 / 60.0))
    raise AssertionError("combat session did not restore")


def hit_combat_marker(model: GameModel, camera: CameraState, marker: float) -> list:
    session = model.combat_session
    assert session is not None
    sweep = model.combat_parry_sweep_sec()
    target_elapsed = marker * sweep
    advance = max(0.0, target_elapsed - session.timing_elapsed_sec)
    events = model.step(InputIntent(), camera, advance)
    events.extend(model.step(InputIntent(barrier=True), camera, 0.0))
    model.step(InputIntent(), camera, 0.0)
    return events


def finish_current_parry_round(model: GameModel, camera: CameraState) -> list:
    events = model.step(InputIntent(), camera, model.combat_parry_sweep_sec() + 0.01)
    session = model.combat_session
    assert session is not None
    assert session.phase == "PARRY_RESOLVE"
    return events


def advance_from_resolve(model: GameModel, camera: CameraState) -> list:
    session = model.combat_session
    assert session is not None
    assert session.phase == "PARRY_RESOLVE"
    return model.step(InputIntent(), camera, model.combat_resolve_sec(session) + 0.01)


def resolve_round_with_hits(model: GameModel, camera: CameraState, hit_count: int):
    step_to_combat_phase(model, camera, "PARRY_TIMING")
    session = model.combat_session
    assert session is not None
    for marker in session.marker_positions[:hit_count]:
        hit_combat_marker(model, camera, marker)
    finish_current_parry_round(model, camera)
    session = model.combat_session
    assert session is not None
    return session


def start_deflect_exit(model: GameModel, camera: CameraState):
    start_fast_combat(model, camera)
    resolve_round_with_hits(model, camera, 2)
    advance_from_resolve(model, camera)
    session = resolve_round_with_hits(model, camera, 2)
    assert session.outcome == "deflect"
    advance_from_resolve(model, camera)
    session = model.combat_session
    assert session is not None
    assert session.phase == "COMBAT_EXIT_DEFLECT"
    return normal_enemy(model)


def step_exit_to_victory_cue(model: GameModel, camera: CameraState) -> list:
    session = model.combat_session
    assert session is not None
    assert session.phase in {"COMBAT_EXIT_DEFLECT", "COMBAT_EXIT_COUNTER"}
    events = model.step(InputIntent(), camera, model.combat_deflect_knockback_sec() + 0.01)
    session = model.combat_session
    assert session is not None
    assert session.phase == "VICTORY_CUE"
    return events


def start_perfect_freeze(model: GameModel, camera: CameraState):
    enemy = start_fast_combat(model, camera)
    session = resolve_round_with_hits(model, camera, 3)
    assert session.result == "perfect"
    assert session.successful_defense_count == 0
    assert session.outcome is None
    advance_from_resolve(model, camera)
    session = model.combat_session
    assert session is not None
    assert session.phase == "PERFECT_FREEZE"
    return enemy


def step_to_bubble_window(model: GameModel, camera: CameraState) -> None:
    model.step(InputIntent(), camera, model.combat_perfect_hold_sec() + 0.01)
    session = model.combat_session
    assert session is not None
    assert session.phase == "PERFECT_BUBBLE_WINDOW"


def step_to_zap_window(model: GameModel, camera: CameraState) -> None:
    step_to_bubble_window(model, camera)
    model.step(InputIntent(action_pressed=True), camera, 0.0)
    session = model.combat_session
    assert session is not None
    assert session.phase == "PERFECT_ZAP_WINDOW"


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
    model.config["combat_v1_enabled"] = False
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


def test_bat006_contact_combat_is_enabled_by_default() -> None:
    model, camera = make_model()
    model.player.x = 300.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    enemy = normal_enemy(model)
    enemy.x = 307.0
    enemy.z = 192.0

    events = model.step(InputIntent(), camera, 1.0 / 60.0)

    assert model.combat_v1_enabled()
    assert [event.kind for event in events] == ["combat_started"]
    assert model.combat_session is not None


def test_abnormal_urchin_contact_starts_combat() -> None:
    model, camera = make_model()
    model.config["combat_v1_enabled"] = True
    model.player.x = 730.0
    model.player.z = 384.0
    camera = camera_for_model(model)
    enemy = abnormal_enemy(model)
    enemy.x = 737.0
    enemy.z = 384.0
    enemy.state = "APPROACH"

    events = model.step(InputIntent(), camera, 1.0 / 60.0)

    assert "combat_started" in [event.kind for event in events]
    assert model.combat_session is not None
    assert model.combat_session.enemy_id == enemy.id
    combat_events = [event for event in events if event.kind == "combat_started"]
    assert combat_events[-1].payload["enemy_kind"] == "abnormal"


def test_bat001_contact_starts_isolated_combat_without_world_knockback() -> None:
    model, camera = make_model()
    model.config["combat_v1_enabled"] = True
    model.player.x = 300.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    enemy = normal_enemy(model)
    enemy.x = 307.0
    enemy.z = 192.0
    start_player = (model.player.x, model.player.z)
    start_enemy = (enemy.x, enemy.z)

    events = model.step(InputIntent(), camera, 1.0 / 60.0)

    assert [event.kind for event in events] == ["combat_started"]
    assert model.combat_session is not None
    assert (model.player.x, model.player.z) == start_player
    assert (enemy.x, enemy.z) == start_enemy
    assert model.debug.player_contacts == 1


def test_bat001_start_combat_cancels_auto_move_snapshot() -> None:
    model, _camera = make_model()
    model.config["combat_v1_enabled"] = True
    model.player.x = 300.0
    model.player.z = 192.0
    enemy = normal_enemy(model)
    enemy.x = 307.0
    enemy.z = 192.0
    model.auto_move_goal = (360.0, 192.0)
    model.auto_move_path = [(330.0, 192.0), (360.0, 192.0)]
    model.auto_move_stuck_elapsed = 0.25
    events = []

    model.start_contact_combat(enemy, events)

    assert [event.kind for event in events] == ["combat_started"]
    assert model.combat_session is not None
    assert model.combat_session.snapshot.auto_move_goal == (360.0, 192.0)
    assert model.combat_session.snapshot.auto_move_path == ((330.0, 192.0), (360.0, 192.0))
    assert model.combat_session.snapshot.auto_move_stuck_elapsed == pytest.approx(0.25)
    assert model.auto_move_goal is None
    assert model.auto_move_path == []


def test_bat001_combat_session_freezes_world_until_restore() -> None:
    model, camera = make_model()
    model.config["combat_v1_enabled"] = True
    model.player.x = 300.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    enemy = normal_enemy(model)
    enemy.x = 307.0
    enemy.z = 192.0

    model.step(InputIntent(), camera, 1.0 / 60.0)
    assert model.combat_session is not None
    start_player = (model.player.x, model.player.z)
    start_enemy = (enemy.x, enemy.z)
    start_tick = model.world_tick

    events = model.step(InputIntent(strength=1.0, screen_x=1.0), camera, 0.1)

    assert events == []
    assert model.combat_session is not None
    assert (model.player.x, model.player.z) == start_player
    assert (enemy.x, enemy.z) == start_enemy
    assert model.world_tick == start_tick


def test_bat001_combat_render_filter_draws_only_background_objects_without_world_mutation() -> None:
    model, camera = make_model()
    model.config["combat_v1_enabled"] = True
    model.player.x = 300.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    enemy = normal_enemy(model)
    enemy.x = 307.0
    enemy.z = 192.0
    before_objects = model.world.objects

    model.step(InputIntent(), camera, 1.0 / 60.0)
    renderer = Renderer(object())
    commands = renderer.world_commands(model, camera, 0.0)
    command_ids = {command.stable_id for command in commands}
    actor_ids = {"buddy", "player", enemy.id}
    background_commands = [command for command in commands if command.stable_id not in actor_ids]
    depth_floor = renderer.combat_background_depth_floor(model, camera)
    assert depth_floor is not None

    assert model.world.objects is before_objects
    assert actor_ids.issubset(command_ids)
    assert background_commands
    assert {
        other_enemy.id
        for other_enemy in model.enemies
        if other_enemy.id != enemy.id and other_enemy.id in command_ids
    } == set()


def test_bat001_combat_render_filter_allows_lateral_foreground_background() -> None:
    model, camera = make_model()
    model.config["combat_v1_enabled"] = True
    model.player.x = 300.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    enemy = normal_enemy(model)
    enemy.x = 307.0
    enemy.z = 192.0

    model.step(InputIntent(), camera, 1.0 / 60.0)
    renderer = Renderer(object())
    depth_floor = renderer.combat_background_depth_floor(model, camera)
    exclusion_rect = renderer.combat_background_screen_exclusion_rect(model, camera)
    assert depth_floor is not None
    assert exclusion_rect is not None

    foreground_depth = depth_floor - 20.0
    left_bounds = ScreenRect(exclusion_rect.x - 32, 80, 16, 16)
    right_bounds = ScreenRect(exclusion_rect.max_x + 16, 80, 16, 16)
    center_bounds = ScreenRect(exclusion_rect.x + 8, 80, 16, 16)

    assert renderer.combat_background_command_is_visible(
        depth_floor, foreground_depth, exclusion_rect, left_bounds
    )
    assert renderer.combat_background_command_is_visible(
        depth_floor, foreground_depth, exclusion_rect, right_bounds
    )
    assert not renderer.combat_background_command_is_visible(
        depth_floor, foreground_depth, exclusion_rect, center_bounds
    )


def test_bat001_combat_does_not_mutate_affine_projection_basis() -> None:
    model, camera = make_model()
    model.config["combat_v1_enabled"] = True
    model.player.x = 300.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    enemy = normal_enemy(model)
    enemy.x = 307.0
    enemy.z = 192.0
    before = AffineProjectionProfile.from_config(model.config)

    model.step(InputIntent(), camera, 1.0 / 60.0)
    during = AffineProjectionProfile.from_config(model.config)
    model.step(InputIntent(), camera, 1.0)
    after = AffineProjectionProfile.from_config(model.config)

    assert during == before
    assert after == before


def test_bat001_restore_separates_actors_and_sets_safety_windows() -> None:
    model, camera = make_model()
    model.config["combat_v1_enabled"] = True
    model.player.x = 300.0
    model.player.z = 192.0
    camera = camera_for_model(model)
    enemy = normal_enemy(model)
    enemy.x = 307.0
    enemy.z = 192.0

    model.step(InputIntent(), camera, 1.0 / 60.0)
    events = []
    model.restore_combat_session(events)

    assert events[-1].kind == "combat_restored"
    assert model.combat_session is None
    assert not model.player_overlaps_enemy(enemy)
    assert enemy.state == "REST"
    assert enemy.state_timer == pytest.approx(1.5)
    assert model.player.invulnerable_remaining == pytest.approx(0.5)
    assert model.combat_reentry_cooldowns[enemy.id] == pytest.approx(2.0)

    model.player.invulnerable_remaining = 0.0
    enemy.state = "APPROACH"
    enemy.x = model.player.x + 1.0
    enemy.z = model.player.z
    before_player = (model.player.x, model.player.z)
    cooldown_events = model.step(InputIntent(), camera, 1.0 / 60.0)

    assert cooldown_events == []
    assert model.combat_session is None
    assert (model.player.x, model.player.z) == before_player


def test_bat002_parry_patterns_have_three_markers_with_safe_spacing() -> None:
    model, _camera = make_model()
    model.config["combat_v1_enabled"] = True

    patterns = model.combat_marker_patterns()
    radius = model.combat_parry_hit_radius_normalized()

    assert patterns
    for pattern in patterns:
        assert len(pattern) == 3
        assert tuple(sorted(pattern)) == pattern
        assert pattern[0] >= 0.32
        assert pattern[0] >= radius
        assert pattern[-1] <= 1.0 - radius
        assert all(b - a >= radius * 2.0 for a, b in zip(pattern, pattern[1:], strict=False))


def test_bat002_slider_advances_monotonically_during_parry_timing() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    step_to_combat_phase(model, camera, "PARRY_TIMING")

    positions = []
    for _ in range(5):
        model.step(InputIntent(), camera, 0.03)
        session = model.combat_session
        assert session is not None
        slider = model.combat_timing_slider_position(session)
        assert slider is not None
        positions.append(slider)

    assert positions == sorted(positions)
    assert positions[-1] > positions[0]


def test_bat002_no_input_marks_all_miss_and_failure() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    step_to_combat_phase(model, camera, "PARRY_TIMING")

    events = model.step(InputIntent(), camera, model.combat_parry_sweep_sec() + 0.01)
    session = model.combat_session

    assert session is not None
    assert session.phase == "PARRY_RESOLVE"
    assert session.marker_judgements == ("MISS", "MISS", "MISS")
    assert session.hit_count == 0
    assert session.result == "failure"
    resolved = [event for event in events if event.kind == "combat_timing_resolved"]
    assert resolved[-1].payload["result"] == "failure"


def test_bat002_press_inside_hit_radius_hits_marker_once() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    step_to_combat_phase(model, camera, "PARRY_TIMING")
    session = model.combat_session
    assert session is not None
    first_marker = session.marker_positions[0]

    first_events = hit_combat_marker(model, camera, first_marker)
    second_events = model.step(InputIntent(barrier=True), camera, 0.0)

    session = model.combat_session
    assert session is not None
    assert session.marker_judgements[0] == "HIT"
    assert session.hit_count == 1
    assert len([event for event in first_events if event.kind == "combat_marker_judged"]) == 1
    assert not [event for event in second_events if event.kind == "combat_marker_judged"]


def test_bat002_one_hit_or_less_resolves_as_failure() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    step_to_combat_phase(model, camera, "PARRY_TIMING")
    session = model.combat_session
    assert session is not None
    hit_combat_marker(model, camera, session.marker_positions[0])

    model.step(InputIntent(), camera, model.combat_parry_sweep_sec() + 0.01)
    session = model.combat_session

    assert session is not None
    assert session.phase == "PARRY_RESOLVE"
    assert session.hit_count == 1
    assert session.result == "failure"
    assert session.successful_defense_count == 0
    assert session.failed_round_count == 1
    assert session.outcome is None


def test_bat002_two_hits_resolves_as_defense_success() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    step_to_combat_phase(model, camera, "PARRY_TIMING")
    session = model.combat_session
    assert session is not None
    hit_combat_marker(model, camera, session.marker_positions[0])
    hit_combat_marker(model, camera, session.marker_positions[1])

    model.step(InputIntent(), camera, model.combat_parry_sweep_sec() + 0.01)
    session = model.combat_session

    assert session is not None
    assert session.phase == "PARRY_RESOLVE"
    assert session.hit_count == 2
    assert session.result == "defense_success"
    assert session.successful_defense_count == 1
    assert session.failed_round_count == 0
    assert session.outcome is None


def test_bat002_three_hits_sets_perfect_result_only() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    step_to_combat_phase(model, camera, "PARRY_TIMING")
    session = model.combat_session
    assert session is not None
    markers = session.marker_positions

    for marker in markers:
        hit_combat_marker(model, camera, marker)
    model.step(InputIntent(), camera, model.combat_parry_sweep_sec() + 0.01)
    session = model.combat_session

    assert session is not None
    assert session.phase == "PARRY_RESOLVE"
    assert session.hit_count == 3
    assert session.result == "perfect"
    assert session.successful_defense_count == 0
    assert session.outcome is None
    assert session.marker_judgements == ("HIT", "HIT", "HIT")


def test_bat002_preimpact_slow_does_not_slow_timing_bar() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    resolve_round_with_hits(model, camera, 0)
    advance_from_resolve(model, camera)
    step_to_combat_phase(model, camera, "PREIMPACT_SLOW")

    assert model.combat_presentation_time_scale() == pytest.approx(0.3)

    step_to_combat_phase(model, camera, "PARRY_TIMING")
    session = model.combat_session
    assert session is not None
    before = model.combat_timing_slider_position(session)
    assert before == pytest.approx(0.0)

    model.step(InputIntent(), camera, 0.06)
    after = model.combat_timing_slider_position(session)

    assert after == pytest.approx(0.06 / model.combat_parry_sweep_sec())
    assert model.combat_presentation_time_scale() == pytest.approx(1.0)


def test_bat002_pause_by_not_stepping_keeps_slider_position() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    step_to_combat_phase(model, camera, "PARRY_TIMING")

    model.step(InputIntent(), camera, 0.05)
    session = model.combat_session
    assert session is not None
    paused_position = model.combat_timing_slider_position(session)
    assert paused_position is not None

    assert model.combat_timing_slider_position(session) == pytest.approx(paused_position)


def test_bat003_failure_loops_without_increasing_success_count() -> None:
    model, camera = make_model()
    enemy = start_fast_combat(model, camera)
    start_player = (model.player.x, model.player.z)
    start_enemy = (enemy.x, enemy.z)
    step_to_combat_phase(model, camera, "PARRY_TIMING")

    finish_current_parry_round(model, camera)
    session = model.combat_session

    assert session is not None
    assert session.result == "failure"
    assert session.successful_defense_count == 0
    assert session.failed_round_count == 1
    assert session.outcome is None
    advance_from_resolve(model, camera)
    assert model.combat_session is not None
    assert model.combat_session.phase == "ENEMY_WINDUP"
    assert (model.player.x, model.player.z) == start_player
    assert (enemy.x, enemy.z) == start_enemy


def test_bat003_success_count_survives_a_failed_round() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)

    resolve_round_with_hits(model, camera, 2)
    advance_from_resolve(model, camera)
    session = resolve_round_with_hits(model, camera, 0)

    assert session.result == "failure"
    assert session.successful_defense_count == 1
    assert session.failed_round_count == 1
    assert session.outcome is None
    advance_from_resolve(model, camera)
    assert model.combat_session is not None
    assert model.combat_session.phase == "ENEMY_WINDUP"
    assert model.combat_session.successful_defense_count == 1


def test_three_failed_parries_knock_player_out_of_enemy_aggro() -> None:
    model, camera = make_model()
    enemy = start_fast_combat(model, camera)
    player_start = (model.player.x, model.player.z)

    for round_index in range(3):
        session = resolve_round_with_hits(model, camera, 1 if round_index == 0 else 0)
        assert session.result == "failure"
        if round_index < 2:
            advance_from_resolve(model, camera)

    session = model.combat_session
    assert session is not None
    assert session.failed_round_count == 3
    assert session.outcome == "player_knockback"

    events = advance_from_resolve(model, camera)
    session = model.combat_session
    assert session is not None
    assert session.phase == "COMBAT_EXIT_PLAYER_KNOCKBACK"
    assert [event.kind for event in events if event.kind == "combat_player_knockback_started"] == [
        "combat_player_knockback_started"
    ]

    model.step(InputIntent(), camera, model.combat_player_knockback_sec() + 0.01)
    session = model.combat_session
    assert session is not None
    assert session.phase == "COMBAT_RESTORE_JUMP"
    assert math.hypot(session.player_return_x - enemy.x, session.player_return_z - enemy.z) > float(
        model.config["enemy"]["normal"]["aggro_radius"]
    )

    restore_events = step_until_combat_restored(model, camera)

    assert restore_events[-1].payload["combat_outcome"] == "player_knockback"
    assert math.hypot(model.player.x - enemy.x, model.player.z - enemy.z) > float(
        model.config["enemy"]["normal"]["aggro_radius"]
    )
    assert math.hypot(model.player.x - player_start[0], model.player.z - player_start[1]) > 1.0
    assert enemy.state == "REST"


def test_bat003_two_successful_rounds_start_deflect_exit() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)

    resolve_round_with_hits(model, camera, 2)
    advance_from_resolve(model, camera)
    session = resolve_round_with_hits(model, camera, 2)

    assert session.result == "defense_success"
    assert session.successful_defense_count == 2
    assert session.outcome == "deflect"

    events = advance_from_resolve(model, camera)
    session = model.combat_session

    assert session is not None
    assert session.phase == "COMBAT_EXIT_DEFLECT"
    assert [event.payload["phase"] for event in events if event.kind == "combat_phase_changed"] == [
        "COMBAT_EXIT_DEFLECT"
    ]


def test_bat003_deflect_knockback_is_presentation_only_until_restore() -> None:
    model, camera = make_model()
    enemy = start_deflect_exit(model, camera)
    enemy_world = (enemy.x, enemy.z)

    model.step(InputIntent(), camera, model.combat_deflect_knockback_sec() * 0.5)
    offset_x, offset_z = model.combat_enemy_presentation_offset(enemy)

    assert (enemy.x, enemy.z) == enemy_world
    assert (offset_x * offset_x + offset_z * offset_z) ** 0.5 > 1.0


def test_bat003_deflect_restore_sets_safety_windows_and_cooldown() -> None:
    model, camera = make_model()
    enemy = start_deflect_exit(model, camera)

    events = step_until_combat_restored(model, camera)

    assert events[-1].kind == "combat_restored"
    assert model.combat_session is None
    assert not model.player_overlaps_enemy(enemy)
    assert enemy.state == "REST"
    assert enemy.state_timer == pytest.approx(1.5)
    assert model.player.invulnerable_remaining == pytest.approx(0.5)
    assert model.combat_reentry_cooldowns[enemy.id] == pytest.approx(2.0)
    assert events[-1].payload["combat_outcome"] == "deflect"
    assert events[-1].payload["successful_defense_count"] == 2


def test_combat_restore_jump_returns_player_to_combat_start() -> None:
    model, camera = make_model()
    start_deflect_exit(model, camera)
    step_exit_to_victory_cue(model, camera)
    session = model.combat_session
    assert session is not None
    player_start = (session.snapshot.player.x, session.snapshot.player.z)

    events = model.step(InputIntent(), camera, model.combat_victory_cue_sec() + 0.01)
    session = model.combat_session

    assert session is not None
    assert session.phase == "COMBAT_RESTORE_JUMP"
    assert session.player_return_x == pytest.approx(player_start[0])
    assert session.player_return_z == pytest.approx(player_start[1])
    assert [event.payload["phase"] for event in events if event.kind == "combat_phase_changed"] == [
        "COMBAT_RESTORE_JUMP"
    ]

    renderer = Renderer(None)
    session.phase_elapsed_sec = model.combat_restore_jump_sec() * 0.5
    presentation = renderer.player_actor_presentation(model, camera)
    assert presentation.jump_y > 0.0

    model.step(InputIntent(), camera, model.combat_restore_jump_sec() + 0.01)
    assert model.combat_session is None
    assert model.player.x == pytest.approx(player_start[0])
    assert model.player.z == pytest.approx(player_start[1])


def test_combat_defeat_restore_timings_leave_room_for_linger() -> None:
    model, _camera = make_model()

    assert model.combat_deflect_knockback_sec() == pytest.approx(0.95)
    assert model.combat_victory_cue_sec() == pytest.approx(1.35)
    assert model.combat_restore_jump_sec() == pytest.approx(0.9)
    assert model.combat_player_knockback_sec() == pytest.approx(0.9)


def test_deflect_restore_commits_enemy_knockback_position() -> None:
    model, camera = make_model()
    enemy = start_deflect_exit(model, camera)
    renderer = Renderer(None)

    step_exit_to_victory_cue(model, camera)
    expected = renderer.enemy_actor_presentation(model, enemy, camera)
    model.step(InputIntent(), camera, model.combat_victory_cue_sec() + 0.01)
    session = model.combat_session
    assert session is not None
    assert session.enemy_return_x == pytest.approx(expected.x)
    assert session.enemy_return_z == pytest.approx(expected.z)

    step_until_combat_restored(model, camera)

    assert enemy.x == pytest.approx(expected.x)
    assert enemy.z == pytest.approx(expected.z)


def test_capture_restore_keeps_enemy_captured_at_knockback_position() -> None:
    model, camera = make_model()
    enemy = start_perfect_freeze(model, camera)
    step_to_zap_window(model, camera)
    renderer = Renderer(None)

    model.step(InputIntent(), camera, model.combat_zap_window_sec() + 0.01)
    step_exit_to_victory_cue(model, camera)
    expected = renderer.enemy_actor_presentation(model, enemy, camera)
    model.step(InputIntent(), camera, model.combat_victory_cue_sec() + 0.01)
    session = model.combat_session
    assert session is not None
    assert session.enemy_return_x == pytest.approx(expected.x)
    assert session.enemy_return_z == pytest.approx(expected.z)

    step_until_combat_restored(model, camera)

    assert enemy.state == "CAPTURED"
    assert enemy.x == pytest.approx(expected.x)
    assert enemy.z == pytest.approx(expected.z)


def test_enemy_restore_moves_farther_when_knockback_target_is_blocked(monkeypatch) -> None:
    model, camera = make_model()
    enemy = start_deflect_exit(model, camera)
    renderer = Renderer(None)
    session = model.combat_session
    assert session is not None
    dx, dz = model.combat_enemy_knockback_direction(session, enemy)
    step_exit_to_victory_cue(model, camera)
    expected = renderer.enemy_actor_presentation(model, enemy, camera)
    desired_x = expected.x
    desired_z = expected.z
    original_collides = model.world.collides_enemy_circle

    def collides_first_knockback_target(x: float, z: float, radius: float) -> bool:
        along = (x - desired_x) * dx + (z - desired_z) * dz
        lateral = abs((x - desired_x) * -dz + (z - desired_z) * dx)
        if math.isclose(along, 0.0, abs_tol=0.01) and lateral <= 0.01:
            return True
        return original_collides(x, z, radius)

    monkeypatch.setattr(model.world, "collides_enemy_circle", collides_first_knockback_target)

    model.step(InputIntent(), camera, model.combat_victory_cue_sec() + 0.01)
    session = model.combat_session
    assert session is not None

    moved_farther = (session.enemy_return_x - desired_x) * dx + (
        session.enemy_return_z - desired_z
    ) * dz
    assert moved_farther > 0.0
    assert not model.world.collides_enemy_circle(
        session.enemy_return_x, session.enemy_return_z, model.enemy_radius(enemy)
    )


def test_enemy_restore_steers_around_blocked_knockback_lane(monkeypatch) -> None:
    model, camera = make_model()
    enemy = start_deflect_exit(model, camera)
    renderer = Renderer(None)
    session = model.combat_session
    assert session is not None
    dx, dz = model.combat_enemy_knockback_direction(session, enemy)
    step_exit_to_victory_cue(model, camera)
    expected = renderer.enemy_actor_presentation(model, enemy, camera)
    desired_x = expected.x
    desired_z = expected.z
    original_collides = model.world.collides_enemy_circle

    def collides_knockback_lane(x: float, z: float, radius: float) -> bool:
        along = (x - desired_x) * dx + (z - desired_z) * dz
        lateral = abs((x - desired_x) * -dz + (z - desired_z) * dx)
        if -0.01 <= along <= 128.0 and lateral <= 0.5:
            return True
        return original_collides(x, z, radius)

    monkeypatch.setattr(model.world, "collides_enemy_circle", collides_knockback_lane)

    model.step(InputIntent(), camera, model.combat_victory_cue_sec() + 0.01)
    session = model.combat_session
    assert session is not None

    delta_x = session.enemy_return_x - desired_x
    delta_z = session.enemy_return_z - desired_z
    lateral = abs(delta_x * -dz + delta_z * dx)
    assert lateral > 0.5
    assert not model.world.collides_enemy_circle(
        session.enemy_return_x, session.enemy_return_z, model.enemy_radius(enemy)
    )


def test_enemy_restore_starts_from_victory_visual_endpoint() -> None:
    model, camera = make_model()
    enemy = start_perfect_freeze(model, camera)
    step_to_zap_window(model, camera)
    renderer = Renderer(None)

    model.step(InputIntent(action_pressed=True), camera, 0.0)
    step_exit_to_victory_cue(model, camera)
    victory_end = renderer.enemy_actor_presentation(model, enemy, camera)
    assert math.hypot(victory_end.x - enemy.x, victory_end.z - enemy.z) > 1.0

    model.step(InputIntent(), camera, model.combat_victory_cue_sec() + 0.01)
    session = model.combat_session
    assert session is not None
    assert session.phase == "COMBAT_RESTORE_JUMP"
    restore_start = renderer.enemy_actor_presentation(model, enemy, camera)

    assert restore_start.x == pytest.approx(victory_end.x)
    assert restore_start.z == pytest.approx(victory_end.z)


def test_bat004_perfect_enters_bubble_counter_window() -> None:
    model, camera = make_model()
    start_perfect_freeze(model, camera)

    assert model.combat_counter_action_mode() == "NONE"
    assert model.combat_presentation_time_scale() == pytest.approx(0.12)
    step_to_bubble_window(model, camera)

    session = model.combat_session
    assert session is not None
    assert session.result == "perfect"
    assert session.successful_defense_count == 0
    assert model.combat_counter_action_mode() == "BUBBLE"


def test_combat_counter_windows_allow_slightly_longer_input() -> None:
    model, _camera = make_model()

    assert model.combat_bubble_window_sec() == pytest.approx(1.65)
    assert model.combat_zap_window_sec() == pytest.approx(1.35)


def test_bat004_bubble_timeout_deflects_without_spending_water() -> None:
    model, camera = make_model()
    start_perfect_freeze(model, camera)
    step_to_bubble_window(model, camera)
    water_before = model.water

    model.step(InputIntent(), camera, model.combat_bubble_window_sec() + 0.01)
    session = model.combat_session

    assert session is not None
    assert session.phase == "COMBAT_EXIT_DEFLECT"
    assert session.outcome == "deflect"
    assert model.water == pytest.approx(water_before)


def test_bat004_insufficient_water_deflects_before_bubble_window() -> None:
    model, camera = make_model()
    model.water = model.combat_bubble_water_cost() - 1.0
    start_perfect_freeze(model, camera)
    water_before = model.water

    model.step(InputIntent(), camera, model.combat_perfect_hold_sec() + 0.01)
    session = model.combat_session

    assert session is not None
    assert session.phase == "COMBAT_EXIT_DEFLECT"
    assert session.outcome == "deflect"
    assert model.combat_counter_action_mode() == "NONE"
    assert model.water == pytest.approx(water_before)


def test_bat004_bubble_success_opens_zap_window_and_spends_water_once() -> None:
    model, camera = make_model()
    enemy = start_perfect_freeze(model, camera)
    step_to_bubble_window(model, camera)
    water_before = model.water

    events = model.step(InputIntent(action_pressed=True), camera, 0.0)
    session = model.combat_session

    assert session is not None
    assert session.phase == "PERFECT_ZAP_WINDOW"
    assert session.bubble_used
    assert enemy.state == "CAPTURED"
    assert model.water == pytest.approx(water_before - model.combat_bubble_water_cost())
    assert [event.kind for event in events if event.kind in {"bubble_fired", "enemy_captured"}] == [
        "bubble_fired",
        "enemy_captured",
    ]


def test_combat_bubble_counter_visual_tracks_bubble_branch() -> None:
    model, camera = make_model()
    start_perfect_freeze(model, camera)
    renderer = Renderer(None)

    assert not renderer.combat_bubble_counter_active(model)

    step_to_zap_window(model, camera)
    session = model.combat_session

    assert session is not None
    assert renderer.combat_bubble_counter_active(model)
    assert renderer.combat_bubble_counter_progress(model) == pytest.approx(0.0)

    session.phase_elapsed_sec = 0.35
    assert 0.0 < renderer.combat_bubble_counter_progress(model) < 1.0

    session.phase = "COMBAT_EXIT_COUNTER"
    session.outcome = "capture"
    session.phase_elapsed_sec = 0.0
    assert renderer.combat_bubble_counter_progress(model) == pytest.approx(1.0)
    assert renderer.combat_bubble_counter_visibility(model) == pytest.approx(1.0)


def test_bat004_zap_timeout_keeps_capture_and_spends_no_energy() -> None:
    model, camera = make_model()
    enemy = start_perfect_freeze(model, camera)
    step_to_zap_window(model, camera)
    energy_before = model.energy

    model.step(InputIntent(), camera, model.combat_zap_window_sec() + 0.01)
    events = step_until_combat_restored(model, camera)

    assert model.energy == pytest.approx(energy_before)
    assert enemy.state == "CAPTURED"
    assert events[-1].payload["combat_outcome"] == "capture"


def test_bat004_insufficient_energy_keeps_capture_without_spending_energy() -> None:
    model, camera = make_model()
    enemy = start_perfect_freeze(model, camera)
    model.energy = model.combat_zap_energy_cost() - 1.0
    step_to_bubble_window(model, camera)
    energy_before = model.energy

    model.step(InputIntent(action_pressed=True), camera, 0.0)
    session = model.combat_session

    assert session is not None
    assert session.phase == "COMBAT_EXIT_COUNTER"
    assert session.outcome == "capture"
    assert enemy.state == "CAPTURED"
    assert model.combat_counter_action_mode() == "NONE"
    assert model.energy == pytest.approx(energy_before)


def test_bat004_zap_success_defeats_enemy_and_spends_energy_once() -> None:
    model, camera = make_model()
    enemy = start_perfect_freeze(model, camera)
    step_to_zap_window(model, camera)
    energy_before = model.energy

    events = model.step(InputIntent(action_pressed=True), camera, 0.0)
    model.step(InputIntent(action_pressed=True), camera, 0.0)
    session = model.combat_session

    assert session is not None
    assert session.phase == "COMBAT_EXIT_COUNTER"
    assert session.outcome == "defeat"
    assert session.zap_used
    assert enemy.state != "DEFEATED"
    assert model.energy == pytest.approx(energy_before - model.combat_zap_energy_cost())
    assert [event.kind for event in events if event.kind == "discharge_succeeded"] == [
        "discharge_succeeded"
    ]
    restore_events = step_until_combat_restored(model, camera)
    assert enemy.state == "DEFEATED"
    assert restore_events[-1].payload["combat_outcome"] == "defeat"


def test_bat005_deflect_routes_through_victory_cue_before_restore() -> None:
    model, camera = make_model()
    enemy = start_deflect_exit(model, camera)
    player_before = (model.player.x, model.player.z)
    enemy_before = (enemy.x, enemy.z)

    events = step_exit_to_victory_cue(model, camera)
    session = model.combat_session

    assert session is not None
    assert session.outcome == "deflect"
    assert session.victory_actor == "buddy"
    assert model.combat_victory_actor() == "buddy"
    assert any(event.kind == "combat_victory_cue_started" for event in events)
    assert (model.player.x, model.player.z) == player_before
    assert (enemy.x, enemy.z) == enemy_before

    restore_events = step_until_combat_restored(model, camera)

    assert restore_events[-1].kind == "combat_restored"
    assert restore_events[-1].payload["combat_outcome"] == "deflect"
    assert enemy.state == "REST"


def test_bat005_capture_routes_through_victory_cue_before_restore() -> None:
    model, camera = make_model()
    enemy = start_perfect_freeze(model, camera)
    step_to_zap_window(model, camera)

    model.step(InputIntent(), camera, model.combat_zap_window_sec() + 0.01)
    events = step_exit_to_victory_cue(model, camera)
    session = model.combat_session

    assert session is not None
    assert session.outcome == "capture"
    assert any(event.kind == "combat_victory_cue_started" for event in events)
    assert enemy.state == "CAPTURED"

    restore_events = step_until_combat_restored(model, camera)

    assert restore_events[-1].payload["combat_outcome"] == "capture"
    assert enemy.state == "CAPTURED"


def test_bat005_defeat_commits_enemy_state_after_victory_cue() -> None:
    model, camera = make_model()
    enemy = start_perfect_freeze(model, camera)
    step_to_zap_window(model, camera)

    model.step(InputIntent(action_pressed=True), camera, 0.0)
    step_exit_to_victory_cue(model, camera)
    session = model.combat_session

    assert session is not None
    assert session.outcome == "defeat"
    assert enemy.state != "DEFEATED"

    restore_events = step_until_combat_restored(model, camera)

    assert restore_events[-1].payload["combat_outcome"] == "defeat"
    assert enemy.state == "DEFEATED"


def test_combat_defeat_special_moves_buddy_and_fades_enemy() -> None:
    model, camera = make_model()
    enemy = start_perfect_freeze(model, camera)
    step_to_zap_window(model, camera)
    renderer = Renderer(None)
    buddy_world = (model.buddy.x, model.buddy.z)

    model.step(InputIntent(action_pressed=True), camera, 0.0)
    session = model.combat_session
    assert session is not None
    assert session.phase == "COMBAT_EXIT_COUNTER"
    assert renderer.combat_defeat_special_active(model)

    session.phase_elapsed_sec = model.combat_deflect_knockback_sec() * 0.45
    buddy_mid = renderer.buddy_actor_presentation(model, camera, 0.0)
    target = renderer.combat_actor_anchor_ground(model, camera, "buddy")
    assert target is not None
    assert math.hypot(buddy_mid.x - buddy_world[0], buddy_mid.z - buddy_world[1]) > 1.0
    assert math.hypot(buddy_mid.x - target[0], buddy_mid.z - target[1]) < math.hypot(
        buddy_world[0] - target[0], buddy_world[1] - target[1]
    )
    assert buddy_mid.jump_y > 0.0
    assert renderer.combat_zap_spin_view_name(model) is not None

    session.phase = "VICTORY_CUE"
    total = model.combat_deflect_knockback_sec() + model.combat_victory_cue_sec()
    session.phase_elapsed_sec = total * 0.89 - model.combat_deflect_knockback_sec()
    assert renderer.combat_defeat_enemy_visibility(model, enemy) == pytest.approx(1.0)

    session.phase_elapsed_sec = total * 0.95 - model.combat_deflect_knockback_sec()
    assert renderer.combat_defeat_enemy_visibility(model, enemy) < 1.0

    session.phase = "COMBAT_RESTORE_JUMP"
    session.phase_elapsed_sec = 0.0
    assert renderer.combat_defeat_enemy_visibility(model, enemy) == pytest.approx(0.0)
    assert renderer.combat_defeat_enemy_flicker_hidden(model, enemy)


def test_combat_enemy_disappear_draws_burst_fragments() -> None:
    pyxel = RecordingPyxel()
    renderer = Renderer(pyxel)

    renderer.draw_combat_enemy_disappear(ProjectedPoint(120.0, 80.0, 1.0), 0.92)

    line_calls = [call for call in pyxel.calls if call[0] == "line"]
    pset_calls = [call for call in pyxel.calls if call[0] == "pset"]
    assert any(call[0] == "circ" for call in pyxel.calls)
    assert any(call[0] == "circb" for call in pyxel.calls)
    assert len(line_calls) >= 12
    assert len(pset_calls) >= 16


def test_combat_defeat_zap_target_matches_repositioned_enemy_sprite_center() -> None:
    model, camera = make_model()
    enemy = start_perfect_freeze(model, camera)
    step_to_zap_window(model, camera)
    renderer = Renderer(None)

    model.step(InputIntent(action_pressed=True), camera, 0.0)
    session = model.combat_session
    assert session is not None
    assert session.phase == "COMBAT_EXIT_COUNTER"
    session.phase_elapsed_sec = model.combat_deflect_knockback_sec() * 0.42

    presentation = renderer.enemy_actor_presentation(model, enemy, camera)
    enemy_center = camera.project(Vec3(presentation.x, 4.0 + presentation.jump_y, presentation.z))
    zap_target = renderer.combat_enemy_effect_target_point(model, enemy, camera)

    assert enemy_center is not None
    assert zap_target is not None
    assert zap_target.x == pytest.approx(enemy_center.x)
    assert zap_target.y == pytest.approx(enemy_center.y)
    assert zap_target.depth == pytest.approx(enemy_center.depth)


def test_combat_defeat_victory_buddy_matches_restore_start() -> None:
    model, camera = make_model()
    start_perfect_freeze(model, camera)
    step_to_zap_window(model, camera)
    renderer = Renderer(None)

    model.step(InputIntent(action_pressed=True), camera, 0.0)
    session = model.combat_session
    assert session is not None
    assert session.phase == "COMBAT_EXIT_COUNTER"

    session.phase = "VICTORY_CUE"
    session.phase_elapsed_sec = model.combat_victory_cue_sec()
    victory_end = renderer.buddy_actor_presentation(model, camera, 0.0)

    session.phase = "COMBAT_RESTORE_JUMP"
    session.phase_elapsed_sec = 0.0
    restore_start = renderer.buddy_actor_presentation(model, camera, 0.0)

    assert restore_start.x == pytest.approx(victory_end.x)
    assert restore_start.z == pytest.approx(victory_end.z)
    assert restore_start.jump_y == pytest.approx(victory_end.jump_y)


def test_combat_restore_starts_buddy_follow_snap_grace() -> None:
    model, camera = make_model()
    start_perfect_freeze(model, camera)
    step_to_zap_window(model, camera)

    model.step(InputIntent(action_pressed=True), camera, 0.0)
    step_until_combat_restored(model, camera)

    assert model.buddy_hard_follow_suppressed_remaining == pytest.approx(
        model.combat_buddy_follow_grace_sec()
    )


def test_buddy_hard_follow_snap_is_suppressed_during_post_combat_grace() -> None:
    model, camera = make_model()
    goal_x, goal_y, goal_z = model.buddy_goal(camera)
    model.buddy.x = goal_x - 200.0
    model.buddy.y = goal_y
    model.buddy.z = goal_z
    model.buddy.goal_x = goal_x
    model.buddy.goal_y = goal_y
    model.buddy.goal_z = goal_z
    before = model.buddy.distance_to_goal()

    model.buddy_hard_follow_suppressed_remaining = 0.6
    model.update_buddy(camera, 1.0 / 60.0)

    assert model.buddy.distance_to_goal() < before
    assert model.buddy.distance_to_goal() > 1.0

    model.buddy.x = goal_x - 200.0
    model.buddy.y = goal_y
    model.buddy.z = goal_z
    model.buddy_hard_follow_suppressed_remaining = 0.0
    model.update_buddy(camera, 1.0 / 60.0)

    assert model.buddy.x == pytest.approx(goal_x)
    assert model.buddy.y == pytest.approx(goal_y)
    assert model.buddy.z == pytest.approx(goal_z)


def test_bat005_failure_round_does_not_enter_victory_cue() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    resolve_round_with_hits(model, camera, 0)

    events = advance_from_resolve(model, camera)
    session = model.combat_session

    assert session is not None
    assert session.phase == "ENEMY_WINDUP"
    assert not [event for event in events if event.kind == "combat_victory_cue_started"]


def test_bat005_night_victory_cue_uses_player_actor() -> None:
    model, camera = make_model()
    model.config["simulation"]["day_phase"] = "night"
    start_deflect_exit(model, camera)

    step_exit_to_victory_cue(model, camera)

    assert model.combat_victory_actor() == "player"


def test_bat005_victory_cue_keeps_world_frozen_until_restore() -> None:
    model, camera = make_model()
    enemy = start_deflect_exit(model, camera)
    step_exit_to_victory_cue(model, camera)
    player_before = (model.player.x, model.player.z)
    enemy_before = (enemy.x, enemy.z)
    world_tick_before = model.world_tick

    events = model.step(InputIntent(), camera, model.combat_victory_cue_sec() * 0.5)

    assert model.combat_session is not None
    assert model.combat_session.phase == "VICTORY_CUE"
    assert events == []
    assert model.world_tick == world_tick_before
    assert (model.player.x, model.player.z) == player_before
    assert (enemy.x, enemy.z) == enemy_before


def test_bat006_marker_feedback_events_follow_hit_and_miss() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    step_to_combat_phase(model, camera, "PARRY_TIMING")
    session = model.combat_session
    assert session is not None

    hit_events = hit_combat_marker(model, camera, session.marker_positions[0])
    resolve_events = finish_current_parry_round(model, camera)

    assert [event.kind for event in hit_events if event.kind == "combat_marker_hit"] == [
        "combat_marker_hit"
    ]
    assert len([event for event in resolve_events if event.kind == "combat_marker_miss"]) == 2
    assert session.result == "failure"


def test_bat006_perfect_and_deflect_feedback_events_are_emitted() -> None:
    model, camera = make_model()
    start_fast_combat(model, camera)
    resolve_round_with_hits(model, camera, 3)

    perfect_events = advance_from_resolve(model, camera)

    assert model.combat_session is not None
    assert model.combat_session.phase == "PERFECT_FREEZE"
    assert [event.kind for event in perfect_events if event.kind == "combat_perfect_started"] == [
        "combat_perfect_started"
    ]

    model, camera = make_model()
    start_fast_combat(model, camera)
    resolve_round_with_hits(model, camera, 2)
    advance_from_resolve(model, camera)
    resolve_round_with_hits(model, camera, 2)

    deflect_events = advance_from_resolve(model, camera)

    assert model.combat_session is not None
    assert model.combat_session.phase == "COMBAT_EXIT_DEFLECT"
    assert [event.kind for event in deflect_events if event.kind == "combat_deflect_started"] == [
        "combat_deflect_started"
    ]


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
    not_finished = model.update_paused(10.0)
    finished = model.complete_interaction()

    assert not_finished == []
    assert model.water == 20.0
    assert [event.kind for event in started] == ["interaction_started"]
    assert [event.kind for event in finished] == ["inspection_completed"]
    assert model.interaction is None
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
