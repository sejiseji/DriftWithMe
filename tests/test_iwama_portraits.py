"""Iwama uses existing counter expressions and fits every office profile."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.app import OFFICE_PORTRAIT_SMILE_IDS
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek
from test_july_week4 import app4, close_case
from test_office_jack_portrait import make_app


def test_dedicated_iwama_assets_preserve_body_and_alpha_between_expressions():
    assets = Path(__file__).resolve().parents[1] / "src/drift_with_me/assets"
    definitions = {
        d["id"]: d for d in json.loads((assets / "jack_sprite.json").read_text())["source_assets"]
    }
    frames = []
    for expression in ("normal", "smug"):
        asset = definitions[f"iwama_bust_{expression}"]
        assert (asset["hex_width"], asset["hex_height"], asset["colkey"]) == (116, 116, 8)
        rows = (assets / asset["frames"][0]["path"]).read_text().splitlines()
        assert len(rows) == 116 and all(len(row) == 116 for row in rows)
        assert (
            hashlib.sha256(bytes(int(c, 16) for row in rows for c in row)).hexdigest()
            == asset["source_hash"]
        )
        frames.append(rows)
    changed = 0
    for y in range(116):
        for x in range(116):
            a, b = (rows[y][x] for rows in frames)
            assert (a == "8") == (b == "8")
            if not (28 <= x < 70 and 20 <= y < 58):
                assert a == b
            changed += a != b
    assert changed > 0
    assert OFFICE_PORTRAIT_SMILE_IDS["iwama_bust_normal"] == "iwama_bust_smug"


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_iwama_existing_expression_mapping_and_frame_fit(profile):
    app, calls = make_app(profile)
    app.pyxel.rect = lambda *args: None
    app.pyxel.rectb = lambda *args: None
    frame = SimpleNamespace(image="iwama", u=0, v=0, width=116, height=116)
    requested = []

    def get(key):
        requested.append(key)
        return SimpleNamespace(frame=lambda: frame, definition=SimpleNamespace(colkey=8))

    app.sprite_assets = SimpleNamespace(get=get)
    rect = app.office_visitor_portrait_rect()
    for smile in (False, True):
        calls.clear()
        app.draw_office_portrait(rect, "iwama_bust_normal", smile=smile)
        assert requested[-1] == ("iwama_bust_smug" if smile else "iwama_bust_normal")
        args, kwargs = calls[0]
        scale = kwargs["scale"]
        left, top = args[0] + 116 * (1 - scale) / 2, args[1] + 116 * (1 - scale) / 2
        assert left >= rect.x - 1 and left + 116 * scale <= rect.x + rect.width + 1
        assert top >= rect.y - 1 and top + 116 * scale <= rect.y + rect.height + 1
        assert kwargs["colkey"] == 8


def test_existing_week4_save_rederives_iwama_without_new_portrait_state():
    app, _ = app4()
    close_case(app)
    assert app.advance_week4_case()
    close_case(app)
    encoded = encode(snapshot(app))
    restored = decode(encoded)[1][WorkWeek(7, 4)]
    assert restored.current_case.visitor.name == "イワマ"
    assert restored.current_case.visitor.portrait_id == "iwama_bust_normal"
    assert restored.current_session.state == app.office.current_session.state
    assert "portrait" not in encoded and "expression" not in encoded
