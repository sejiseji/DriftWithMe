from types import SimpleNamespace

from drift_with_me.audio import SE_CHANNEL, SOUND_SHAPES, AudioEngine
from drift_with_me.config import load_runtime_config
from drift_with_me.events import GameEvent
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.world import load_world_data


def event(ident, kind, **payload):
    return GameEvent(ident, 0, kind, "player", "enemy", (0, 0, 0), payload)


def engine():
    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    state = SimpleNamespace(busy=False, played=[], stopped=[])
    audio._pyxel = SimpleNamespace(
        play=lambda *args: state.played.append(args),
        play_pos=lambda ch: (0, 0) if state.busy else None,
        stop=lambda *args: state.stopped.append(args),
    )
    audio._sound_slots = {key: i for i, key in enumerate(SOUND_SHAPES)}
    return audio, state


def test_one_se_channel_and_cross_frame_priority():
    audio, state = engine()
    assert SE_CHANNEL == 3
    assert {d.channel for d in audio.defs.values()} == {3}
    audio.play_events([event(1, "combat_started")])
    state.busy = True
    audio.play_events([event(2, "bubble_fired")])
    assert len(state.played) == 1
    audio.play_preview("action_denied")
    assert len(state.played) == 1
    audio.play_events([event(3, "combat_position_settle_started")])
    assert state.played[-1] == (3, audio._sound_slots["battle_position_zaza"])
    audio.play_events([event(4, "enemy_captured")])
    assert state.played[-1] == (3, audio._sound_slots["capture_success"])
    audio.play_events([event(5, "collectible_claimed")])
    assert len(state.played) == 3
    state.busy = False
    audio.play_events([event(6, "bubble_fired")])
    assert state.played[-1] == (3, audio._sound_slots["bubble_launch"])


def test_same_frame_arbitration_and_no_duplicate_or_late_queue():
    audio, state = engine()
    cue = event(2, "combat_started")
    audio.play_events([cue, event(1, "enemy_captured")])
    assert state.played == [(3, audio._sound_slots["capture_success"])]
    audio.play_events([cue])
    state.busy = False
    audio.play_events([])
    assert len(state.played) == 1


def test_mute_and_lifecycle_do_not_replay_cues():
    audio, state = engine()
    audio.play_events([event(1, "combat_started")])
    audio.toggle_mute()
    assert state.stopped == [(3,)]
    audio.play_events([event(2, "combat_position_settle_started")])
    audio.toggle_mute()
    audio.suspend_for_lifecycle()
    audio.resume_from_lifecycle()
    audio.play_events([])
    assert len(state.played) == 1


def model_and_camera():
    runtime = load_runtime_config()
    model = GameModel(runtime.raw, load_world_data())
    camera = CameraState.from_config(runtime.raw, Vec3(model.player.x, 0, model.player.z), 512, 236)
    return model, camera


def test_normal_entry_emits_once_at_actual_motion_start_without_resource_change():
    model, camera = model_and_camera()
    enemy = next(e for e in model.enemies if e.kind == "normal")
    started = []
    model.start_contact_combat(enemy, started)
    assert [e.kind for e in started].count("combat_started") == 1
    before = (model.water, model.energy)
    frames = []
    for frame in range(60):
        events = []
        model.update_combat_session(InputIntent(), camera, 1 / 60, events)
        frames += [frame for e in events if e.kind == "combat_position_settle_started"]
    assert frames == [10]
    assert (model.water, model.energy) == before


def test_large_step_crossing_once_and_swarm_entry_clock():
    model, camera = model_and_camera()
    enemy = next(e for e in model.enemies if e.kind == "normal")
    model.start_contact_combat(enemy, [])
    events = []
    model.update_combat_session(InputIntent(), camera, 0.5, events)
    model.update_combat_session(InputIntent(), camera, 0.1, events)
    assert sum(e.kind == "combat_position_settle_started" for e in events) == 1

    from test_swarm_field import setup_field

    model, camera, field = setup_field()
    events = []
    assert field.start("northwest", camera, events)
    assert any(e.kind == "swarm_started" for e in events)
    for _ in range(60):
        field.step(InputIntent(), camera, 1 / 60, events)
    assert sum(e.kind == "combat_position_settle_started" for e in events) == 1
