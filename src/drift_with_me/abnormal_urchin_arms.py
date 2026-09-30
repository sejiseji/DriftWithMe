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
    segment_lengths: tuple[float, ...]
    curve_sign: int
    outward_sign: int
    layer: str


@dataclass
class UrchinArm:
    spec: UrchinArmSpec
    target_x: float = 0.0
    target_y: float = 0.0
    target_vx: float = 0.0
    target_vy: float = 0.0
    joints: tuple[tuple[float, float], ...] = ()
    segment_dirs: tuple[int, ...] = ()


@dataclass
class UrchinArmRig:
    enemy_id: str
    state: str
    arms: tuple[UrchinArm, ...]
    age_frames: int = 0


DEFAULT_ARM_SPECS = (
    UrchinArmSpec("back_left", 27.0, 23.0, (7.0, 7.0, 7.0, 7.0), -1, -1, "back"),
    UrchinArmSpec("back_right", 37.0, 23.0, (7.0, 7.0, 7.0, 7.0), 1, 1, "back"),
    UrchinArmSpec("front_left", 23.0, 36.0, (7.0, 7.0, 7.0, 7.0), 1, -1, "front"),
    UrchinArmSpec("front_right", 41.0, 36.0, (7.0, 7.0, 7.0, 7.0), -1, 1, "front"),
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


def curved_chain_points(
    spec: UrchinArmSpec,
    target_x: float,
    target_y: float,
    state: str,
    age_frames: int,
    *,
    curve_strength: float = 1.0,
    undulation_strength: float = 1.0,
) -> tuple[tuple[float, float], ...]:
    shoulder_x = spec.shoulder_x
    shoulder_y = spec.shoulder_y
    segment_count = max(1, len(spec.segment_lengths))
    maximum_reach = max(1.0, sum(spec.segment_lengths) * 0.97)
    direction_x, direction_y = normalized_direction(
        target_x - shoulder_x,
        target_y - shoulder_y,
    )
    target_distance = math.hypot(target_x - shoulder_x, target_y - shoulder_y)
    distance = clamp(target_distance, maximum_reach * 0.30, maximum_reach)
    end_x = shoulder_x + direction_x * distance
    end_y = shoulder_y + direction_y * distance
    perpendicular_x = -direction_y
    perpendicular_y = direction_x

    curve_profiles = {
        "IDLE": (6.4, 3.0, 0.042),
        "PLAYER_FOUND": (7.0, 3.3, 0.052),
        "CHARGE": (7.8, 3.8, 0.060),
        "DASH": (3.0, 1.8, 0.075),
        "STUN": (3.4, 1.3, 0.030),
        "BUBBLE": (7.2, 3.8, 0.055),
        "ZAP": (5.0, 4.5, 0.200),
        "RECOVER": (5.7, 2.6, 0.042),
    }
    arc_amount, wave_amount, phase_speed = curve_profiles.get(state, curve_profiles["IDLE"])
    arc_amount *= max(0.0, curve_strength)
    wave_amount *= max(0.0, undulation_strength)
    arm_phase = (
        age_frames * phase_speed
        + (0.0 if spec.outward_sign < 0 else 1.8)
        + (0.7 if spec.layer == "front" else 0.0)
    )

    points: list[tuple[float, float]] = []
    for index in range(segment_count + 1):
        progress = index / segment_count
        envelope = math.sin(math.pi * progress)
        arc_offset = float(spec.curve_sign) * arc_amount * envelope
        traveling_wave = math.sin(arm_phase - progress * math.pi * 2.4) * wave_amount * envelope
        along_wave = math.cos(arm_phase - progress * math.pi * 1.6) * wave_amount * 0.20 * envelope
        points.append(
            (
                shoulder_x
                + (end_x - shoulder_x) * progress
                + perpendicular_x * (arc_offset + traveling_wave)
                + direction_x * along_wave,
                shoulder_y
                + (end_y - shoulder_y) * progress
                + perpendicular_y * (arc_offset + traveling_wave)
                + direction_y * along_wave,
            )
        )
    return tuple(points)


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
    phase_offset = {
        "back_left": 0.0,
        "back_right": 2.1,
        "front_left": 1.0,
        "front_right": 3.2,
    }.get(spec.name, 0.0)
    phase = age_frames * 0.035 + phase_offset
    idle_x = outward * 19.0
    idle_y = (-5.0 if spec.layer == "back" else 10.0) + math.sin(phase) * 2.0

    if state == "PLAYER_FOUND":
        return (
            spec.shoulder_x + attack_x * 14.0 + outward * 8.0,
            spec.shoulder_y + attack_y * 14.0 + idle_y * 0.3,
        )
    if state == "CHARGE":
        return (
            spec.shoulder_x - attack_x * 21.0 + outward * 5.0,
            spec.shoulder_y - attack_y * 21.0 + idle_y * 0.25,
        )
    if state == "DASH":
        return (
            spec.shoulder_x + attack_x * 26.0 + outward * 3.0,
            spec.shoulder_y + attack_y * 26.0 + idle_y * 0.2,
        )
    if state == "STUN":
        return spec.shoulder_x + outward * 7.0, spec.shoulder_y + 25.0
    if state == "BUBBLE":
        return (
            spec.shoulder_x + outward * 27.0,
            spec.shoulder_y + (-7.0 if spec.layer == "back" else 12.0),
        )
    if state == "ZAP":
        jitter_x = (-2.0, 1.0, 2.0, -1.0)[(age_frames + int(spec.shoulder_x)) % 4]
        jitter_y = (1.0, -2.0, 0.0, 2.0)[(age_frames + int(spec.shoulder_y)) % 4]
        return (
            spec.shoulder_x + outward * 16.0 + jitter_x,
            spec.shoulder_y + (3.0 if spec.layer == "back" else 10.0) + jitter_y,
        )
    if state == "RECOVER":
        return spec.shoulder_x + outward * 18.0, spec.shoulder_y + idle_y * 0.8
    return spec.shoulder_x + idle_x, spec.shoulder_y + idle_y


def quantized_arm_points(
    arm: UrchinArm,
) -> tuple[tuple[float, float], ...]:
    points = [(arm.spec.shoulder_x, arm.spec.shoulder_y)]
    for length, direction_index in zip(
        arm.spec.segment_lengths,
        arm.segment_dirs,
        strict=True,
    ):
        direction_x, direction_y = DIR8[direction_index]
        previous_x, previous_y = points[-1]
        points.append(
            (
                previous_x + direction_x * length,
                previous_y + direction_y * length,
            )
        )
    return tuple(points)


class AbnormalUrchinArmSystem:
    def __init__(
        self,
        *,
        fixed_hz: int = 60,
        damping: float = 0.78,
        stiffness: float = 0.08,
        direction_hysteresis: float = 0.08,
        curve_strength: float = 1.0,
        undulation_strength: float = 1.0,
    ) -> None:
        self.fixed_hz = max(1, int(fixed_hz))
        self.damping = clamp(damping, 0.0, 1.0)
        self.stiffness = max(0.0, stiffness)
        self.direction_hysteresis = max(0.0, direction_hysteresis)
        self.curve_strength = max(0.0, curve_strength)
        self.undulation_strength = max(0.0, undulation_strength)
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
            self._solve_arm(arm, state, 0)
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
                self._solve_arm(arm, state, rig.age_frames)
        return rig

    def prune(self, active_enemy_ids: Iterable[str]) -> None:
        active = set(active_enemy_ids)
        for enemy_id in tuple(self.rigs):
            if enemy_id not in active:
                del self.rigs[enemy_id]

    def _solve_arm(self, arm: UrchinArm, state: str, age_frames: int) -> None:
        arm.joints = curved_chain_points(
            arm.spec,
            arm.target_x,
            arm.target_y,
            state,
            age_frames,
            curve_strength=self.curve_strength,
            undulation_strength=self.undulation_strength,
        )
        previous_dirs = arm.segment_dirs
        if len(previous_dirs) != len(arm.spec.segment_lengths):
            previous_dirs = tuple(0 for _ in arm.spec.segment_lengths)
        arm.segment_dirs = tuple(
            quantize_dir8_hysteresis(
                end[0] - start[0],
                end[1] - start[1],
                previous,
                self.direction_hysteresis,
            )
            for start, end, previous in zip(
                arm.joints[:-1],
                arm.joints[1:],
                previous_dirs,
                strict=True,
            )
        )
