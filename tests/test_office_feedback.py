"""Accepted office UI actions and the shared native audio channel."""

from types import SimpleNamespace

import pytest

from drift_with_me.audio import OFFICE_SOUND_SHAPES, OFFICE_SOUND_SLOTS, AudioEngine
from drift_with_me.audio_levels import OUTPUT_GAIN
from drift_with_me.dialogue_voice import VOICE_SLOTS
from drift_with_me.music import MusicContext
from drift_with_me.office import CLASSIFICATION_ORDER, CaseState
from test_dialogue_voice import page
from test_office import ask_and_complete, drain_office_dialogue, make_office_dialogue_app
from test_office_music import RecordingPyxel


def app_with_feedback():
    app = make_office_dialogue_app()
    cues = []
    app.audio = SimpleNamespace(play_office_feedback=cues.append)
    return app, cues


def test_question_acceptance_repeat_pending_and_answer_reference():
    app, cues = app_with_feedback()
    question = app.office.current_case.questions[0]
    assert app.ask_or_select_office_question(question)
    assert not app.ask_or_select_office_question(question)
    assert cues == ["question"]
    drain_office_dialogue(app.office)
    assert app.ask_or_select_office_question(question)
    assert app.office_answer_question_id == question.question_id
    assert cues == ["question", "question"]
    app.office.current_index = len(app.office.cases)
    assert not app.ask_or_select_office_question(question)
    assert len(cues) == 2


def test_classification_verdict_only_and_no_stale_verdict_after_disabled_input():
    app, cues = app_with_feedback()
    case = app.office.current_case
    wrong = next(
        choice for choice in CLASSIFICATION_ORDER if choice != case.expected_classification
    )
    assert not app.classify_office_case(wrong)
    assert cues == ["incorrect"]
    assert not app.classify_office_case(case.expected_classification)  # Questions missing.
    assert app.office.last_classification_result is None
    assert cues == ["incorrect"]
    for question in case.questions:
        ask_and_complete(app.office, question.question_id)
    assert app.classify_office_case(case.expected_classification)
    assert cues == ["incorrect", "correct"]
    assert not app.classify_office_case(case.expected_classification)
    assert cues == ["incorrect", "correct"]
    app.office.current_session.state = CaseState.HEARING
    app.office.current_session.pending_question_id = case.questions[0].question_id
    assert not app.classify_office_case(wrong)
    assert len(cues) == 2


def test_subclass_prerequisite_rejection_cannot_reuse_previous_verdict():
    app, cues = app_with_feedback()
    app.office.last_classification_result = False
    app.office.classify = lambda choice: False  # Week3 precondition can return before super.
    assert not app.classify_office_case(CLASSIFICATION_ORDER[0])
    assert not cues


@pytest.mark.parametrize("cue", OFFICE_SOUND_SHAPES)
def test_setup_gain_slots_and_bgm_isolation(cue):
    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    player = RecordingPyxel()
    audio.setup(player)
    assert not set(OFFICE_SOUND_SLOTS.values()) & set(VOICE_SLOTS.values())
    assert set(OFFICE_SOUND_SLOTS.values()) == {22, 23, 24}
    audio.music.update(MusicContext(True, ambient="office"), 2, muted=False, suspended=False)
    bgm = {ch: player.playing[ch] for ch in (0, 1)}
    gains = [player.channels[ch].gain for ch in (0, 1, 2)]
    audio.play_dialogue_reveal(page(), 0, 1, 1)
    audio.play_office_feedback(cue)
    assert player.plays[-1] == (3, OFFICE_SOUND_SLOTS[cue], {})
    assert player.definitions[OFFICE_SOUND_SLOTS[cue]] == OFFICE_SOUND_SHAPES[cue]
    assert player.channels[3].gain == pytest.approx(0.125 * OUTPUT_GAIN * 0.5)
    assert {ch: player.playing[ch] for ch in (0, 1)} == bgm
    assert [player.channels[ch].gain for ch in (0, 1, 2)] == gains
    count = len(player.plays)
    audio.play_office_feedback(cue)
    audio.play_dialogue_reveal(page(), 1, 2, 1)
    assert len(player.plays) == count
    player.playing.pop(3)
    audio.play_preview("action_denied")
    assert player.channels[3].gain == pytest.approx(0.125 * OUTPUT_GAIN)


def test_verdict_preempts_question_but_question_never_truncates_verdict():
    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    player = RecordingPyxel()
    audio.setup(player)
    audio.play_office_feedback("question")
    audio.play_office_feedback("incorrect")
    audio.play_office_feedback("correct")
    audio.play_office_feedback("question")
    assert [slot for _, slot, _ in player.plays] == [22, 24, 23]


def test_mute_lifecycle_and_reset_have_no_feedback_queue():
    audio = AudioEngine({"audio": {"enabled_by_default": True}})
    player = RecordingPyxel()
    audio.setup(player)
    audio.toggle_mute()
    audio.play_office_feedback("question")
    audio.toggle_mute()
    audio.suspend_for_lifecycle()
    audio.play_office_feedback("incorrect")
    audio.resume_from_lifecycle()
    audio.reset_event_history()
    assert not player.plays
    audio.play_office_feedback("correct")
    assert player.plays == [(3, 23, {})]


@pytest.mark.parametrize("action", ["question", "classification"])
@pytest.mark.parametrize("input_kind", ["keyboard", "pointer"])
def test_ui_routes_both_input_methods_once(action, input_kind):
    app, cues = app_with_feedback()
    app.update_office_shared_controls = lambda dt: False
    app.week2_active = lambda: False
    app.clear_world_input_latches = lambda: None
    app.update_office_dialogue_playback = lambda dt: None
    app.office_dialogue_requires_advance = lambda: False
    app.office_focus = "questions" if action == "question" else "classifications"
    app.office_question_index = 0
    case = app.office.current_case
    wrong_index = next(
        i for i, choice in enumerate(CLASSIFICATION_ORDER) if choice != case.expected_classification
    )
    app.office_classification_index = wrong_index
    target = (
        app.office_question_rect(0, len(case.questions))
        if action == "question"
        else app.office_classification_rect(wrong_index)
    )
    app.pointer_snapshot = SimpleNamespace(x=target.x + 2, y=target.y + 2)
    app.mouse_pressed_in = lambda rect: input_kind == "pointer" and rect == target
    app.key_pressed = lambda *keys: input_kind == "keyboard" and "KEY_RETURN" in keys
    app.update_office_screen(0)
    assert cues == ["question" if action == "question" else "incorrect"]
