import json
import sys
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from drift_with_me.app import AppScreen, PointerSnapshot
from drift_with_me.app import DriftWithMeApp as App
from drift_with_me.config import load_runtime_config
from drift_with_me.pixel_font import pixel_text_size


def subject(monkeypatch, enabled=True, host=None):
    bridge = SimpleNamespace(enabled=True, boot=lambda: 2, read=lambda: json.dumps(host or {}))
    monkeypatch.setitem(
        sys.modules, "js", SimpleNamespace(window=SimpleNamespace(__driftWithMeUiTrace=bridge))
    )
    app = App.__new__(App)
    app.runtime = load_runtime_config()
    app.frame = 5
    app.screen = AppScreen.OFFICE
    app.work_week = SimpleNamespace(month=6, number=1)
    app.office = SimpleNamespace(
        current_case=SimpleNamespace(case_id="OFF-PROT-001"),
        current_session=SimpleNamespace(pending_question_id="identity", pending_dialogue_steps=[1]),
    )
    app.office_dialogue_playback = SimpleNamespace(
        pages=((SimpleNamespace(text="SECRET DIALOGUE"),),), page_index=0, revealed_chars=2
    )
    app.week_debug_menu_open = False
    app.week_debug_active = False
    app.pointer_snapshot = PointerSnapshot(False, True, 363, 120)
    app.browser_pointer_sequence_seen = 0
    app.pyxel = SimpleNamespace(mouse_x=494, mouse_y=13, btn=lambda _: False, btnp=lambda _: True)
    app.initialize_ui_trace(enabled)
    return app, bridge


def test_off_never_records_or_reads_host(monkeypatch):
    app, bridge = subject(monkeypatch, False)
    bridge.read = Mock(side_effect=AssertionError("off reader"))
    app.ui_trace_begin_frame()
    app.ui_trace_note("x")
    app.ui_trace_pointer("H", "ok", 1, 0, app.pointer_snapshot)
    app.ui_trace_menu_open("calendar")
    app.ui_trace_end_frame()
    app.ui_trace_did_draw()
    assert app.ui_trace is None
    assert not app.update_ui_trace_menu()
    bridge.read.assert_not_called()


def test_memory_bounded_and_freeze_copies_every_nested_value(monkeypatch):
    host = {
        "events": [{"epoch": 4}],
        "taps": [{"sequence": 50, "client": [5, 6], "down": [363, 120]}],
        "geometry": {"canvas": {"left": 0}},
    }
    app, _ = subject(monkeypatch, host=host)
    for n in range(50):
        app.ui_trace_begin_frame()
        app.ui_trace_pointer("H", "ok", n + 1, n, app.pointer_snapshot)
        app.ui_trace_note("reveal", chars=n)
        app.frame += 1
        app.ui_trace_end_frame()
    assert len(app.ui_trace.events) == 32
    assert len(app.ui_trace.taps) == 3
    app.ui_trace_did_draw()
    app.ui_trace_menu_open("calendar")
    frozen = deepcopy(app.ui_trace.frozen)
    app.ui_trace_note("diagnostic tap")
    app.ui_trace.taps[-1]["point"][0] = 0
    app.ui_trace_did_draw()
    assert app.ui_trace.frozen == frozen
    assert "SECRET DIALOGUE" not in json.dumps(frozen)
    assert frozen["last_draw"]["chars"] == 2
    assert frozen["input"]["point"] == [363, 120]
    assert frozen["taps"][-1]["owner"] == "OPEN"


@pytest.mark.parametrize("failure", ["missing", "fields", "current-nan", "down-nan"])
def test_failed_js_and_native_source_are_distinguishable(monkeypatch, failure):
    app, _ = subject(monkeypatch)
    b = SimpleNamespace(down=False, pressed=True, sequence=1, x=10, y=10, pressedX=10, pressedY=10)
    if failure == "missing":
        b = None
    elif failure == "fields":
        del b.sequence
    elif failure == "current-nan":
        b.x = float("nan")
    else:
        b.pressedX = float("nan")
    sys.modules["js"].window.__driftWithMePointer = b
    p = app.read_pointer_snapshot()
    assert p.pressed and (p.x, p.y) == (494, 13)
    assert app.ui_trace.input["source"] == "N"
    assert app.ui_trace.input["reason"] == failure


def test_valid_consumed_host_does_not_fall_back(monkeypatch):
    app, _ = subject(monkeypatch)
    sys.modules["js"].window.__driftWithMePointer = SimpleNamespace(
        down=False, pressed=True, sequence=1, x=494, y=13, pressedX=363, pressedY=120
    )
    first = app.read_pointer_snapshot()
    second = app.read_pointer_snapshot()
    assert first.pressed and (first.x, first.y) == (363, 120)
    assert not second.pressed
    assert app.ui_trace.input["source"] == "H"
    assert app.ui_trace.input["reason"] == "ok"


def test_diag_open_close_and_holds_never_mutate_cause(monkeypatch):
    app, _ = subject(monkeypatch)
    app.ui_trace_menu_open("calendar")
    app.week_debug_menu_open = True
    frozen = deepcopy(app.ui_trace.frozen)

    def point(rect, down=True, pressed=True):
        app.pointer_snapshot = PointerSnapshot(
            down, pressed, rect.x + rect.width / 2, rect.y + rect.height / 2
        )

    point(app.ui_trace_button_rect())
    assert app.update_ui_trace_menu() and app.ui_trace.sheet
    for _ in range(3):
        assert app.update_ui_trace_menu()
    point(app.ui_trace_back_rect(), False, False)
    assert app.update_ui_trace_menu()  # release gate consumes only diagnostic control
    app.key_pressed = lambda *_: False
    point(app.ui_trace_back_rect())
    assert app.update_ui_trace_menu() and not app.ui_trace.sheet
    assert app.week_debug_menu_open
    assert app.ui_trace.frozen == frozen


def test_sheet_rows_fit_one_phone_landscape_screen(monkeypatch):
    app, _ = subject(
        monkeypatch,
        host={"geometry": {"canvas": None, "childViewport": None, "parentViewport": None}},
    )
    app.ui_trace_menu_open("park-escape")
    lines = app.ui_trace_lines()
    assert len(lines) == 17
    assert all(pixel_text_size(line, 2)[0] <= 504 for line in lines)
    assert app.runtime.screen_height >= 27 + 16 * 12 + 10


def test_trace_reader_does_not_acknowledge_pointer(monkeypatch):
    app, _ = subject(monkeypatch)
    app.read_pointer_snapshot = Mock(side_effect=AssertionError("observer consumed input"))
    app.read_browser_pointer_snapshot = Mock(
        side_effect=AssertionError("observer consumed sequence")
    )
    app.ui_trace_menu_open("launch")
    assert app.browser_pointer_sequence_seen == 0
    assert app.ui_trace.frozen["reason"] == "launch"
