import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.app import FUSE_OFFICE_PORTRAIT_IDS
from drift_with_me.office import DialogueLine
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek, load_week_office
from test_june_portrait_identity import june_app
from test_office_supervisor import app_for, finish
from test_week2_loop import resolve

ROOT = Path(__file__).resolve().parents[1]


def siblings_app():
    app = june_app(4)
    resolve(app.office)
    assert app.office.advance_case()
    finish(app.office)
    assert app.office.ask_question("talk")
    return app


def test_authored_turns_restore_expression_without_changing_dialogue_or_save_shape():
    app = siblings_app()
    seen = []
    while True:
        office = app.office
        session = office.current_session
        active = office.active_dialogue_lines()
        if active and active[-1].speaker == "ヒューズ":
            expected = "thinking" if "傘探し係" in active[-1].text else "smile"
            assert app.office_current_visitor_identity(office.current_case) == (
                "fuse_matte",
                "ヒューズ",
            )
            assert app.office_fuse_portrait_expression() == expected
            before = deepcopy(session)
            assert not office.ask_question("talk")  # Repeated input cannot restart the turn.
            assert session == before
            saved = snapshot(app)
            week, offices, *_ = decode(encode(saved))
            app.office = offices[week]
            app.week_office_history = offices
            restored = app.office.current_session
            assert restored.dialogue == session.dialogue
            assert restored.pending_dialogue_steps == session.pending_dialogue_steps
            assert restored.active_dialogue_line_count == session.active_dialogue_line_count
            assert restored.pending_question_id == session.pending_question_id
            assert restored.completed_dialogue_turn_ids == session.completed_dialogue_turn_ids
            assert app.office_fuse_portrait_expression() == expected
            seen.append(expected)
        if not app.office.advance_dialogue_step():
            break
    app.office.complete_pending_question()
    assert seen == ["thinking", "smile"]
    assert app.office.classify(app.office.current_case.expected_classification)
    finish(app.office)
    assert app.office.advance_case()
    assert app.office_current_visitor_identity(app.office.current_case) == ("fuji_matte", "フジ")
    assert app.office_fuse_portrait_expression() == "normal"


def test_fuse_holds_across_jack_and_returns_to_current_visitor_with_default_fallback():
    app = siblings_app()
    session = app.office.current_session
    for speaker, text, identity, expression in [
        ("ヒューズ", "ふふ。タコのお仕事、好評で何より", "fuse_matte", "smile"),
        ("ジャック", "確認", "fuse_matte", "smile"),
        ("ヒューズ", "未指定の会話", "fuse_matte", "normal"),
        ("ルビィ", "確認", "ruby_matte", "normal"),
        ("モリス", "確認", "morris_matte", "normal"),
    ]:
        session.dialogue.append(DialogueLine(speaker, text))
        assert app.office_current_visitor_identity(app.office.current_case)[0] == identity
        assert app.office_fuse_portrait_expression() == expression
    saved = deepcopy(session)
    app.office_consultation = None
    assert not app.begin_office_consultation()  # No authored advice in week four.
    app.end_office_consultation()
    assert session == saved


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
@pytest.mark.parametrize("expression", sorted(FUSE_OFFICE_PORTRAIT_IDS))
def test_five_expressions_draw_aspect_preserved_with_entire_hover_cycle_inside_frame(
    profile, expression
):
    app = app_for(load_week_office(WorkWeek(6, 4)), profile)
    app.office_fuse_portrait_expression = lambda: expression
    calls = []
    assets = {}
    for name in FUSE_OFFICE_PORTRAIT_IDS.values():
        frame = SimpleNamespace(width=116, height=116, image=name, u=0, v=0)
        assets[name] = SimpleNamespace(
            frame=lambda frame=frame: frame, definition=SimpleNamespace(colkey=2)
        )
    app.sprite_assets = SimpleNamespace(get=assets.get)
    app.pyxel = SimpleNamespace(
        rect=lambda *a: None, rectb=lambda *a: None, blt=lambda *a, **kw: calls.append((a, kw))
    )
    rect = app.office_visitor_portrait_rect()
    for frame in range(145):
        app.presentation_time = frame / 30
        app.draw_office_portrait(rect, "fuse_matte", smile=True)
        args, kw = calls[-1]
        assert args[2] == FUSE_OFFICE_PORTRAIT_IDS[expression]
        assert kw["colkey"] == 2
        scale = kw["scale"]
        assert math.isclose(scale, min(int(rect.width) / 116, int(rect.height) / 116))
        left, top = args[0] + 58 * (1 - scale), args[1] + 58 * (1 - scale)
        assert rect.x - 0.51 <= left and left + 116 * scale <= rect.x + rect.width + 0.51
        assert rect.y - 0.51 <= top and top + 116 * scale <= rect.y + rect.height + 0.51
    assert calls[0] == calls[-1]
    assert max(a[1] for a, _ in calls) - min(a[1] for a, _ in calls) == 4
    # Missing optional expression falls back to the loaded normal rather than blank/synthetic art.
    if expression != "normal":
        del assets[FUSE_OFFICE_PORTRAIT_IDS[expression]]
        app.draw_office_portrait(rect, "fuse_matte")
        assert calls[-1][0][2] == "fuse_matte"


def test_approved_cleaned_pixels_hashes_palette_and_map_fuse_registration():
    manifest = json.loads((ROOT / "src/drift_with_me/assets/jack_sprite.json").read_text())
    base = None
    for asset_id in FUSE_OFFICE_PORTRAIT_IDS.values():
        asset = next(a for a in manifest["source_assets"] if a["id"] == asset_id)
        rows = (
            (ROOT / "src/drift_with_me/assets" / asset["frames"][0]["path"])
            .read_text()
            .splitlines()
        )
        assert len(rows) == 116 and all(len(row) == 116 for row in rows)
        pixels = bytes(int(c, 16) for c in "".join(rows))
        assert hashlib.sha256(pixels).hexdigest() == asset["source_hash"]
        assert set(pixels) == {0, 1, 2, 5, 6, 10, 12}
        assert asset["colkey"] == 2  # Black 0 is never the transparency key.
        assert pixels[50 * 116 + 50] == 0
        if base is None:
            base = pixels
        else:
            assert all(a == b for a, b in zip(base, pixels, strict=True) if a != 10 and b != 10)
    assert manifest["assets"]["fuse_front_neutral_48"]["frames"][0]["source_hash"] == (
        "a9c9661505e49fbf9d42a4e2f066c2a668b68677d844eb8eaa8000620460189c"
    )
