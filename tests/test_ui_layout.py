from __future__ import annotations

from types import SimpleNamespace

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
        "resource": (6, 6, 132, 40),
        "sound_hit": (356, 6, 30, 30),
        "pause_hit": (390, 6, 30, 30),
        "context_action": (274, 154, 76, 38),
        "primary_action": (350, 154, 76, 38),
        "progress_chip": (274, 126, 148, 24),
        "minimap": (10, 120, 56, 70),
        "location": (8, 178, 72, 14),
    },
    "medium": {
        "resource": (8, 8, 132, 40),
        "sound_hit": (436, 8, 32, 32),
        "pause_hit": (472, 8, 32, 32),
        "context_action": (356, 192, 76, 40),
        "primary_action": (432, 192, 76, 40),
        "progress_chip": (352, 164, 152, 24),
        "minimap": (8, 162, 60, 70),
        "location": (8, 218, 72, 14),
    },
    "high": {
        "resource": (10, 10, 156, 44),
        "sound_hit": (545, 10, 40, 40),
        "pause_hit": (590, 10, 40, 40),
        "context_action": (432, 228, 94, 48),
        "primary_action": (536, 228, 94, 48),
        "progress_chip": (432, 190, 198, 30),
        "minimap": (20, 196, 84, 88),
        "location": (10, 272, 100, 18),
    },
}

EXPECTED_VISUAL_RECTS = {
    "low": {
        "sound": (360, 10, 22, 22),
        "pause": (394, 10, 22, 22),
        "context_action": (278, 160, 68, 28),
        "primary_action": (354, 160, 68, 28),
        "minimap": (14, 124, 48, 48),
        "wordmark": (226, 10, 112, 14),
        "tooltip_one": (274, 126, 148, 24),
        "tooltip_two": (274, 104, 148, 40),
    },
    "medium": {
        "sound": (440, 12, 24, 24),
        "pause": (476, 12, 24, 24),
        "context_action": (360, 198, 68, 28),
        "primary_action": (436, 198, 68, 28),
        "minimap": (12, 166, 52, 52),
        "wordmark": (316, 13, 112, 14),
        "tooltip_one": (352, 164, 152, 24),
        "tooltip_two": (352, 148, 152, 40),
    },
    "high": {
        "sound": (550, 15, 30, 30),
        "pause": (595, 15, 30, 30),
        "context_action": (438, 238, 84, 30),
        "primary_action": (542, 238, 84, 30),
        "minimap": (28, 208, 64, 64),
        "wordmark": (388, 16, 132, 16),
        "tooltip_one": (432, 190, 198, 30),
        "tooltip_two": (432, 162, 198, 54),
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


def test_compact_hud_c_visual_rects_match_uic_targets_across_profiles() -> None:
    for profile in ("low", "medium", "high"):
        app = make_app_for_profile(profile)
        expected = EXPECTED_VISUAL_RECTS[profile]

        assert rect_tuple(app.sound_visual_rect()) == expected["sound"]
        assert rect_tuple(app.pause_visual_rect()) == expected["pause"]
        assert rect_tuple(app.interact_button_visual_rect()) == expected["context_action"]
        assert rect_tuple(app.action_button_visual_rect()) == expected["primary_action"]
        assert rect_tuple(app.minimap_visual_rect()) == expected["minimap"]
        assert rect_tuple(app.wordmark_rect()) == expected["wordmark"]
        assert rect_tuple(app.tooltip_rect(two_lines=False)) == expected["tooltip_one"]
        assert rect_tuple(app.tooltip_rect(two_lines=True)) == expected["tooltip_two"]

        assert app.action_button_rect().width >= app.action_button_visual_rect().width
        assert app.action_button_rect().height >= app.action_button_visual_rect().height
        assert app.interact_button_rect().width >= app.interact_button_visual_rect().width
        assert app.interact_button_rect().height >= app.interact_button_visual_rect().height
        assert app.minimap_rect().width >= app.minimap_visual_rect().width
        assert app.minimap_rect().height >= app.minimap_visual_rect().height


def test_numeric_layout_data_keeps_permanent_hud_inside_screen() -> None:
    layout = load_data_json("ui_numeric_layout.json")
    permanent_ids = [
        "resource",
        "sound_hit",
        "pause_hit",
        "context_action",
        "primary_action",
        "progress_chip",
        "minimap",
        "location",
    ]
    for profile in ("low", "medium", "high"):
        app = make_app_for_profile(profile)
        screen = Rect(0, 0, app.runtime.screen_width, app.runtime.screen_height)
        rects = [(rect_id, app.ui_rect(rect_id)) for rect_id in permanent_ids]

        for _rect_id, rect in rects:
            assert contains(screen, rect)
        allowed_overlaps = {frozenset(("minimap", "location"))}
        for index, (rect_id, rect) in enumerate(rects):
            for other_id, other in rects[index + 1 :]:
                if frozenset((rect_id, other_id)) in allowed_overlaps:
                    continue
                assert not overlaps(rect, other)
        assert layout["profiles"][profile]["rects"]["resource"] == list(
            EXPECTED_RECTS[profile]["resource"]
        )


def test_uic002_status_slot_blocks_only_rejection_and_progress() -> None:
    app = make_app_for_profile("medium")
    app.model = SimpleNamespace(interaction=None)
    app.last_denied_reason = ""

    assert app.tooltip_rect(two_lines=False) not in app.active_ui_rects()

    app.last_denied_reason = "auto_move_blocked"
    assert app.tooltip_rect(two_lines=False) in app.active_ui_rects()

    app.model.interaction = SimpleNamespace(kind="water_refill")
    active_rects = app.active_ui_rects()
    assert app.interaction_chip_rect() in active_rects
    assert active_rects.count(app.interaction_chip_rect()) == 1


def test_uic003_location_label_is_temporary_and_nonblocking() -> None:
    app = make_app_for_profile("medium")
    app.model = SimpleNamespace(interaction=None)
    app.last_denied_reason = ""
    app.debug_enabled = False
    app.location_label_remaining = 0.0

    assert not app.location_label_visible()
    assert app.location_rect() not in app.active_ui_rects()

    app.show_location_label()

    assert app.location_label_visible()
    assert app.location_rect() not in app.active_ui_rects()

    app.update_location_label(app.location_label_duration() + 0.01)

    assert not app.location_label_visible()
    assert app.location_rect() not in app.active_ui_rects()


def test_uic003_build_label_visibility_modes() -> None:
    app = make_app_for_profile("medium")
    app.debug_enabled = False

    assert app.build_label_visible()

    app.runtime.raw["ui"]["build_label_mode"] = "hidden"
    assert not app.build_label_visible()

    app.runtime.raw["ui"]["build_label_mode"] = "debug"
    assert not app.build_label_visible()

    app.debug_enabled = True
    assert app.build_label_visible()


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
