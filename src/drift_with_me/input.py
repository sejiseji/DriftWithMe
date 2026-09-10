from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto

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
