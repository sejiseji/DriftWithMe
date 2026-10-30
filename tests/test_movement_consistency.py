import json
import shutil
import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from scripts.build_web import HOST_JS

from drift_with_me.app import DriftWithMeApp as App
from drift_with_me.input import DoubleTapMoveRecognizer, PointerInput, PointerState, Rect
from drift_with_me.math3d import AffineProjectionProfile, Vec3, affine_camera_from_perspective
from drift_with_me.model import InputIntent
from test_movement import make_model


@pytest.mark.parametrize("yaw", [20, 27.5, 35])
@pytest.mark.parametrize("zoom", [0.7, 1.0, 1.14, 1.55])
@pytest.mark.parametrize(
    "sx,sy", [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
)
def test_manual_direction_uses_the_same_projection_as_render(yaw, zoom, sx, sy):
    model, base = make_model()
    model.config["player"]["manual_inertia_enabled"] = False
    camera = replace(base, yaw_deg=yaw, distance=480 / zoom)
    rendered = affine_camera_from_perspective(
        camera, AffineProjectionProfile.from_config(model.config), base_distance=480
    )
    before = rendered.project(Vec3(model.player.x, 0, model.player.z))
    model.step(
        InputIntent(screen_x=sx, screen_y=sy, strength=1), camera, 1 / 60, movement_camera=rendered
    )
    after = rendered.project(Vec3(model.player.x, 0, model.player.z))
    dx, dy = after.x - before.x, after.y - before.y
    assert dx * sx + dy * sy > 0
    assert abs(dx * sy - dy * sx) < 1e-7


@pytest.mark.parametrize("rects", [(), (Rect(290, 100, 40, 40),)])
def test_dom_new_sequence_resets_drag_anchor_even_without_sampled_up(monkeypatch, rects):
    app = App.__new__(App)
    app.runtime = SimpleNamespace(screen_width=512, screen_height=236)
    app.browser_pointer_sequence_seen = 0
    app.pointer = PointerInput(0.22, 8, 8, 48)
    app.active_ui_rects = lambda: rects
    bridge = SimpleNamespace(down=True, pressed=True, sequence=1, x=200, y=120)
    monkeypatch.setitem(
        sys.modules, "js", SimpleNamespace(window=SimpleNamespace(__driftWithMePointer=bridge))
    )

    def sample():
        app.pointer_snapshot = app.read_browser_pointer_snapshot()
        return app.pointer_intent(1 / 60)

    assert sample().strength == 0
    bridge.x = 150
    assert sample().screen_x == -1
    bridge.sequence = 2
    bridge.x = 300
    assert sample().strength == 0
    assert app.pointer.start_x == 300
    assert app.pointer.state == (PointerState.UI_CAPTURE if rects else PointerState.WORLD_PENDING)


def test_double_tap_does_not_join_distinct_unsampled_gestures():
    _, camera = make_model()
    recognizer = DoubleTapMoveRecognizer(0.18, 0.3, 20, 8)
    args = dict(down=True, y=120, dt=1 / 60, ui_rects=(), camera=camera)
    recognizer.update(x=200, pressed=True, **args)
    recognizer.update(x=150, **args)
    assert recognizer.update(x=300, pressed=True, **args) is None
    assert recognizer.start_x == 300
    assert recognizer.update(False, 300, 120, 1 / 60, (), camera) is None


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required for host execution")
@pytest.mark.parametrize(
    "event_name", ["resize", "orientationchange", "viewport_resize", "viewport_scroll"]
)
def test_geometry_change_cancels_dom_drag_and_advances_python_epoch(event_name):
    harness = r"""
const vm=require('vm'),
fs=require('fs'),
assert=require('assert');

const code=fs.readFileSync(0,
'utf8'),
events={},
windows={},
viewport={};

let rect={left:0,
top:0,
width:1024,
height:472};

const canvas={width:1024,
height:472,
getBoundingClientRect:()=>rect,
setPointerCapture(){},
releasePointerCapture(){}};

const win={top:{},
innerWidth:1024,
innerHeight:472,
__driftWithMeLogicalSize:{width:512,
height:236},
__driftWithMeLifecycle:{active:true,
inputEpoch:0},
addEventListener:(n,
f)=>windows[n]=f,
visualViewport:{width:1024,
height:472,
addEventListener:(n,
f)=>viewport[n]=f}};

const doc={querySelector:()=>canvas,
documentElement:{style:{setProperty(){}}},
body:{classList:{toggle(){}}},
addEventListener:(n,
f)=>events[n]=f};

vm.runInNewContext(code,
{window:win,
document:doc});

const e=x=>({clientX:x,
clientY:240,
pointerId:1,
cancelable:true,
preventDefault(){}});

events.pointerdown(e(400));
events.pointermove(e(380));
const before={...win.__driftWithMePointer};

rect={left:0,
top:0,
width:512,
height:236};

const name=process.argv[1];
if(name.startsWith('viewport_'))viewport[name.slice(9)]();
else windows[name]();

events.pointermove(e(380));
const after={...win.__driftWithMePointer};

console.log(JSON.stringify({before,
after,
epoch:win.__driftWithMeLifecycle.inputEpoch}));

"""
    result = subprocess.run(
        ["node", "-e", harness, event_name],
        input=HOST_JS,
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(result.stdout)
    pointer = PointerInput(0.22, 8, 8, 48)
    pointer.update(True, 200, 120, 1 / 60)
    assert pointer.update(True, data["before"]["x"], 120, 1 / 60).screen_x == -1
    assert data["epoch"] == 1
    assert not data["after"]["down"]
    assert (
        pointer.update(
            data["after"]["down"], data["after"]["x"], data["after"]["y"], 1 / 60
        ).strength
        == 0
    )
    assert pointer.state == PointerState.IDLE


@pytest.mark.parametrize(
    "sx,sy", [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
)
def test_held_drag_stays_aligned_through_zoom_and_yaw_blend(sx, sy):
    model, base = make_model()
    pointer = PointerInput(0.22, 8, 8, 48)
    pointer.update(True, 200, 120, 1 / 120, pressed=True)
    for frame in range(60):
        amount = frame / 59
        intent = pointer.update(True, 200 + 40 * sx, 120 + 40 * sy, 1 / 120)
        camera = replace(
            base,
            target=Vec3(model.player.x, 0, model.player.z),
            yaw_deg=20 + 15 * amount,
            distance=480 / (1 - 0.3 * amount),
        )
        rendered = affine_camera_from_perspective(
            camera, AffineProjectionProfile.from_config(model.config), base_distance=480
        )
        a = rendered.project(Vec3(model.player.x, 0, model.player.z))
        model.step(intent, camera, 1 / 120, movement_camera=rendered)
        b = rendered.project(Vec3(model.player.x, 0, model.player.z))
        dx, dy = b.x - a.x, b.y - a.y
        assert dx * sx + dy * sy > 0
        assert abs(dx * sy - dy * sx) < 1e-7
        assert pointer.state == PointerState.MOVE
    released = pointer.update(False, 200, 120, 1 / 120)
    before = (model.player.x, model.player.z)
    model.step(released, camera, 1 / 120, movement_camera=rendered)
    assert (model.player.x, model.player.z) == before


def test_geometry_epoch_cancels_python_anchor_and_requires_release_before_resume():
    from test_lifecycle_pause import subject

    app = subject()
    pointer = PointerInput(0.22, 8, 8, 48)
    pointer.update(True, 200, 120, 1 / 60)
    pointer.update(True, 160, 120, 1 / 60)
    app.clear_world_input_latches = pointer.cancel
    assert not app.lifecycle_update_blocked()
    app._lifecycle_bridge.inputEpoch += 1
    assert app.lifecycle_update_blocked()
    assert pointer.state == PointerState.WAIT_ALL_RELEASE
    app.lifecycle_did_draw()
    # A fresh DOM press arriving before Python has observed release stays gated.
    app.pointer_snapshot = replace(app.pointer_snapshot, down=True)
    assert app.lifecycle_update_blocked()
    app.pointer_snapshot = replace(app.pointer_snapshot, down=False)
    assert app.lifecycle_update_blocked()
    assert not app.lifecycle_update_blocked()
    assert pointer.update(False, 380, 120, 1 / 60).strength == 0
    assert pointer.update(True, 300, 120, 1 / 60, pressed=True).strength == 0
    assert pointer.start_x == 300
