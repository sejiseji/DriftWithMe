from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from drift_with_me.app import OFFICE_DIALOGUE_CHARS_PER_SEC, AppScreen
from drift_with_me.dialogue_voice import VOICE_SLOTS, voice_metadata
from drift_with_me.east_site import SITE_FACTS
from drift_with_me.field_transition import FieldTransition
from drift_with_me.field_visit import FieldConversation
from drift_with_me.week_cycle import WorkWeek
from test_combat_entry_audio import engine, event
from test_office_jack_portrait import make_app

LINES = (("ジャック", "ゆっくり見ていこう。"), ("ヒューズ", "ええ、足元には気をつけてね。"))
OWNERS = (
    "field_conversation",
    "first_sight_conversation",
    "flowerbed_dialogue",
    "week2_dialogue",
    "week3_dialogue",
    "week4_dialogue",
    "patrol_dialogue",
)


def setup(owner="field_conversation", lines=LINES):
    app, _ = make_app()
    app.screen = AppScreen.PLAY
    app.work_week = WorkWeek()
    conversation = FieldConversation("test", lines)
    setattr(app, owner, conversation)
    app.audio, audio = engine()
    app.key_pressed = lambda *names: False
    app.mouse_pressed_in = lambda rect: False
    return app, conversation, audio


@pytest.mark.parametrize("owner", OWNERS)
def test_all_field_owners_reveal_and_only_then_allow_scene_advance(owner):
    app, conversation, audio = setup(owner)
    assert not app.update_field_dialogue_playback(0.07)
    assert app.field_dialogue_playback.revealed_chars == pytest.approx(
        0.07 * OFFICE_DIALOGUE_CHARS_PER_SEC
    )
    assert audio.played == [(3, VOICE_SLOTS["male_adult"])]
    app.key_pressed = lambda *names: "KEY_RETURN" in names
    assert app.update_field_dialogue_playback(0.01)
    assert conversation.index == 0  # The owner has not saved, advanced or awarded anything.
    assert app.field_dialogue_playback.revealed_chars == len(LINES[0][1])
    assert len(audio.played) == 1
    assert not app.update_field_dialogue_playback(0.01)  # Now pass input to the existing owner.
    conversation.index += 1
    app.key_pressed = lambda *names: False
    app.update_field_dialogue_playback(0.07)
    assert audio.played[-1] == (3, VOICE_SLOTS["female_adult"])
    assert app.field_dialogue_playback.revealed_chars < len(LINES[1][1])


def test_full_frame_intercepts_reveal_before_any_dispatch_or_save(monkeypatch):
    app, conversation, audio = setup()
    app.lifecycle_update_blocked = lambda: False
    app.consume_elapsed = lambda: 0.01
    app.sync_office_save_notice = lambda: None
    app.frame = 0
    app.read_pointer_snapshot = lambda: SimpleNamespace(pressed=False, down=False)
    app.key_pressed = lambda *names: "KEY_RETURN" in names
    owner = Mock(return_value=True)
    monkeypatch.setattr("drift_with_me.screen_flow.dispatch_early", owner)
    app.update_game_frame()
    owner.assert_not_called()
    assert conversation.index == 0 and not audio.played
    app.update_game_frame()
    owner.assert_called_once_with(app, 0.01)


@pytest.mark.parametrize("key", ["KEY_ESCAPE", "KEY_X"])
def test_cancellation_is_never_consumed_as_reveal_all(key):
    app, conversation, _ = setup()
    conversation.target_id = next(iter(SITE_FACTS))
    app.key_pressed = lambda *names: key in names
    assert not app.update_field_dialogue_playback(0)
    assert app.field_dialogue_playback.revealed_chars == 0
    assert conversation.index == 0


