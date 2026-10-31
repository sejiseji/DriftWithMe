"""Opt-in UI diagnosis. Bounded RAM only; observers never read/acknowledge input."""

from __future__ import annotations

import json
from collections import deque
from contextlib import suppress
from copy import deepcopy
from functools import wraps


def trace_action(name):
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            trace = getattr(self, "ui_trace", None)
            if trace is None:
                return method(self, *args, **kwargs)
            try:
                before = self.ui_trace_state()
            except Exception:
                before = {}
            result = method(self, *args, **kwargs)
            try:
                after = self.ui_trace_state()
                action = name
                if name == "dialogue":
                    action = (
                        "reveal"
                        if after["chars"] > before["chars"] and after["page"] == before["page"]
                        else "page/step"
                        if result
                        else "terminal"
                    )
                self.ui_trace_note(action, result=bool(result), before=before, after=after)
            except Exception:
                pass
            return result

        return wrapped

    return decorate


class TraceMemory:
    def __init__(self, bridge=None):
        self.bridge = bridge
        self.events = deque(maxlen=32)
        self.taps = deque(maxlen=3)
        self.frozen = None
        self.last_draw = None
        self.input = {}
        self.sheet = False
        self.wait_release = False
        self.boot = 1
        self.update_number = 0
        self.start_frame = 0
        self.failure = "no-bridge"
        self.action = "none"
        self.last_gates = None
        try:
            if bridge is not None:
                self.boot = int(bridge.boot())
        except Exception:
            pass


