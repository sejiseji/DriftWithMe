"""Independent observer contract and before-mutation hook coverage."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.ui_trace import TraceMemory, UITraceMixin

ROOT = Path(__file__).resolve().parents[1] / "src" / "drift_with_me"


@pytest.mark.parametrize(
    ("filename", "reason", "mutation"),
    [
        ("week_debug.py", "launch", "self.week_debug_compact = False"),
        ("week_debug.py", "calendar", "self.week_debug_compact = True"),
        ("week_debug.py", "badge", "self.week_debug_menu_open = True"),
        ("week_debug.py", "park-escape", "self.jump_to_debug_week"),
        ("week_debug.py", "park-menu", "self.jump_to_debug_week"),
        ("week_debug.py", "garden-menu", "self.jump_to_debug_week"),
        ("week_debug.py", "slug-menu", "self.jump_to_debug_week"),
        ("week_debug.py", "portrait-menu", "self.portrait_preview = None"),
        ("ring_puzzle.py", "ring-quit", "self.restore_ring_grid_palette()"),
    ],
)
def test_all_menu_open_hooks_precede_destructive_state_changes(filename, reason, mutation):
    source = (ROOT / filename).read_text()
    tree = ast.parse(source)
    hooks = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "record_menu_open"
        and len(node.args) == 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == reason
    ]
    assert len(hooks) == 1
    following = "\n".join(source.splitlines()[hooks[0].end_lineno :][:4])
    assert mutation in following


class Probe(UITraceMixin):
    def ui_trace_state(self):
        return {"screen": "SOURCE", "gates": {}, "nested": [1]}

    def read_pointer_snapshot(self):
        raise AssertionError("diagnostics must never acknowledge input")

    read_browser_pointer_snapshot = read_pointer_snapshot


def test_frozen_cause_survives_draw_input_history_and_sheet_updates():
    probe = Probe()
    host = {"taps": [{"sequence": 7}], "events": []}
    probe.ui_trace = TraceMemory(SimpleNamespace(read=lambda: json.dumps(host)))
    trace = probe.ui_trace
    trace.last_draw = {"screen": "OFFICE", "chars": 8}
    trace.input = {"sequence": 7, "point": [30, 40]}
    trace.taps.append({"sequence": 7, "update": 0})
    probe.ui_trace_menu_open("calendar")
    frozen = json.dumps(trace.frozen, sort_keys=True)
    host["taps"][0]["sequence"] = 9
    trace.input["point"][0] = 99
    trace.taps[-1]["owner"] = "OTHER"
    trace.last_draw["chars"] = 500
    trace.sheet = True
    probe.ui_trace_begin_frame()
    probe.ui_trace_note("back")
    probe.ui_trace_did_draw()
    probe.ui_trace_end_frame()
    assert json.dumps(trace.frozen, sort_keys=True) == frozen


def test_unavailable_or_malformed_host_capture_stays_local_and_safe():
    probe = Probe()
    probe.ui_trace = TraceMemory(SimpleNamespace(read=lambda: "not-json"))
    probe.ui_trace_menu_open("calendar")
    assert probe.ui_trace.frozen["reason"] == "calendar"
    assert probe.ui_trace.frozen["host"] == {"error": "host-read-failed"}
    assert len(probe.ui_trace.events) == 0


def test_disabled_observer_works_during_partial_initialization():
    probe = Probe()
    probe.initialize_ui_trace(False)
    probe.ui_trace_begin_frame()
    probe.ui_trace_menu_open("launch")
    probe.ui_trace_pointer("H", "missing")
    probe.ui_trace_end_frame()
    probe.ui_trace_did_draw()
    assert probe.ui_trace is None
    assert not probe.update_ui_trace_menu()