@pytest.mark.parametrize("owner", ["field_conversation", "field_transition", "week2_dialogue"])
def test_cancel_pointer_is_not_stolen_by_overlapping_dialogue_panel(owner):
    app, conversation, _ = setup(owner)
    if owner == "field_transition":
        app.field_transition = conversation = FieldTransition("back", LINES, wait_release=False)
        target = app.field_travel_cancel_rect()
    elif owner == "week2_dialogue":
        conversation.target_id = "week2_return_choice"
        target = app.week2_return_choice_rects()[1]
    else:
        conversation.target_id = next(iter(SITE_FACTS))
        target = app.site_cancel_rect()
    x, y = target.x + 1, target.y + 1
    app.mouse_pressed_in = lambda rect: rect.contains(x, y)
    assert not app.update_field_dialogue_playback(0)
    assert app.field_dialogue_playback.revealed_chars == 0


def test_wait_release_prevents_held_opening_input_from_skipping():
    app, conversation, audio = setup("first_sight_conversation")
    conversation.wait_release = True
    app.key_pressed = lambda *names: "KEY_RETURN" in names
    assert not app.update_field_dialogue_playback(0.01)
    assert app.field_dialogue_playback.revealed_chars < len(LINES[0][1])
    conversation.wait_release = False
    assert app.update_field_dialogue_playback(0.01)
    assert not audio.played


def test_pause_and_lifecycle_freeze_without_catchup_then_close_and_reopen_reset():
    app, conversation, audio = setup()
    app.update_field_dialogue_playback(0.07)
    before = app.field_dialogue_playback.revealed_chars
    app.screen = AppScreen.PAUSE
    app.update_field_dialogue_playback(100)
    app.screen = AppScreen.PLAY
    app._lifecycle_wait_release = True
    app.update_field_dialogue_playback(100)
    assert app.field_dialogue_playback.revealed_chars == before
    assert len(audio.played) == 1
    app._lifecycle_wait_release = False
    app.update_field_dialogue_playback(0.07)
    assert len(audio.played) == 2
    app.field_conversation = None
    app.update_field_dialogue_playback(1)
    assert app.field_dialogue_playback is None
    app.field_conversation = FieldConversation("test", LINES)
    app.update_field_dialogue_playback(0)
    assert app.field_dialogue_playback.revealed_chars == 0


@pytest.mark.parametrize("flag", ["week_debug_menu_open", "flowerbed_editor", "park_preview_week"])
def test_hidden_field_dialogue_does_not_reveal_or_play(flag):
    app, _, audio = setup()
    setattr(app, flag, True)
    app.update_field_dialogue_playback(10)
    assert not audio.played
    assert getattr(app, "field_dialogue_playback", None) is None


def test_transitions_reveal_only_in_dialogue_phase_and_keep_existing_advance():
    app, _, audio = setup()
    app.field_conversation = None
    app.field_transition = transition = FieldTransition("out", LINES, wait_release=False)
    app.update_field_dialogue_playback(1)
    assert not audio.played
    transition.phase = "dialogue"
    app.update_field_dialogue_playback(0.07)
    assert len(audio.played) == 1
    app.key_pressed = lambda *names: "KEY_RETURN" in names
    assert app.update_field_dialogue_playback(0)
    assert transition.index == 0
    assert not app.update_field_dialogue_playback(0)
    transition.advance()
    assert transition.index == 1


def test_reconstructed_july_story_and_august_sighting_share_stable_presentation():
    app, _, audio = setup()
    app.field_conversation = None
    app.work_week = WorkWeek(7, 1)
    app.office.july_progress = SimpleNamespace(stage="after_clear", scene_index=0)
    app.update_field_dialogue_playback(0.07)
    before = app.field_dialogue_playback.revealed_chars
    _, rebuilt = app.active_field_dialogue()
    assert app.sync_field_dialogue_playback(rebuilt).revealed_chars == before
    app.work_week = WorkWeek(8, 1)
    from drift_with_me.august_sightings import LINES as AUGUST_LINES

    site = next(iter(AUGUST_LINES))
    app.office.august_progress = SimpleNamespace(pending_sighting=site, sighting_index=0)
    app.august_crossing = (site, 0.1)
    app.update_field_dialogue_playback(1)
    assert len(audio.played) == 1
    app.august_crossing = None
    app.update_field_dialogue_playback(0.07)
    assert len(audio.played) == 2
    app.key_pressed = lambda *names: "KEY_SPACE" in names
    assert app.update_field_dialogue_playback(0)
    assert app.office.august_progress.sighting_index == 0


