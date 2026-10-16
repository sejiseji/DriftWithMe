"""Execute the actual browser host source against CSS/backing-buffer viewport cases."""

import shutil
import subprocess

import pytest
from scripts.build_web import HOST_JS


@pytest.mark.skipif(
    shutil.which("node") is None, reason="Node is needed to execute host JavaScript"
)
def test_actual_host_pointer_bridge_excludes_letterbox_and_tracks_resize():
    harness = r"""
const assert=require('assert'),vm=require('vm'),fs=require('fs');
const code=fs.readFileSync(0,'utf8'),events={},windowEvents={};
let rect={left:0,top:0,width:1024,height:600};
const canvas={width:1024,height:600,getBoundingClientRect:()=>rect,
  setPointerCapture(){},releasePointerCapture(){}};
const win={top:{},innerWidth:1024,innerHeight:600,
  __driftWithMeLogicalSize:{width:512,height:236},
  addEventListener:(name,fn)=>{windowEvents[name]=fn}};
const doc={querySelector:()=>canvas,documentElement:{style:{setProperty(){}}},
  body:{classList:{toggle(){}}},addEventListener:(name,fn)=>{events[name]=fn}};
vm.runInNewContext(code,{window:win,document:doc});
const p=win.__driftWithMePointer;
function point(x,y){const k=Math.min(canvas.width/512,canvas.height/236);
 return {clientX:rect.left+((canvas.width-512*k)/2+x*k)*rect.width/canvas.width,
 clientY:rect.top+((canvas.height-236*k)/2+y*k)*rect.height/canvas.height,
 pointerId:1,cancelable:true,preventDefault(){}}}
const cases=[
 [1024,600,0,0,1024,600], [1600,600,13,9,1600,600],
 [800,1000,7,12,800,1000], [2048,1200,0,0,1024,600],
 [1024,600,19,37,768,450], [512,236,0,0,390,179.765625],
 [1365,768,0,0,1365,768], [1200,900,0,0,960,450]];
let count=0;
for(const [bw,bh,x,y,w,h] of cases){
 canvas.width=bw;canvas.height=bh;rect={left:x,top:y,width:w,height:h};
 windowEvents.resize();
 for(const [lx,ly] of [[188,13.5],[136.75,151.75],[490.25,218.25]]){
  const e=point(lx,ly);events.pointerdown(e);
  assert(Math.abs(p.x-lx)<1e-8&&Math.abs(p.y-ly)<1e-8);
  assert(p.down&&p.inside);events.pointerup(e);assert(!p.down);count++;
 }
 const scale=Math.min(bw/512,bh/236),seq=p.sequence;
 if(bh>236*scale){events.pointerdown({...point(20,20),clientY:y+.1});assert.equal(p.sequence,seq)}
 if(bw>512*scale){events.pointerdown({...point(20,20),clientX:x+.1});assert.equal(p.sequence,seq)}
}
// Re-read geometry during a held pointer as well as after release.
events.pointerdown(point(100,100));rect={left:31,top:17,width:800,height:500};
events.pointermove(point(220,140));assert(Math.abs(p.x-220)<1e-8&&Math.abs(p.y-140)<1e-8);
events.pointerup(point(220,140));assert(!p.down);
console.log(count+' points passed; letterbox rejected; resize during drag passed');
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", harness],
        input=HOST_JS,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
