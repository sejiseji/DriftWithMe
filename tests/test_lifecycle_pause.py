from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from drift_with_me.app import DriftWithMeApp as App
from drift_with_me.app import PointerSnapshot
from drift_with_me.lifecycle import LifecycleMixin


def subject():
    app = App.__new__(App)
    app._lifecycle_bridge = SimpleNamespace(
        active=True, generation=0, inputEpoch=0, acknowledge=Mock()
    )
    app.previous_time = 100.0
    app.pointer_snapshot = PointerSnapshot(True, True, 12, 13)
    app.clear_world_input_latches = Mock()
    app.model = SimpleNamespace(cancel_auto_move=Mock())
    app.audio = SimpleNamespace(suspend_for_lifecycle=Mock(), resume_from_lifecycle=Mock())
    app.pyxel = SimpleNamespace(KEY_RIGHT=1, MOUSE_BUTTON_LEFT=2, btn=lambda _: False)
    app.read_pointer_snapshot = lambda: app.pointer_snapshot
    return app


@pytest.mark.parametrize("scene", ["field", "conversation", "combat"])
def test_hidden_update_never_reaches_elapsed_or_scene_and_resume_waits_for_draw_release(scene):
    app = subject()
    app.scene = scene
    app.consume_elapsed = Mock(side_effect=AssertionError("hidden game advanced"))
    assert not app.lifecycle_update_blocked()
    for _ in range(20):
        app._lifecycle_bridge.active = False
        app._lifecycle_bridge.generation += 1
        app._lifecycle_bridge.inputEpoch += 1
        for _ in range(10):
            App.update(app)
            assert not app.lifecycle_draw_allowed()
        assert app.previous_time is None
        assert not app.pointer_snapshot.down
        app._lifecycle_bridge.active = True
        app._lifecycle_bridge.generation += 1
        App.update(app)  # engine catch-up callbacks before its first draw are discarded
        assert app.lifecycle_draw_allowed()
        app.lifecycle_did_draw()
        app.pyxel.btn = lambda _: True
        App.update(app)  # held keyboard input cannot leak into the resumed scene
        app.pyxel.btn = lambda _: False
        App.update(app)  # release edge is swallowed too
        assert not app.lifecycle_update_blocked()
    app.consume_elapsed.assert_not_called()
    assert app.model.cancel_auto_move.call_count == 40
    assert app._lifecycle_bridge.acknowledge.call_count == 20


def test_elapsed_after_pause_is_single_fixed_step(monkeypatch):
    app = subject()
    app.runtime = SimpleNamespace(fixed_dt=1 / 60)
    app.reset_lifecycle_input_and_clock()
    monkeypatch.setattr("drift_with_me.app.time.monotonic", lambda: 10_000)
    assert App.consume_elapsed(app) == 1 / 60


def test_desktop_without_bridge_has_no_gate():
    app = subject()
    app._lifecycle_bridge = False
    assert not LifecycleMixin.lifecycle_update_blocked(app)
    assert app.lifecycle_draw_allowed()
    assert app.previous_time == 100


def test_audio_suspension_is_idempotent_and_preserves_user_mute_and_event_history():
    from drift_with_me.audio import AudioEngine

    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    audio._pyxel = SimpleNamespace(stop=Mock(), play=Mock())
    audio._processed_event_ids.add(42)
    audio.suspend_for_lifecycle()
    audio.suspend_for_lifecycle()
    audio.play_preview("capture_success")
    audio._pyxel.stop.assert_called_once()
    audio._pyxel.play.assert_not_called()
    audio.resume_from_lifecycle()
    assert not audio.muted
    assert audio._processed_event_ids == {42}
    audio._pyxel.play.assert_not_called()
