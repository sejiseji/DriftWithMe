"""One selected pointer authority for actions, coordinates and release readiness.

Web bridge failure is quarantined, never replaced with an unrelated native click.
A peek does not acknowledge a press; lifecycle cancellation is explicit.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PointerSnapshot:
    down: bool
    pressed: bool
    x: float
    y: float


class PointerDataError(ValueError):
    pass


def _number(value):
    if type(value) not in (int, float):
        raise PointerDataError("snapshot-number")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        raise PointerDataError("snapshot-number") from None
    if not math.isfinite(result):
        raise PointerDataError("snapshot-number")
    return result


def _integer(value, reason):
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise PointerDataError(reason)
    return value


def decode_pointer_json(raw, width, height, boundary):
    """Validate plain JSON primitives before conversion or UI dispatch."""
    if type(raw) is not str or len(raw) > 4096:
        raise PointerDataError("snapshot-type")

    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise PointerDataError("snapshot-json")
            out[key] = value
        return out

    try:
        data = json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, RecursionError):
        raise PointerDataError("snapshot-json") from None
    if type(data) is not dict or type(data.get("schema")) is not int or data["schema"] != 1:
        raise PointerDataError("snapshot-type")
    current, press, logical = (data.get(k) for k in ("current", "press", "logical"))
    if any(type(v) is not dict for v in (current, press, logical)):
        raise PointerDataError("snapshot-type")
    boundary["received"] = {
        "sequence": data.get("sequence"),
        "epoch": data.get("epoch"),
        "current": [current.get("x"), current.get("y")],
        "press": [press.get("x"), press.get("y")],
    }
    boundary["types"] = {
        "current": [type(current.get(k)).__name__ for k in ("x", "y")],
        "press": [type(press.get(k)).__name__ for k in ("x", "y")],
        "sequence": type(data.get("sequence")).__name__,
        "flags": [
            type(data.get(k)).__name__
            for k in ("down", "pressed", "released", "inside", "cancelled")
        ],
    }
    for key in ("down", "pressed", "released", "inside", "cancelled"):
        if type(data.get(key)) is not bool:
            raise PointerDataError("snapshot-flags")
    if data["down"] and data["released"]:
        raise PointerDataError("snapshot-flags")
    sequence = _integer(data.get("sequence"), "snapshot-sequence")
    epoch = _integer(data.get("epoch"), "snapshot-epoch")
    if any(type(logical.get(k)) is not int for k in ("width", "height")) or (
        logical.get("width"),
        logical.get("height"),
    ) != (width, height):
        raise PointerDataError("snapshot-size")
    point = tuple(_number(current.get(k)) for k in ("x", "y"))
    if data["pressed"]:
        if (
            type(press.get("sequence")) is not int
            or press["sequence"] != sequence
            or type(press.get("epoch")) is not int
            or press["epoch"] != epoch
            or data["cancelled"]
        ):
            raise PointerDataError("snapshot-press")
        point = tuple(_number(press.get(k)) for k in ("x", "y"))
    boundary["converted"] = list(point)
    # Both the current and down positions must obey the HOST logical-pixel contract.
    for xy in (tuple(_number(current.get(k)) for k in ("x", "y")), point):
        if not (0 <= xy[0] < width and 0 <= xy[1] < height):
            raise PointerDataError("snapshot-bounds")
    return data, point


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
        first_failure = not getattr(self, "_pointer_recovery_wait", False)
        if first_failure:
            self._pointer_generation = getattr(self, "_pointer_generation", 0) + 1
            if hasattr(self, "double_tap_move"):
                self.clear_world_input_latches()
        if hasattr(self, "pointer_boundary"):
            self.pointer_boundary.update(final=None, decision=reason)
        self._pointer_recovery_wait = True
        if consume and sequence is not None:
            self.browser_pointer_sequence_seen = sequence
        pointer = self._pointer_sample(
            "Q", reason, PointerSnapshot(down, False, 0.0, 0.0), sequence, consume=consume
        )
        # A rejected press cannot open DIAG itself. Publish its first evidence directly.
        if first_failure and reason not in {"recover-release", "source-change"}:
            trace = getattr(self, "ui_trace", None)
            if trace is not None:
                if not consume:
                    self.ui_trace_pointer(
                        "Q",
                        reason,
                        sequence,
                        getattr(self, "browser_pointer_sequence_seen", None),
                        pointer,
                    )
                self.ui_trace_menu_open("input:" + reason)
        return pointer

    def read_pointer_snapshot(self, *, consume=True):
        browser = self.read_browser_pointer_snapshot(consume=consume)
        if browser is not None:
            return browser
        self._pointer_native_used = True
        p = self.pyxel
        button = getattr(p, "MOUSE_BUTTON_LEFT", 0)
        self.pointer_boundary = {"raw": "native", "final": None}
        try:
            x, y = _number(p.mouse_x), _number(p.mouse_y)
        except PointerDataError:
            return self._pointer_quarantine("native-number", consume=consume)
        down = bool(p.btn(button))
        frame = getattr(p, "frame_count", None)
        pressed = bool(p.btnp(button)) and (
            frame is None or frame != getattr(self, "_native_pointer_frame_seen", None)
        )
        inside = 0 <= x < self.runtime.screen_width and 0 <= y < self.runtime.screen_height
        self.pointer_boundary.update(received={"current": [x, y]}, converted=[x, y])
        # A started drag may reach the window edge; a new UI press outside may not.
        if not inside and (
            pressed or (down and not getattr(self, "_pointer_last_consumed_down", False))
        ):
            return self._pointer_quarantine("native-bounds", consume=consume)
        if getattr(self, "_pointer_recovery_wait", False):
            pointer = self._pointer_quarantine("recover-release", consume=consume, down=down)
            if consume and not down:
                self._pointer_recovery_wait = False
            return pointer
        if consume and pressed and frame is not None:
            self._native_pointer_frame_seen = frame
        if not inside:
            x, y = self.clamp_pointer_position(x, y)
        self.pointer_boundary.update(final=[x, y], decision="accepted")
        return self._pointer_sample(
            "N", "native-only", PointerSnapshot(down, pressed, x, y), consume=consume
        )

    def read_browser_pointer_snapshot(self, *, consume=True):
        try:
            import js
        except ImportError:
            if getattr(self, "_browser_pointer_expected", False):
                self.pointer_boundary = {"raw": None, "final": None}
                return self._pointer_quarantine("import", consume=consume)
            return None
        self._browser_pointer_expected = True
        self.pointer_boundary = {"raw": None, "final": None}
        try:
            reader = getattr(js.window, "__driftWithMeReadPointerSnapshot", None)
        except Exception:
            return self._pointer_quarantine("window", consume=consume)
        if not callable(reader):
            return self._pointer_quarantine("missing", consume=consume)
        try:
            raw = reader()  # One synchronous immutable JSON value; no live coordinate attributes.
        except Exception:
            return self._pointer_quarantine("snapshot-read", consume=consume)
        self.pointer_boundary["raw"] = raw[:2048] if type(raw) is str else type(raw).__name__
        try:
            data, (x, y) = decode_pointer_json(
                raw, self.runtime.screen_width, self.runtime.screen_height, self.pointer_boundary
            )
        except PointerDataError as error:
            return self._pointer_quarantine(str(error), consume=consume)
        down, sequence = data["down"], data["sequence"]
        seen = getattr(self, "browser_pointer_sequence_seen", 0)
        if sequence < seen and not getattr(self, "_pointer_recovery_wait", False):
            return self._pointer_quarantine("snapshot-sequence", consume=consume, sequence=sequence)
        pressed = data["pressed"] and sequence != seen
        if not pressed:
            x, y = (_number(data["current"][k]) for k in ("x", "y"))
            self.pointer_boundary["converted"] = [x, y]
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
        self.pointer_boundary.update(final=[x, y], decision="accepted")
        return self._pointer_sample(
            "H",
            "ok",
            PointerSnapshot(down, pressed, x, y),
            sequence,
            consume=consume,
            released=data["released"],
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
