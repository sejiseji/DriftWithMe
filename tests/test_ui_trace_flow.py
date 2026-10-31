"""Actual host event code -> lifecycle -> root UI + native draw; synthetic DOM only."""

import json
import subprocess
import sys
from pathlib import Path


def run_flow(enabled, screenshot=None):
    from types import SimpleNamespace

    import pyxel

    import test_screen_flow_mina_bridge as h
    from drift_with_me.app import DriftWithMeApp as App
    from drift_with_me.save_state import snapshot

    pyxel.run = lambda *_: None
    pyxel.btn = lambda *_: False
    pyxel.btnp = lambda *_: False
    source = h.HOST_EVENT_SERVER
    source = source.replace(
        "const events = {}, windows = {};", "const events = {}, windows = {}, viewportEvents = {};"
    )
    source = source.replace(
        "vm.runInNewContext(config.source, {window: win, document: doc});",
        "win.URLSearchParams=URLSearchParams;win.location={search:"
        + repr("?trace=ui" if enabled else "")
        + (
            "};win.visualViewport={width,height,addEventListener:(n,f)=>viewpo"
            "rtEvents[n]=f};\nvm.runInNewContext(config.source, {window: win, d"
            "ocument: doc});"
        ),
    )
    source = source.replace(
        "for (const operation of operations) events[operation.kind](toEvent(operation));",
        (
            "for(const operation of operations) { if(operation.kind==='boot')w"
            "in.__driftWithMeUiTrace.boot();else if(operation.kind.startsWith("
            "'viewport:'))viewportEvents[operation.kind.slice(9)]({});else eve"
            "nts[operation.kind](toEvent(operation)); }"
        ),
    )
    source = source.replace(
        "return {...win.__driftWithMePointer};",
        (
            "return {...win.__driftWithMePointer, lifeActive:win.__driftWithMe"
            "Lifecycle.active,lifeGeneration:win.__driftWithMeLifecycle.genera"
            "tion,lifeEpoch:win.__driftWithMeLifecycle.inputEpoch,traceJSON:wi"
            "n.__driftWithMeUiTrace?.read()||'{}'};"
        ),
    )
    h.HOST_EVENT_SERVER = source
    host = h.HostEvents((1280, 720, 0, 0, 844, 390))
    pointer = SimpleNamespace(**host.pointer)
    life = SimpleNamespace(active=True, generation=0, inputEpoch=0, acknowledge=lambda *_: None)

    def boot():
        host.emit({"kind": "boot"})
        return json.loads(host.pointer["traceJSON"])["boot"]

    trace = SimpleNamespace(enabled=True, boot=boot, read=lambda: host.pointer["traceJSON"])
    window = SimpleNamespace(__driftWithMePointer=pointer, __driftWithMeLifecycle=life)
    if enabled:
        window.__driftWithMeUiTrace = trace
    sys.modules["js"] = SimpleNamespace(window=window)
    app = App(headless=True, week_debug=False)
    app.consume_elapsed = lambda: 1 / 60
    assert not app.normal_progress_store.enabled
    assert (app.ui_trace is not None) == enabled
    app._lifecycle_bridge = life
    frames = 0

    def tick():
        nonlocal frames
        pointer.__dict__.update(host.pointer)
        life.active = host.pointer["lifeActive"]
        life.generation = host.pointer["lifeGeneration"]
        life.inputEpoch = host.pointer["lifeEpoch"]
        app.update()
        app.draw()
        frames += 1

    def idle():
        host.emit()
        tick()

    def tap(rect, hold=0):
        p = h.center(rect)
        host.emit(h.operation("pointerdown", p))
        for _ in range(hold):
            tick()
        host.emit(h.operation("pointerup", p))
        tick()
        shown = app.office_dialogue_playback.revealed_chars
        idle()
        return shown

    try:
        tap(app.new_game_button_rect())
        assert app.office_dialogue_requires_advance()
        host.emit({"kind": "viewport:scroll"})
        tick()
        before = app.office_dialogue_playback.revealed_chars
        shown = tap(app.office_dialog_rect())
        assert shown == before  # release gate swallowed fresh tap
        if enabled:
            assert app.ui_trace.taps[-1]["owner"] == "LIFECYCLE"
        for _ in range(160):
            if not app.office_dialogue_requires_advance():
                break
            tap(app.office_dialog_rect())
        case = app.office.current_case
        index = next(i for i, q in enumerate(case.questions) if q.question_id == "identity")
        tap(app.office_question_rect(index, len(case.questions)))
        assert app.office.current_session.pending_question_id == "identity"
        tap(app.office_dialog_rect(), hold=10)
        for _ in range(160):
            if "identity" in app.office.current_session.asked_question_ids:
                break
            tap(app.office_dialog_rect())
        assert "identity" in app.office.current_session.asked_question_ids
        payload = snapshot(app)
        tap(app.office_calendar_rect())
        assert app.week_debug_menu_open
        assert snapshot(app) == payload
        if enabled:
            from copy import deepcopy

            frozen = deepcopy(app.ui_trace.frozen)
            assert frozen["reason"] == "calendar"
            assert frozen["state"]["menu"] is False
            assert frozen["last_draw"]["screen"] == "OFFICE"
            assert len(frozen["host"]["taps"]) == 3
            assert frozen["input"]["source"] == "H"
            tap(app.ui_trace_button_rect(), hold=4)
            assert app.ui_trace.sheet
            assert app.ui_trace.frozen == frozen
            if screenshot:
                pyxel.screenshot(str(screenshot), scale=3)
            lines = app.ui_trace_lines()
            assert len(lines) == 17
            tap(app.ui_trace_back_rect(), hold=3)
            assert not app.ui_trace.sheet and app.week_debug_menu_open
            assert app.ui_trace.frozen == frozen
            assert len(app.ui_trace.events) <= 32
            assert snapshot(app) == payload
        else:
            lines = []
        assert not app.normal_progress_store.enabled
        return {"enabled": enabled, "frames": frames, "payload": payload, "lines": lines}
    finally:
        host.close()


def test_trace_on_off_same_story_and_save_payload():
    results = []
    root = Path(__file__).parents[1]
    for enabled in (False, True):
        code = (
            "import sys,json;sys.path[:0]="
            + repr([str(root / "tests"), str(root / "src"), str(root)])
            + ";from test_ui_trace_flow import run_flow;print(json.dumps(run_flow("
            + repr(enabled)
            + ")))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=45
        )
        assert result.returncode == 0, result.stdout + result.stderr
        results.append(json.loads(result.stdout.splitlines()[-1]))
    assert results[0]["payload"] == results[1]["payload"]
    assert results[1]["lines"]
