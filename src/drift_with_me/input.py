from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto

from drift_with_me.math3d import AffineCameraState, CameraState
from drift_with_me.model import InputIntent


class PointerState(Enum):
    IDLE = auto()
    WORLD_PENDING = auto()
    MOVE = auto()
    BARRIER = auto()
    UI_CAPTURE = auto()
    WAIT_ALL_RELEASE = auto()


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height


@dataclass(frozen=True)
class DoubleTapMoveRequest:
    screen_x: float
    screen_y: float
    camera: CameraState | AffineCameraState


class DoubleTapMoveRecognizer:
    def __init__(
        self,
        short_tap_sec: float,
        max_interval_sec: float,
        max_distance_px: float,
        drag_threshold_px: float,
    ) -> None:
        self.short_tap_sec = short_tap_sec
        self.max_interval_sec = max_interval_sec
        self.max_distance_px = max_distance_px
        self.drag_threshold_px = drag_threshold_px
        self.was_down = False
        self.candidate_active = False
        self.candidate_valid = False
        self.start_x = 0.0
        self.start_y = 0.0
        self.current_x = 0.0
        self.current_y = 0.0
        self.held_sec = 0.0
        self.start_camera: CameraState | None = None
        self.candidate_matches_last_tap = False
        self.last_tap_active = False
        self.last_tap_elapsed = 0.0
        self.last_tap_x = 0.0
        self.last_tap_y = 0.0

    def cancel(self) -> None:
        self.candidate_active = False
        self.candidate_valid = False
        self.start_camera = None
        self.candidate_matches_last_tap = False
        self.last_tap_active = False
        self.last_tap_elapsed = 0.0

    def update(
        self,
        down: bool,
        x: float,
        y: float,
        dt: float,
        ui_rects: tuple[Rect, ...],
        camera: CameraState | AffineCameraState,
        accepting_world_input: bool = True,
    ) -> DoubleTapMoveRequest | None:
        dt = max(0.0, dt)
        if self.last_tap_active:
            self.last_tap_elapsed += dt
            if self.last_tap_elapsed > self.max_interval_sec:
                self.last_tap_active = False

        if not accepting_world_input:
            self.cancel()
            self.was_down = down
            return None

        if not down:
            if self.was_down and self.candidate_active:
                self.held_sec += dt
            request = self._release(x, y)
            self.was_down = False
            return request

        if not self.was_down:
            self.was_down = True
            if any(rect.contains(x, y) for rect in ui_rects):
                self.candidate_active = False
                self.candidate_valid = False
                return None
            self.candidate_active = True
            self.candidate_valid = True
            self.start_x = x
            self.start_y = y
            self.current_x = x
            self.current_y = y
            self.held_sec = 0.0
            self.start_camera = camera
            self.candidate_matches_last_tap = False
            if self.last_tap_active and self.last_tap_elapsed <= self.max_interval_sec:
                distance = math.hypot(
                    self.start_x - self.last_tap_x, self.start_y - self.last_tap_y
                )
                self.candidate_matches_last_tap = distance <= self.max_distance_px
            return None

        self.current_x = x
        self.current_y = y
        self.held_sec += dt
        if not self.candidate_active:
            return None

        moved = math.hypot(self.current_x - self.start_x, self.current_y - self.start_y)
        if moved >= self.drag_threshold_px or self.held_sec > self.short_tap_sec:
            self.candidate_valid = False
            if moved >= self.drag_threshold_px:
                self.last_tap_active = False
        return None

    def _release(self, x: float, y: float) -> DoubleTapMoveRequest | None:
        if not self.was_down or not self.candidate_active:
            self.candidate_active = False
            self.candidate_valid = False
            return None

        start_camera = self.start_camera
        moved = math.hypot(x - self.start_x, y - self.start_y)
        short_tap = (
            self.candidate_valid
            and self.held_sec <= self.short_tap_sec
            and moved < self.drag_threshold_px
            and start_camera is not None
        )
        self.candidate_active = False
        self.candidate_valid = False
        self.start_camera = None
        if not short_tap:
            self.candidate_matches_last_tap = False
            return None

        if self.candidate_matches_last_tap:
            self.candidate_matches_last_tap = False
            self.last_tap_active = False
            self.last_tap_elapsed = 0.0
            return DoubleTapMoveRequest(self.start_x, self.start_y, start_camera)

        self.candidate_matches_last_tap = False
        self.last_tap_active = True
        self.last_tap_elapsed = 0.0
        self.last_tap_x = self.start_x
        self.last_tap_y = self.start_y
        return None


class PointerInput:
    def __init__(
        self,
        hold_sec: float,
        drag_threshold_px: float,
        deadzone_px: float,
        radius_px: float,
    ) -> None:
        self.hold_sec = hold_sec
        self.drag_threshold_px = drag_threshold_px
        self.deadzone_px = deadzone_px
        self.radius_px = radius_px
        self.state = PointerState.IDLE
        self.start_x = 0.0
        self.start_y = 0.0
        self.current_x = 0.0
        self.current_y = 0.0
        self.held_sec = 0.0
        self.was_down = False

    def cancel(self) -> None:
        self.state = PointerState.WAIT_ALL_RELEASE
        self.held_sec = 0.0

    def update(
        self,
        down: bool,
        x: float,
        y: float,
        dt: float,
        ui_rects: tuple[Rect, ...] = (),
    ) -> InputIntent:
        if not down:
            self.was_down = False
            self.held_sec = 0.0
            self.state = PointerState.IDLE
            return InputIntent()

        if self.state == PointerState.WAIT_ALL_RELEASE:
            self.was_down = True
            return InputIntent()

        if not self.was_down:
            self.start_x = x
            self.start_y = y
            self.current_x = x
            self.current_y = y
            self.held_sec = 0.0
            self.was_down = True
            self.state = (
                PointerState.UI_CAPTURE
                if any(rect.contains(x, y) for rect in ui_rects)
                else PointerState.WORLD_PENDING
            )
        else:
            self.current_x = x
            self.current_y = y
            self.held_sec += dt

        if self.state in {PointerState.UI_CAPTURE, PointerState.WAIT_ALL_RELEASE}:
            return InputIntent()

        dx = self.current_x - self.start_x
        dy = self.current_y - self.start_y
        distance = math.hypot(dx, dy)

        if self.state == PointerState.WORLD_PENDING:
            if distance >= self.drag_threshold_px:
                self.state = PointerState.MOVE
            elif self.held_sec >= self.hold_sec:
                self.state = PointerState.BARRIER

        if self.state == PointerState.BARRIER:
            return InputIntent(barrier=True)

        if self.state != PointerState.MOVE:
            return InputIntent()

        strength = max(
            0.0, min((distance - self.deadzone_px) / (self.radius_px - self.deadzone_px), 1.0)
        )
        if strength <= 0.0 or distance <= 1e-9:
            return InputIntent()
        return InputIntent(screen_x=dx / distance, screen_y=dy / distance, strength=strength)
