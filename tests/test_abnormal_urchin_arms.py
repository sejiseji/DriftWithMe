from __future__ import annotations

import json
import math
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.abnormal_urchin_arms import (
    DIR8,
    AbnormalUrchinArmSystem,
    abnormal_urchin_pose_state,
    arm_goal,
    quantize_dir8,
    quantize_dir8_hysteresis,
    solve_two_bone_ik,
)
from drift_with_me.render import Renderer

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("direction_index", range(8))
def test_quantize_dir8_recovers_each_canonical_direction(direction_index: int) -> None:
    direction_x, direction_y = DIR8[direction_index]

    assert quantize_dir8(direction_x, direction_y) == direction_index


def test_quantize_dir8_hysteresis_holds_near_boundary_then_switches() -> None:
    near_boundary = math.radians(23.0)
    clear_switch = math.radians(40.0)

    assert (
        quantize_dir8_hysteresis(
            math.cos(near_boundary),
            math.sin(near_boundary),
            previous=0,
            margin=0.08,
        )
        == 0
    )
    assert (
        quantize_dir8_hysteresis(
            math.cos(clear_switch),
            math.sin(clear_switch),
            previous=0,
            margin=0.08,
        )
        == 1
    )


@pytest.mark.parametrize(
    ("target", "upper", "lower"),
    (
        ((10.0, 6.0), 8.0, 9.0),
        ((100.0, 0.0), 8.0, 9.0),
        ((0.01, 0.0), 8.0, 9.0),
        ((0.0, 0.0), 8.0, 8.0),
    ),
)
def test_two_bone_ik_stays_finite_and_preserves_segment_lengths(
    target: tuple[float, float], upper: float, lower: float
) -> None:
    elbow_x, elbow_y, hand_x, hand_y = solve_two_bone_ik(
        0.0,
        0.0,
        target[0],
        target[1],
        upper,
        lower,
        1,
    )

    assert all(math.isfinite(value) for value in (elbow_x, elbow_y, hand_x, hand_y))
    assert math.hypot(elbow_x, elbow_y) == pytest.approx(upper, abs=1.0e-6)
    assert math.hypot(hand_x - elbow_x, hand_y - elbow_y) == pytest.approx(lower, abs=1.0e-6)
    assert math.hypot(hand_x, hand_y) <= upper + lower


def test_two_bone_ik_bend_sign_places_elbow_on_opposite_sides() -> None:
    positive = solve_two_bone_ik(0.0, 0.0, 10.0, 0.0, 8.0, 8.0, 1)
    negative = solve_two_bone_ik(0.0, 0.0, 10.0, 0.0, 8.0, 8.0, -1)

    assert positive[0] == pytest.approx(negative[0])
    assert positive[1] == pytest.approx(-negative[1])


def test_two_bone_ik_random_stress_never_produces_non_finite_coordinates() -> None:
    random_source = random.Random(0xAB002)
    for _ in range(2000):
        upper = random_source.uniform(0.1, 24.0)
        lower = random_source.uniform(0.1, 24.0)
        values = solve_two_bone_ik(
            random_source.uniform(-20.0, 20.0),
            random_source.uniform(-20.0, 20.0),
            random_source.uniform(-100.0, 100.0),
            random_source.uniform(-100.0, 100.0),
            upper,
            lower,
            random_source.choice((-1, 1)),
        )
        assert all(math.isfinite(value) for value in values)


@pytest.mark.parametrize(
    ("exploration_state", "combat_phase", "expected"),
    (
        ("IDLE", None, "IDLE"),
        ("APPROACH", None, "PLAYER_FOUND"),
        ("WINDUP", None, "CHARGE"),
        ("DASH", None, "DASH"),
        ("CAPTURED", None, "BUBBLE"),
        ("IDLE", "COMBAT_ENTRY", "PLAYER_FOUND"),
        ("IDLE", "COMBAT_READY", "CHARGE"),
        ("IDLE", "PARRY_TIMING", "DASH"),
        ("IDLE", "PERFECT_FREEZE", "STUN"),
        ("IDLE", "PERFECT_BUBBLE_WINDOW", "BUBBLE"),
        ("IDLE", "PERFECT_ZAP_WINDOW", "ZAP"),
        ("IDLE", "COMBAT_EXIT_DEFLECT", "RECOVER"),
    ),
)
def test_current_game_states_map_to_distinct_arm_poses(
    exploration_state: str, combat_phase: str | None, expected: str
) -> None:
    assert abnormal_urchin_pose_state(exploration_state, combat_phase) == expected


