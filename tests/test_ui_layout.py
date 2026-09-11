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
