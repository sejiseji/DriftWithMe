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
    assert resources.token("DONE") == "閉じる"
    assert resources.reason("insufficient_water") == "水が足りない"
    assert resources.raw_text("WATER REFILL") == "給水"


def test_dotgothic16_font_loads_and_major_labels_fit_existing_buttons() -> None:
    pyxel.init(64, 64, headless=True)
    action_tokens = ("ACTION", "WAIT", "BUBBLE", "GUARD", "ZAP")
    interact_tokens = ("CHECK", "REFILL", "CHARGE")
    done_token = "DONE"

    for profile in ("low", "medium", "high"):
        app = make_app(profile)
        renderer = load_ui_text_renderer(pyxel, app.runtime)
        app.ui_text = renderer

        assert renderer.font_loaded
        for token in action_tokens:
            label = renderer.resources.token(token)
            assert renderer.text_width(label, "label") <= app.action_button_rect().width - 8
        for token in interact_tokens:
            label = renderer.resources.token(token)
            assert renderer.text_width(label, "label") <= app.interact_button_rect().width - 8
        assert (
            renderer.text_width(renderer.resources.token(done_token), "label")
            <= app.interaction_done_button_rect().width - 8
        )
        assert renderer.text_width("水 100", "label") <= 80
        assert renderer.text_width("電力 060", "label") <= 80
