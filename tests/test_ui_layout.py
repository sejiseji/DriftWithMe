from __future__ import annotations

from drift_with_me.app import DriftWithMeApp, PointerSnapshot
from drift_with_me.config import load_data_json, load_runtime_config
from drift_with_me.input import Rect


def make_app_for_profile(profile: str) -> DriftWithMeApp:
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config(profile)
    return app


class FakePyxel:
    KEY_RETURN = 1

    def __init__(self, return_pressed: bool = False) -> None:
        self.return_pressed = return_pressed

    def btnp(self, key: int) -> bool:
        return key == self.KEY_RETURN and self.return_pressed


def overlaps(a: Rect, b: Rect) -> bool:
    return (
        a.x < b.x + b.width
        and a.x + a.width > b.x
        and a.y < b.y + b.height
        and a.y + a.height > b.y
    )


def contains(outer: Rect, inner: Rect) -> bool:
    return (
        inner.x >= outer.x
        and inner.y >= outer.y
        and inner.x + inner.width <= outer.x + outer.width
        and inner.y + inner.height <= outer.y + outer.height
    )


EXPECTED_RECTS = {
    "low": {
        "resource": (6, 6, 156, 44),
        "sound_hit": (356, 6, 30, 30),
        "pause_hit": (390, 6, 30, 30),
        "context_action": (286, 148, 62, 36),
        "primary_action": (356, 148, 62, 36),
        "progress_chip": (148, 148, 132, 36),
        "minimap": (18, 113, 56, 56),
        "location": (6, 172, 80, 18),
    },
    "medium": {
        "resource": (8, 8, 168, 48),
        "sound_hit": (436, 8, 32, 32),
        "pause_hit": (472, 8, 32, 32),
        "context_action": (348, 184, 74, 38),
        "primary_action": (430, 184, 74, 38),
        "progress_chip": (180, 182, 148, 40),
        "minimap": (20, 142, 64, 64),
        "location": (8, 210, 88, 18),
    },
    "high": {
        "resource": (10, 10, 210, 60),
        "sound_hit": (545, 10, 40, 40),
        "pause_hit": (590, 10, 40, 40),
        "context_action": (432, 228, 94, 48),
        "primary_action": (536, 228, 94, 48),
        "progress_chip": (225, 228, 180, 48),
        "minimap": (25, 176, 80, 80),
        "location": (10, 261, 110, 23),
    },
}


def rect_tuple(rect: Rect) -> tuple[int, int, int, int]:
    return (int(rect.x), int(rect.y), int(rect.width), int(rect.height))


def test_numeric_hud_rects_match_v02_reference_across_profiles() -> None:
    for profile in ("low", "medium", "high"):
        app = make_app_for_profile(profile)
        expected = EXPECTED_RECTS[profile]

        assert rect_tuple(app.resource_panel_rect()) == expected["resource"]
        assert rect_tuple(app.sound_button_rect()) == expected["sound_hit"]
        assert rect_tuple(app.pause_button_rect()) == expected["pause_hit"]
        assert rect_tuple(app.interact_button_rect()) == expected["context_action"]
        assert rect_tuple(app.action_button_rect()) == expected["primary_action"]
        assert rect_tuple(app.interaction_chip_rect()) == expected["progress_chip"]
        assert rect_tuple(app.minimap_rect()) == expected["minimap"]
        assert rect_tuple(app.location_rect()) == expected["location"]


def test_numeric_layout_data_keeps_permanent_hud_inside_screen() -> None:
    layout = load_data_json("ui_numeric_layout.json")
    permanent_ids = (
        "resource",
        "sound_hit",
        "pause_hit",
        "context_action",
        "primary_action",
        "progress_chip",
        "minimap",
        "location",
    )
    for profile in ("low", "medium", "high"):
        app = make_app_for_profile(profile)
        screen = Rect(0, 0, app.runtime.screen_width, app.runtime.screen_height)
        rects = [app.ui_rect(rect_id) for rect_id in permanent_ids]

        for rect in rects:
            assert contains(screen, rect)
        for index, rect in enumerate(rects):
            for other in rects[index + 1 :]:
                assert not overlaps(rect, other)
        assert layout["profiles"][profile]["rects"]["resource"] == list(
            EXPECTED_RECTS[profile]["resource"]
        )


def test_pause_debug_controls_fit_inside_panel_across_profiles() -> None:
    for profile in ("low", "medium", "high"):
        app = make_app_for_profile(profile)
        panel = app.pause_panel_rect()
        controls = (
            app.resume_button_rect(),
            app.pause_reset_button_rect(),
            app.pause_audio_button_rect(),
            app.pause_dev_entry_button_rect(),
        )

        assert panel.x >= 0
        assert panel.y >= 0
        assert panel.x + panel.width <= app.runtime.screen_width
        assert panel.y + panel.height <= app.runtime.screen_height
        for index, rect in enumerate(controls):
            assert contains(panel, rect)
            for other in controls[index + 1 :]:
                assert not overlaps(rect, other)


def test_inspect_panel_uses_dedicated_modal_rects() -> None:
    for profile in ("low", "medium", "high"):
        app = make_app_for_profile(profile)
        panel = app.inspect_panel_rect()
        assert contains(panel, app.inspect_title_rect())
        assert contains(panel, app.inspect_text_rect())
        assert contains(panel, app.inspect_page_rect())
        assert contains(panel, app.interaction_done_button_rect())


def test_inspect_panel_closes_on_done_enter_or_outside_press_only() -> None:
    app = make_app_for_profile("medium")
    app.pyxel = FakePyxel()
    panel = app.inspect_panel_rect()
    done = app.interaction_done_button_rect()

    app.pointer_snapshot = PointerSnapshot(
        True,
        True,
        panel.x + panel.width * 0.5,
        panel.y + panel.height * 0.5,
    )
    assert not app.inspect_completion_requested()

    app.pointer_snapshot = PointerSnapshot(
        True,
        True,
        done.x + done.width * 0.5,
        done.y + done.height * 0.5,
    )
    assert app.inspect_completion_requested()

    app.pointer_snapshot = PointerSnapshot(True, True, panel.x - 1.0, panel.y - 1.0)
    assert app.inspect_completion_requested()

    app.pyxel = FakePyxel(return_pressed=True)
    app.pointer_snapshot = PointerSnapshot(False, False, 0.0, 0.0)
    assert app.inspect_completion_requested()
