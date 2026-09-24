from __future__ import annotations

from types import SimpleNamespace

import drift_with_me.app as app_module
from drift_with_me.app import AppScreen, DriftWithMeApp, PointerSnapshot
from drift_with_me.audio import AudioEngine
from drift_with_me.camera import CameraController
from drift_with_me.config import load_runtime_config
from drift_with_me.effects import EffectSystem
from drift_with_me.input import DoubleTapMoveRecognizer, PointerInput
from drift_with_me.math3d import Vec3
from drift_with_me.model import GameModel
from drift_with_me.water_study_assets import (
    APPROVED_WATER_PRODUCTION_LAYER_IDS,
    WaterStudyChunk,
    WaterStudyPlane,
)
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


class FakeDrawPyxel(FakePyxel):
    def __init__(self) -> None:
        super().__init__()
        self.palette_calls: list[tuple[int, int] | tuple[()]] = []
        self.blt_calls: list[tuple] = []

    def pal(self, source_color: int | None = None, target_color: int | None = None) -> None:
        if source_color is None and target_color is None:
            self.palette_calls.append(())
            return
        assert source_color is not None
        assert target_color is not None
        self.palette_calls.append((source_color, target_color))

    def blt(self, *args, **kwargs) -> None:
        self.blt_calls.append((args, kwargs))


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
    app.water_study_open_latency_ms = 0.0
    app.water_study_asset_cache = make_fake_water_cache()
    app.water_study_planes = app.water_study_asset_cache.static_layers
    app.water_study_phase_planes = app.water_study_asset_cache.phase_layers
    app.pointer_snapshot = PointerSnapshot(False, False, 0.0, 0.0)
    app.pending_action_pressed = True
    app.pending_interact_pressed = True
    app.pending_auto_move_goal = (12.0, 34.0)
    app.pending_cancel_auto_move = True
    app.last_denied_reason = ""
    app.accumulator = 0.2
    return app


def make_fake_water_cache() -> SimpleNamespace:
    return SimpleNamespace(
        ready=True,
        static_layers={"water_deep_plane_c": object(), "water_highlights_plane_c": object()},
        phase_layers={
            "water_surface_plane_c": tuple(f"surface-{index}" for index in range(8)),
        },
        plane_for_frame=lambda layer_id, elapsed, fps: (
            f"surface-{(2 + int(max(0.0, elapsed) * fps) // 9) % 8}"
            if layer_id == "water_surface_plane_c"
            else None
        ),
    )


def test_wtr001_m_opens_and_closes_water_study_from_exploration() -> None:
    app = make_water_app()
    app.pyxel = FakePyxel({FakePyxel.KEY_M})

    assert app.handle_water_study_shortcut()
    assert app.screen == AppScreen.WATER_STUDY
    assert app.pending_auto_move_goal is None
    assert app.pending_cancel_auto_move is False

    assert app.handle_water_study_shortcut()
    assert app.screen == AppScreen.PLAY


def test_wtr001_enter_uses_preloaded_cache_without_rebuild(monkeypatch) -> None:
    app = make_water_app()
    cache = make_fake_water_cache()
    app.water_study_asset_cache = cache
    app.water_study_planes = {}
    app.water_study_phase_planes = {}

    import drift_with_me.app as app_module

    def fail_preload(_pyxel):
        raise AssertionError("Water Study open must not rebuild resident cache")

    monkeypatch.setattr(app_module, "preload_water_study_cache", fail_preload)

    assert app.enter_water_study()
    assert app.water_study_planes is cache.static_layers
    assert app.water_study_phase_planes is cache.phase_layers
    assert app.water_study_clock == 0.0
    assert app.water_study_open_latency_ms >= 0.0


def test_wtr001_close_keeps_resident_cache_for_reopen() -> None:
    app = make_water_app()
    cache = make_fake_water_cache()
    app.water_study_asset_cache = cache
    app.water_study_planes = {}
    app.water_study_phase_planes = {}

    assert app.enter_water_study()
    assert app.exit_water_study()
    assert app.water_study_asset_cache is cache
    assert app.enter_water_study()
    assert app.water_study_asset_cache is cache
    assert app.water_study_planes is cache.static_layers


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
    assert app.water_study_profile().name == "APPROVED_LOOK03"
    assert app.water_study_profile().layer_ids == APPROVED_WATER_PRODUCTION_LAYER_IDS


def test_wtr001_b_motion_weights_are_normalized() -> None:
    app = make_water_app()

    for t in (0.0, 6.5, 7.5, 8.25, 15.5, 23.5):
        weights = app.water_study_motion_weights(t)
        assert all(0.0 <= weight <= 1.0 for weight in weights)
        assert abs(sum(weights) - 1.0) < 0.000001


