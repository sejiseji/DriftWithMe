from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from drift_with_me.app import DriftWithMeApp, OfficeDialogueLine
from drift_with_me.config import load_runtime_config
from drift_with_me.office import FieldResult, OfficePrototype
from drift_with_me.render import Renderer, jack_blink_closed, jack_idle_hover


class OfficeFont:
    @staticmethod
    def text_width(text, style_name):
        return sum(6 if ord(c) < 128 else 12 for c in text)

    @staticmethod
    def visual_vertical_metrics(style_name):
        return 0, 12


def make_app(profile="medium"):
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config(profile)
    app.office = OfficePrototype.load()
    app.ui_text = OfficeFont()
    app.presentation_time = 0.0
    calls = []
    app.pyxel = SimpleNamespace(blt=lambda *args, **kwargs: calls.append((args, kwargs)))
    assets = {}
    for name in ("jack_front_32", "jack_front_blink_32"):
        frame = SimpleNamespace(image=name, u=0, v=0, width=32, height=32)
        assets[name] = SimpleNamespace(
            frame=lambda frame=frame: frame, definition=SimpleNamespace(colkey=0)
        )
    app.sprite_assets = SimpleNamespace(get=assets.get)
    return app, calls


def overlaps(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_jack_fits_every_dialogue_page_at_hover_extremes(profile):
    app, calls = make_app(profile)
    observed_pages = 0
    observed_assets = set()

    def drain():
        nonlocal observed_pages
        while True:
            playback = app.sync_office_dialogue_playback()
            content = app.office_dialogue_content_rect()
            for page in playback.pages:
                assert len({line.speaker for line in page}) == 1
                for t in (0.0, 0.4, 1.2, 3.05):
                    calls.clear()
                    app.presentation_time = t
                    app.draw_office_jack(page)
                    if page[0].speaker != "Jack":
                        assert not calls
                        continue
                    assert len(calls) == 1
                    args, kwargs = calls[0]
                    x, y, image, _u, _v, width, height = args
                    observed_assets.add(image)
                    assert (width, height, kwargs) == (32, 32, {"colkey": 0})
                    assert x == int(content.x)
                    assert y >= round(content.y + max(0, (content.height / 5 - 12) / 2)) + 14
                    assert y + height <= math.floor(content.y + content.height)
                    square = x, y, x + width, y + height
                    for row, line in enumerate(page):
                        text_x = int(content.x + line.indent_px)
                        text_y = round(
                            content.y
                            + row * content.height / 5
                            + max(0, (content.height / 5 - 12) / 2)
                        )
                        text = (
                            text_x,
                            text_y,
                            text_x + app.ui_text.text_width(line.text, "office_japanese"),
                            text_y + 12,
                        )
                        assert not overlaps(square, text)
                observed_pages += page[0].speaker == "Jack"
            if not app.office.has_pending_dialogue_step():
                break
            app.office.advance_dialogue_step()
        app.office.complete_pending_question()

    for idx, case in enumerate(app.office.cases):
        app.office.current_index = idx
        app.office.begin_current_case()
        drain()
        for question in case.questions:
            assert app.office.ask_question(question.question_id)
            drain()
        assert app.office.classify(case.expected_classification)
        drain()
        if case.field_task:
            task = app.office.prepare_field_task()
            assert app.office.complete_field_task(
                FieldResult(
                    task_id=task.task_id,
                    case_id=task.case_id,
                    result_code="LAYOUT",
                    discovered_fact_ids=(),
                    report_lines=("確認記録",),
                )
            )
            drain()
    assert observed_pages == 53
    assert observed_assets == {"jack_front_32", "jack_front_blink_32"}


def test_portrait_speaker_filter_does_not_treat_report_as_jack():
    app, calls = make_app()
    for speaker, visitor in (("確認記録", False), ("ミナ", True), ("", False)):
        app.draw_office_jack((OfficeDialogueLine("text", visitor, speaker=speaker),))
    app.draw_office_jack(())
    assert not calls
    app.draw_office_jack((OfficeDialogueLine("Jack: （確かめよう。）", False, speaker="Jack"),))
    assert len(calls) == 1


def test_ui_hover_and_blink_share_world_clock_without_page_reset():
    app, calls = make_app()
    player = app.runtime.raw["player"]
    model = SimpleNamespace(config={"player": player})
    renderer = Renderer.__new__(Renderer)
    jack_page = (OfficeDialogueLine("Jack: hello", False, speaker="Jack"),)
    visitor_page = (OfficeDialogueLine("ミナ: はい", True, speaker="ミナ"),)
    for frame in range(round(sum(player["blink"]["interval_pattern_sec"]) * 60)):
        t = frame / 60
        app.presentation_time = t
        assert renderer.player_visual_hover(model, t) == jack_idle_hover(player, t)
        before = app.office_jack_portrait_rect()
        app.draw_office_jack(jack_page)
        expected_asset = (
            "jack_front_blink_32" if jack_blink_closed(player["blink"], t) else "jack_front_32"
        )
        assert calls[-1][0][2] == expected_asset
        calls.clear()
        app.draw_office_jack(visitor_page)
        app.draw_office_jack(())
        assert not calls
        app.draw_office_jack(jack_page)
        assert app.office_jack_portrait_rect() == before
        assert len(calls) == 1
        calls.clear()
