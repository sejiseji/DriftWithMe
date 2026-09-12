from __future__ import annotations

from drift_with_me.app import DriftWithMeApp
from drift_with_me.config import load_runtime_config
from drift_with_me.input import Rect


def make_app_for_profile(profile: str) -> DriftWithMeApp:
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config(profile)
    return app


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


def test_interaction_chip_fits_between_hud_and_pause_across_profiles() -> None:
    for profile in ("low", "medium", "high"):
        app = make_app_for_profile(profile)
        chip = app.interaction_chip_rect()
        done = app.interaction_done_button_rect()
        hud = Rect(6, 6, 164, 48)

        assert chip.x >= 0
        assert chip.y >= 0
        assert chip.x + chip.width <= app.runtime.screen_width
        assert chip.y + chip.height <= app.runtime.screen_height
        assert done.x >= chip.x
        assert done.y >= chip.y
        assert done.x + done.width <= chip.x + chip.width
        assert done.y + done.height <= chip.y + chip.height
        assert not overlaps(chip, hud)
        assert not overlaps(chip, app.pause_button_rect())
        assert not overlaps(chip, app.sound_button_rect())
        assert not overlaps(chip, app.interact_button_rect())
        assert not overlaps(chip, app.action_button_rect())


def test_pause_debug_controls_fit_inside_panel_across_profiles() -> None:
    for profile in ("low", "medium", "high"):
        app = make_app_for_profile(profile)
        panel = app.pause_panel_rect()
        controls = (
            app.resume_button_rect(),
            app.pause_reset_button_rect(),
            app.pause_fill_button_rect(),
            app.pause_zero_button_rect(),
            app.pause_culling_button_rect(),
            app.pause_debug_button_rect(),
        )

        assert panel.x >= 0
        assert panel.y >= 0
        assert panel.x + panel.width <= app.runtime.screen_width
        assert panel.y + panel.height <= app.runtime.screen_height
        for index, rect in enumerate(controls):
            assert contains(panel, rect)
            for other in controls[index + 1 :]:
                assert not overlaps(rect, other)
