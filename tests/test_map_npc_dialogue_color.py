from types import SimpleNamespace

import pytest

from drift_with_me.app import FieldConversation
from drift_with_me.week4 import FUJI_ID
from drift_with_me.week_cycle import WorkWeek
from test_field_visit import inspect
from test_office_jack_portrait import make_app
from test_week4 import app4, roundtrip


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_body_color_follows_explicit_target_speaker_on_each_page(profile):
    app, _ = make_app(profile)
    app.work_week = WorkWeek(6, 4)
    colors = []
    app.draw_panel_frame = lambda *a, **k: None
    app.draw_office_text_in_rect = lambda *a, **k: None
    app.draw_office_wrapped_lines = lambda rect, text, color: colors.append(color)
    app.draw_field_fuji_portrait = lambda: None
    conversation = FieldConversation(
        FUJI_ID,
        (
            ("フジ", "助かる。"),
            ("ジャック", "フジさんに渡します。"),
            ("ヒューズ", "フジさん、お待たせしました。"),
            ("フジ", "ありがとう。"),
            ("", "フジの説明を確認する。"),
        ),
        target_speaker="フジ",
    )
    app.field_conversation = conversation
    for index in range(len(conversation.lines)):
        conversation.index = index
        app.draw_field_conversation()
    assert colors == [10, 7, 7, 10, 7]
    app.field_conversation = None
    app.draw_field_conversation()
    assert len(colors) == 5
    # A description mentioning an NPC, or an observation without metadata, stays white.
    app.field_conversation = FieldConversation("observation_post", (("フジ", "同じ名前"),))
    app.draw_field_conversation()
    assert colors[-1] == 7
    # Future NPCs can declare their speaker without a renderer-specific name rule.
    app.field_conversation = FieldConversation(
        "future_npc", (("別の住人", "こんにちは"),), target_speaker="別の住人"
    )
    app.draw_field_conversation()
    assert colors[-1] == 10
    # First-sight conversations have no target speaker metadata.
    app.field_conversation = SimpleNamespace(
        target_id="normal_urchin", lines=(("ヒューズ", "あそこを見て"),), index=0, kind="normal"
    )
    app.draw_field_conversation()
    assert colors[-1] == 7


def test_resumed_fuji_conversation_reconstructs_speaker_metadata():
    app = app4()
    inspect(app, FUJI_ID)
    assert app.field_conversation.target_speaker == "フジ"
    assert app.advance_field_conversation()
    assert app.field_conversation.lines[app.field_conversation.index][0] == "フジ"
    roundtrip(app)
    app.model.cancel_interaction()
    app.field_conversation = None
    inspect(app, FUJI_ID)
    assert app.field_conversation.index == 1
    assert app.field_conversation.target_speaker == "フジ"
    while app.field_conversation:
        app.advance_field_conversation()
    inspect(app, "jun_w4_north")
    assert app.field_conversation.target_speaker is None
