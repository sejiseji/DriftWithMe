"""Shared map playback contracts, exercised independently for both approved scores."""

import pytest

from drift_with_me.audio_levels import OUTPUT_GAIN
from drift_with_me.music import MusicContext
from test_explore_music import update
from test_office_music import setup


@pytest.mark.parametrize(("ambient", "slot"), [("explore", 32), ("infestation", 43)])
def test_map_plays_one_native_loop_without_touching_spare_channels(ambient, slot):
    music, player = setup()
    assert 33 not in player.definitions and 34 not in player.definitions
    player.play(3, 0)
    context = MusicContext(True, ambient=ambient)
    update(music, context)
    assert music.track == ambient and music.active_channels == (0,)
    assert player.plays[-1] == (0, slot, {"sec": 0.0, "loop": True})
    for _ in range(240):
        update(music, context)
    assert len(player.plays) == 2  # SE plus one loop start, no per-note callbacks.
    assert set(player.playing) == {0, 3}
    assert player.channels[0].gain == pytest.approx(0.125 * OUTPUT_GAIN)
    assert all(player.channels[ch].gain == 0.125 for ch in (1, 2, 3))


@pytest.mark.parametrize("ambient", ["explore", "infestation"])
@pytest.mark.parametrize("victory", [False, True])
def test_combat_and_fanfare_release_extra_voices_to_current_map(ambient, victory):
    music, player = setup()
    player.play(3, 0)
    update(music, MusicContext(True, ambient=ambient))
    update(music, MusicContext(True, ambient=ambient, battle=object(), victory=victory))
    assert music.track == ("fanfare" if victory else "battle")
    assert set(player.playing) == {0, 1, 2, 3}
    if victory:
        player.playing[0] = (0, music.scores["fanfare"]["seconds"])
    update(music, MusicContext(True, ambient=ambient))
    assert music.track == ambient and set(player.playing) == {0, 3}
    assert {1, 2} <= set(player.stops)
    assert 3 not in player.stops
