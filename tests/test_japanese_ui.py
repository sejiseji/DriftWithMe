from __future__ import annotations

import pyxel

from drift_with_me.app import DriftWithMeApp
from drift_with_me.config import load_runtime_config
from drift_with_me.ui_text import TextResources, load_ui_text_renderer


def make_app(profile: str) -> DriftWithMeApp:
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config(profile)
    return app


def test_japanese_ui_resources_translate_existing_tokens() -> None:
    resources = TextResources.load("ja")

    assert resources.token("BUBBLE") == "泡"
    assert resources.token("GUARD") == "防御"
    assert resources.token("ZAP") == "電撃"
    assert resources.token("CHECK") == "調べる"
    assert resources.token("CANCEL_REFILL") == "中断"
    assert resources.token("NONE") == "行動"
    assert resources.token("DONE") == "閉じる"
    assert resources.token("NEXT") == "次へ"
    assert resources.reason("insufficient_water") == "水が足りない"
    assert resources.reason("auto_move_blocked") == "行けません"
    assert resources.reason("auto_move_no_path") == "道なし"
    assert resources.raw_text("WATER REFILL") == "給水"


def test_japanese_ui_text_draws_eight_pixels_higher_than_ascii() -> None:
    app = make_app("medium")

    assert app.ui_text_language_y(40, "調べる") == 32
    assert app.ui_text_language_y(40, "水") == 32
    assert app.ui_text_language_y(40, "DRIFTWITHME") == 40
    assert app.ui_text_language_y(40, "100%") == 40


def test_dotgothic16_font_loads_and_major_labels_fit_existing_buttons() -> None:
    pyxel.init(64, 64, headless=True)
    primary_tokens = ("NONE", "BUBBLE", "GUARD", "ZAP")
    context_tokens = ("CHECK", "REFILL", "CHARGE", "CANCEL_REFILL", "CANCEL_CHARGE")
    inspect_tokens = ("DONE", "NEXT")

    for profile in ("low", "medium", "high"):
        app = make_app(profile)
        renderer = load_ui_text_renderer(pyxel, app.runtime)
        app.ui_text = renderer

        assert renderer.font_loaded
        for token in primary_tokens:
            label = renderer.resources.token(token)
            label_rect = app.action_button_label_rect(app.action_button_visual_rect())
            assert renderer.text_width(label, "button") <= label_rect.width
            assert renderer.text_height("button") + 2 <= label_rect.height
        for token in context_tokens:
            label = renderer.resources.token(token)
            label_rect = app.action_button_label_rect(app.interact_button_visual_rect())
            assert renderer.text_width(label, "button") <= label_rect.width
            assert renderer.text_height("button") + 2 <= label_rect.height
        for token in inspect_tokens:
            label = renderer.resources.token(token)
            assert (
                renderer.text_width(label, "button") <= app.interaction_done_button_rect().width - 8
            )
        assert renderer.text_width("水", "resource") <= 34
        assert renderer.text_width("電力", "resource") <= 42
        assert renderer.text_width("100", "numeric") <= 28
        assert renderer.text_width("060", "numeric") <= 28
        progress_width = app.ui_profile_layout()["progress"][0]
        compact_title_width = progress_width - 58
        assert renderer.text_width("給水", "body") <= compact_title_width
        assert renderer.text_width("充電", "body") <= compact_title_width
        assert renderer.text_width("100%", "numeric") <= 42
