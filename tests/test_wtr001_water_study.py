from __future__ import annotations

from types import SimpleNamespace

from drift_with_me.app import AppScreen, DriftWithMeApp, PointerSnapshot
from drift_with_me.audio import AudioEngine
from drift_with_me.camera import CameraController
from drift_with_me.config import load_runtime_config
from drift_with_me.effects import EffectSystem
from drift_with_me.input import DoubleTapMoveRecognizer, PointerInput
from drift_with_me.math3d import Vec3
from drift_with_me.model import GameModel
from drift_with_me.world import load_world_data


class FakePyxel:
    KEY_1 = 49
    KEY_2 = 50
    KEY_3 = 51
    KEY_4 = 52
    KEY_M = 77

    def __init__(self, pressed: set[int] | None = None) -> None:
        self.pressed = pressed or set()

    def btnp(self, key: int) -> bool:
        return key in self.pressed

    def btn(self, _key: int) -> bool:
        return False


def make_water_app() -> DriftWithMeApp:
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config("medium")
    app.world = load_world_data()
    app.model = GameModel(app.runtime.raw, app.world)
    app.audio = AudioEngine(app.runtime.raw)
    app.effects = EffectSystem(app.runtime.raw)
    app.camera_controller = CameraController(
        app.runtime.raw,
        app.world,
        app.runtime.screen_width,
        app.runtime.screen_height,
        Vec3(app.model.player.x, 0.0, app.model.player.z),
    )
    input_config = app.runtime.raw["input"]
    auto_move_config = app.runtime.raw.get("auto_move", {})
    app.pointer = PointerInput(
        hold_sec=float(input_config["hold_sec"]),
        drag_threshold_px=float(input_config["drag_threshold_ref_px"]),
        deadzone_px=float(input_config["stick_deadzone_ref_px"]),
        radius_px=float(input_config["stick_radius_ref_px"]),
    )
    app.double_tap_move = DoubleTapMoveRecognizer(
        short_tap_sec=float(auto_move_config.get("short_tap_sec", 0.18)),
        max_interval_sec=float(auto_move_config.get("max_interval_sec", 0.3)),
        max_distance_px=float(auto_move_config.get("max_distance_ref_px", 20.0)),
        drag_threshold_px=float(input_config["drag_threshold_ref_px"]),
    )
    app.pyxel = FakePyxel()
    app.screen = AppScreen.PLAY
    app.water_study_clock = 0.0
    app.water_study_menu_open = False
    app.water_study_profile_index = 1
    app.water_study_last_draw_ms = 0.0
    app.water_study_last_layer_count = 0
    app.water_study_last_wrap_calls = 0
    app.water_study_planes = {"water_deep_plane_c": object()}
    app.water_study_phase_planes = {}
    app.pointer_snapshot = PointerSnapshot(False, False, 0.0, 0.0)
    app.pending_action_pressed = True
    app.pending_interact_pressed = True
    app.pending_auto_move_goal = (12.0, 34.0)
    app.pending_cancel_auto_move = True
    app.last_denied_reason = ""
    app.accumulator = 0.2
    return app


def test_wtr001_m_opens_and_closes_water_study_from_exploration() -> None:
    app = make_water_app()
    app.pyxel = FakePyxel({FakePyxel.KEY_M})

    assert app.handle_water_study_shortcut()
    assert app.screen == AppScreen.WATER_STUDY
    assert app.pending_auto_move_goal is None
    assert app.pending_cancel_auto_move is False

    assert app.handle_water_study_shortcut()
    assert app.screen == AppScreen.PLAY


def test_wtr001_m_does_not_open_during_combat() -> None:
    app = make_water_app()
    app.model.combat_session = SimpleNamespace()
    app.pyxel = FakePyxel({FakePyxel.KEY_M})

    assert not app.handle_water_study_shortcut()
    assert app.screen == AppScreen.PLAY


def test_wtr001_menu_opens_panel_and_enters_water_study() -> None:
    app = make_water_app()
    button = app.water_study_menu_button_rect()
    app.pointer_snapshot = PointerSnapshot(
        True,
        True,
        button.x + button.width * 0.5,
        button.y + button.height * 0.5,
    )

    assert app.handle_water_study_menu_pointer_controls()
    assert app.water_study_menu_open

    item = app.water_study_menu_item_rect()
    app.pointer_snapshot = PointerSnapshot(
        True,
        True,
        item.x + item.width * 0.5,
        item.y + item.height * 0.5,
    )

    assert app.handle_water_study_menu_pointer_controls()
    assert app.screen == AppScreen.WATER_STUDY


