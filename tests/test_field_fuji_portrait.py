from types import SimpleNamespace

import pytest

from drift_with_me.app import FieldConversation
from drift_with_me.week4 import FUJI_ID
from drift_with_me.week_cycle import WorkWeek
from test_office_jack_portrait import make_app
from test_week4 import app4, read, roundtrip


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_knee_portrait_uniform_scale_stays_clear_of_text_and_controls(profile):
    app, calls = make_app(profile)
    frame = SimpleNamespace(image="fuji", u=0, v=0, width=100, height=216)
    app.sprite_assets = SimpleNamespace(
        get=lambda key: SimpleNamespace(frame=lambda: frame, definition=SimpleNamespace(colkey=8))
    )
    app.draw_field_fuji_portrait()
    args, kwargs = calls[0]
    scale = kwargs["scale"]
    left = args[0] + frame.width * (1 - scale) / 2
    top = args[1] + frame.height * (1 - scale) / 2
    text = app.office_rect(50, 154, 306, 48)
    controls = app.office_rect(356, 204, 96, 16)
    assert left > text.x + text.width
    assert top >= 0
    assert top + frame.height * scale < controls.y
    assert left + frame.width * scale <= app.runtime.screen_width
    assert (
        left + frame.width * scale
        <= app.office_rect(40, 126, 432, 100).x + app.office_rect(40, 126, 432, 100).width
    )
    assert kwargs["colkey"] == 8


@pytest.mark.parametrize(
    ("target", "week", "expected"),
    [
        (FUJI_ID, WorkWeek(6, 4), True),
        ("jun_w4_north", WorkWeek(6, 4), False),
        (FUJI_ID, WorkWeek(6, 3), False),
    ],
)
def test_only_fuji_map_conversation_draws_knee_portrait(target, week, expected):
    app, _ = make_app()
    app.work_week = week
    app.field_conversation = FieldConversation(target, (("フジ", "ああ"),), 0)
    portraits, widths, layers = [], [], []
    app.draw_panel_frame = lambda *a, **k: layers.append("panel")
    app.draw_office_text_in_rect = lambda *a, **k: layers.append("text")
    app.draw_office_wrapped_lines = lambda rect, *a: widths.append(rect.width)

    def draw_portrait():
        portraits.append(True)
        layers.append("portrait")

    app.draw_field_fuji_portrait = draw_portrait
    app.office.plant_progress = SimpleNamespace(instructed=False, collected=set())
    app.draw_field_conversation()
    assert bool(portraits) == expected
    assert widths == [app.office_rect(0, 0, 306 if expected else 400, 48).width]
    assert layers[:2] == (["portrait", "panel"] if expected else ["panel", "text"])
    assert layers[-1] == "text"
    app.field_conversation = None
    app.draw_field_conversation()
    assert len(portraits) == int(expected)


def test_fuji_dialogue_save_resume_keeps_partial_handover_pending_until_acknowledged():
    from test_field_visit import inspect

    app = app4()
    read(app, FUJI_ID)
    read(app, "jun_w4_north")
    inspect(app, FUJI_ID)
    assert app.advance_field_conversation()
    progress = roundtrip(app)
    assert progress.carried == {"jun_w4_north"} and not progress.delivered
    # Restored conversation is reconstructed from existing progress, not visual state.
    app.model.cancel_interaction()
    app.field_conversation = None
    read(app, FUJI_ID)
    assert app.office.plant_progress.delivered == {"jun_w4_north"}
