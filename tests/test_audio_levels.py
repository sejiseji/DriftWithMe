"""Global attenuation preserves dynamics, dialogue balance, and scene transitions."""

import pytest

from drift_with_me.audio import SOUND_SHAPES, AudioEngine
from drift_with_me.audio_levels import OUTPUT_GAIN
from drift_with_me.music import MusicContext
from test_office_music import RecordingPyxel


def test_every_effect_keeps_notes_and_applies_one_output_step():
    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    player = RecordingPyxel()
    audio.setup(player)
    assert OUTPUT_GAIN == 6 / 7
    for slot, shape in enumerate(SOUND_SHAPES.values()):
        assert player.definitions[slot] == shape
        audio._play_effect(slot)
        assert player.channels[3].gain == pytest.approx(0.125 * 6 / 7)


@pytest.mark.parametrize("track", ["explore", "battle", "fanfare", "office"])
def test_every_music_track_preserves_score_and_scales_fades(track):
    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    player = RecordingPyxel()
    audio.setup(player)
    music = audio.music
    for slot, part in zip(music.slots[track], music.scores[track]["parts"], strict=True):
        assert player.definitions[slot][2] == part["volumes"]
    music._start(track)
    for fade in (0, 0.25, 0.5, 1):
        music._gain(fade)
        for channel in music.active_channels:
            assert player.channels[channel].gain == pytest.approx(0.125 * 6 / 7 * fade)
    assert player.channels[3].gain == 0.125


def test_repeated_scene_mute_suspend_reset_never_restores_louder_output():
    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    player = RecordingPyxel()
    audio.setup(player)
    for _ in range(3):
        for ambient in ("office", "explore"):
            context = MusicContext(True, ambient=ambient)
            for _ in range(2):
                audio.music.update(context, 2, muted=False, suspended=False)
            audio.play_preview("action_denied")
            for channel in (*audio.music.active_channels, 3):
                assert player.channels[channel].gain == pytest.approx(0.125 * 6 / 7)
            audio.toggle_mute()
            assert not player.playing
            audio.toggle_mute()
            audio.suspend_for_lifecycle()
            assert not player.playing
            audio.resume_from_lifecycle()
            audio.reset_event_history()