def test_wtr001_close_preserves_world_state() -> None:
    app = make_water_app()
    before = (
        app.model.player.x,
        app.model.player.z,
        app.model.buddy.x,
        app.model.buddy.z,
        app.model.water,
        app.model.energy,
        app.camera_controller.current,
    )

    assert app.enter_water_study()
    app.water_study_clock = 2.0
    close = app.water_study_close_rect()
    app.pointer_snapshot = PointerSnapshot(
        True,
        True,
        close.x + close.width * 0.5,
        close.y + close.height * 0.5,
    )
    app.update_water_study_screen(0.5)

    after = (
        app.model.player.x,
        app.model.player.z,
        app.model.buddy.x,
        app.model.buddy.z,
        app.model.water,
        app.model.energy,
        app.camera_controller.current,
    )
    assert app.screen == AppScreen.PLAY
    assert after == before


def test_wtr001_active_rects_are_screen_specific() -> None:
    app = make_water_app()

    assert app.water_study_menu_button_rect() in app.active_ui_rects()

    app.water_study_menu_open = True
    assert app.water_study_menu_item_rect() in app.active_ui_rects()

    app.screen = AppScreen.WATER_STUDY
    assert app.active_ui_rects() == (app.water_study_close_rect(),)


def test_wtr001_b_profile_shortcuts_switch_profiles() -> None:
    app = make_water_app()
    app.screen = AppScreen.WATER_STUDY
    app.pyxel = FakePyxel({FakePyxel.KEY_4})

    app.update_water_study_screen(0.25)

    assert app.water_study_profile_index == 3
    assert app.water_study_profile().name == "FULL_SIX_OBSERVE"


def test_wtr001_b_motion_weights_are_normalized() -> None:
    app = make_water_app()

    for t in (0.0, 6.5, 7.5, 8.25, 15.5, 23.5):
        weights = app.water_study_motion_weights(t)
        assert all(0.0 <= weight <= 1.0 for weight in weights)
        assert abs(sum(weights) - 1.0) < 0.000001


def test_wtr001_b_profile_contracts_are_ordered_by_load() -> None:
    app = make_water_app()

    app.water_study_profile_index = 0
    baseline = app.water_study_profile()
    app.water_study_profile_index = 1
    three_layer = app.water_study_profile()
    app.water_study_profile_index = 2
    full = app.water_study_profile()
    app.water_study_profile_index = 3
    observe = app.water_study_profile()

    assert baseline.name == "BASE_ONLY"
    assert baseline.layer_ids == ("water_deep_plane_c",)
    assert three_layer.layer_ids == (
        "water_deep_plane_c",
        "water_surface_plane_c",
        "water_surface_caustics_plane_c",
    )
    assert full.layer_ids == (
        "water_deep_plane_c",
        "water_mid_plane_c",
        "water_surface_plane_c",
        "water_surface_caustics_plane_c",
        "water_upper_lightnet_plane_c",
        "water_highlights_plane_c",
    )
    assert observe.layer_ids == full.layer_ids
    assert len(baseline.layer_ids) < len(three_layer.layer_ids) < len(full.layer_ids)


def test_wtr001_phase_plane_selection_uses_layer_step_frames() -> None:
    app = make_water_app()
    app.water_study_planes = {"water_surface_caustics_plane_c": "base"}
    app.water_study_phase_planes = {
        "water_surface_caustics_plane_c": tuple(f"phase-{index}" for index in range(8))
    }

    assert app.water_study_plane_for_frame("water_surface_caustics_plane_c", 0.0) == "phase-5"
    assert app.water_study_plane_for_frame("water_surface_caustics_plane_c", 6 / 60) == "phase-5"
    assert app.water_study_plane_for_frame("water_surface_caustics_plane_c", 7 / 60) == "phase-6"
    assert app.water_study_plane_for_frame("water_surface_caustics_plane_c", 56 / 60) == "phase-5"
    assert app.water_study_plane_for_frame("water_mid_plane_c", 8 / 60) is None


def test_wtr001_wave2_phase_plane_selection_uses_independent_initial_offsets() -> None:
    app = make_water_app()
    app.water_study_phase_planes = {
        "water_mid_plane_c": tuple(f"mid-{index}" for index in range(8)),
        "water_surface_plane_c": tuple(f"surface-{index}" for index in range(8)),
        "water_upper_lightnet_plane_c": tuple(f"light-{index}" for index in range(8)),
    }

    assert app.water_study_plane_for_frame("water_mid_plane_c", 0.0) == "mid-0"
    assert app.water_study_plane_for_frame("water_mid_plane_c", 12 / 60) == "mid-0"
    assert app.water_study_plane_for_frame("water_mid_plane_c", 13 / 60) == "mid-1"
    assert app.water_study_plane_for_frame("water_surface_plane_c", 0.0) == "surface-2"
    assert app.water_study_plane_for_frame("water_surface_plane_c", 9 / 60) == "surface-3"
    assert app.water_study_plane_for_frame("water_upper_lightnet_plane_c", 0.0) == "light-1"
    assert app.water_study_plane_for_frame("water_upper_lightnet_plane_c", 5 / 60) == "light-2"
