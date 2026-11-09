from types import SimpleNamespace

import pytest

from drift_with_me.app import AppScreen, OfficeDialogueLine
from drift_with_me.audio import SOUND_SHAPES, AudioEngine
from drift_with_me.audio_levels import OUTPUT_GAIN
from drift_with_me.dialogue_voice import (
    VOICE_GAIN,
    VOICE_SHAPES,
    VOICE_SLOTS,
    audible_character,
    voice_for_speaker,
    voice_metadata,
)
from drift_with_me.office import SUPERVISOR_NAME
from test_combat_entry_audio import engine, event
from test_office import make_office_dialogue_app


def page(preset="male_child", text="こんにちは世界"):
    return (OfficeDialogueLine(text, True, speaker="test", voice_preset=preset),)


def test_six_profiles_native_slots_disjoint_from_se_and_bgm():
    assert len(set(VOICE_SHAPES.values())) == 6
    assert set(VOICE_SLOTS.values()) == set(range(16, 22))
    assert not set(VOICE_SLOTS.values()) & set(range(len(SOUND_SHAPES)))
    assert not set(VOICE_SLOTS.values()) & set(range(32, 43))
    calls = {}
    sounds = [SimpleNamespace(set=lambda *args, i=i: calls.update({i: args})) for i in range(64)]
    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    audio.music.setup = lambda p: None
    audio.setup(SimpleNamespace(sounds=sounds))
    for key, slot in VOICE_SLOTS.items():
        assert calls[slot] == VOICE_SHAPES[key]


def test_metadata_aliases_and_unknown_are_explicitly_provisional():
    assert voice_for_speaker("Jack") == voice_for_speaker("ジャック")
    assert voice_for_speaker("上司") == voice_for_speaker(SUPERVISOR_NAME)
    assert voice_for_speaker("unknown") == voice_metadata()["default"]["preset"]
    assert "provisional" in voice_metadata()["default"]["status"]


@pytest.mark.parametrize("char", list(" 、。！？…「」（）\n\t🙂"))
def test_skip_whitespace_punctuation_symbols(char):
    assert not audible_character(char)
    audio, state = engine()
    audio.play_dialogue_reveal(page(text=char), 0, 1, 1)
    assert not state.played


def test_throttle_no_catchup_or_equal_priority_interruption():
    audio, state = engine()
    audio.play_dialogue_reveal(page(), 0, 1, 0.016)
    for i in range(1, 5):
        audio.play_dialogue_reveal(page(), i, i + 1, 0.016)
    assert len(state.played) == 1
    audio.play_dialogue_reveal(page(), 5, 6, 0.016)
    assert len(state.played) == 2
    state.busy = True
    audio.play_dialogue_reveal(page(), 0, 6, 8)
    assert len(state.played) == 2
    state.busy = False
    audio.play_dialogue_reveal(page(), 6, 6, 8)
    assert len(state.played) == 2
    audio.play_dialogue_reveal(page(), 0, 6, 8)
    assert len(state.played) == 3  # Slow frame still emits at most one tick.


def test_speaker_changes_use_latest_revealed_line_without_queued_voice():
    audio, state = engine()
    lines = page("male_elder", "あ") + page("female_child", "いう")
    audio.play_dialogue_reveal(lines, 0, 1, 0.07)
    audio.play_dialogue_reveal(lines, 1, 3, 0.07)
    assert state.played == [(3, VOICE_SLOTS["male_elder"]), (3, VOICE_SLOTS["female_child"])]


def test_higher_priority_se_wins_and_voice_never_interrupts_se():
    audio, state = engine()
    audio.play_dialogue_reveal(page(), 0, 1, 1)
    state.busy = True
    audio.play_events([event(1, "interaction_started", interaction_kind="inspect")])
    assert state.played[-1] == (3, audio._sound_slots["explore_inspect"])
    audio.play_dialogue_reveal(page(), 1, 2, 1)
    assert len(state.played) == 2
    audio.play_events([event(2, "enemy_captured")])
    assert state.played[-1] == (3, audio._sound_slots["capture_success"])


def test_mute_lifecycle_no_late_replay():
    audio, state = engine()
    audio.toggle_mute()
    audio.play_dialogue_reveal(page(), 0, 1, 1)
    audio.toggle_mute()
    audio.suspend_for_lifecycle()
    audio.play_dialogue_reveal(page(), 1, 2, 1)
    audio.resume_from_lifecycle()
    audio.play_dialogue_reveal(page(), 2, 2, 1)
    assert not state.played
    audio.play_dialogue_reveal(page(), 2, 3, 1)
    assert len(state.played) == 1


def test_real_office_natural_reveal_instant_reveal_pages_and_pause():
    app = make_office_dialogue_app()
    app.audio, state = engine()
    app.screen = AppScreen.OFFICE
    app.ui_text = SimpleNamespace(text_width=lambda text, style_name: len(text) * 32)
    assert app.office.ask_question("identity")
    playback = app.sync_office_dialogue_playback()
    app.update_office_dialogue_playback(0.07)
    assert len(state.played) == 1
    app.advance_office_dialogue_page()  # Fill immediately; no tick loop.
    app.update_office_dialogue_playback(1)
    assert len(state.played) == 1
    app.advance_office_dialogue_page()
    assert playback.revealed_chars == 0
    app.screen = AppScreen.PAUSE
    app.update_office_dialogue_playback(5)
    assert playback.revealed_chars == 0
    assert len(state.played) == 1
    app.screen = AppScreen.OFFICE
    app.update_office_dialogue_playback(0.07)
    assert len(state.played) == 2


