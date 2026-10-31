"""Actual HOST parent/child bridge without a game tap or draw prerequisite."""

import json
import shutil
import subprocess

import pytest
from scripts.build_web import HOST_JS

HARNESS = r"""
const vm=require('vm'),source=require('fs').readFileSync(0,'utf8');
function run(enabled) {
 const handlers={},created=[],appended=[],child={};
 const frame={style:{},contentWindow:child};
 const win={location:{href:'https://example.test/?trace=ui',origin:'https://example.test',
 search:enabled?'?trace=ui':''},__driftWithMeLogicalSize:{width:512,height:236},
 innerWidth:844,innerHeight:390,URLSearchParams,addEventListener:(n,f)=>handlers[n]=f};
 win.top=win;
 const doc={body:{appendChild(n){appended.push(n)}},createElement(tag){created.push(tag);
 return tag==='iframe'?frame:{style:{},setAttribute(){},textContent:''}}};
 vm.runInNewContext(source,{window:win,document:doc});
 const send=(data,origin=win.location.origin,source=child)=>
 handlers.message?.({data,origin,source});
 const f={reason:'calendar',build:'LOCAL',boot:1,
 state:{screen:'OFFICE',week:[6,1],case:'OFF-PROT-001',
 question:'identity',page:0,pages:2,chars:4,total:29,gates:{draw:false,release:true},
 native_buttons:{held:true,pressed:false}},input:{source:'H',reason:'ok',sequence:4,seen_before:3,
 down:false,pressed:true,released:true,point:[494,13],native:[252,79]},host:{attempts:[{reason:'accepted',
 sequence:4,client:[811,22],down:[494,13],held:false,epoch:1}],geometry:{canvas:{left:0,top:0,width:844,height:390}}}};
 const msg={channel:'drift-ui-trace-v2',kind:'freeze',payload:JSON.stringify(f)};
 send(msg,'https://evil.test');send(msg,win.location.origin,{});
 send({...msg,payload:'x'.repeat(65537)});send({...msg,payload:'{broken'});
 const before=appended.length;send(msg);
 const panel=appended.find(n=>n.id==='drift-ui-diagnostic'),frozen=panel?.textContent;
 send({channel:'drift-ui-trace-v2',kind:'live',payload:JSON.stringify({kind:'up',down:false})});
 const live=panel?.textContent;
 send({...msg,payload:JSON.stringify({...f,reason:"second-open"})});
 send({...msg,payload:'null'});send({...msg,payload:'[]'});
 return {created,before,appended:appended.length,frozen,live,final:panel?.textContent,
 style:panel?.style.cssText,listeners:Object.keys(handlers)};
}
console.log(JSON.stringify({on:run(true),off:run(false)}));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required")
def test_parent_diagnostic_auto_displays_with_safe_origin_and_bounded_payload():
    result = subprocess.run(["node", "-e", HARNESS], input=HOST_JS, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    on, off = (json.loads(result.stdout)[k] for k in ("on", "off"))
    assert on["before"] == 1  # Spoofed, oversized, malformed messages create no panel.
    assert on["appended"] == 2 and on["created"] == ["iframe", "pre"]
    assert "WHY calendar" in on["frozen"]
    assert "SOURCE H ERR ok SEQ 4/3" in on["frozen"]
    assert "NATIVE held/press" in on["frozen"]
    assert "identity" in on["frozen"] and "TEXT 4/29" in on["frozen"]
    assert "T1 accepted S4 C[811,22] L[494,13]" in on["frozen"]
    assert on["live"].split("\nLIVE JS ")[0] == on["frozen"].split("\nLIVE JS ")[0]
    assert '"kind":"up"' in on["live"] and on["final"] == on["live"]
    assert "pointer-events:auto" in on["style"]
    assert "message" in on["listeners"] and "pointerdown" not in on["listeners"]
    assert off["created"] == ["iframe"] and off["appended"] == 1
    assert "message" not in off["listeners"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required")
def test_child_publishes_existing_frozen_snapshot_without_reading_pointer():
    from test_ui_trace_host import HARNESS as CHILD_HARNESS

    harness = (
        CHILD_HARNESS.replace(
            "const handlers={}, vvHandlers={}, windowHandlers={}, names=[];",
            "const handlers={}, vvHandlers={}, windowHandlers={}, names=[], posted=[];",
        )
        .replace(
            "offsetLeft:1,offsetTop:2,scale:0.8}};",
            "offsetLeft:1,offsetTop:2,scale:0.8},postMessage:(m,o)=>posted.push([m,o])};",
        )
        .replace(
            "location:{search:mode==='on'?'?trace=ui':'?trace=no'},",
            "location:{origin:'https://example.test',search:mode==='on'?'?trace=ui':'?trace=no'},",
        )
        .replace(
            "const before=api?JSON.parse(api.read()):null;",
            "const before=api?JSON.parse(api.read()):null;"
            "if(api){api.publish(JSON.stringify({reason:'calendar',state:{chars:3}}));"
            "api.publish('x'.repeat(65537));}",
        )
        .replace(
            "epoch:win.__driftWithMeLifecycle.inputEpoch,before,after,attemptsBeforeFlood,",
            "epoch:win.__driftWithMeLifecycle.inputEpoch,before,after,attemptsBeforeFlood,posted,",
        )
    )
    result = subprocess.run(["node", "-e", harness], input=HOST_JS, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    messages = data["on"]["posted"]
    freezes = [(m, origin) for m, origin in messages if m["kind"] == "freeze"]
    assert len(freezes) == 1
    assert freezes[0][1] == "https://example.test"
    assert json.loads(freezes[0][0]["payload"])["state"]["chars"] == 3
    assert any(m["kind"] == "live" for m, _ in messages)
    assert not data["off"]["posted"]
