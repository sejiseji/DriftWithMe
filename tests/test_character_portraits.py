from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.app import FieldConversation
from test_office_jack_portrait import make_app
from test_week_debug_safety import debug_app, records  # noqa: F401


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
@pytest.mark.parametrize("npc", ["ユメサキ", "ミヤノ"])
def test_speaker_switch_restores_and_clears_portrait(profile, npc):
    app, calls = make_app(profile)
    app.office.plant_progress = SimpleNamespace(instructed=False, collected=set())
    requested, colors, layers = [], [], []
    frame = SimpleNamespace(image="portrait", u=0, v=0, width=100, height=216)
    app.sprite_assets = SimpleNamespace(
        get=lambda key: (
            requested.append(key)
            or SimpleNamespace(frame=lambda: frame, definition=SimpleNamespace(colkey=8))
        )
    )
    app.draw_panel_frame = lambda *a, **k: layers.append("panel")
    app.draw_office_text_in_rect = lambda *a, **k: None
    app.draw_office_wrapped_lines = lambda rect, text, color: colors.append(color)
    conversation = FieldConversation(
        "portrait_preview",
        ((npc, "確認"), ("ジャック", "切替"), ("ヒューズ", "切替"), (npc, "復帰")),
        target_speaker=npc,
    )
    for i in range(4):
        conversation.index = i
        app.draw_field_conversation(conversation)
    assert requested == [("yumesaki" if npc == "ユメサキ" else "miyano") + "_map_knees"] * 2
    assert colors == [10, 7, 7, 10]
    assert len(calls) == 2
    args, kwargs = calls[0]
    rect = app.office_rect(360, 6, 132, 196)
    assert kwargs["scale"] == min(rect.width / 100, rect.height / 216)
    assert kwargs["colkey"] == 8
    app.field_conversation = None
    app.draw_field_conversation()
    assert len(calls) == 2


def test_preview_forward_close_reenter_preserves_normal_slots(records):  # noqa: F811
    before = deepcopy(records.items)
    app = debug_app(records)
    assert app.start_portrait_preview("ユメサキ")
    app.mouse_pressed_in = lambda rect: rect == app.office_rect(356, 204, 96, 16)
    for i in range(1, 4):
        app.update_portrait_preview()
        assert app.portrait_preview.index == i
    app.update_portrait_preview()
    assert app.portrait_preview is None
    assert app.start_portrait_preview("ミヤノ")
    app.mouse_pressed_in = lambda rect: rect == app.portrait_preview_rects()["close"]
    app.update_portrait_preview()
    assert app.portrait_preview is None
    assert app.start_portrait_preview("ユメサキ")
    assert app.portrait_preview.index == 0
    assert not app.checkpoint_progress()
    app.return_from_week_debug()
    assert app.portrait_preview is None
    assert records.items == before


def test_preview_is_inaccessible_in_normal_play(records):  # noqa: F811
    app = debug_app(records, enabled=False)
    assert not app.start_portrait_preview("ユメサキ")
    assert app.portrait_preview is None
