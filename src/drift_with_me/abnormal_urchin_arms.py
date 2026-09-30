from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

SQRT_HALF = math.sqrt(0.5)
DIR8 = (
    (1.0, 0.0),
    (SQRT_HALF, SQRT_HALF),
    (0.0, 1.0),
    (-SQRT_HALF, SQRT_HALF),
    (-1.0, 0.0),
    (-SQRT_HALF, -SQRT_HALF),
    (0.0, -1.0),
    (SQRT_HALF, -SQRT_HALF),
)


@dataclass(frozen=True)
class UrchinArmSpec:
    name: str
    shoulder_x: float
    shoulder_y: float
    upper_len: float
    lower_len: float
    bend_sign: int
    outward_sign: int
    layer: str


@dataclass
class UrchinArm:
    spec: UrchinArmSpec
    target_x: float = 0.0
    target_y: float = 0.0
    target_vx: float = 0.0
    target_vy: float = 0.0
    elbow_x: float = 0.0
    elbow_y: float = 0.0
    hand_x: float = 0.0
    hand_y: float = 0.0
    upper_dir8: int = 0
    lower_dir8: int = 0


@dataclass
class UrchinArmRig:
    enemy_id: str
    state: str
    arms: tuple[UrchinArm, ...]
    age_frames: int = 0


