"""Actual HOST JSON API: no Python property proxies or diagnostic opt-in required."""

import json
import shutil
import subprocess

import pytest
from scripts.build_web import HOST_JS

HARNESS = r"""
const vm=require('vm'),source=require('fs').readFileSync(0,'utf8');
const events={},windows={},vv={},width=852,height=329;
let rectReads=0;
const canvas={width,height,getBoundingClientRect(){rectReads++;return {left:0,top:0,width,height}},
 setPointerCapture(){},releasePointerCapture(){}};
const win={top:{},innerWidth:width,innerHeight:height,URLSearchParams,
 location:{search:''},__driftWithMeLogicalSize:{width:512,height:236},
 visualViewport:{width,height,addEventListener:(n,f)=>vv[n]=f},
 addEventListener:(n,f)=>windows[n]=f};
const doc={querySelector:()=>canvas,documentElement:{style:{setProperty(){}}},
 body:{classList:{toggle(){}}},addEventListener:(n,f)=>events[n]=f};
vm.runInNewContext(source,{window:win,document:doc});
const read=()=>JSON.parse(win.__driftWithMeReadPointerSnapshot());
const event=(type,x=564.6666870117188,y=156.3333282470703)=>
 ({type,pointerId:9,clientX:x,clientY:y,cancelable:true,preventDefault(){}});
const neutral=read();
events.pointerdown(event('pointerdown'));
const readsBefore=rectReads,serialized=win.__driftWithMeReadPointerSnapshot();
const down=JSON.parse(serialized);
const pureReads=rectReads===readsBefore;
events.pointermove(event('pointermove',700,200));
const moved=read();
events.pointerup(event('pointerup',700,200));
const quick=read(),old=JSON.parse(serialized);
events.pointerdown(event('pointerdown'));
const second=read();events.pointercancel(event('pointercancel'));
const cancel=read();
events.pointerdown(event('pointerdown'));vv.scroll({});
const invalidated=read();
console.log(JSON.stringify({neutral,down,moved,quick,old,second,cancel,invalidated,pureReads,
 traceAbsent:!win.__driftWithMeUiTrace}));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required")
def test_host_json_snapshot_preserves_recorded_point_and_atomic_latched_press():
    result = subprocess.run(
        ["node", "-e", HARNESS], input=HOST_JS, text=True, capture_output=True, check=True
    )
    s = json.loads(result.stdout)
    assert s["traceAbsent"] and s["pureReads"]
    assert s["neutral"]["schema"] == 1 and s["neutral"]["sequence"] == 0
    down = s["down"]
    assert down["current"] == pytest.approx({"x": 355.46911287162806, "y": 112.14184032312642})
    assert down["press"]["x"] == down["current"]["x"]
    assert down["press"]["y"] == down["current"]["y"]
    assert down["press"]["sequence"] == down["sequence"] == 1
    assert down["press"]["epoch"] == down["epoch"] == 0
    assert down["logical"] == {"width": 512, "height": 236}
    assert down["down"] and down["pressed"] and not down["released"]
    assert s["old"] == down  # A serialized sample cannot track later pointer mutations.
    assert s["moved"]["current"] != down["current"]
    assert s["moved"]["press"] == down["press"]
    assert not s["quick"]["down"] and s["quick"]["pressed"] and s["quick"]["released"]
    assert s["second"]["press"]["sequence"] == s["second"]["sequence"] == 2
    assert s["cancel"]["cancelled"] and not s["cancel"]["pressed"]
    assert s["invalidated"]["cancelled"] and not s["invalidated"]["pressed"]
    assert s["invalidated"]["epoch"] == 1
    assert s["invalidated"]["press"]["epoch"] == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required")
def test_parent_displays_boundary_stages_without_mutating_raw_record():
    from test_ui_trace_dom import HARNESS as PARENT_HARNESS

    boundary = {
        "received": {
            "sequence": 26,
            "epoch": 8,
            "current": [355.46911287162806, 112.14184032312642],
            "press": [355.46911287162806, 112.14184032312642],
        },
        "types": {
            "current": ["float", "float"],
            "press": ["float", "float"],
            "sequence": "int",
            "flags": ["bool", "bool", "bool"],
        },
        "converted": [355.46911287162806, 112.14184032312642],
        "final": [355.46911287162806, 112.14184032312642],
        "decision": "accepted",
    }
    harness = PARENT_HARNESS.replace(
        "input:{source:", "input:{boundary:" + json.dumps(boundary) + ",source:"
    )
    result = subprocess.run(
        ["node", "-e", harness], input=HOST_JS, text=True, capture_output=True, check=True
    )
    text = json.loads(result.stdout)["on"]["frozen"]
    assert "RAW seq/epoch [26,8] C[355.47,112.14] P[355.47,112.14]" in text
    assert 'TYPES C/P/seq/flags [["float","float"],["float","float"],"int"' in text
    assert "PY converted [355.47,112.14] FINAL [355.47,112.14] accepted" in text
    assert boundary["converted"][0] == 355.46911287162806
