"""Recorded HOST coordinate and hostile-boundary regressions (not real Safari)."""

import json
import sys
from types import SimpleNamespace

import pytest

from drift_with_me.app import DriftWithMeApp as App
from drift_with_me.config import load_runtime_config
from drift_with_me.input import Rect

POINT = [355.46911287162806, 112.14184032312642]


def payload():
    return dict(
        schema=1,
        sequence=26,
        epoch=8,
        down=True,
        pressed=True,
        released=False,
        cancelled=False,
        inside=True,
        current=dict(zip(("x", "y"), POINT, strict=True)),
        press=dict(x=POINT[0], y=POINT[1], sequence=26, epoch=8),
        logical=dict(width=512, height=236),
    )


def subject(monkeypatch, data=None):
    app = App.__new__(App)
    app.runtime = load_runtime_config()
    app.browser_pointer_sequence_seen = 25
    app.ui_trace = None
    app.pyxel = SimpleNamespace(
        mouse_x=355, mouse_y=111, MOUSE_BUTTON_LEFT=1, btn=lambda _: True, btnp=lambda _: True
    )
    data = payload() if data is None else data
    window = SimpleNamespace(__driftWithMeReadPointerSnapshot=lambda: json.dumps(data))
    monkeypatch.setitem(sys.modules, "js", SimpleNamespace(window=window))
    return app, data, window


def test_recorded_point_is_not_saturated_to_calendar(monkeypatch):
    app, _, _ = subject(monkeypatch)
    pointer = app.read_pointer_snapshot()
    assert [pointer.x, pointer.y] == POINT
    app.pointer_snapshot = pointer
    assert not app.mouse_pressed_in(Rect(476, 0, 36, 27))
    boundary = app.pointer_boundary
    assert json.loads(boundary["raw"])["press"]["x"] == POINT[0]
    assert boundary["received"]["press"] == POINT
    assert boundary["converted"] == boundary["final"] == POINT
    assert boundary["types"]["press"] == ["float", "float"]
    assert app.browser_pointer_sequence_seen == 26


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("schema", True, "snapshot-type"),
        ("sequence", True, "snapshot-sequence"),
        ("sequence", -1, "snapshot-sequence"),
        ("sequence", 2**53, "snapshot-sequence"),
        ("epoch", "8", "snapshot-epoch"),
        ("down", 1, "snapshot-flags"),
        ("released", True, "snapshot-flags"),
        ("pressed", "true", "snapshot-flags"),
        ("inside", None, "snapshot-flags"),
        ("current.x", True, "snapshot-number"),
        ("current.x", "355", "snapshot-number"),
        ("current.x", None, "snapshot-number"),
        ("current.x", float("nan"), "snapshot-number"),
        ("current.y", float("inf"), "snapshot-number"),
        ("current.x", 10**1000, "snapshot-number"),
        ("press.x", -1, "snapshot-bounds"),
        ("press.y", 236, "snapshot-bounds"),
        ("press.x", 1000, "snapshot-bounds"),
        ("current.x", 512, "snapshot-bounds"),
        ("current.y", -0.1, "snapshot-bounds"),
        ("logical.width", 1024, "snapshot-size"),
        ("logical.height", 236.0, "snapshot-size"),
        ("press.sequence", 25, "snapshot-press"),
        ("press.epoch", 7, "snapshot-press"),
        ("cancelled", True, "snapshot-press"),
    ],
)
def test_invalid_snapshot_cannot_activate_ui_or_native(monkeypatch, field, value, reason):
    app, data, _ = subject(monkeypatch)
    target = data
    path = field.split(".")
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    p = app.read_pointer_snapshot()
    assert not p.pressed and not p.down
    assert app.pointer_input_status["source"] == "Q"
    assert app.pointer_input_status["reason"] == reason
    assert app.pointer_boundary["final"] is None


@pytest.mark.parametrize(
    "raw", [None, 123, "{broken", "[]", "null", '{"schema":1,"schema":1}', " " * 4097]
)
def test_corrupt_json_is_quarantined(monkeypatch, raw):
    app, _, window = subject(monkeypatch)
    window.__driftWithMeReadPointerSnapshot = lambda: raw
    assert not app.read_pointer_snapshot().pressed
    assert app.pointer_input_status["source"] == "Q"


def test_reader_called_once_and_no_live_coordinate_properties(monkeypatch):
    app, data, window = subject(monkeypatch)

    class Hostile:
        def __getattribute__(self, name):
            raise AssertionError("live proxy field accessed: " + name)

    window.__driftWithMePointer = Hostile()
    calls = []

    def read():
        calls.append(1)
        raw = json.dumps(data)
        data["press"]["x"] = 1000
        data["press"]["y"] = -1
        return raw

    window.__driftWithMeReadPointerSnapshot = read
    p = app.read_pointer_snapshot()
    assert [p.x, p.y] == POINT and calls == [1]


def test_used_press_retains_current_drag_position(monkeypatch):
    app, data, _ = subject(monkeypatch)
    assert app.read_pointer_snapshot().pressed
    data["current"] = dict(x=460, y=180)
    p = app.read_pointer_snapshot()
    assert not p.pressed and p.down and (p.x, p.y) == (460, 180)
    assert app.pointer_boundary["final"] == [460, 180]