class UITraceMixin:
    def initialize_ui_trace(self, enabled=None):
        bridge = None
        if enabled is not False:
            try:
                import js

                bridge = getattr(js.window, "__driftWithMeUiTrace", None)
            except Exception:
                pass
        if enabled is None:
            try:
                enabled = bridge is not None and bool(bridge.enabled)
            except Exception:
                enabled = False
        self.ui_trace = TraceMemory(bridge) if enabled else None

    def ui_trace_state(self):
        p = getattr(self, "office_dialogue_playback", None)
        consultation = getattr(self, "office_consultation", None)
        if consultation is not None:
            p = consultation
        pages = getattr(p, "pages", ())
        page = getattr(p, "page_index", 0)
        lines = pages[page] if pages and 0 <= page < len(pages) else ()
        office = getattr(self, "office", None)
        session = getattr(office, "current_session", None)
        case = getattr(office, "current_case", None)
        week = getattr(self, "work_week", None)
        lifecycle = getattr(self, "_lifecycle_state", None)
        return {
            "life": {
                "active": getattr(lifecycle, "active", None),
                "generation": getattr(lifecycle, "generation", None),
                "epoch": getattr(lifecycle, "input_epoch", None),
            },
            "frame": getattr(self, "frame", 0),
            "native": [
                getattr(getattr(self, "pyxel", None), "mouse_x", None),
                getattr(getattr(self, "pyxel", None), "mouse_y", None),
            ],
            "logical": [
                getattr(getattr(self, "runtime", None), "screen_width", None),
                getattr(getattr(self, "runtime", None), "screen_height", None),
            ],
            "screen": getattr(getattr(self, "screen", None), "name", "INIT"),
            "week": [getattr(week, "month", 0), getattr(week, "number", 0)],
            "case": getattr(case, "case_id", "-"),
            "question": getattr(session, "pending_question_id", None),
            "steps": len(getattr(session, "pending_dialogue_steps", ())),
            "page": page,
            "pages": len(pages),
            "chars": int(getattr(p, "revealed_chars", 0)),
            "total": sum(len(getattr(line, "text", "")) for line in lines),
            "menu": bool(getattr(self, "week_debug_menu_open", False)),
            "debug": bool(getattr(self, "week_debug_active", False)),
            "previews": [
                n
                for n in (
                    "ring_preview",
                    "park_preview_week",
                    "portrait_preview",
                    "garden_props_preview",
                    "nudibranch_preview",
                )
                if getattr(self, n, None) is not None
            ],
            "gates": {
                n: bool(getattr(self, n, False))
                for n in (
                    "_lifecycle_wait_draw",
                    "_lifecycle_wait_release",
                    "week_debug_wait_release",
                    "week_input_wait_for_release",
                    "field_input_wait_for_release",
                )
            },
        }

    def ui_trace_begin_frame(self):
        t = getattr(self, "ui_trace", None)
        if t is not None:
            t.update_number += 1
            t.start_frame = getattr(self, "frame", 0)
            t.action = "none"

    def ui_trace_note(self, action, **data):
        t = getattr(self, "ui_trace", None)
        if t is not None:
            try:
                t.action = action
                t.events.append(
                    {
                        "kind": action,
                        "update": t.update_number,
                        "sequence": t.input.get("sequence"),
                        **deepcopy(data),
                    }
                )
            except Exception:
                pass

    def ui_trace_pointer(self, source, reason, sequence=None, seen=None, pointer=None):
        t = getattr(self, "ui_trace", None)
        if t is None:
            return
        try:
            t.failure = reason
            t.input = {
                "source": source,
                "reason": reason,
                "native": [
                    getattr(getattr(self, "pyxel", None), "mouse_x", None),
                    getattr(getattr(self, "pyxel", None), "mouse_y", None),
                ],
                "sequence": sequence,
                "seen_before": seen,
                "seen_after": getattr(self, "browser_pointer_sequence_seen", None),
                "point": [pointer.x, pointer.y] if pointer is not None else None,
                "down": bool(getattr(pointer, "down", False)),
                "pressed": bool(getattr(pointer, "pressed", False)),
            }
            if pointer is not None and pointer.pressed:
                entry = {"kind": "pointer", "update": t.update_number, **deepcopy(t.input)}
                t.events.append(entry)
                t.taps.append(entry)
        except Exception:
            pass

    def ui_trace_end_frame(self):
        t = getattr(self, "ui_trace", None)
        if t is None:
            return
        try:
            blocked = getattr(self, "frame", 0) == t.start_frame
            owner = (
                "LIFECYCLE"
                if blocked
                else str(getattr(self, "last_ui_dispatch", (None, "unknown"))[1])
            )
            gates = self.ui_trace_state()["gates"]
            if t.taps and t.taps[-1]["update"] == t.update_number:
                t.taps[-1].update(owner=owner, action=t.action, gates=gates)
            if gates != t.last_gates:
                self.ui_trace_note("gates", owner=owner, gates=gates)
                t.last_gates = gates
        except Exception:
            pass

    def ui_trace_did_draw(self):
        t = getattr(self, "ui_trace", None)
        if t is not None:
            with suppress(Exception):
                t.last_draw = self.ui_trace_state()

    def ui_trace_menu_open(self, reason):
        t = getattr(self, "ui_trace", None)
        if t is None:
            return
        try:
            from drift_with_me.build_info import BUILD_ID

            try:
                host = json.loads(str(t.bridge.read())) if t.bridge is not None else {}
            except Exception:
                host = {"error": "host-read-failed"}
            if t.taps and t.taps[-1]["update"] == t.update_number:
                t.taps[-1].update(owner="OPEN", action=reason)
            t.frozen = deepcopy(
                {
                    "reason": reason,
                    "schema": 1,
                    "build": BUILD_ID,
                    "boot": t.boot,
                    "update": t.update_number,
                    "state": self.ui_trace_state(),
                    "last_draw": t.last_draw,
                    "input": t.input,
                    "taps": list(t.taps),
                    "events": list(t.events),
                    "host": host,
                }
            )
            t.sheet = False
            t.wait_release = False
        except Exception:
            # Observer failures never change whether the original menu opens.
            t.frozen = {"reason": reason, "error": "capture-failed"}

    def ui_trace_button_rect(self):
        return self.office_rect(112, 1, 70, 25)

    def ui_trace_back_rect(self):
        return self.office_rect(420, 0, 92, 24)

    def update_ui_trace_menu(self):
        t = getattr(self, "ui_trace", None)
        if t is None or not getattr(self, "week_debug_menu_open", False):
            return False
        if t.wait_release:
            if not self.pointer_snapshot.down:
                t.wait_release = False
            return True
        if t.sheet:
            if self.mouse_pressed_in(self.ui_trace_back_rect()) or self.key_pressed("KEY_ESCAPE"):
                t.sheet = False
                t.wait_release = True
            return True
        if t.frozen is not None and self.mouse_pressed_in(self.ui_trace_button_rect()):
            t.sheet = True
            t.wait_release = True
            return True
        return False

    def draw_ui_trace_entry(self):
        t = getattr(self, "ui_trace", None)
        if t is not None and t.frozen is not None:
            self.draw_week_debug_button(self.ui_trace_button_rect(), "DIAG")

    def ui_trace_lines(self):
        t = getattr(self, "ui_trace", None)
        f = t.frozen if t is not None and t.frozen else {}
        s, d, inp, host = (f.get(n, {}) or {} for n in ("state", "last_draw", "input", "host"))
        g = host.get("geometry", {}) or {}

        def fmt(v):
            if isinstance(v, dict):
                v = (
                    [v.get(n, "-") for n in ("left", "top", "width", "height")]
                    if "left" in v
                    else [v.get("width", "-"), v.get("height", "-")]
                )
            if isinstance(v, (list, tuple)):
                return "/".join(fmt(x) for x in v)
            if isinstance(v, float):
                return str(round(v, 1))
            return str(v if v is not None else "-")

        def vp(v):
            v = v or {}
            return fmt(
                [v.get(n, "-") for n in ("width", "height", "offsetLeft", "offsetTop", "scale")]
            )

        event_codes = {
            "pointerdown": "PD",
            "pointerup": "UP",
            "pointercancel": "CANCEL",
            "touchstart": "TS",
            "touchend": "TE",
            "mousedown": "MD",
            "resize": "RES",
            "scroll": "SCR",
        }
        lines = [
            f"V1 BUILD {f.get('build', '-')} BOOT {f.get('boot', '-')} WHY {f.get('reason', '-')}",
            f"U {s.get('frame', '-')} {s.get('screen', '-')} "
            f"D {d.get('frame', '-')} {d.get('screen', '-')} "
            f"W {fmt(s.get('week'))}",
            f"CASE {s.get('case', '-')} Q {s.get('question') or '-'}",
            f"PAGE {s.get('page', '-')}/{s.get('pages', '-')} "
            f"TXT {s.get('chars', '-')}/{s.get('total', '-')} "
            f"STEPS {s.get('steps', '-')}",
            f"SRC {inp.get('source', '-')} ERR {inp.get('reason', '-')} "
            f"SEQ {inp.get('sequence', '-')}/{inp.get('seen_before', '-')}",
            f"PY "
            f"L{fmt(inp.get('point'))} "
            f"N{fmt(inp.get('native'))} "
            f"D{int(inp.get('down', False))} P{int(inp.get('pressed', False))}",
        ]
        taps = host.get("attempts", host.get("taps", []))[-3:]
        for i in range(3):
            e = taps[i] if i < len(taps) else {}
            py = next(
                (
                    p
                    for p in reversed(f.get("taps", []))
                    if e.get("reason", "accepted") == "accepted"
                    and p.get("sequence") == e.get("sequence")
                ),
                {},
            )
            outcome = (
                py.get("owner", "-")
                if e.get("reason", "accepted") == "accepted"
                else "NO-" + str(e.get("reason"))
            )
            event_point = (
                e.get("down") if e.get("reason", "accepted") == "accepted" else e.get("logical")
            )
            lines.append(
                f"{i + 1} S{e.get('sequence', '-')} C{fmt(e.get('client'))} "
                f"L{fmt(event_point)} "
                f"N{fmt(py.get('native'))} "
                f"{outcome} {py.get('action', '-')}"
            )
        lines += [
            f"CV {fmt(g.get('canvas'))} BUF {fmt(g.get('backing'))}",
            f"T1CV {fmt((taps[0].get('geometry') or {}).get('canvas')) if taps else '-'} "
            f"L{fmt(g.get('logical'))}",
            f"VP C {vp(g.get('childViewport', {}))}",
            f"VP P {vp(g.get('parentViewport', {}))}",
            f"IF {fmt(g.get('iframeRect'))} "
            f"FX {g.get('iframeTransform', '-')} "
            f"E {host.get('events', [{}])[-1].get('epoch', '-') if host.get('events') else '-'}",
            f"L A{s.get('life', {}).get('active', '-')} "
            f"G{s.get('life', {}).get('generation', '-')} "
            f"PE{s.get('life', {}).get('epoch', '-')} WAIT "
            f"{'/'.join(str(int(v)) for v in s.get('gates', {}).values())}",
            f"DRAW TXT {d.get('chars', '-')}/{d.get('total', '-')} "
            f"N{fmt(d.get('native'))} "
            f"LOG {fmt(d.get('logical'))}",
            "EV "
            + "/".join(
                event_codes.get(e.get("type"), e.get("kind", "-")[:4])
                for e in host.get("events", [])[-6:]
            )
            + " / MEMORY ONLY",
        ]
        return [
            line.upper().replace("(", "/").replace(")", "").replace(",", "/")[:63] for line in lines
        ]

    def draw_ui_trace_sheet(self):
        t = getattr(self, "ui_trace", None)
        if t is None or not t.sheet:
            return False
        from drift_with_me.pixel_font import draw_pixel_text

        self.pyxel.cls(0)
        self.draw_office_text_in_rect(
            self.office_rect(8, 0, 400, 22), "INPUT TRACE - SCREENSHOT", 7
        )
        self.draw_week_debug_button(self.ui_trace_back_rect(), "BACK")
        for i, line in enumerate(self.ui_trace_lines()):
            draw_pixel_text(self.pyxel, 4, 27 + i * 12, line, 10 if i in (0, 4) else 7, scale=2)
        return True


def record_menu_open(app, reason):
    if getattr(app, "ui_trace", None) is not None:
        app.ui_trace_menu_open(reason)