DEFAULT_ARM_SPECS = (
    UrchinArmSpec("back_left", 27.0, 23.0, 8.0, 9.0, -1, -1, "back"),
    UrchinArmSpec("back_right", 37.0, 23.0, 8.0, 9.0, 1, 1, "back"),
    UrchinArmSpec("front_left", 23.0, 36.0, 9.0, 10.0, 1, -1, "front"),
    UrchinArmSpec("front_right", 41.0, 36.0, 9.0, 10.0, -1, 1, "front"),
)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def normalized_direction(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    if length <= 1.0e-8 or not math.isfinite(length):
        return 1.0, 0.0
    return dx / length, dy / length


def quantize_dir8(dx: float, dy: float) -> int:
    if abs(dx) <= 1.0e-8 and abs(dy) <= 1.0e-8:
        return 0
    return max(range(len(DIR8)), key=lambda index: dx * DIR8[index][0] + dy * DIR8[index][1])


def quantize_dir8_hysteresis(
    dx: float,
    dy: float,
    previous: int,
    margin: float = 0.08,
) -> int:
    candidate = quantize_dir8(dx, dy)
    if candidate == previous or not 0 <= previous < len(DIR8):
        return candidate
    length = math.hypot(dx, dy)
    if length <= 1.0e-8:
        return previous
    candidate_dot = dx * DIR8[candidate][0] + dy * DIR8[candidate][1]
    previous_dot = dx * DIR8[previous][0] + dy * DIR8[previous][1]
    if candidate_dot <= previous_dot + max(0.0, margin) * length:
        return previous
    return candidate


def solve_two_bone_ik(
    shoulder_x: float,
    shoulder_y: float,
    target_x: float,
    target_y: float,
    upper_len: float,
    lower_len: float,
    bend_sign: int,
) -> tuple[float, float, float, float]:
    upper = max(abs(upper_len), 1.0e-4)
    lower = max(abs(lower_len), 1.0e-4)
    dx = target_x - shoulder_x
    dy = target_y - shoulder_y
    original_distance = math.hypot(dx, dy)
    if original_distance <= 1.0e-8 or not math.isfinite(original_distance):
        unit_x, unit_y = 1.0, 0.0
        original_distance = 0.0
    else:
        unit_x = dx / original_distance
        unit_y = dy / original_distance

    minimum_distance = abs(upper - lower) + 1.0e-4
    maximum_distance = max(minimum_distance, upper + lower - 1.0e-4)
    distance = clamp(original_distance, minimum_distance, maximum_distance)
    hand_x = shoulder_x + unit_x * distance
    hand_y = shoulder_y + unit_y * distance

    along = (upper * upper - lower * lower + distance * distance) / (2.0 * distance)
    height = math.sqrt(max(0.0, upper * upper - along * along))
    perpendicular_x = -unit_y
    perpendicular_y = unit_x
    sign = 1.0 if bend_sign >= 0 else -1.0
    elbow_x = shoulder_x + unit_x * along + perpendicular_x * height * sign
    elbow_y = shoulder_y + unit_y * along + perpendicular_y * height * sign
    return elbow_x, elbow_y, hand_x, hand_y


def abnormal_urchin_pose_state(
    exploration_state: str,
    combat_phase: str | None = None,
    *,
    combat_outcome: str | None = None,
    bubble_used: bool = False,
    zap_used: bool = False,
) -> str:
    if combat_phase is not None:
        if combat_phase == "COMBAT_ENTRY":
            return "PLAYER_FOUND"
        if combat_phase in {"COMBAT_READY", "ENEMY_WINDUP", "ENEMY_CHARGE", "PREIMPACT_SLOW"}:
            return "CHARGE"
        if combat_phase in {"PARRY_TIMING", "PARRY_RESOLVE"}:
            return "DASH"
        if combat_phase == "PERFECT_FREEZE":
            return "STUN"
        if combat_phase == "PERFECT_BUBBLE_WINDOW":
            return "BUBBLE"
        if combat_phase == "PERFECT_ZAP_WINDOW":
            return "ZAP"
        if combat_phase == "COMBAT_EXIT_COUNTER":
            if zap_used or combat_outcome == "defeat":
                return "ZAP"
            if bubble_used or combat_outcome == "capture":
                return "BUBBLE"
        if combat_phase in {
            "COMBAT_EXIT_DEFLECT",
            "COMBAT_EXIT_PLAYER_KNOCKBACK",
            "VICTORY_CUE",
            "COMBAT_RESTORE_JUMP",
        }:
            return "RECOVER"
        return "PLAYER_FOUND"

    return {
        "APPROACH": "PLAYER_FOUND",
        "WINDUP": "CHARGE",
        "DASH": "DASH",
        "RECOVER": "RECOVER",
        "REPELLED": "RECOVER",
        "CAPTURED": "BUBBLE",
    }.get(exploration_state, "IDLE")


def arm_goal(
    spec: UrchinArmSpec,
    state: str,
    attack_dx: float,
    attack_dy: float,
    age_frames: int,
) -> tuple[float, float]:
    attack_x, attack_y = normalized_direction(attack_dx, attack_dy)
    outward = float(spec.outward_sign)
    phase = age_frames * 0.035 + (0.0 if outward < 0.0 else 1.7)
    idle_x = outward * 12.0
    idle_y = (-3.0 if spec.layer == "back" else 7.0) + math.sin(phase) * 1.3

    if state == "PLAYER_FOUND":
        return (
            spec.shoulder_x + attack_x * 10.0 + outward * 5.0,
            spec.shoulder_y + attack_y * 10.0 + idle_y * 0.3,
        )
    if state == "CHARGE":
        return (
            spec.shoulder_x - attack_x * 14.0 + outward * 4.0,
            spec.shoulder_y - attack_y * 14.0 + idle_y * 0.25,
        )
    if state == "DASH":
        return (
            spec.shoulder_x + attack_x * 18.0 + outward * 3.0,
            spec.shoulder_y + attack_y * 18.0 + idle_y * 0.2,
        )
    if state == "STUN":
        return spec.shoulder_x + outward * 5.0, spec.shoulder_y + 16.0
    if state == "BUBBLE":
        return (
            spec.shoulder_x + outward * 19.0,
            spec.shoulder_y + (-5.0 if spec.layer == "back" else 9.0),
        )
    if state == "ZAP":
        jitter_x = (-2.0, 1.0, 2.0, -1.0)[(age_frames + int(spec.shoulder_x)) % 4]
        jitter_y = (1.0, -2.0, 0.0, 2.0)[(age_frames + int(spec.shoulder_y)) % 4]
        return (
            spec.shoulder_x + outward * 9.0 + jitter_x,
            spec.shoulder_y + (2.0 if spec.layer == "back" else 7.0) + jitter_y,
        )
    if state == "RECOVER":
        return spec.shoulder_x + outward * 11.0, spec.shoulder_y + idle_y * 0.8
    return spec.shoulder_x + idle_x, spec.shoulder_y + idle_y


def quantized_arm_points(
    arm: UrchinArm,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    shoulder = arm.spec.shoulder_x, arm.spec.shoulder_y
    upper_x, upper_y = DIR8[arm.upper_dir8]
    lower_x, lower_y = DIR8[arm.lower_dir8]
    elbow = (
        shoulder[0] + upper_x * arm.spec.upper_len,
        shoulder[1] + upper_y * arm.spec.upper_len,
    )
    hand = (
        elbow[0] + lower_x * arm.spec.lower_len,
        elbow[1] + lower_y * arm.spec.lower_len,
    )
    return shoulder, elbow, hand


class AbnormalUrchinArmSystem:
    def __init__(
        self,
        *,
        fixed_hz: int = 60,
        damping: float = 0.78,
        stiffness: float = 0.08,
        direction_hysteresis: float = 0.08,
    ) -> None:
        self.fixed_hz = max(1, int(fixed_hz))
        self.damping = clamp(damping, 0.0, 1.0)
        self.stiffness = max(0.0, stiffness)
        self.direction_hysteresis = max(0.0, direction_hysteresis)
        self.rigs: dict[str, UrchinArmRig] = {}

    def ensure_rig(
        self,
        enemy_id: str,
        state: str,
        attack_dx: float,
        attack_dy: float,
    ) -> UrchinArmRig:
        rig = self.rigs.get(enemy_id)
        if rig is not None:
            return rig
        arms = tuple(UrchinArm(spec=spec) for spec in DEFAULT_ARM_SPECS)
        rig = UrchinArmRig(enemy_id=enemy_id, state=state, arms=arms)
        for arm in arms:
            arm.target_x, arm.target_y = arm_goal(arm.spec, state, attack_dx, attack_dy, 0)
            self._solve_arm(arm)
        self.rigs[enemy_id] = rig
        return rig

    def update_enemy(
        self,
        enemy_id: str,
        state: str,
        attack_dx: float,
        attack_dy: float,
        dt: float,
    ) -> UrchinArmRig:
        rig = self.ensure_rig(enemy_id, state, attack_dx, attack_dy)
        rig.state = state
        steps = max(0, int(round(max(0.0, dt) * self.fixed_hz)))
        for _ in range(steps):
            rig.age_frames += 1
            for arm in rig.arms:
                goal_x, goal_y = arm_goal(
                    arm.spec,
                    state,
                    attack_dx,
                    attack_dy,
                    rig.age_frames,
                )
                arm.target_vx = (
                    arm.target_vx * self.damping + (goal_x - arm.target_x) * self.stiffness
                )
                arm.target_vy = (
                    arm.target_vy * self.damping + (goal_y - arm.target_y) * self.stiffness
                )
                arm.target_x += arm.target_vx
                arm.target_y += arm.target_vy
                self._solve_arm(arm)
        return rig

    def prune(self, active_enemy_ids: Iterable[str]) -> None:
        active = set(active_enemy_ids)
        for enemy_id in tuple(self.rigs):
            if enemy_id not in active:
                del self.rigs[enemy_id]

    def _solve_arm(self, arm: UrchinArm) -> None:
        arm.elbow_x, arm.elbow_y, arm.hand_x, arm.hand_y = solve_two_bone_ik(
            arm.spec.shoulder_x,
            arm.spec.shoulder_y,
            arm.target_x,
            arm.target_y,
            arm.spec.upper_len,
            arm.spec.lower_len,
            arm.spec.bend_sign,
        )
        arm.upper_dir8 = quantize_dir8_hysteresis(
            arm.elbow_x - arm.spec.shoulder_x,
            arm.elbow_y - arm.spec.shoulder_y,
            arm.upper_dir8,
            self.direction_hysteresis,
        )
        arm.lower_dir8 = quantize_dir8_hysteresis(
            arm.hand_x - arm.elbow_x,
            arm.hand_y - arm.elbow_y,
            arm.lower_dir8,
            self.direction_hysteresis,
        )
