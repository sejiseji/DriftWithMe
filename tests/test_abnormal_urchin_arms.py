from __future__ import annotations

import json
import math
import random
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.abnormal_urchin_arms import (
    DEFAULT_ARM_SPECS,
    DIR8,
    AbnormalUrchinArmSystem,
    abnormal_urchin_pose_state,
    arm_goal,
    curved_chain_points,
    quantize_dir8,
    quantize_dir8_hysteresis,
    quantized_arm_points,
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


def test_curved_chain_adds_three_internal_joints_and_reaches_target() -> None:
    spec = DEFAULT_ARM_SPECS[0]
    target = spec.shoulder_x + 14.0, spec.shoulder_y + 2.0

    points = curved_chain_points(spec, *target, "IDLE", 0)

    assert len(points) == 5
    assert points[0] == (spec.shoulder_x, spec.shoulder_y)
    assert points[-1] == pytest.approx(target)


def test_curved_chain_sign_places_arc_on_opposite_sides() -> None:
    source = DEFAULT_ARM_SPECS[0]
    positive = replace(source, curve_sign=1)
    negative = replace(source, curve_sign=-1)
    target = source.shoulder_x + 15.0, source.shoulder_y

    positive_points = curved_chain_points(positive, *target, "IDLE", 0, undulation_strength=0.0)
    negative_points = curved_chain_points(negative, *target, "IDLE", 0, undulation_strength=0.0)

    assert positive_points[2][0] == pytest.approx(negative_points[2][0])
    assert positive_points[2][1] - source.shoulder_y == pytest.approx(
        -(negative_points[2][1] - source.shoulder_y)
    )


def test_curved_chain_wave_travels_without_moving_endpoints() -> None:
    spec = DEFAULT_ARM_SPECS[2]
    target = spec.shoulder_x + 13.0, spec.shoulder_y + 4.0
    early = curved_chain_points(spec, *target, "IDLE", 0)
    later = curved_chain_points(spec, *target, "IDLE", 50)

    assert early[0] == later[0]
    assert early[-1] == pytest.approx(later[-1])
    assert early[1:-1] != later[1:-1]


def test_curved_chain_random_stress_never_produces_non_finite_coordinates() -> None:
    random_source = random.Random(0xAB002)
    for _ in range(2000):
        spec = random_source.choice(DEFAULT_ARM_SPECS)
        points = curved_chain_points(
            spec,
            random_source.uniform(-100.0, 100.0),
            random_source.uniform(-100.0, 100.0),
            random_source.choice(
                ("IDLE", "PLAYER_FOUND", "CHARGE", "DASH", "STUN", "BUBBLE", "ZAP")
            ),
            random_source.randrange(10000),
        )
        assert all(math.isfinite(value) for point in points for value in point)


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
    assert all(len(arm.joints) == 5 for arm in rig.arms)
    assert all(len(arm.segment_dirs) == 4 for arm in rig.arms)
    assert all(0 <= direction < 8 for arm in rig.arms for direction in arm.segment_dirs)
    for arm in rig.arms:
        points = quantized_arm_points(arm)
        assert len(points) == 5
        for start, end, expected_length in zip(
            points[:-1],
            points[1:],
            arm.spec.segment_lengths,
            strict=True,
        ):
            assert math.dist(start, end) == pytest.approx(expected_length)

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
        ik_config["link_asset"],
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
