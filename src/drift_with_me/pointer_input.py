"""One selected pointer authority for actions, coordinates and release readiness.

Web bridge failure is quarantined, never replaced with an unrelated native click.
A peek does not acknowledge a press; lifecycle cancellation is explicit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PointerSnapshot:
    down: bool
    pressed: bool
    x: float
    y: float


class PointerInputMixin:
    def _pointer_sample(
        self,
        source,
        reason,
        pointer,
        sequence=None,
        *,
        consume=True,
        released=None,
        seen_before=None,
    ):
        previous_down = getattr(self, "_pointer_last_consumed_down", False)
        status = dict(
            source=source,
            reason=reason,
            down=pointer.down,
            pressed=pointer.pressed,
            released=bool(previous_down and not pointer.down)
            if released is None
            else bool(released),
            sequence=sequence,
            generation=getattr(self, "_pointer_generation", 0),
            cancelled=source == "Q",
        )
        self.pointer_input_status = status
        if consume:
            self._pointer_last_consumed_down = pointer.down
            self.ui_trace_pointer(source, reason, sequence, seen_before, pointer)
        return pointer

    def _pointer_quarantine(self, reason, *, consume=True, down=False, sequence=None):
        if not getattr(self, "_pointer_recovery_wait", False):
            self._pointer_generation = getattr(self, "_pointer_generation", 0) + 1
            if hasattr(self, "double_tap_move"):
                self.clear_world_input_latches()
        self._pointer_recovery_wait = True
        if consume and sequence is not None:
            self.browser_pointer_sequence_seen = sequence
        return self._pointer_sample(
            "Q", reason, PointerSnapshot(down, False, 0.0, 0.0), sequence, consume=consume
        )

    def read_pointer_snapshot(self, *, consume=True):
        browser = self.read_browser_pointer_snapshot(consume=consume)
        if browser is not None:
            return browser
        self._pointer_native_used = True
        p = self.pyxel
        button = getattr(p, "MOUSE_BUTTON_LEFT", 0)
        x, y = self.clamp_pointer_position(float(p.mouse_x), float(p.mouse_y))
        frame = getattr(p, "frame_count", None)
        pressed = bool(p.btnp(button)) and (
            frame is None or frame != getattr(self, "_native_pointer_frame_seen", None)
        )
        if consume and pressed and frame is not None:
            self._native_pointer_frame_seen = frame
        return self._pointer_sample(
            "N", "native-only", PointerSnapshot(bool(p.btn(button)), pressed, x, y), consume=consume
        )

    def read_browser_pointer_snapshot(self, *, consume=True):
        try:
            import js
        except ImportError:
            if getattr(self, "_browser_pointer_expected", False):
                return self._pointer_quarantine("import", consume=consume)
            return None
        self._browser_pointer_expected = True
        try:
            bridge = getattr(js.window, "__driftWithMePointer", None)
        except Exception:
            return self._pointer_quarantine("window", consume=consume)
        if bridge is None:
            return self._pointer_quarantine("missing", consume=consume)
        try:
            down, flag = bool(bridge.down), bool(bridge.pressed)
            sequence = int(bridge.sequence)
            x, y = float(bridge.x), float(bridge.y)
            if not math.isfinite(x) or not math.isfinite(y):
                return self._pointer_quarantine("current-nan", consume=consume)
            seen = getattr(self, "browser_pointer_sequence_seen", 0)
            pressed = flag and sequence != seen
            if pressed:
                x, y = float(getattr(bridge, "pressedX", x)), float(getattr(bridge, "pressedY", y))
                if not math.isfinite(x) or not math.isfinite(y):
                    return self._pointer_quarantine("down-nan", consume=consume, sequence=sequence)
        except Exception:
            return self._pointer_quarantine("fields", consume=consume)
        if getattr(self, "_pointer_native_used", False):
            self._pointer_native_used = False
            self._pointer_quarantine("source-change", consume=consume, down=down, sequence=sequence)
        if getattr(self, "_pointer_recovery_wait", False):
            pointer = self._pointer_quarantine(
                "recover-release", consume=consume, down=down, sequence=sequence
            )
            if consume and not down:
                self._pointer_recovery_wait = False
            return pointer
        if consume and pressed:
            self.browser_pointer_sequence_seen = sequence
        x, y = self.clamp_pointer_position(x, y)
        return self._pointer_sample(
            "H",
            "ok",
            PointerSnapshot(down, pressed, x, y),
            sequence,
            consume=consume,
            released=bool(getattr(bridge, "released", False)),
            seen_before=seen,
        )

    def peek_pointer_snapshot(self):
        """Observe without acknowledging an action; failure still invalidates the source."""
        return self.read_pointer_snapshot(consume=False)

    def discard_pointer_press(self):
        """Explicit transition cancellation; never used as a release-state query."""
        pointer = self.read_pointer_snapshot()
        if hasattr(self, "pointer_input_status"):
            self.pointer_input_status.update(pressed=False, cancelled=True)
        return pointer
