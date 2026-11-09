"""Office BGM channel budget, scene routing and playback regression checks."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from drift_with_me.audio import SE_CHANNEL, SOUND_SHAPES, AudioEngine
from drift_with_me.audio_levels import OUTPUT_GAIN
from drift_with_me.config import load_data_json
from drift_with_me.music import MusicContext, MusicController, context_for


class RecordingPyxel:
    def __init__(self):
        self.definitions = {}
        self.sounds = [SimpleNamespace(set=self.setter(slot)) for slot in range(64)]
        self.channels = [SimpleNamespace(gain=0.125) for _ in range(4)]
        self.plays = []
        self.stops = []
        self.playing = {}

    def setter(self, slot):
        def set_sound(*args):
            self.definitions[slot] = args

        return set_sound

    def play(self, channel, slot, **kwargs):
        self.plays.append((channel, slot, kwargs))
        self.playing[channel] = (0, kwargs.get("sec", 0.0))

    def stop(self, channel=None):
        self.stops.append(channel)
        if channel is None:
            self.playing.clear()
        else:
            self.playing.pop(channel, None)

    def play_pos(self, channel):
        return self.playing.get(channel)


def setup():
    player = RecordingPyxel()
    music = MusicController()
    music.setup(player)
    return music, player


def update(music, *, office=True, paused=False, muted=False, suspended=False, dt=1 / 60):
    music.update(
        MusicContext(True, paused=paused, ambient="office" if office else "explore"),
        dt,
        muted=muted,
        suspended=suspended,
    )


def test_office_score_is_exactly_preview_melody_and_inner_voice():
    score = load_data_json("bgm_score.json")["office"]
    # Fingerprint of parts 0/1 in the approved three-voice preview, excluding bass.
    encoded = json.dumps(score["parts"], sort_keys=True).encode()
    assert (
        hashlib.sha256(encoded).hexdigest()
        == "711f3238ffbaa259178a3417c8c5d1f1387820891a21008d94b3d10915a1e4be"
    )
    assert (score["bpm"], score["bars"], score["seconds"], score["loop"]) == (80, 8, 24, True)
    assert len(score["parts"]) == 2
    for part in score["parts"]:
        assert len(part["notes"].split()) == 192
        assert len(part["volumes"]) == len(part["effects"]) == 192
        assert part["tones"] == "t"
        assert 192 * part["speed"] / 120 == score["seconds"]


def test_office_uses_two_slots_without_restarting_or_touching_spare_channels():
    music, player = setup()
    player.channels[2].gain = 0.21
    player.channels[3].gain = 0.37
    update(music)
    assert music.track == "office"
    assert music.active_channels == (0, 1)
    assert [(ch, slot) for ch, slot, _ in player.plays] == [(0, 41), (1, 42)]
    for _ in range(240):
        update(music)
    assert len(player.plays) == 2
    assert set(player.playing) == {0, 1}
    assert player.channels[2].gain == 0.21
    assert player.channels[3].gain == 0.37
    assert player.channels[0].gain == pytest.approx(0.125 * OUTPUT_GAIN)
    assert not ({2, 3} & set(player.stops))
    assert all(kwargs["loop"] for _, _, kwargs in player.plays)


def test_field_office_switch_releases_third_voice_and_restores_three_voice_field():
    music, player = setup()
    update(music, office=False)
    assert set(player.playing) == {0, 1, 2}
    update(music)
    assert set(player.playing) == {0, 1}
    assert 2 in player.stops
    update(music, office=False)
    assert music.track == "explore"
    assert set(player.playing) == {0, 1, 2}
    assert [slot for _, slot, _ in player.plays[-3:]] == [32, 33, 34]
    assert 3 not in player.stops


@pytest.mark.parametrize("pause_kind", ["paused", "suspended"])
def test_office_pause_or_background_freezes_and_resumes_native_position(pause_kind):
    music, player = setup()
    update(music)
    player.playing[0] = (0, 7.25)
    update(music, **{pause_kind: True})
    for _ in range(4):
        update(music, dt=3, **{pause_kind: True})
    assert music.position == 7.25
    assert not player.playing
    update(music)
    assert len(player.plays) == 4
    assert all(kw["sec"] == 7.25 for _, _, kw in player.plays[-2:])
    assert set(player.playing) == {0, 1}


def test_office_mute_advances_clock_and_wraps_without_playing_a_third_voice():
    music, player = setup()
    update(music, muted=True, dt=23.75)
    update(music, muted=True, dt=0.5)
    assert music.position == pytest.approx(0.25)
    assert not player.plays
    update(music)
    assert all(kw["sec"] == pytest.approx(0.25) for _, _, kw in player.plays)
    assert set(player.playing) == {0, 1}


def test_office_entry_clears_stale_battle_and_victory_state():
    music, player = setup()
    battle = object()
    music.update(MusicContext(True, battle=battle), 0.1, muted=False, suspended=False)
    music.restore_win = True
    update(music)
    assert music.track == "office" and music.battle is None
    assert not music.restore_win and not music.celebrated
    update(music, office=False)
    music.update(MusicContext(True, battle=battle), 0.1, muted=False, suspended=False)
    assert music.track == "battle"
    assert set(player.playing) == {0, 1, 2}


@pytest.mark.parametrize("screen", ["START", "CREDITS", "COLLECTION_ROOM", "WATER_STUDY"])
def test_other_screens_stop_office_without_touching_se(screen):
    music, player = setup()
    update(music)
    player.play(3, 0)
    context = context_for(SimpleNamespace(screen=SimpleNamespace(name=screen)))
    music.update(context, 0.1, muted=False, suspended=False)
    assert not context.active and music.track is None
    assert set(player.playing) == {3}


@pytest.mark.parametrize("transition", ["field_transition", "week_transition"])
def test_office_scene_routing_and_transition_silence(transition):
    # Office context does not inspect a stale field combat model.
    app = SimpleNamespace(screen=SimpleNamespace(name="OFFICE"))
    assert context_for(app) == MusicContext(True, ambient="office")
    setattr(app, transition, object())
    assert not context_for(app).active
    app._lifecycle_wait_release = True
    assert context_for(app).paused


def test_office_and_se_use_disjoint_channels_and_sound_slots():
    engine = AudioEngine({"audio": {"enabled_by_default": True}})
    player = RecordingPyxel()
    engine.setup(player)
    update(engine.music)
    engine.play_preview("action_denied")
    assert player.plays[-1][0] == SE_CHANNEL == 3
    assert set(player.playing) == {0, 1, 3}
    all_music_slots = [slot for slots in engine.music.slots.values() for slot in slots]
    assert len(all_music_slots) == len(set(all_music_slots))
    assert min(all_music_slots) >= len(SOUND_SHAPES)
    assert max(all_music_slots) < len(player.sounds)
    engine.music.reset()
    assert engine.music.track is None and set(player.playing) == {3}
    update(engine.music)
    assert all(kw["sec"] == 0 for _, _, kw in player.plays[-2:])
