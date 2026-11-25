from types import SimpleNamespace

import pytest

from drift_with_me.audio import AudioEngine
from drift_with_me.audio_levels import OUTPUT_GAIN
from drift_with_me.music import PAUSE_FADE_SEC, PAUSE_SILENCE_SEC, MusicContext, context_for
from test_office_music import RecordingPyxel


def screen(name):
    return SimpleNamespace(screen=SimpleNamespace(name=name), model=SimpleNamespace())


@pytest.fixture
def engine():
    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    p = RecordingPyxel()
    audio.setup(p)
    return audio, p


def finish_gap(audio, app, elapsed=PAUSE_SILENCE_SEC):
    audio.update_music(app, elapsed)


@pytest.mark.parametrize("ambient", ["explore", "office", "infestation", "battle", "fanfare"])
def test_pause_music_starts_once_and_gameplay_resumes_at_exact_native_position(engine, ambient):
    audio, p = engine
    music = audio.music
    battle = SimpleNamespace()
    play = MusicContext(
        True,
        ambient=ambient,
        battle=battle if ambient in {"battle", "fanfare"} else None,
        victory=ambient == "fanfare",
    )
    music.update(play, 0.05, muted=False, suspended=False)
    assert music.track == ambient
    p.playing[0] = (0, 0.73)
    p.play(3, 0)  # An effect currently sounding just before pause.
    pause = screen("PAUSE")
    audio.update_music(pause, 1 / 60)
    assert not p.playing and music.position == 0.73
    audio.update_music(pause, PAUSE_SILENCE_SEC - 0.02)
    assert not p.playing
    audio.update_music(pause, 0.02)
    assert set(p.playing) == {0, 1, 2, 3}
    assert [(ch, slot) for ch, slot, _ in p.plays[-4:]] == list(enumerate(range(44, 48)))
    assert all(ch.gain == 0 for ch in p.channels)
    count = len(p.plays)
    audio.play_preview("action_denied")
    audio.play_office_feedback("correct")
    audio.update_music(pause, PAUSE_FADE_SEC)
    audio.update_music(pause, 1 / 60)
    assert len(p.plays) == count and all(ch.gain > 0 for ch in p.channels)
    assert music.track == ambient and music.position == 0.73

    music.update(play, 1 / 60, muted=False, suspended=False)
    assert not p.playing and music.blocks_sound_effects
    assert p.channels[3].gain == 0.125 * OUTPUT_GAIN
    music.update(play, PAUSE_SILENCE_SEC - 0.02, muted=False, suspended=False)
    assert not p.playing
    music.update(play, 0.02, muted=False, suspended=False)
    assert not music.blocks_sound_effects
    assert tuple(p.playing) == music.active_channels
    assert all(item[2]["sec"] == 0.73 for item in p.plays[count:])
    assert all(p.channels[ch].gain == 0 for ch in music.active_channels)
    audio.play_preview("action_denied")
    assert p.plays[-1][:2] == (3, audio._sound_slots["action_denied"])


def test_pause_mute_and_lifecycle_hold_never_start_or_leak_a_channel(engine):
    audio, p = engine
    pause = screen("PAUSE")
    audio.update_music(pause, 0.01)
    assert audio.music.pause_active
    audio.toggle_mute()
    finish_gap(audio, pause)
    assert not p.playing
    audio.toggle_mute()
    audio.update_music(pause, 0.01)
    assert len(p.playing) == 4
    p.playing[0] = (0, 0.84)
    audio.suspend_for_lifecycle()
    assert not p.playing and audio.music.pause_position == 0.84
    audio.update_music(pause, 4)
    audio.resume_from_lifecycle()
    pause._lifecycle_wait_release = True
    audio.update_music(pause, 3)
    assert not p.playing and not context_for(pause).pause_menu
    pause._lifecycle_wait_release = False
    audio.update_music(pause, 0.01)
    assert all(p.plays[-4 + i][2]["sec"] == 0.84 for i in range(4))
    audio.reset_event_history()
    assert not p.playing and not audio.music.blocks_sound_effects


def test_reopening_pause_during_resume_gap_starts_fresh_without_old_music(engine):
    audio, p = engine
    pause, play = screen("PAUSE"), screen("PLAY")
    audio.update_music(play, 0.01)
    audio.update_music(pause, 0.01)
    finish_gap(audio, pause)
    audio.update_music(play, 0.01)
    audio.update_music(pause, 0.01)
    assert not p.playing
    finish_gap(audio, pause)
    assert all(p.plays[-4 + i][2]["sec"] == 0 for i in range(4))
    audio.update_music(screen("START"), 0.01)
    assert not p.playing and not audio.music.blocks_sound_effects


def test_pause_score_parts_share_exact_loop_and_use_four_distinct_slots(engine):
    audio, p = engine
    score = audio.music.scores["pause"]
    assert score["seconds"] == 48 and score["loop"]
    slots = audio.music.slots["pause"]
    assert slots == (44, 45, 46, 47)
    assert len({p.definitions[slot][0] for slot in slots}) == 4
    for slot in slots:
        notes, tones, volumes, effects, speed = p.definitions[slot]
        assert len(notes.split()) == len(volumes) == len(effects) == 192
        assert len(tones) == 1 and speed == 30
        assert speed * len(volumes) / 120 == score["seconds"]