def test_office_report_keeps_its_existing_playback_not_field_voice():
    app, _, audio = setup("week3_dialogue")
    app.screen = AppScreen.OFFICE
    app.update_field_dialogue_playback(10)
    assert not audio.played
    app.week2_dialogue = FieldConversation("week2_report", LINES)
    app.update_field_dialogue_playback(0.07)
    assert len(audio.played) == 1


@pytest.mark.parametrize(
    "speaker,text", [("ヒューズ", " 、。！？…"), ("", "静かな説明"), ("確認記録", "記録しました")]
)
def test_punctuation_and_noncharacter_text_are_silent(speaker, text):
    app, _, audio = setup(lines=((speaker, text),))
    app.update_field_dialogue_playback(1)
    assert not audio.played


def test_muted_text_still_reveals_without_late_tick():
    app, _, audio = setup()
    app.audio.toggle_mute()
    app.update_field_dialogue_playback(1)
    app.audio.toggle_mute()
    app.update_field_dialogue_playback(1)
    assert not audio.played


def test_voice_reset_cannot_interrupt_ordinary_gameplay_effect():
    app, _, audio = setup()
    app.audio.play_events([event(1, "enemy_captured")])
    before = list(audio.stopped)
    app.update_field_dialogue_playback(0)
    app.audio.stop_dialogue_reveal()
    assert audio.stopped == before


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_draw_is_incremental_stable_wrapped_and_does_not_advance_or_sound(profile):
    app, _ = make_app(profile)
    app.screen = AppScreen.PLAY
    app.work_week = WorkWeek()
    app.audio, audio = engine()
    app.field_conversation = conversation = FieldConversation(
        "test", (("ヒューズ", "あいうえおかきくけこ。さしすせそ。"),)
    )
    rect = app.office_rect(50, 154, 60, 48)
    app.key_pressed = lambda *names: False
    app.mouse_pressed_in = lambda r: False
    app.update_field_dialogue_playback(0.07)
    rendered = []
    app.draw_office_wrapped_lines = lambda r, lines, color: rendered.append(lines)
    app.draw_field_dialogue_text(rect, conversation, 7)
    app.draw_field_dialogue_text(rect, conversation, 7)
    assert rendered[0] == rendered[1]
    assert len("".join(rendered[0])) == int(0.07 * OFFICE_DIALOGUE_CHARS_PER_SEC)
    assert len(audio.played) == 1
    assert conversation.index == 0
    app.field_dialogue_playback.revealed_chars = len(conversation.lines[0][1])
    app.draw_field_dialogue_text(rect, conversation, 7)
    assert "".join(rendered[-1]) == conversation.lines[0][1]
    assert all(
        final.startswith(part) for final, part in zip(rendered[-1], rendered[0], strict=True)
    )


def test_fuse_casting_is_now_explicit_young_adult_user_request():
    entry = voice_metadata()["speakers"]["ヒューズ"]
    assert entry["preset"] == "female_adult"
    assert entry["status"] == "user-requested young-adult feminine casting"


@pytest.mark.parametrize(
    "owner", ["field_conversation", "patrol_dialogue", "field_transition", "week2_dialogue"]
)
def test_no_invisible_cancel_rectangle_can_bypass_reveal(owner):
    app, conversation, _ = setup(owner)
    if owner == "field_transition":
        app.field_transition = conversation = FieldTransition("out", LINES, wait_release=False)
        conversation.phase = "dialogue"
        rect = app.field_travel_cancel_rect()
    else:
        if owner == "week2_dialogue":
            conversation.target_id = "week2_report"
        rect = app.site_cancel_rect()
    app.mouse_pressed_in = lambda area: area.contains(rect.x + 1, rect.y + 1)
    assert app.update_field_dialogue_playback(0)
    assert conversation.index == 0
    assert app.field_dialogue_playback.revealed_chars == len(LINES[0][1])