@pytest.mark.parametrize("fps", [30, 60])
def test_frame_quantized_tick_spacing_stays_between_60_and_80_ms(fps):
    audio, state = engine()
    frames = []
    for frame in range(fps):
        before = len(state.played)
        audio.play_dialogue_reveal(page(), 0, 1, 1 / fps)
        if len(state.played) > before:
            frames.append(frame)
    assert all(0.06 <= (b - a) / fps <= 0.08 for a, b in zip(frames, frames[1:], strict=False))


@pytest.mark.parametrize("method", ["event", "preview"])
def test_quiet_voice_gain_restores_for_normal_se_without_touching_music(method):
    from test_office_music import RecordingPyxel

    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    player = RecordingPyxel()
    player.channels[3].gain = 0.2  # Preserve the configured baseline, not a hardcoded gain.
    audio.setup(player)
    music_gains = [channel.gain for channel in player.channels[:3]]
    audio.play_dialogue_reveal(page(), 0, 1, 1)
    assert player.channels[3].gain == pytest.approx(0.2 * OUTPUT_GAIN * VOICE_GAIN)
    assert 0 < VOICE_GAIN < 1
    assert [channel.gain for channel in player.channels[:3]] == music_gains
    if method == "event":
        audio.play_events([event(1, "interaction_started", interaction_kind="inspect")])
    else:
        audio.play_preview("action_denied")
    assert player.channels[3].gain == pytest.approx(0.2 * OUTPUT_GAIN)
    assert player.plays[-1][1] < 16
    before = len(player.plays)
    audio.play_dialogue_reveal(page(), 1, 2, 1)
    assert len(player.plays) == before
    assert player.channels[3].gain == pytest.approx(0.2 * OUTPUT_GAIN)
    player.stop(3)
    audio.play_dialogue_reveal(page(), 2, 3, 1)
    assert player.channels[3].gain == pytest.approx(0.2 * OUTPUT_GAIN * VOICE_GAIN)


@pytest.mark.parametrize("method", ["toggle_mute", "suspend_for_lifecycle", "reset_event_history"])
def test_voice_gain_reset_stops_tick_and_preserves_bgm_gain(method):
    from test_office_music import RecordingPyxel

    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    player = RecordingPyxel()
    audio.setup(player)
    audio.play_dialogue_reveal(page(), 0, 1, 1)
    assert 3 in player.playing
    assert player.channels[3].gain == pytest.approx(0.125 * OUTPUT_GAIN * VOICE_GAIN)
    getattr(audio, method)()
    assert 3 not in player.playing
    assert player.channels[3].gain == pytest.approx(0.125 * OUTPUT_GAIN)
    assert all(ch.gain == 0.125 for ch in player.channels[:3])


@pytest.mark.parametrize("speaker,preset", [("ラメル", "female_adult"), ("イワマ", "male_elder")])
def test_authored_character_casting_is_explicit_and_sourced(speaker, preset):
    assert voice_for_speaker(speaker) == preset
    entry = voice_metadata()["speakers"][speaker]
    assert entry["source"] and entry["basis"]
    assert entry["status"] == "supported by authored character description"


def test_future_unknown_character_uses_provisional_fallback():
    assert voice_for_speaker("future_unknown_speaker") == voice_metadata()["default"]["preset"]
    assert "provisional" in voice_metadata()["default"]["status"]


CASTING = {
    "Jack": "male_adult",
    "エトウ": "male_elder",
    "ヒューズ": "female_adult",
    "ミナ": "female_adult",
    "グロウ": "male_elder",
    "ラメル": "female_adult",
    "旅の勇者": "male_adult",
    "タカナシ": "female_adult",
    "サガン": "male_adult",
    "ヨアケ": "female_adult",
    "メリル": "female_elder",
    "ウラ": "female_adult",
    "ミズノ": "male_adult",
    "モリス": "male_child",
    "ルビィ": "female_child",
    "フジ": "male_elder",
    "ユメサキ": "female_adult",
    "ミヤノ": "female_adult",
    "イワマ": "male_elder",
}


@pytest.mark.parametrize("speaker,preset", CASTING.items())
def test_all_office_character_profiles_reach_the_correct_sound_slot(speaker, preset):
    assert voice_for_speaker(speaker) == preset
    metadata = voice_metadata()["speakers"][speaker]
    assert metadata["portrait_asset"] and metadata["basis"]
    audio, state = engine()
    audio.play_dialogue_reveal((OfficeDialogueLine("こんにちは", True, speaker=speaker),), 0, 5, 1)
    assert state.played == [(3, VOICE_SLOTS[preset])]


def test_visual_casting_covers_six_groups_and_legacy_aliases():
    assert set(CASTING.values()) == set(VOICE_SHAPES)
    assert set(voice_metadata()["speakers"]) == set(CASTING)
    for alias, name in voice_metadata()["aliases"].items():
        assert name in CASTING
        assert voice_for_speaker(alias) == CASTING[name]
    assert "middle-aged" in voice_metadata()["age_groups"]["elder"]


def test_report_label_is_silent_not_an_invented_character_voice():
    assert voice_for_speaker("確認記録") is None
    audio, state = engine()
    audio.play_dialogue_reveal(
        (OfficeDialogueLine("確認しました", False, speaker="確認記録"),), 0, 6, 1
    )
    assert not state.played
