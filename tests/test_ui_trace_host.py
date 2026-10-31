"""Opt-in host evidence must remain bounded, read-only and absent by default."""

import json
import shutil
import subprocess

import pytest
from scripts.build_web import HOST_JS

HARNESS = r"""
const vm=require('vm');
const source=require('fs').readFileSync(0,'utf8');
function run(mode, crossOrigin=false) {
 const handlers={}, vvHandlers={}, windowHandlers={}, names=[];
 let reads=0,captures=0,releases=0,prevented=0;
 let rect={left:0,top:0,width:1024,height:472};
 const canvas={width:1024,height:472,getBoundingClientRect(){reads++;return rect},
   setPointerCapture(){captures++},releasePointerCapture(){releases++}};
 const vv={width:1024,height:472,offsetLeft:4,offsetTop:5,scale:1,
   addEventListener(n,f){vvHandlers[n]=f}};
 const win={top:{},innerWidth:1024,innerHeight:472,visualViewport:vv,
   location:{search:mode==='on'?'?trace=ui':'?trace=no'},
   __driftWithMeLogicalSize:{width:512,height:236},
   performance:{now:()=>123},addEventListener(n,f){windowHandlers[n]=f}};
 if(mode!=='missing') win.URLSearchParams=URLSearchParams;
 if(crossOrigin) Object.defineProperty(win,'parent',{get(){throw Error('cross origin')}});
 else {win.parent={innerWidth:900,innerHeight:400,visualViewport:{width:900,height:400,
   offsetLeft:1,offsetTop:2,scale:0.8}};
 win.frameElement={getBoundingClientRect:()=>({left:0,top:0,width:900,height:400}),
   style:{transform:'scale(0.8)'}};}
 const doc={querySelector:()=>canvas,documentElement:{style:{setProperty(){}}},
 body:{classList:{toggle(){}}},addEventListener(n,f,o){handlers[n]=f;names.push([n,o])}};
 vm.runInNewContext(source,{window:win,document:doc,Date});
 const initialReads=reads;
 const ev=(type,id=1,x=160,y=120)=>({type,pointerId:id,pointerType:'touch',isTrusted:true,
 clientX:x,clientY:y,cancelable:true,preventDefault(){prevented++}});
 handlers.pointerdown(ev('pointerdown'));handlers.pointerdown(ev('pointerdown',2));
 handlers.pointerup(ev('pointerup'));
 handlers.pointerdown(ev('pointerdown'));handlers.pointercancel(ev('pointercancel'));
 handlers.pointerup(ev('pointerup',99));handlers.pointerdown(ev('pointerdown',1,-10));
 win.__driftWithMeLifecycle.active=false;handlers.pointerdown(ev('pointerdown'));
 win.__driftWithMeLifecycle.active=true;
 if(handlers.touchstart) handlers.touchstart({type:'touchstart',isTrusted:true,
   changedTouches:[{identifier:7,clientX:160,clientY:120}]});
 for(let i=0;i<4;i++){
  handlers.pointerdown(ev('pointerdown',1,200+i));handlers.pointerup(ev('pointerup'));
 }
 const api=win.__driftWithMeUiTrace;
 const before=api?JSON.parse(api.read()):null;
 // Three ignored downs retain their own reasons even though sequence does not change.
 handlers.pointerdown(ev('pointerdown'));handlers.pointerdown(ev('pointerdown',2));
 handlers.pointerdown(ev('pointerdown',3,-10));
 win.__driftWithMeLifecycle.active=false;handlers.pointerdown(ev('pointerdown',4));
 win.__driftWithMeLifecycle.active=true;handlers.pointerup(ev('pointerup'));
 const attemptsBeforeFlood=api?JSON.parse(api.read()).attempts:null;
 for(let i=0;i<40;i++) vvHandlers.scroll({type:'scroll',isTrusted:true});
 const after=api?JSON.parse(api.read()):null;
 let pure=true,boots=null;
 if(api) {const a=JSON.parse(api.read());a.events.length=0;a.taps[0].geometry.canvas.left=999;
 pure=JSON.parse(api.read()).events.length===32&&JSON.parse(api.read()).taps[0].geometry.canvas.left===0;
 boots=[api.boot(),api.boot(),JSON.parse(api.read()).boot];}
 return {initialReads,reads,captures,releases,prevented,names,pointer:win.__driftWithMePointer,
 epoch:win.__driftWithMeLifecycle.inputEpoch,before,after,attemptsBeforeFlood,
 pure,boots,enabled:api?.enabled??false};
}
console.log(JSON.stringify({on:run('on'),off:run('off'),missing:run('missing'),cross:run('on',true)}));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required for actual host execution")
def test_ui_trace_host_is_opt_in_bounded_pure_and_does_not_change_pointer_behavior():
    result = subprocess.run(
        ["node", "-e", HARNESS], input=HOST_JS, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    on, off, missing, cross = (data[k] for k in ("on", "off", "missing", "cross"))
    assert on["enabled"] and not off["enabled"] and not missing["enabled"]
    assert off["initialReads"] == missing["initialReads"] == 0
    assert off["reads"] == missing["reads"] == 18  # Existing mapping reads only.
    for entry in (off, missing):
        assert not any(n in {"mousedown", "touchstart", "touchend"} for n, _ in entry["names"])
    for key in ("pointer", "epoch", "captures", "releases", "prevented"):
        assert on[key] == off[key] == missing[key] == cross[key]
    assert on["pure"] and on["boots"] == [1, 2, 2]
    assert len(on["after"]["events"]) == 32
    assert len(on["after"]["taps"]) == 3
    assert all(t["kind"] == "pd" and t["reason"] == "accepted" for t in on["after"]["taps"])
    assert all(t["seq"] == t["sequence"] for t in on["after"]["taps"])
    assert on["after"]["attempts"] == on["attemptsBeforeFlood"]
    assert len(on["after"]["attempts"]) == 3
    assert [t["reason"] for t in on["after"]["attempts"]] == [
        "active-pointer",
        "outside",
        "inactive",
    ]
    assert len({t["seq"] for t in on["after"]["attempts"]}) == 1
    assert all("geometry" in t for t in on["after"]["attempts"])
    assert on["after"]["events"][-1]["epoch"] == 40
    assert on["before"]["geometry"]["parentViewport"]["offsetLeft"] == 1
    assert on["before"]["geometry"]["iframeTransform"] == "scale(0.8)"
    assert cross["before"]["geometry"]["parentViewport"] is None
    reasons = {(e["kind"], e["reason"]) for e in on["before"]["events"]}
    assert {
        ("pd", "active-pointer"),
        ("pd", "inactive"),
        ("pd", "outside"),
        ("cancel", "accepted"),
        ("pu", "inactive-pointer"),
    } <= reasons
