"""Sparse field score and its one-channel playback contract."""

import hashlib
import json

import pytest

from drift_with_me.audio_levels import OUTPUT_GAIN
from drift_with_me.config import load_data_json
from drift_with_me.music import MusicContext
from test_office_music import setup


def update(music, context=None, **kwargs):
    music.update(
        context or MusicContext(True),
        kwargs.pop("dt", 1 / 60),
        muted=kwargs.pop("muted", False),
        suspended=kwargs.pop("suspended", False),
    )


def test_explore_is_slow_staccato_with_explicit_silence():
    score = load_data_json("bgm_score.json")["explore"]
    assert len(score["parts"]) == 1
    assert (score["bpm"], score["bars"], score["seconds"], score["loop"]) == (60, 16, 64, True)
    part = score["parts"][0]
    notes = part["notes"].split()
    assert len(notes) == 256
    assert len(notes) * part["speed"] / 120 == score["seconds"]
    assert part["speed"] / 120 == 0.25
    assert part["tones"] == "t" and part["volumes"] == "2" and part["effects"] == "f"
    assert all(notes[i : i + 3] == ["r"] * 3 for i in range(1, len(notes), 4))
    assert notes[-8:] == ["r"] * 8


@pytest.mark.parametrize(
    ("name", "fingerprint"),
    [
        ("battle", "f50f7791b95056aa04dea1967d8561ba74cf971459a97594257940abc9648bf9"),
        ("fanfare", "1fa37375788cb3dbdff1c3f4ea2f32fa43a782856a21eb8f5c23b4e13ffe1e02"),
        ("office", "89675e8a3cbe089336c9b51e046dbf1563f30fb83bd958d4cb209d6a077846bf"),
    ],
)
def test_other_scores_are_unchanged(name, fingerprint):
    score = load_data_json("bgm_score.json")[name]
    assert hashlib.sha256(json.dumps(score, sort_keys=True).encode()).hexdigest() == fingerprint


def test_explore_loads_and_plays_one_native_loop_without_touching_spare_channels():
    music, player = setup()
    assert 33 not in player.definitions and 34 not in player.definitions
    player.play(3, 0)
    update(music)
    assert music.active_channels == (0,)
    assert player.plays[-1] == (0, 32, {"sec": 0.0, "loop": True})
    for _ in range(240):
        update(music)
    assert len(player.plays) == 2  # SE plus one loop start, no per-note callbacks.
    assert set(player.playing) == {0, 3}
    assert player.channels[0].gain == pytest.approx(0.125 * OUTPUT_GAIN)
    assert all(player.channels[ch].gain == 0.125 for ch in (1, 2, 3))


@pytest.mark.parametrize("victory", [False, True])
def test_combat_and_fanfare_release_both_extra_voices_on_return(victory):
    music, player = setup()
    player.play(3, 0)
    update(music, MusicContext(True, battle=object(), victory=victory))
    assert music.track == ("fanfare" if victory else "battle")
    assert set(player.playing) == {0, 1, 2, 3}
    if victory:
        player.playing[0] = (0, music.scores["fanfare"]["seconds"])
    update(music)
    assert music.track == "explore" and set(player.playing) == {0, 3}
    assert {1, 2} <= set(player.stops)
    assert 3 not in player.stops


def test_explore_pause_mute_wrap_and_reset_keep_single_channel():
    music, player = setup()
    update(music)
    player.playing[0] = (0, 6.25)
    update(music, MusicContext(True, paused=True))
    update(music, suspended=True, dt=100)
    assert music.position == 6.25 and not player.playing
    update(music)
    assert player.plays[-1][2]["sec"] == 6.25
    update(music, muted=True, dt=64)
    assert music.position == 6.25 and not player.playing
    update(music)
    assert set(player.playing) == {0}
    music.reset()
    assert music.track is None and not player.playing
    update(music)
    assert player.plays[-1][2]["sec"] == 0