def test_charge_pulls_back_and_dash_reaches_forward() -> None:
    system = AbnormalUrchinArmSystem()
    rig = system.ensure_rig("abnormal", "CHARGE", 1.0, 0.0)
    arm = rig.arms[0]
    charge_goal = arm_goal(arm.spec, "CHARGE", 1.0, 0.0, 0)
    dash_goal = arm_goal(arm.spec, "DASH", 1.0, 0.0, 0)

    assert charge_goal[0] < arm.spec.shoulder_x
    assert dash_goal[0] > arm.spec.shoulder_x

    initial_target_x = arm.target_x
    system.update_enemy("abnormal", "DASH", 1.0, 0.0, 1.0 / 60.0)
    assert initial_target_x < arm.target_x < dash_goal[0]

    for _ in range(90):
        system.update_enemy("abnormal", "DASH", 1.0, 0.0, 1.0 / 60.0)
    assert arm.target_x > arm.spec.shoulder_x


def test_arm_system_builds_four_layered_arms_and_prunes_missing_enemies() -> None:
    system = AbnormalUrchinArmSystem()
    rig = system.update_enemy("abnormal", "IDLE", 1.0, 0.0, 1.0 / 60.0)

    assert len(rig.arms) == 4
    assert [arm.spec.layer for arm in rig.arms].count("back") == 2
    assert [arm.spec.layer for arm in rig.arms].count("front") == 2
    assert all(0 <= arm.upper_dir8 < 8 for arm in rig.arms)
    assert all(0 <= arm.lower_dir8 < 8 for arm in rig.arms)

    system.prune(())
    assert not system.rigs


def test_arm_system_uses_configured_fixed_rate() -> None:
    system = AbnormalUrchinArmSystem(fixed_hz=30)
    rig = system.update_enemy("abnormal", "IDLE", 1.0, 0.0, 1.0 / 30.0)

    assert rig.age_frames == 1


def test_runtime_config_and_manifest_enable_ik_assets() -> None:
    config = json.loads(
        (ROOT / "src/drift_with_me/data/game_config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / "src/drift_with_me/assets/jack_sprite.json").read_text(encoding="utf-8")
    )
    ik_config = config["abnormal_urchin_ik"]
    source_ids = {asset["id"] for asset in manifest["source_assets"]}

    assert ik_config["enabled"] is True
    assert {
        ik_config["body_asset"],
        ik_config["upper_arm_asset"],
        ik_config["lower_arm_asset"],
        ik_config["claw_asset"],
    } <= source_ids


def test_ik_sprite_draws_back_arms_then_body_then_front_arms(monkeypatch) -> None:
    renderer = Renderer(None)
    placement = SimpleNamespace()
    body = SimpleNamespace(definition=object())
    enemy = SimpleNamespace(id="abnormal", kind="abnormal", x=0.0, z=0.0, state="IDLE")
    model = SimpleNamespace(config={"abnormal_urchin_ik": {}})
    draw_order: list[str] = []

    renderer.abnormal_urchin_ik_asset = lambda _model, key: body if key == "body_asset" else None
    renderer.abnormal_urchin_arm_pose_state = lambda _model, _enemy: "IDLE"
    renderer.abnormal_urchin_attack_local_direction = lambda _model, _enemy, _camera: (1.0, 0.0)
    renderer.draw_abnormal_urchin_arm_layer = lambda _model, _rig, _placement, layer: (
        draw_order.append(layer)
    )
    renderer.draw_atmospheric_scaled_sprite = lambda _asset, _placement: draw_order.append("body")
    monkeypatch.setattr(
        "drift_with_me.render.placement_for_upright_height_billboard",
        lambda *_args, **_kwargs: placement,
    )

    result = renderer.draw_abnormal_urchin_ik_sprite(model, enemy, object())

    assert result is placement
    assert draw_order == ["back", "body", "front"]
