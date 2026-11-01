"""Actual HOST + lifecycle producer, Python guard and office hit-test consumers."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts.build_web import HOST_JS

from drift_with_me.office import OfficePrototype
from drift_with_me.week_cycle import WorkWeek
from pointer_json_fixture import pointer_window
from test_office_supervisor import app_for, finish


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required")
@pytest.mark.parametrize("action", ["notice", "consult", "calendar", "dialogue"])
@pytest.mark.parametrize("mode", ["tap", "hold", "drift", "cancel", "resize"])
def test_header_real_host_lifecycle_ownership(monkeypatch, action, mode):
    office = OfficePrototype.load()
    finish(office)
    app = app_for(office)
    app.work_week = WorkWeek()
    app.week_debug_active = app.week_debug_menu_open = False
    app.clear_world_input_latches = Mock()
    app.model = SimpleNamespace(cancel_auto_move=Mock())
    app.audio = SimpleNamespace(suspend_for_lifecycle=Mock(), resume_from_lifecycle=Mock())
    app.pyxel = SimpleNamespace(MOUSE_BUTTON_LEFT=1, btn=lambda _: False, btnp=lambda _: False)
    app.key_pressed = lambda *args: False
    app.browser_pointer_sequence_seen = 0
    app.ui_trace = None
    targets = {
        "notice": (150, 13),
        "consult": (450, 13),
        "calendar": (494, 13),
        "dialogue": (363, 120),
    }
    x, y = targets[action]
    source = (Path(__file__).parent / "fixtures/web_lifecycle_harness.cjs").read_text()
    harness = (
        source.split("const life=win.__driftWithMeLifecycle;")[0]
        + r"""
const [x,y,mode]=JSON.parse(process.argv[1]);
const event=(type,a=x,b=y)=>({type,pointerId:1,clientX:a,clientY:b,
 cancelable:true,preventDefault(){}});
fire('document','pointerdown',event('pointerdown'));
if(mode==='drift')fire('document','pointermove',event('pointermove',494,13));
if(mode==='cancel')fire('document','pointercancel',event('pointercancel'));
if(mode==='tap'||mode==='drift')fire('document','pointerup',event('pointerup'));
if(mode==='resize')fire('window','resize');
const l=win.__driftWithMeLifecycle;
console.log(JSON.stringify({pointer:win.__driftWithMePointer,
 snapshot:win.__driftWithMeReadPointerSnapshot(),
 life:{active:l.active,generation:l.generation,inputEpoch:l.inputEpoch}}));
"""
    )
    run = subprocess.run(
        ["node", "-e", harness, json.dumps([x, y, mode])],
        input=HOST_JS,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(run.stdout)
    bridge = SimpleNamespace(**result["pointer"], snapshotJSON=result["snapshot"])
    window = pointer_window(bridge)
    window.__driftWithMeLifecycle = SimpleNamespace(**result["life"], acknowledge=Mock())
    monkeypatch.setitem(sys.modules, "js", SimpleNamespace(window=window))
    app.pointer_snapshot = app.read_pointer_snapshot()
    blocked = app.lifecycle_update_blocked()
    if mode == "resize":
        assert blocked
        assert not app.pointer_snapshot.pressed
        return
    assert not blocked
    opened = app.update_week_debug()
    if action == "calendar" and mode != "cancel":
        assert opened and app.week_debug_menu_open
        return
    assert not opened and not app.week_debug_menu_open
    app.begin_office_consultation = Mock(return_value=True)
    handled = app.update_office_shared_controls(1 / 60)
    assert handled == (action == "consult" and mode != "cancel")
    assert app.begin_office_consultation.call_count == int(handled)
    if action == "notice":
        assert not app.mouse_pressed_in(app.office_dialog_rect())
    app.pointer_snapshot = app.read_pointer_snapshot()
    assert not app.pointer_snapshot.pressed  # no replay into another UI next frame


@pytest.mark.parametrize(
    "block", ["typing", "report", "transition", "release", "modal", "complete"]
)
def test_unavailable_consultation_cannot_open_or_change_story(block):
    office = OfficePrototype.load()
    finish(office)
    app = app_for(office)
    app.work_week = WorkWeek()
    app.week_debug_active = app.week_debug_menu_open = False
    app.key_pressed = lambda *args: False
    app.mouse_pressed_in = lambda rect: rect == app.office_consultation_button_rect()
    app.clear_world_input_latches = Mock()
    app.begin_office_consultation = Mock()
    if block == "typing":
        app.office_dialogue_requires_advance = lambda: True
    elif block == "report":
        app.office_story_report_active = lambda: True
    elif block == "transition":
        app.week_transition = object()
    elif block == "release":
        app.week_input_wait_for_release = True
    elif block == "modal":
        app.week_debug_menu_open = True
    else:
        office.current_index = len(office.cases)
    assert not app.update_office_shared_controls(1 / 60)
    app.begin_office_consultation.assert_not_called()
