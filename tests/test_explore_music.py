"""Approved quick-note field score and its one-channel playback contract."""

import hashlib
import json

import pytest

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


def test_explore_is_the_approved_quick_melody_in_one_voice():
    score = load_data_json("bgm_score.json")["explore"]
    assert hashlib.sha256(json.dumps(score, sort_keys=True).encode()).hexdigest() == (
        "ce3dd497a31cd343a3be1d9eec7e56e6eceb56727636839223c3a298cbc66264"
    )
    assert len(score["parts"]) == 1
    assert (score["bpm"], score["bars"], score["seconds"], score["loop"]) == (60, 16, 64, True)
    part = score["parts"][0]
    notes = part["notes"].split()
    assert len(notes) == len(part["effects"]) == len(part["volumes"]) == 1536
    assert len(notes) * part["speed"] / 120 == score["seconds"]
    assert part["speed"] == 5 and part["tones"] == "t"
    for i in range(248):
        phrase = notes[i * 6 : (i + 1) * 6]
        assert phrase[:5] == [phrase[0]] * 5 and phrase[0] != "r"
        assert phrase[5] == "r"
        assert part["effects"][i * 6 : (i + 1) * 6] == "nnnnfn"
        assert part["volumes"][i * 6 : (i + 1) * 6] == "222220"
    assert notes[-48:] == ["r"] * 48
    assert notes[::6][:8] == ["d3", "e-3", "d3", "e-3", "f3", "g3", "f3", "e-3"]


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
