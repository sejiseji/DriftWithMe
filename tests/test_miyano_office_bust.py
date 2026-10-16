"""Miyano counter bust is independent of map art and saved speaker/emotion state."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.save_state import decode, encode, snapshot
from test_field_visit import drain
from test_office_jack_portrait import make_app
from test_yumesaki_office_portraits import identity, researcher


def test_saved_miyano_turn_restores_then_hands_back_to_yumesaki():
    app = researcher()
    drain(app.office)
    app.office.ask_question("talk")
    while not any(
        line.speaker == "ミヤノ" and "植物と同じ" in line.text
        for line in app.office.active_dialogue_lines()
    ):
        assert app.office.advance_dialogue_step()
    assert identity(app) == ("miyano_bust_normal", "ミヤノ")
    before = snapshot(app)
    app.saved_progress = decode(encode(before))
    app.start_game()
    assert snapshot(app) == before
    assert identity(app) == ("miyano_bust_normal", "ミヤノ")
    assert app.office.advance_dialogue_step()
    assert identity(app) == ("yumesaki_bust_worried", "ユメサキ")
    assert app.office.advance_dialogue_step()
    assert identity(app) == ("yumesaki_bust_normal", "ユメサキ")


def test_miyano_bust_is_counter_only_with_tan_teal_and_lip_palette():
    assets = Path(__file__).resolve().parents[1] / "src/drift_with_me/assets"
    m = json.loads((assets / "jack_sprite.json").read_text())
    item = next(i for i in m["source_assets"] if i["id"] == "miyano_bust_normal")
    assert (item["hex_width"], item["hex_height"], item["colkey"]) == (116, 116, 8)
    assert item["ui_role"] == "office_visitor_portrait"
    rows = (assets / item["frames"][0]["path"]).read_text().splitlines()
    pixels = bytes(int(c, 16) for row in rows for c in row)
    assert hashlib.sha256(pixels).hexdigest() == item["source_hash"]
    assert {0, 2, 3, 4, 7, 9, 10, 13} <= set(pixels)
    assert (
        next(i for i in m["source_assets"] if i["id"] == "miyano_map_knees")["ui_role"]
        == "field_conversation_portrait"
    )


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_miyano_bust_fits_existing_counter_frame(profile):
    app, calls = make_app(profile)
    app.pyxel.rect = lambda *args: None
    app.pyxel.rectb = lambda *args: None
    frame = SimpleNamespace(image="miyano", u=0, v=0, width=116, height=116)
    app.sprite_assets = SimpleNamespace(
        get=lambda key: SimpleNamespace(frame=lambda: frame, definition=SimpleNamespace(colkey=8))
    )
    rect = app.office_visitor_portrait_rect()
    app.draw_office_portrait(rect, "miyano_bust_normal", smile=True)
    args, kwargs = calls[0]
    k = kwargs["scale"]
    left, top = args[0] + 116 * (1 - k) / 2, args[1] + 116 * (1 - k) / 2
    assert left >= rect.x - 1 and left + 116 * k <= rect.x + rect.width + 1
    assert top >= rect.y - 1 and top + 116 * k <= rect.y + rect.height + 1
    assert kwargs["colkey"] == 8
