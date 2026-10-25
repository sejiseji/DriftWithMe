const assert = require('assert'), vm = require('vm'), fs = require('fs');
const listeners = {window: {}, document: {}};
const on = (target, name, fn) => (listeners[target][name] ||= []).push(fn);
const fire = (target, name, extra={}) => {
  const event = {type:name,...extra};
  for (const fn of listeners[target][name] || []) fn(event);
};
let id = 0, count = 0;
const physical = new Map(), late = [];
let audioSuspends=0, audioResumes=0;
class Audio {
  constructor() {this.state=Audio.initialState || 'running';this.denied=false;}
  async suspend() {audioSuspends++;this.state='suspended';}
  async resume() {audioResumes++;if(this.denied)throw Error('gesture');this.state='running';}
}
class KeyboardEvent {constructor(type,opts) {this.type=type;Object.assign(this,opts);}}
const dispatch = e => fire('window',e.type,e);
const canvas={width:512,height:236,getBoundingClientRect:()=>({left:0,top:0,width:512,height:236}),
  setPointerCapture(){},releasePointerCapture(){},dispatchEvent:dispatch};
const win={top:{},innerWidth:512,innerHeight:236,AudioContext:Audio,KeyboardEvent,
  __driftWithMeLogicalSize:{width:512,height:236},
  requestAnimationFrame:fn=>{physical.set(++id,fn);return id;},
  cancelAnimationFrame:id=>{if(physical.has(id))late.push(physical.get(id));physical.delete(id);},
  addEventListener:(name,fn)=>on('window',name,fn)};
const doc={hidden:false,querySelector:()=>canvas,documentElement:{style:{setProperty(){}}},
  body:{classList:{toggle(){}}},addEventListener:(name,fn)=>on('document',name,fn),dispatchEvent:dispatch};
vm.runInNewContext(fs.readFileSync(0,'utf8'),{window:win,document:doc});
const life=win.__driftWithMeLifecycle;
const pump = () => {const jobs=[...physical.values()];physical.clear();for(const fn of jobs)fn(1000+count);};
const tick=()=>{count++;win.requestAnimationFrame(tick);};
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
(async()=>{
  const ctx=new win.AudioContext();await flush();
  win.requestAnimationFrame(tick);pump();assert.equal(count,1);assert.equal(physical.size,1);
  // Blur releases input, but does not conflate browser controls with a hidden page.
  const pointer=win.__driftWithMePointer;pointer.down=pointer.pressed=true;
  let ups=0;on('window','keyup',()=>ups++);
  fire('window','keydown',{code:'ArrowRight',key:'ArrowRight',keyCode:39});
  fire('window','blur');assert(life.active);assert(!pointer.down&&!pointer.pressed);assert.equal(ups,1);
  for(let cycle=0;cycle<20;cycle++){
    doc.hidden=true;fire('document','visibilitychange');await flush();
    assert(!life.active);assert.equal(ctx.state,'suspended');assert.equal(physical.size,0);
    const old=count;for(let t=0;t<50;t++)pump();assert.equal(count,old);
    // A pagehide/bfcache round trip must not resume until both conditions clear.
    fire('window','pagehide',{persisted:true});
    doc.hidden=false;fire('document','visibilitychange');assert(!life.active);
    fire('window','pageshow',{persisted:true});assert(life.active);assert.equal(physical.size,1);
    await flush();assert.equal(ctx.state,'suspended');
    life.acknowledge(life.generation-1);await flush();assert.equal(ctx.state,'suspended');
    life.acknowledge(life.generation);await flush();assert.equal(ctx.state,'running');
    // Even a late, cancelled native callback must not produce a duplicate loop.
    for(const fn of late.splice(0))fn(999999);
    assert.equal(count,old);pump();assert.equal(count,old+1);assert.equal(physical.size,1);
    fire('window','pageshow');assert.equal(physical.size,1);
  }
  fire('document','freeze');assert(!life.active);assert.equal(physical.size,0);
  fire('document','resume');assert(life.active);assert.equal(physical.size,1);
  life.acknowledge(life.generation);await flush();
  // No new pointer input can be buffered while hidden.
  doc.hidden=true;fire('document','visibilitychange');
  fire('document','pointerdown',{clientX:100,clientY:100,pointerId:1});assert(!pointer.down);
  const cancelled=win.requestAnimationFrame(()=>assert.fail('cancelled callback'));
  win.cancelAnimationFrame(cancelled);
  // Contexts which the user had not started must not be started by restoration.
  Audio.initialState='suspended';const dormant=new win.AudioContext();Audio.initialState='running';await flush();
  doc.hidden=false;fire('document','visibilitychange');life.acknowledge(life.generation);await flush();
  assert.equal(dormant.state,'suspended');
  // Resume may need a user gesture; do not loop or unmute as a workaround.
  doc.hidden=true;fire('document','visibilitychange');await flush();ctx.denied=true;
  doc.hidden=false;fire('document','visibilitychange');life.acknowledge(life.generation);await flush();
  assert.equal(ctx.state,'suspended');const attempts=audioResumes;
  pump();pump();await flush();assert.equal(audioResumes,attempts);
  ctx.denied=false;fire('window','pointerdown');await flush();assert.equal(ctx.state,'running');
  assert(audioSuspends>20);console.log('PASS:20cycles,zerohiddenframes,audiopause/ack,latecancel,dormantcontext,gesture,frozen,bfcache,blur,input');
})().catch(e=>{console.error(e);process.exitCode=1;});
