import json
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from scripts.build_web import HOST_JS

from drift_with_me.app import AppScreen
from drift_with_me.app import DriftWithMeApp as App
from drift_with_me.config import load_runtime_config

HOST_HARNESS = r"""
const vm=require('vm'),fs=require('fs');
const g=JSON.parse(process.argv[1]),mode=process.argv[2],events={},windows={};
const [bw,bh,left,top,width,height]=g;
const canvas={width:bw,height:bh,getBoundingClientRect:()=>({left,top,width,height}),
setPointerCapture(){},releasePointerCapture(){}};
const win={top:{},innerWidth:width,innerHeight:height,
__driftWithMeLogicalSize:{width:512,height:236},addEventListener:(n,f)=>windows[n]=f};
const doc={querySelector:()=>canvas,documentElement:{style:{setProperty(){}}},
body:{classList:{toggle(){}}},addEventListener:(n,f)=>events[n]=f};
vm.runInNewContext(fs.readFileSync(0,'utf8'),{window:win,document:doc});
function e(x,y,type='pointerdown'){
 const k=Math.min(bw/512,bh/236);
 return {type,pointerId:1,cancelable:true,preventDefault(){},
 clientX:left+((bw-512*k)/2+x*k)*width/bw,
 clientY:top+((bh-236*k)/2+y*k)*height/bh};
}
const target=JSON.parse(process.argv[3]||'[363,120]');
events.pointerdown(e(...target));
if(mode==='drift')events.pointermove(e(494,13,'pointermove'));
if(mode==='quick_up')events.pointerup(e(494,13,'pointerup'));
if(mode==='cancel')events.pointercancel(e(494,13,'pointercancel'));
console.log(JSON.stringify(win.__driftWithMePointer));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required")
@pytest.mark.parametrize(
    "geometry",
    [
        (1024, 472, 0, 0, 1024, 472),
        (1600, 600, 13, 9, 800, 300),
        (800, 1000, 7, 12, 400, 500),
        (2048, 1200, 0, 0, 1024, 600),
        (512, 236, 0, 0, 390, 179.765625),
        (1365, 768, 20, 47, 844, 475),
    ],
)
@pytest.mark.parametrize("mode", ["stable", "drift", "quick_up", "cancel"])
def test_host_to_python_office_arrow_never_becomes_calendar(monkeypatch, geometry, mode):
    # Run the actual generated host JS, then the actual Python snapshot and UI dispatch.
    harness = HOST_HARNESS
    result = subprocess.run(
        ["node", "-e", harness, json.dumps(geometry), mode],
        input=HOST_JS,
        text=True,
        capture_output=True,
        check=True,
    )
    bridge = SimpleNamespace(**json.loads(result.stdout))
    monkeypatch.setitem(
        sys.modules, "js", SimpleNamespace(window=SimpleNamespace(__driftWithMePointer=bridge))
    )
    app = App.__new__(App)
    app.screen = AppScreen.OFFICE
    app.runtime = load_runtime_config()
    app.browser_pointer_sequence_seen = 0
    app.presentation_time = 0
    app.week_debug_active = False
    app.week_debug_menu_open = False
    app.office_calendar_visible = lambda: True
    app.pointer_snapshot = app.read_browser_pointer_snapshot()
    assert not app.update_week_debug()
    assert not app.week_debug_menu_open
    app.week2_active = lambda: False
    app.clear_world_input_latches = lambda: None
    app.office_consultation = object()
    app.key_pressed = lambda *args: False
    app.update_office_dialogue_playback = lambda elapsed: None
    app.advance_office_dialogue_page = Mock()
    app.update_office_screen(1 / 60)
    assert app.advance_office_dialogue_page.call_count == (0 if mode == "cancel" else 1)
    # A latched press is consumed once by sequence, not re-fired on the next frame.
    app.pointer_snapshot = app.read_browser_pointer_snapshot()
    app.update_office_screen(1 / 60)
    assert app.advance_office_dialogue_page.call_count == (0 if mode == "cancel" else 1)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required")
@pytest.mark.parametrize(
    "action", ["month6", "month7", "month8", "week1", "week2", "week3", "week4", "start", "cancel"]
)
@pytest.mark.parametrize("mode", ["drift", "quick_up"])
@pytest.mark.parametrize(
    "geometry",
    [(1024, 472, 0, 0, 1024, 472), (800, 1000, 7, 12, 400, 500), (2048, 1200, 0, 0, 1024, 600)],
)
def test_host_to_python_week_modal_buttons_consume_press_position(
    monkeypatch, action, mode, geometry
):
    from drift_with_me.week_cycle import WorkWeek

    app = App.__new__(App)
    app.screen = AppScreen.OFFICE
    app.runtime = load_runtime_config()
    app.browser_pointer_sequence_seen = 0
    app.presentation_time = 0
    app.week_debug_active = True
    app.week_debug_compact = True
    app.week_debug_menu_open = True
    app.week_debug_wait_release = False
    app.week_debug_month = 6
    app.week_debug_selection = 1
    app.session_started = True
    app.jump_to_debug_week = Mock(return_value=True)
    rect = app.week_debug_rects()[action]
    target = [rect.x + rect.width / 2, rect.y + rect.height / 2]
    result = subprocess.run(
        ["node", "-e", HOST_HARNESS, json.dumps(geometry), mode, json.dumps(target)],
        input=HOST_JS,
        text=True,
        capture_output=True,
        check=True,
    )
    bridge = SimpleNamespace(**json.loads(result.stdout))
    monkeypatch.setitem(
        sys.modules, "js", SimpleNamespace(window=SimpleNamespace(__driftWithMePointer=bridge))
    )
    app.pointer_snapshot = app.read_browser_pointer_snapshot()
    assert app.update_week_debug()
    if action.startswith("month"):
        assert app.week_debug_month == int(action[-1])
    elif action.startswith("week"):
        assert app.week_debug_selection == int(action[-1])
    elif action == "start":
        app.jump_to_debug_week.assert_called_once_with(WorkWeek(6, 1))
    else:
        assert not app.week_debug_menu_open
    assert app.week_debug_wait_release
