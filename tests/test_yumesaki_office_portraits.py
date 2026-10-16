"""Counter portraits follow current pages; emotion adds no persistent state."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.yumesaki_portraits import YUMESAKI_PORTRAITS, yumesaki_office_portrait
from test_field_visit import drain
from test_july_week2 import app2
from test_office_jack_portrait import make_app


def researcher():
    app, _ = app2()
    app.office.current_index = 2
    app.office.begin_current_case()
    return app


def identity(app):
    return app.office_current_visitor_identity(app.office.current_case)


def test_current_pages_and_next_speaker_do_not_keep_expression():
    app = researcher()
    assert identity(app) == (YUMESAKI_PORTRAITS["normal"], "ユメサキ")
    drain(app.office)
    assert app.office.ask_question("talk")
    seen = set()
    for _ in range(12):
        playback = app.sync_office_dialogue_playback()
        for index, page in enumerate(playback.pages):
            playback.page_index = index
            speaker = page[0].speaker
            portrait, name = identity(app)
            if speaker == "ミヤノ":
                assert (portrait, name) == ("miyano_bust_normal", "ミヤノ")
            elif speaker == "ユメサキ":
                assert (portrait, name) == (YUMESAKI_PORTRAITS["worried"], "ユメサキ")
            else:
                assert portrait == YUMESAKI_PORTRAITS["normal"]
            seen.add(speaker)
        if not app.office.advance_dialogue_step():
            break
    assert seen == {"ミヤノ", "ユメサキ", "ジャック"}


def test_saved_turn_rederives_emotion_without_new_save_fields():
    app = researcher()
    drain(app.office)
    app.office.ask_question("talk")
    while not any("原因も" in line.text for line in app.office.active_dialogue_lines()):
        assert app.office.advance_dialogue_step()
    assert identity(app)[0] == YUMESAKI_PORTRAITS["worried"]
    before = snapshot(app)
    app.saved_progress = decode(encode(before))
    app.start_game()
    assert snapshot(app) == before
    assert identity(app)[0] == YUMESAKI_PORTRAITS["worried"]
    assert "expression" not in encode(before) and "portrait" not in encode(before)
    assert app.office.advance_dialogue_step()
    assert identity(app)[0] == YUMESAKI_PORTRAITS["normal"]


def test_five_approved_assets_keep_palette_mask_and_nonface_pixels():
    assert yumesaki_office_portrait("新しい台詞") == YUMESAKI_PORTRAITS["normal"]
    assets = Path(__file__).resolve().parents[1] / "src/drift_with_me/assets"
    definitions = {
        i["id"]: i for i in json.loads((assets / "jack_sprite.json").read_text())["source_assets"]
    }
    normal = (assets / "Yumesaki_bust_normal_116.hex").read_text().splitlines()
    for key in YUMESAKI_PORTRAITS.values():
        item = definitions[key]
        assert (item["hex_width"], item["hex_height"], item["colkey"]) == (116, 116, 8)
        rows = (assets / item["frames"][0]["path"]).read_text().splitlines()
        assert (
            hashlib.sha256(bytes(int(c, 16) for row in rows for c in row)).hexdigest()
            == item["source_hash"]
        )
        for y, row in enumerate(rows):
            for x, color in enumerate(row):
                assert (color == "8") == (normal[y][x] == "8")
                if not (
                    37 <= x < 51
                    and 28 <= y < 44
                    or 51 <= x < 67
                    and 25 <= y < 43
                    or 50 <= x < 61
                    and 46 <= y < 54
                ):
                    assert color == normal[y][x]


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_five_busts_fit_actual_visitor_frame(profile):
    app, calls = make_app(profile)
    app.pyxel.rect = lambda *args: None
    app.pyxel.rectb = lambda *args: None
    frame = SimpleNamespace(image="bust", u=0, v=0, width=116, height=116)
    app.sprite_assets = SimpleNamespace(
        get=lambda key: SimpleNamespace(frame=lambda: frame, definition=SimpleNamespace(colkey=8))
    )
    rect = app.office_visitor_portrait_rect()
    for key in YUMESAKI_PORTRAITS.values():
        calls.clear()
        app.draw_office_portrait(rect, key, smile=True)
        args, kwargs = calls[0]
        scale = kwargs["scale"]
        left, top = args[0] + 116 * (1 - scale) / 2, args[1] + 116 * (1 - scale) / 2
        assert left >= rect.x - 1 and left + 116 * scale <= rect.x + rect.width + 1
        assert top >= rect.y - 1 and top + 116 * scale <= rect.y + rect.height + 1
        assert kwargs["colkey"] == 8
