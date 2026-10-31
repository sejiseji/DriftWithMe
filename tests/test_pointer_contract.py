"""Independent regression checks for the selected pointer authority contract.

Fake browser/native samples deliberately disagree. These checks exercise actual
App and Lifecycle methods; they are not an iPhone/Safari event reproduction.
"""

import sys
from types import SimpleNamespace

import pytest

from drift_with_me.app import DriftWithMeApp as App
from drift_with_me.config import load_runtime_config


def subject(monkeypatch, *, host=True, native_down=False, native_pressed=False):
    app = App.__new__(App)
    app.runtime = load_runtime_config()
    app.browser_pointer_sequence_seen = 0
    app.ui_trace = None
    app.pyxel = SimpleNamespace(
        MOUSE_BUTTON_LEFT=1,
        KEY_Z=2,
        mouse_x=494,
        mouse_y=13,
        btn=lambda key: native_down and key == 1,
        btnp=lambda key: native_pressed and key == 1,
    )
    bridge = SimpleNamespace(
        down=False,
        pressed=False,
        released=True,
        sequence=0,
        x=252,
        y=79,
        pressedX=252,
        pressedY=79,
    )
    window = SimpleNamespace(__driftWithMePointer=bridge)
    monkeypatch.setitem(sys.modules, "js", SimpleNamespace(window=window) if host else None)
    return app, bridge, window


def down(bridge, sequence=1, *, held=True, point=(252, 79)):
    bridge.down = held
    bridge.pressed = True
    bridge.released = not held
    bridge.sequence = sequence
    bridge.x, bridge.y = bridge.pressedX, bridge.pressedY = point


def release(bridge):
    bridge.down = False
    bridge.released = True


@pytest.mark.parametrize("native_down", [False, True])
def test_host_release_is_authoritative_for_lifecycle(monkeypatch, native_down):
    app, _, _ = subject(monkeypatch, native_down=native_down)
    assert not app.lifecycle_input_held()
    assert app.read_pointer_snapshot().down is False
    assert app.pointer_input_status["source"] == "H"


def test_host_hold_cannot_be_cancelled_by_native_release(monkeypatch):
    app, bridge, _ = subject(monkeypatch)
    down(bridge)
    assert app.lifecycle_input_held()
    assert app.browser_pointer_sequence_seen == 0
    assert app.read_pointer_snapshot().pressed
    assert app.browser_pointer_sequence_seen == 1


def test_native_keyboard_still_blocks_release_with_host_selected(monkeypatch):
    app, _, _ = subject(monkeypatch)
    app.pyxel.btn = lambda key: key == app.pyxel.KEY_Z
    assert app.lifecycle_input_held()


def test_peek_never_acknowledges_short_press(monkeypatch):
    app, bridge, _ = subject(monkeypatch)
    down(bridge, held=False)
    for _ in range(4):
        sample = app.peek_pointer_snapshot()
        assert sample.pressed and not sample.down
        assert app.browser_pointer_sequence_seen == 0
    assert app.read_pointer_snapshot().pressed
    assert not app.read_pointer_snapshot().pressed


def test_explicit_discard_prevents_stale_press_after_release(monkeypatch):
    app, bridge, _ = subject(monkeypatch)
    down(bridge, held=False)
    app.discard_pointer_press()
    assert not app.read_pointer_snapshot().pressed
    down(bridge, 2, held=False)
    assert app.read_pointer_snapshot().pressed


@pytest.mark.parametrize("failure", ["missing", "invalid", "window"])
def test_web_failure_is_quarantined_not_native_fallback(monkeypatch, failure):
    app, bridge, window = subject(monkeypatch, native_down=True, native_pressed=True)
    app.read_pointer_snapshot()  # establish HOST before losing bridge
    if failure == "missing":
        del window.__driftWithMePointer
    elif failure == "invalid":
        bridge.x = float("nan")
    else:
        monkeypatch.setitem(sys.modules, "js", SimpleNamespace())
    sample = app.read_pointer_snapshot()
    assert not sample.down and not sample.pressed
    assert app.pointer_input_status["source"] == "Q"
    assert (sample.x, sample.y) != (494, 13)


