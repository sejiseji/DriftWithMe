"""Transient feedback is success-gated, bounded, and independent of saved logic."""

from types import SimpleNamespace

from drift_with_me.audio import AudioEngine
from drift_with_me.config import load_runtime_config
from drift_with_me.events import GameEvent
from drift_with_me.exploration_feedback import ExplorationFeedback


def event(ident=1, kind="resource_refilled", **payload):
    return GameEvent(ident, 0, kind, "player", "station", (10, 0, 10), payload)


def model():
    return SimpleNamespace(
        player=SimpleNamespace(x=0, z=0),
        buddy=SimpleNamespace(x=1, y=10, z=1),
        interaction_candidate=lambda camera: SimpleNamespace(id="station"),
    )


def test_zero_refill_and_duplicate_do_not_replay_success():
    feedback = ExplorationFeedback()
    m = model()
    feedback.process([event(resource="water", amount=0)], m)
    assert not feedback.pulses and feedback.flashes["water"] == 0
    success = event(2, resource="water", amount=1)
    feedback.process([success, success], m)
    assert len(feedback.pulses) == 1
    for i in range(3, 200):
        feedback.process([event(i, resource="energy", amount=1)], m)
    assert len(feedback.pulses) == feedback.LIMIT
    assert len(feedback.recent_ids) == 64
    feedback.update(0.1, m, None, active=False)
    assert not feedback.pulses and not any(feedback.flashes.values())


def test_marker_reentry_cooldown_and_reset():
    feedback = ExplorationFeedback()
    m = model()
    feedback.update(0.05, m, None)
    feedback.update(0.05, m, None)
    assert feedback.marker_offset("station") < 0
    m.interaction_candidate = lambda camera: None
    feedback.update(0.05, m, None)
    m.interaction_candidate = lambda camera: SimpleNamespace(id="station")
    feedback.update(0.05, m, None)
    assert feedback.target_age > 0
    feedback.enabled = False
    feedback.reset()
    assert not feedback.enabled and not feedback.recent_ids


def test_soft_audio_never_interrupts_busy_channel_or_full_refill():
    engine = AudioEngine(load_runtime_config().raw)
    played = []
    engine._pyxel = SimpleNamespace(
        play=lambda *args: played.append(args), play_pos=lambda channel: (1, 0)
    )
    engine._sound_slots = {"explore_water": 12}
    engine.muted = False
    engine.play_events([event(resource="water", amount=0)])
    engine.play_events([event(2, resource="water", amount=1)])
    assert not played
    engine._pyxel.play_pos = lambda channel: None
    engine.play_events([event(3, resource="water", amount=1)])
    assert played == [(3, 12)]
    engine.play_events([event(3, resource="water", amount=1)])
    assert len(played) == 1