def test_cancelled_geometry_allows_unused_old_press_epoch(monkeypatch):
    app, data, _ = subject(monkeypatch)
    data.update(down=False, pressed=False, released=True, cancelled=True, epoch=9)
    p = app.read_pointer_snapshot()
    assert not p.pressed and app.pointer_input_status["source"] == "H"


def test_native_new_outside_press_cannot_become_calendar(monkeypatch):
    app, _, _ = subject(monkeypatch)
    monkeypatch.setitem(sys.modules, "js", None)
    app.pyxel.mouse_x, app.pyxel.mouse_y = 999, -10
    p = app.read_pointer_snapshot()
    assert not p.pressed and not p.down
    assert app.pointer_input_status["reason"] == "native-bounds"


def test_native_started_drag_can_reach_screen_edge(monkeypatch):
    app, _, _ = subject(monkeypatch)
    monkeypatch.setitem(sys.modules, "js", None)
    assert app.read_pointer_snapshot().pressed
    app.pyxel.mouse_x, app.pyxel.mouse_y = 999, -10
    app.pyxel.btnp = lambda _: False
    p = app.read_pointer_snapshot()
    assert p.down and not p.pressed and (p.x, p.y) == (511, 0)


def test_actual_host_json_drag_and_release(monkeypatch):
    import test_screen_flow_mina_bridge as h

    host = h.HostEvents((852, 329, 0, 0, 852, 329))
    try:
        app, _, window = subject(monkeypatch)
        app.browser_pointer_sequence_seen = 0
        window.__driftWithMeReadPointerSnapshot = lambda: host.pointer["snapshotJSON"]
        host.emit(h.operation("pointerdown", POINT))
        p = app.read_pointer_snapshot()
        assert p.pressed and abs(p.x - POINT[0]) < 1e-9
        host.emit(h.operation("pointermove", (450, 180)))
        p = app.read_pointer_snapshot()
        assert not p.pressed and p.down and abs(p.x - 450) < 1e-9
        host.emit(h.operation("pointerup", (450, 180)))
        p = app.read_pointer_snapshot()
        assert not p.down and not p.pressed
        assert app.pointer_input_status["released"]
    finally:
        host.close()


def test_screenshot_payload_excludes_bulk_histories_but_retains_evidence():
    from drift_with_me.ui_trace import ui_trace_publication

    frozen = {
        "reason": "calendar",
        "input": {"boundary": {"raw": "x" * 2048}},
        "taps": [{"boundary": {"raw": "x" * 2048}} for _ in range(3)],
        "events": [{"raw": "x" * 2048} for _ in range(32)],
        "host": {
            "events": [{"raw": "x" * 2048} for _ in range(32)],
            "attempts": [{"sequence": 26}],
            "geometry": {"canvas": [0, 0, 852, 329]},
        },
    }
    sent = ui_trace_publication(frozen)
    assert len(json.dumps(sent)) < 65536
    assert sent["input"] == frozen["input"] and sent["taps"] == frozen["taps"]
    assert sent["host"]["attempts"] == frozen["host"]["attempts"]
    assert len(frozen["events"]) == len(frozen["host"]["events"]) == 32


def test_invalid_input_trace_publishes_without_opening_calendar(monkeypatch):
    from drift_with_me.ui_trace import TraceMemory

    app, data, _ = subject(monkeypatch)
    published = []
    app.ui_trace = TraceMemory(
        SimpleNamespace(
            boot=lambda: 1, read=lambda: "{}", publish=lambda raw: published.append(json.loads(raw))
        )
    )
    data["press"]["x"] = 1000
    data["press"]["y"] = -1
    p = app.read_pointer_snapshot()
    assert not p.pressed
    assert published[0]["reason"] == "input:snapshot-bounds"
    assert published[0]["input"]["source"] == "Q"
    assert published[0]["input"]["boundary"]["converted"] == [1000.0, -1.0]
    assert published[0]["input"]["boundary"]["final"] is None
    app.read_pointer_snapshot()
    assert len(published) == 1  # repeated invalid held input cannot replace first evidence
    assert not getattr(app, "week_debug_menu_open", False)


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_evidence_is_valid_json_for_parent(monkeypatch, nonfinite):
    from drift_with_me.ui_trace import TraceMemory

    app, _, _ = subject(monkeypatch)
    monkeypatch.setitem(sys.modules, "js", None)
    app.pyxel.mouse_x = nonfinite
    posted = []
    app.ui_trace = TraceMemory(
        SimpleNamespace(boot=lambda: 1, read=lambda: "{}", publish=posted.append)
    )
    app.read_pointer_snapshot()

    def forbidden(value):
        raise AssertionError("Nonstandard JSON number: " + value)

    result = json.loads(posted[0], parse_constant=forbidden)
    assert result["reason"] == "input:native-number"
    assert result["input"]["native"][0] in ["NaN", "+Infinity", "-Infinity"]


def test_peek_first_failure_also_auto_displays_without_consuming(monkeypatch):
    from drift_with_me.ui_trace import TraceMemory

    app, data, _ = subject(monkeypatch)
    data["press"]["x"] = 1000
    posted = []
    app.ui_trace = TraceMemory(
        SimpleNamespace(boot=lambda: 1, read=lambda: "{}", publish=posted.append)
    )
    app.peek_pointer_snapshot()
    assert app.browser_pointer_sequence_seen == 25
    assert json.loads(posted[0])["reason"] == "input:snapshot-bounds"
    app.read_pointer_snapshot()
    assert len(posted) == 1