def test_web_loss_of_js_import_never_activates_native_stale_press(monkeypatch):
    app, _, _ = subject(monkeypatch, native_down=True, native_pressed=True)
    app.read_pointer_snapshot()
    monkeypatch.setitem(sys.modules, "js", None)
    sample = app.read_pointer_snapshot()
    assert not sample.down and not sample.pressed
    assert app.pointer_input_status["source"] == "Q"


def test_recovery_requires_observed_release_and_new_sequence(monkeypatch):
    app, bridge, window = subject(monkeypatch, native_down=True, native_pressed=True)
    app.read_pointer_snapshot()
    del window.__driftWithMePointer
    assert not app.read_pointer_snapshot().pressed
    down(bridge, 7)
    window.__driftWithMePointer = bridge
    for _ in range(3):
        sample = app.read_pointer_snapshot()
        assert not sample.pressed
    release(bridge)
    assert not app.read_pointer_snapshot().pressed
    assert not app.read_pointer_snapshot().pressed
    down(bridge, 8, held=False)
    sample = app.read_pointer_snapshot()
    assert sample.pressed and not sample.down
    assert app.pointer_input_status["source"] == "H"


def test_recovery_peek_does_not_rearm_or_consume_stale_release(monkeypatch):
    app, bridge, window = subject(monkeypatch)
    app.read_pointer_snapshot()
    del window.__driftWithMePointer
    app.read_pointer_snapshot()
    down(bridge, 7, held=False)
    window.__driftWithMePointer = bridge
    assert not app.peek_pointer_snapshot().pressed
    assert not app.peek_pointer_snapshot().pressed
    assert not app.read_pointer_snapshot().pressed
    down(bridge, 8, held=False)
    assert app.read_pointer_snapshot().pressed


@pytest.mark.parametrize("native_down", [False, True])
def test_native_only_environment_retains_native_mouse_authority(monkeypatch, native_down):
    app, _, _ = subject(monkeypatch, host=False, native_down=native_down, native_pressed=True)
    sample = app.read_pointer_snapshot()
    assert sample.down == native_down
    assert sample.pressed
    assert (sample.x, sample.y) == (494, 13)
    assert app.pointer_input_status["source"] == "N"
    assert app.lifecycle_input_held() == native_down


def test_lifecycle_release_gate_discards_press_without_ui_activation(monkeypatch):
    app, bridge, _ = subject(monkeypatch, native_down=True)
    state = SimpleNamespace(active=True, generation=0, input_epoch=0)
    app.sync_browser_lifecycle = lambda: state
    app._lifecycle_wait_release = True
    app._lifecycle_wait_draw = False
    down(bridge, held=False)
    assert app.lifecycle_update_blocked()
    assert not app._lifecycle_wait_release
    assert not app.read_pointer_snapshot().pressed
    assert not app.lifecycle_update_blocked()
    down(bridge, 2, held=False)
    assert app.read_pointer_snapshot().pressed


def test_short_tap_release_metadata(monkeypatch):
    app, bridge, _ = subject(monkeypatch)
    down(bridge, held=False)
    p = app.read_pointer_snapshot()
    assert p.pressed and not p.down
    assert app.pointer_input_status["released"]


def test_native_press_acknowledged_once_per_engine_frame(monkeypatch):
    app, _, _ = subject(monkeypatch, host=False, native_down=True)
    app.pyxel.btnp = lambda key: key == app.pyxel.MOUSE_BUTTON_LEFT
    app.pyxel.frame_count = 42
    assert app.peek_pointer_snapshot().pressed
    assert app.read_pointer_snapshot().pressed
    assert not app.read_pointer_snapshot().pressed
    app.pyxel.frame_count += 1
    assert app.read_pointer_snapshot().pressed