def test_wtr001_water_layer_offsets_are_visible_on_mobile_scale() -> None:
    app = make_water_app()

    before = app.water_study_layer_offset(
        0.0,
        speed_x=1.65,
        speed_y=1.12,
        sine_amp=2.4,
        orbit_x=2.25,
        orbit_y=1.9,
        phase=2.6,
    )
    after = app.water_study_layer_offset(
        4.0,
        speed_x=1.65,
        speed_y=1.12,
        sine_amp=2.4,
        orbit_x=2.25,
        orbit_y=1.9,
        phase=2.6,
    )

    delta = max(
        abs(after_value - before_value)
        for before_value, after_value in zip(before, after, strict=True)
    )
    assert delta >= 3.0


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

    assert baseline.name == "APPROVED_LOOK03"
    assert baseline.layer_ids == APPROVED_WATER_PRODUCTION_LAYER_IDS
    assert three_layer.layer_ids == APPROVED_WATER_PRODUCTION_LAYER_IDS
    assert full.layer_ids == APPROVED_WATER_PRODUCTION_LAYER_IDS
    assert observe.layer_ids == full.layer_ids
    assert "water_upper_lightnet_plane_d" not in full.layer_ids


def test_wtr001_phase_plane_selection_uses_layer_step_frames() -> None:
    app = make_water_app()
    app.water_study_asset_cache = None
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
    app.water_study_asset_cache = None
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


def test_wtr001_phase_selection_uses_resident_cache_when_ready() -> None:
    app = make_water_app()
    cache = make_fake_water_cache()
    app.water_study_asset_cache = cache
    app.water_study_phase_planes = {}

    assert app.water_study_plane_for_frame("water_surface_plane_c", 0.0) == "surface-2"
    assert app.water_study_plane_for_frame("water_surface_plane_c", 9 / 60) == "surface-3"


def test_wtr_look03_water_study_tempers_coarse_caustics_palette() -> None:
    app = make_water_app()
    app.pyxel = FakeDrawPyxel()
    app.water_study_asset_cache = None
    app.water_study_phase_planes = {}
    app.water_study_planes = {
        "water_surface_caustics_plane_c": WaterStudyPlane(
            layer_id="water_surface_caustics_plane_c",
            logical_width=1024,
            logical_height=512,
            chunk_width=256,
            chunk_height=256,
            colkey=8,
            chunks=(
                WaterStudyChunk(
                    image=object(),
                    origin_x=0,
                    origin_y=0,
                    width=256,
                    height=256,
                ),
            ),
        )
    }

    calls = app.draw_water_study_plane("water_surface_caustics_plane_c", 0.0)

    assert calls == 1
    assert app.pyxel.palette_calls == [(7, 12), (6, 12), ()]
    assert len(app.pyxel.blt_calls) == 1


def test_wtr_look03_water_study_tempers_coarse_surface_palette() -> None:
    app = make_water_app()
    app.pyxel = FakeDrawPyxel()
    app.water_study_asset_cache = None
    app.water_study_phase_planes = {}
    app.water_study_planes = {
        "water_surface_plane_c": WaterStudyPlane(
            layer_id="water_surface_plane_c",
            logical_width=1024,
            logical_height=512,
            chunk_width=256,
            chunk_height=256,
            colkey=8,
            chunks=(
                WaterStudyChunk(
                    image=object(),
                    origin_x=0,
                    origin_y=0,
                    width=256,
                    height=256,
                ),
            ),
        )
    }

    calls = app.draw_water_study_plane("water_surface_plane_c", 0.0)

    assert calls == 1
    assert app.pyxel.palette_calls == [(6, 12), (12, 5), ()]
    assert len(app.pyxel.blt_calls) == 1


def test_approved_water_production_planes_draw_with_identity_palette_and_no_motion(
    monkeypatch,
) -> None:
    app = make_water_app()
    app.pyxel = FakeDrawPyxel()
    app.water_study_asset_cache = None
    app.water_study_phase_planes = {}
    app.water_study_planes = {
        "water_highlights_plane_d": WaterStudyPlane(
            layer_id="water_highlights_plane_d",
            logical_width=1024,
            logical_height=512,
            chunk_width=256,
            chunk_height=256,
            colkey=8,
            chunks=(
                WaterStudyChunk(
                    image=object(),
                    origin_x=0,
                    origin_y=0,
                    width=256,
                    height=256,
                ),
            ),
        )
    }
    monkeypatch.setitem(
        app_module.WATER_STUDY_LAYER_PALETTE_REMAPS,
        "water_highlights_plane_d",
        ((6, 12), (7, 12), (12, 5)),
    )

    def fail_if_motion_is_requested(*args, **kwargs):
        raise AssertionError("approved production plane_d must not use draw-time motion")

    monkeypatch.setattr(app, "water_study_layer_offset", fail_if_motion_is_requested)

    calls = app.draw_water_study_plane("water_highlights_plane_d", 12.0)

    assert calls == 1
    assert app.pyxel.palette_calls == [(), ()]
    assert len(app.pyxel.blt_calls) == 1
