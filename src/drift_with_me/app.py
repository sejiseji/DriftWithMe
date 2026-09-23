from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace
from enum import Enum, auto

from drift_with_me import config
from drift_with_me.audio import AudioEngine
from drift_with_me.build_info import BUILD_LABEL
from drift_with_me.camera import CameraController
from drift_with_me.effects import EffectSystem
from drift_with_me.hex_assets import SpriteAssetLibrary, load_runtime_sprite_library
from drift_with_me.input import DoubleTapMoveRecognizer, PointerInput, Rect
from drift_with_me.math3d import (
    AffineCameraState,
    AffineProjectionProfile,
    CameraState,
    Vec3,
    affine_camera_from_perspective,
    normalize2,
    screen_to_ground_affine,
    screen_to_ground_point,
)
from drift_with_me.model import GameModel, InputIntent, merge_intents
from drift_with_me.pixel_font import draw_pixel_text, pixel_text_size
from drift_with_me.render import Renderer
from drift_with_me.ui_text import UITextRenderer, load_ui_text_renderer
from drift_with_me.water_study_assets import (
    WATER_STUDY_LAYER_IDS,
    WaterStudyPlane,
    load_water_study_planes,
)
from drift_with_me.world import load_world_data


class AppScreen(Enum):
    START = auto()
    PLAY = auto()
    PAUSE = auto()
    WATER_STUDY = auto()


@dataclass(frozen=True)
class PointerSnapshot:
    down: bool
    pressed: bool
    x: float
    y: float


@dataclass
class CombatCameraRestore:
    from_camera: CameraState
    elapsed_sec: float
    duration_sec: float


@dataclass(frozen=True)
class WaterStudyProfile:
    name: str
    layer_ids: tuple[str, ...]


WATER_STUDY_PROFILES: tuple[WaterStudyProfile, ...] = (
    WaterStudyProfile(
        "BASE_ONLY",
        layer_ids=("water_deep_plane_a",),
    ),
    WaterStudyProfile(
        "THREE_LAYER",
        layer_ids=(
            "water_deep_plane_a",
            "water_surface_plane_a",
            "water_surface_caustics_plane_a",
        ),
    ),
    WaterStudyProfile(
        "FULL_SIX",
        layer_ids=WATER_STUDY_LAYER_IDS,
    ),
    WaterStudyProfile(
        "FULL_SIX_OBSERVE",
        layer_ids=WATER_STUDY_LAYER_IDS,
    ),
)

WATER_STUDY_LOGICAL_SIZE = (1024, 512)
WATER_STUDY_CHUNK_SIZE = 256
WATER_STUDY_LAYER_MOTION: dict[str, tuple[float, float, float, float, float, float]] = {
    "water_deep_plane_a": (0.018, 0.01, 0.18, 0.35, 0.25, 0.1),
    "water_mid_plane_a": (0.04, 0.028, 0.55, 0.55, 0.42, 1.0),
    "water_surface_plane_a": (0.065, 0.04, 0.85, 0.8, 0.6, 1.8),
    "water_surface_caustics_plane_a": (0.1, 0.072, 1.1, 1.2, 1.0, 2.6),
    "water_upper_lightnet_plane_a": (0.048, 0.09, 0.95, 0.65, 1.15, 3.4),
    "water_highlights_plane_a": (0.082, 0.055, 0.7, 1.05, 0.72, 4.1),
}


class DriftWithMeApp:
    def __init__(
        self,
        profile: str | None = None,
        headless: bool = False,
        smoke_frames: int | None = None,
    ) -> None:
        import pyxel

        self.pyxel = pyxel
        self.runtime = config.load_runtime_config(profile)
        self.world = load_world_data()
        self.model = GameModel(self.runtime.raw, self.world)
        self.audio = AudioEngine(self.runtime.raw)
        self.effects = EffectSystem(self.runtime.raw)
        self.camera_controller = CameraController(
            self.runtime.raw,
            self.world,
            self.runtime.screen_width,
            self.runtime.screen_height,
            Vec3(self.model.player.x, 0.0, self.model.player.z),
        )
        self.model.snap_buddy(self.camera_controller.current)
        self.renderer: Renderer | None = None
        self.sprite_assets: SpriteAssetLibrary | None = None
        self.screen = AppScreen.START
        self.debug_enabled = False
        self.projection_mode = self.initial_projection_mode()
        self.affine_projection_profile = AffineProjectionProfile.from_config(self.runtime.raw)
        self.presentation_time = 0.0
        self.accumulator = 0.0
        self.hitstop_remaining = 0.0
        self._processed_hitstop_event_ids: set[int] = set()
        self.previous_time: float | None = None
        self.frame = 0
        self.smoke_frames = smoke_frames
        input_config = self.runtime.raw["input"]
        auto_move_config = self.runtime.raw.get("auto_move", {})
        ui_scale = self.runtime.screen_height / float(
            self.runtime.raw["display"]["reference_ui_height"]
        )
        drag_threshold_px = float(input_config["drag_threshold_ref_px"]) * ui_scale
        self.pointer = PointerInput(
            hold_sec=float(input_config["hold_sec"]),
            drag_threshold_px=drag_threshold_px,
            deadzone_px=float(input_config["stick_deadzone_ref_px"]) * ui_scale,
            radius_px=float(input_config["stick_radius_ref_px"]) * ui_scale,
        )
        self.double_tap_move = DoubleTapMoveRecognizer(
            short_tap_sec=float(auto_move_config.get("short_tap_sec", 0.18)),
            max_interval_sec=float(auto_move_config.get("max_interval_sec", 0.3)),
            max_distance_px=float(auto_move_config.get("max_distance_ref_px", 20.0)) * ui_scale,
            drag_threshold_px=drag_threshold_px,
        )
        self.pending_action_pressed = False
        self.pending_interact_pressed = False
        self.pending_auto_move_goal: tuple[float, float] | None = None
        self.pending_cancel_auto_move = False
        self.last_denied_reason = ""
        self.last_denied_remaining = 0.0
        self.location_label_remaining = 0.0
        self.pointer_snapshot = PointerSnapshot(False, False, 0.0, 0.0)
        self.browser_pointer_sequence_seen = 0
        self.last_combat_scene_camera: CameraState | None = None
        self.combat_camera_restore: CombatCameraRestore | None = None
        self.combat_camera_snapshot_zoom: float | None = None
        self.water_study_clock = 0.0
        self.water_study_menu_open = False
        self.water_study_profile_index = 1
        self.water_study_last_draw_ms = 0.0
        self.water_study_last_layer_count = 0
        self.water_study_last_wrap_calls = 0
        self.water_study_planes: dict[str, WaterStudyPlane] = {}

        pyxel.init(
            self.runtime.screen_width,
            self.runtime.screen_height,
            title=config.APP_TITLE,
            fps=self.runtime.target_fps,
            quit_key=None,
            display_scale=self.runtime.desktop_scale,
            headless=headless,
        )
        pyxel.mouse(True)
        self.ui_text = load_ui_text_renderer(pyxel, self.runtime)
        self.sprite_assets = load_runtime_sprite_library(pyxel, self.runtime.raw)
        for error in self.sprite_assets.errors:
            print(f"asset_error: {error}")
        self.audio.setup(pyxel)
        self.renderer = Renderer(pyxel, self.sprite_assets)
        pyxel.run(self.update, self.draw)

    def camera(self) -> CameraState:
        return self.camera_controller.current

    def update_camera_controller(self, elapsed: float) -> CameraState:
        lookahead_x, lookahead_z = self.camera_lookahead_direction()
        return self.camera_controller.update(
            elapsed,
            self.model.player.x,
            self.model.player.z,
            lookahead_x,
            lookahead_z,
        )

    def camera_lookahead_direction(self) -> tuple[float | None, float | None]:
        if (
            self.camera_controller.focus is not None
            or self.camera_controller.sequence is not None
            or self.camera_controller.active_zone_id is not None
        ):
            return None, None

        min_length = float(self.runtime.raw["camera"].get("lookahead_min_direction", 0.05))
        for target_x, target_z in self.model.auto_move_path:
            dx = target_x - self.model.player.x
            dz = target_z - self.model.player.z
            if math.hypot(dx, dz) > min_length:
                return dx, dz

        dx = self.model.player.last_move_x
        dz = self.model.player.last_move_z
        if math.hypot(dx, dz) > min_length:
            return dx, dz
        return None, None

    def initial_projection_mode(self) -> str:
        mode = str(self.runtime.raw.get("projection", {}).get("mode", "perspective"))
        return mode if mode in {"perspective", "affine"} else "perspective"

    def handle_projection_mode_shortcut(self) -> None:
        toggle_key = getattr(self.pyxel, "KEY_V", None)
        if toggle_key is None or not self.pyxel.btnp(toggle_key):
            return
        self.projection_mode = "affine" if self.projection_mode == "perspective" else "perspective"

    def update(self) -> None:
        pyxel = self.pyxel
        elapsed = self.consume_elapsed()
        self.presentation_time += elapsed
        self.frame += 1
        self.pointer_snapshot = self.read_pointer_snapshot()
        self.update_denied_feedback(elapsed)
        self.update_location_label(elapsed)
        if self.screen == AppScreen.PLAY:
            self.update_combat_camera_restore(elapsed)

        f1_key = getattr(pyxel, "KEY_F1", None)
        if f1_key is not None and pyxel.btnp(f1_key):
            self.debug_enabled = not self.debug_enabled
        self.handle_projection_mode_shortcut()
        if self.handle_water_study_shortcut():
            if self.smoke_frames is not None and self.frame >= self.smoke_frames:
                pyxel.quit()
            return
        if pyxel.btnp(pyxel.KEY_M):
            self.audio.toggle_mute()

        if self.screen == AppScreen.START:
            self.update_start_screen()
        elif self.screen == AppScreen.PAUSE:
            self.update_pause_screen()
        elif self.screen == AppScreen.WATER_STUDY:
            self.update_water_study_screen(elapsed)
        else:
            self.update_play_screen(elapsed)

        if self.smoke_frames is not None and self.frame >= self.smoke_frames:
            pyxel.quit()

    def consume_elapsed(self) -> float:
        now = time.monotonic()
        if self.previous_time is None:
            self.previous_time = now
            return self.runtime.fixed_dt
        elapsed = now - self.previous_time
        self.previous_time = now
        max_elapsed = float(self.runtime.raw["simulation"]["max_elapsed_sec"])
        if elapsed > max_elapsed:
            self.model.debug.discarded_elapsed_count += 1
            return max_elapsed
        return max(0.0, elapsed)

    def update_start_screen(self) -> None:
        pyxel = self.pyxel
        if pyxel.btnp(pyxel.KEY_RETURN):
            self.start_game()
            return
        if pyxel.btnp(pyxel.KEY_1):
            self.audio.play_preview("bubble_fired")
        if pyxel.btnp(pyxel.KEY_2):
            self.audio.play_preview("enemy_captured")
        if pyxel.btnp(pyxel.KEY_3):
            self.audio.play_preview("barrier_repelled")
        if pyxel.btnp(pyxel.KEY_4):
            self.audio.play_preview("discharge_succeeded")
        if pyxel.btnp(pyxel.KEY_5):
            self.audio.play_preview("action_denied")

        if self.mouse_pressed_in(self.start_button_rect()):
            self.start_game()
        if self.mouse_pressed_in(self.sound_button_rect()):
            self.audio.toggle_mute()
        for event_name, rect in self.preview_button_rects():
            if self.mouse_pressed_in(rect):
                self.audio.play_preview(event_name)

    def start_game(self) -> None:
        self.pointer.cancel()
        self.cancel_double_tap_move_gesture()
        self.model.cancel_auto_move()
        self.previous_time = None
        self.accumulator = 0.0
        self.hitstop_remaining = 0.0
        self.pending_auto_move_goal = None
        self.pending_cancel_auto_move = False
        self.last_combat_scene_camera = None
        self.combat_camera_restore = None
        self.screen = AppScreen.PLAY
        self.show_location_label()

    def update_pause_screen(self) -> None:
        pyxel = self.pyxel
        self.pointer.cancel()
        self.cancel_double_tap_move_gesture()
        self.model.cancel_auto_move()
        self.pending_auto_move_goal = None
        self.pending_cancel_auto_move = False
        if pyxel.btnp(pyxel.KEY_ESCAPE) or pyxel.btnp(pyxel.KEY_RETURN):
            self.resume_from_pause()
            return
        if pyxel.btnp(pyxel.KEY_R):
            self.reset_scene_for_debug()
        if pyxel.btnp(pyxel.KEY_F):
            self.fill_resources_for_debug()
        if pyxel.btnp(pyxel.KEY_Z):
            self.zero_resources_for_debug()
        if pyxel.btnp(pyxel.KEY_C):
            self.toggle_culling_for_debug()
        if pyxel.btnp(pyxel.KEY_D):
            self.debug_enabled = not self.debug_enabled
        if pyxel.btnp(pyxel.KEY_Q):
            pyxel.quit()
        if self.handle_pause_pointer_controls():
            return
        if self.pointer_snapshot.pressed:
            return

    def resume_from_pause(self) -> None:
        self.screen = AppScreen.PLAY
        self.cancel_double_tap_move_gesture()
        self.previous_time = None

    def can_open_water_study(self) -> bool:
        return (
            self.screen == AppScreen.PLAY
            and self.model.combat_session is None
            and not self.model.world_paused
            and not self.camera_controller.freezes_world
        )

    def clear_world_input_latches(self) -> None:
        self.pointer.cancel()
        self.cancel_double_tap_move_gesture()
        self.pending_action_pressed = False
        self.pending_interact_pressed = False
        self.pending_auto_move_goal = None
        self.pending_cancel_auto_move = False
        self.accumulator = 0.0

    def enter_water_study(self) -> bool:
        if not self.can_open_water_study():
            return False
        self.ensure_water_study_planes()
        self.clear_world_input_latches()
        self.water_study_menu_open = False
        self.water_study_clock = 0.0
        self.screen = AppScreen.WATER_STUDY
        return True

    def ensure_water_study_planes(self) -> None:
        if self.water_study_planes:
            return
        self.water_study_planes = load_water_study_planes(self.pyxel)

    def exit_water_study(self) -> bool:
        if self.screen != AppScreen.WATER_STUDY:
            return False
        self.clear_world_input_latches()
        self.water_study_menu_open = False
        self.previous_time = None
        self.screen = AppScreen.PLAY
        return True

    def handle_water_study_shortcut(self) -> bool:
        pyxel = self.pyxel
        menu_key = getattr(pyxel, "KEY_M", None)
        if menu_key is None or not pyxel.btnp(menu_key):
            return False
        if self.screen == AppScreen.WATER_STUDY:
            self.exit_water_study()
            return True
        if self.can_open_water_study():
            self.enter_water_study()
            return True
        return False

    def update_water_study_screen(self, elapsed: float) -> None:
        self.water_study_clock += max(0.0, elapsed)
        self.clear_world_input_latches()
        self.handle_water_study_profile_shortcuts()
        if self.mouse_pressed_in(self.water_study_close_rect()):
            self.exit_water_study()

    def handle_water_study_profile_shortcuts(self) -> None:
        pyxel = self.pyxel
        for index, key_name in enumerate(("KEY_1", "KEY_2", "KEY_3", "KEY_4")):
            key = getattr(pyxel, key_name, None)
            if key is not None and pyxel.btnp(key):
                self.water_study_profile_index = index
                return

    def water_study_profile(self) -> WaterStudyProfile:
        index = int(getattr(self, "water_study_profile_index", 1))
        return WATER_STUDY_PROFILES[index % len(WATER_STUDY_PROFILES)]

    def water_study_motion_weights(self, elapsed_sec: float) -> tuple[float, float, float]:
        phase_length = 8.0
        blend_length = 2.0
        phase = max(0.0, elapsed_sec) % (phase_length * 3.0)
        mode = int(phase // phase_length)
        local = phase - mode * phase_length
        weights = [0.0, 0.0, 0.0]
        if local < phase_length - blend_length:
            weights[mode] = 1.0
            return weights[0], weights[1], weights[2]
        blend_t = (local - (phase_length - blend_length)) / blend_length
        smooth = blend_t * blend_t * (3.0 - 2.0 * blend_t)
        weights[mode] = 1.0 - smooth
        weights[(mode + 1) % 3] = smooth
        return weights[0], weights[1], weights[2]

    def water_study_layer_offset(
        self,
        elapsed_sec: float,
        *,
        speed_x: float,
        speed_y: float,
        sine_amp: float,
        orbit_x: float,
        orbit_y: float,
        phase: float,
    ) -> tuple[float, float]:
        calm, wide, circular = self.water_study_motion_weights(elapsed_sec)
        amp = sine_amp * (0.35 * calm + 1.0 * wide + 0.7 * circular)
        orbit_scale = 0.2 * calm + 0.45 * wide + 1.0 * circular
        x = elapsed_sec * speed_x
        x += amp * math.sin(elapsed_sec * 0.55 + phase)
        x += orbit_x * orbit_scale * math.cos(elapsed_sec * 0.42 + phase * 1.7)
        y = elapsed_sec * speed_y
        y += amp * 0.65 * math.sin(elapsed_sec * 0.38 + phase * 0.7)
        y += orbit_y * orbit_scale * math.sin(elapsed_sec * 0.46 + phase * 1.3)
        return x, y

    def reset_scene_for_debug(self) -> None:
        self.model.reset_scene()
        self.audio.reset_event_history()
        self.effects.reset()
        self.camera_controller.reset(Vec3(self.model.player.x, 0.0, self.model.player.z))
        self.model.snap_buddy(self.camera())
        self.pointer.cancel()
        self.cancel_double_tap_move_gesture()
        self.pending_action_pressed = False
        self.pending_interact_pressed = False
        self.pending_auto_move_goal = None
        self.pending_cancel_auto_move = False
        self.last_denied_reason = ""
        self.last_denied_remaining = 0.0
        self.show_location_label()
        self.previous_time = None
        self.accumulator = 0.0
        self.hitstop_remaining = 0.0
        self._processed_hitstop_event_ids.clear()
        self.last_combat_scene_camera = None
        self.combat_camera_restore = None

    def fill_resources_for_debug(self) -> None:
        self.model.water = self.model.water_max
        self.model.energy = self.model.energy_max
        self.last_denied_reason = ""
        self.last_denied_remaining = 0.0

    def zero_resources_for_debug(self) -> None:
        self.model.water = 0.0
        self.model.energy = 0.0
        self.model.player.barrier_active = False
        self.last_denied_reason = ""
        self.last_denied_remaining = 0.0

    def toggle_culling_for_debug(self) -> None:
        self.model.culling_enabled = not self.model.culling_enabled
        self.model.refresh_active_enemies()

    def handle_pause_pointer_controls(self) -> bool:
        if self.mouse_pressed_in(self.resume_button_rect()):
            self.resume_from_pause()
            return True
        if self.mouse_pressed_in(self.pause_reset_button_rect()):
            self.reset_scene_for_debug()
            return True
        if self.mouse_pressed_in(self.pause_audio_button_rect()):
            self.audio.toggle_mute()
            return True
        if self.mouse_pressed_in(self.pause_dev_entry_button_rect()):
            self.debug_enabled = not self.debug_enabled
            return True
        return False

    def cancel_double_tap_move_gesture(self) -> None:
        recognizer = getattr(self, "double_tap_move", None)
        if recognizer is not None:
            recognizer.cancel()

    def update_play_screen(self, elapsed: float) -> None:
        pyxel = self.pyxel
        if pyxel.btnp(pyxel.KEY_ESCAPE):
            if self.model.world_paused:
                self.process_events(self.model.cancel_interaction())
                self.camera_controller.cancel_focus()
            self.screen = AppScreen.PAUSE
            self.pointer.cancel()
            self.cancel_double_tap_move_gesture()
            self.pending_auto_move_goal = None
            self.pending_cancel_auto_move = False
            self.model.cancel_auto_move()
            return
        if self.mouse_pressed_in(self.pause_button_rect()):
            if self.model.world_paused:
                self.process_events(self.model.cancel_interaction())
                self.camera_controller.cancel_focus()
            self.screen = AppScreen.PAUSE
            self.pointer.cancel()
            self.cancel_double_tap_move_gesture()
            self.pending_auto_move_goal = None
            self.pending_cancel_auto_move = False
            self.model.cancel_auto_move()
            return
        if self.mouse_pressed_in(self.sound_button_rect()):
            self.audio.toggle_mute()
            return
        if self.handle_water_study_menu_pointer_controls():
            return

        self.handle_debug_camera_shortcuts()
        if self.model.world_paused:
            self.pointer.cancel()
            self.cancel_double_tap_move_gesture()
            self.pending_auto_move_goal = None
            self.pending_cancel_auto_move = False
            interaction = self.model.interaction
            if interaction is not None and interaction.kind in {"water_refill", "energy_refill"}:
                if self.mouse_pressed_in(self.interact_button_rect()):
                    self.process_events(self.model.cancel_interaction())
                    self.camera_controller.cancel_focus()
                    self.update_camera_controller(elapsed)
                    return
                if pyxel.btnp(pyxel.KEY_RETURN):
                    self.process_events(self.model.complete_interaction())
                    self.update_camera_controller(elapsed)
                    return
            elif interaction is not None and interaction.kind == "inspect":
                if not self.inspect_completion_requested():
                    paused_events = self.model.update_paused(elapsed)
                    self.update_camera_controller(elapsed)
                    self.process_events(paused_events)
                    self.effects.update(elapsed, self.model)
                    return
                self.process_events(self.model.complete_interaction())
                self.camera_controller.cancel_focus()
                self.update_camera_controller(elapsed)
                return
            paused_events = self.model.update_paused(elapsed)
            self.update_camera_controller(elapsed)
            self.process_events(paused_events)
            self.effects.update(elapsed, self.model)
            return

        input_camera = self.camera()
        if self.camera_controller.freezes_world:
            self.pointer.cancel()
            self.cancel_double_tap_move_gesture()
            self.pending_auto_move_goal = None
            self.pending_cancel_auto_move = False
            self.model.cancel_auto_move()
            self.update_camera_controller(elapsed)
            self.effects.update(elapsed, self.model)
            return

        keyboard_intent = self.keyboard_intent()
        pointer_intent = self.pointer_intent(elapsed)
        ui_button_intent = self.ui_button_intent()
        ground_pointer_cancel_intent = self.ground_pointer_cancel_intent()
        double_tap_intent = self.double_tap_move_intent(elapsed, self.scene_camera(input_camera))
        if keyboard_intent.action_pressed or ui_button_intent.action_pressed:
            self.pending_action_pressed = True
        if keyboard_intent.interact_pressed or ui_button_intent.interact_pressed:
            self.pending_interact_pressed = True
        base_intent = merge_intents(
            keyboard_intent,
            pointer_intent,
            ui_button_intent,
            ground_pointer_cancel_intent,
            double_tap_intent,
        )
        if base_intent.auto_move_goal_x is not None and base_intent.auto_move_goal_z is not None:
            self.pending_auto_move_goal = (
                base_intent.auto_move_goal_x,
                base_intent.auto_move_goal_z,
            )
            self.pending_cancel_auto_move = False
        elif base_intent.cancel_auto_move:
            self.pending_cancel_auto_move = True
        if self.update_hitstop(elapsed, base_intent):
            return

        self.accumulator += elapsed
        fixed_dt = self.runtime.fixed_dt
        max_steps = int(self.runtime.raw["simulation"]["max_steps_per_callback"])
        steps = 0
        all_events = []
        while self.accumulator >= fixed_dt and steps < max_steps:
            first_step = steps == 0
            pending_auto_move_goal = self.pending_auto_move_goal if first_step else None
            one_shot_auto_goal_x = (
                pending_auto_move_goal[0] if pending_auto_move_goal is not None else None
            )
            one_shot_auto_goal_z = (
                pending_auto_move_goal[1] if pending_auto_move_goal is not None else None
            )
            one_shot_cancel_auto_move = self.pending_cancel_auto_move if first_step else False
            step_intent = InputIntent(
                screen_x=base_intent.screen_x,
                screen_y=base_intent.screen_y,
                strength=base_intent.strength,
                barrier=base_intent.barrier,
                action_pressed=self.pending_action_pressed,
                interact_pressed=self.pending_interact_pressed,
                auto_move_goal_x=one_shot_auto_goal_x,
                auto_move_goal_z=one_shot_auto_goal_z,
                cancel_auto_move=one_shot_cancel_auto_move,
            )
            self.pending_action_pressed = False
            self.pending_interact_pressed = False
            model_camera = (
                self.scene_camera(input_camera)
                if self.model.combat_session is not None
                else input_camera
            )
            events = self.model.step(step_intent, model_camera, fixed_dt)
            if first_step:
                self.pending_auto_move_goal = None
                self.pending_cancel_auto_move = False
            all_events.extend(events)
            self.accumulator -= fixed_dt
            steps += 1
            if self.model.world_paused:
                self.accumulator = 0.0
                break

        self.update_camera_controller(elapsed)

        if steps >= max_steps and self.accumulator >= fixed_dt:
            self.accumulator = 0.0
            self.model.debug.discarded_elapsed_count += 1
        self.model.debug.fixed_steps_last_callback = steps
        self.process_events(all_events)
        self.effects.update(elapsed, self.model)

    def handle_water_study_menu_pointer_controls(self) -> bool:
        if self.mouse_pressed_in(self.water_study_menu_button_rect()):
            self.water_study_menu_open = not self.water_study_menu_open
            self.clear_world_input_latches()
            return True
        if not self.water_study_menu_open:
            return False
        pointer = self.pointer_snapshot
        if not pointer.pressed:
            return False
        if self.water_study_menu_item_rect().contains(pointer.x, pointer.y):
            self.enter_water_study()
            return True
        self.water_study_menu_open = False
        self.clear_world_input_latches()
        return True

    def process_events(self, events) -> None:
        if not events:
            return
        for event in events:
            if event.kind == "combat_started":
                self.combat_camera_restore = None
                self.combat_camera_snapshot_zoom = self.camera_zoom(self.camera())
            elif event.kind == "combat_restored":
                self.start_combat_camera_restore()
            elif event.kind == "action_denied":
                self.set_denied_reason(str(event.payload.get("reason", "denied")))
            elif event.kind == "inspection_completed":
                self.show_location_label()
            elif event.kind == "interaction_started" and event.target_id is not None:
                target = self.world.object_by_id(event.target_id)
                interaction_kind = str(event.payload.get("interaction_kind", ""))
                hold_sec = (
                    math.inf
                    if interaction_kind == "inspect"
                    else float(event.payload.get("duration_sec", 0.8)) + 0.15
                )
                if interaction_kind == "water_refill":
                    self.camera_controller.start_focus_point(
                        self.player_focus_point(), hold_sec=hold_sec
                    )
                elif interaction_kind == "energy_refill":
                    self.camera_controller.start_focus_point(
                        self.buddy_focus_point(), hold_sec=hold_sec
                    )
                elif target is not None:
                    self.camera_controller.start_focus_demo(target, hold_sec=hold_sec)
                else:
                    enemy = self.model.enemy_by_id(event.target_id)
                    if enemy is not None:
                        self.camera_controller.start_focus_point(
                            self.enemy_focus_point(enemy), hold_sec=hold_sec
                        )
        camera_reaction_delay = self.request_hitstop_from_events(events)
        self.effects.process_events(
            events,
            self.model,
            camera_reaction_delay=camera_reaction_delay,
            camera_reactions_allowed=self.combat_camera_reactions_allowed(),
        )
        self.audio.play_events(events)

    def update_hitstop(self, elapsed: float, intent: InputIntent) -> bool:
        if self.hitstop_remaining <= 0.0:
            return False
        if not intent.barrier:
            self.model.player.barrier_active = False
        self.hitstop_remaining = max(0.0, self.hitstop_remaining - max(0.0, elapsed))
        self.accumulator = 0.0
        self.model.debug.fixed_steps_last_callback = 0
        self.effects.update(elapsed, self.model)
        return True

    def request_hitstop_from_events(self, events) -> float:
        effects_config = self.runtime.raw["effects"]
        if not bool(effects_config.get("hitstop_enabled", False)):
            return 0.0
        event_durations = effects_config.get("hitstop_event_ms", {})
        cap_sec = float(effects_config.get("hitstop_hard_cap_ms", 66.6666666667)) / 1000.0
        requested = 0.0
        for event in events:
            if event.event_id in self._processed_hitstop_event_ids:
                continue
            duration_ms = float(event_durations.get(event.kind, 0.0))
            if duration_ms <= 0.0:
                continue
            self._processed_hitstop_event_ids.add(event.event_id)
            requested = max(requested, min(duration_ms / 1000.0, cap_sec))
        if requested > 0.0:
            self.hitstop_remaining = max(self.hitstop_remaining, requested)
            self.accumulator = 0.0
            return self.hitstop_remaining
        return 0.0

    def player_focus_point(self) -> Vec3:
        return Vec3(
            self.model.player.x,
            self.model.player_cube_size * 0.5,
            self.model.player.z,
        )

    def buddy_focus_point(self) -> Vec3:
        return Vec3(
            self.model.buddy.x,
            max(0.0, self.model.buddy.y - self.model.buddy_cube_size),
            self.model.buddy.z,
        )

    def enemy_focus_point(self, enemy) -> Vec3:
        return Vec3(enemy.x, max(6.0, self.model.enemy_radius(enemy)), enemy.z)

    def combat_camera_reactions_allowed(self) -> bool:
        return (
            self.camera_controller.mode_name in {"FOLLOW", "OVERVIEW"}
            and self.camera_controller.base_blend is None
        )

    def handle_debug_camera_shortcuts(self) -> None:
        pyxel = self.pyxel
        focus_key = getattr(pyxel, "KEY_F", None)
        pan_key = getattr(pyxel, "KEY_P", None)
        if focus_key is not None and pyxel.btnp(focus_key):
            focus_target = self.nearest_focus_object()
            if focus_target is not None:
                self.camera_controller.start_focus_demo(focus_target)
        if pan_key is not None and pyxel.btnp(pan_key):
            self.camera_controller.start_pan_demo()

    def nearest_focus_object(self):
        inspectables = [obj for obj in self.world.objects if obj.inspectable]
        if not inspectables:
            return None
        return min(
            inspectables,
            key=lambda obj: (
                (obj.x - self.model.player.x) ** 2 + (obj.z - self.model.player.z) ** 2,
                obj.id,
            ),
        )

    def keyboard_intent(self) -> InputIntent:
        pyxel = self.pyxel
        action_mode = self.action_button_mode()
        screen_x = float(pyxel.btn(pyxel.KEY_RIGHT) or pyxel.btn(pyxel.KEY_D))
        screen_x -= float(pyxel.btn(pyxel.KEY_LEFT) or pyxel.btn(pyxel.KEY_A))
        screen_y = float(pyxel.btn(pyxel.KEY_DOWN) or pyxel.btn(pyxel.KEY_S))
        screen_y -= float(pyxel.btn(pyxel.KEY_UP) or pyxel.btn(pyxel.KEY_W))
        direction = normalize2(screen_x, screen_y)
        strength = 1.0 if abs(screen_x) > 0.0 or abs(screen_y) > 0.0 else 0.0
        action_down = pyxel.btn(pyxel.KEY_X)
        return InputIntent(
            screen_x=direction.x,
            screen_y=direction.y,
            strength=strength,
            barrier=pyxel.btn(pyxel.KEY_SPACE) or (action_mode == "GUARD" and action_down),
            action_pressed=False if action_mode == "GUARD" else pyxel.btnp(pyxel.KEY_X),
            interact_pressed=pyxel.btnp(pyxel.KEY_E),
        )

    def read_pointer_snapshot(self) -> PointerSnapshot:
        browser_pointer = self.read_browser_pointer_snapshot()
        if browser_pointer is not None:
            return browser_pointer

        pyxel = self.pyxel
        mouse_button = getattr(pyxel, "MOUSE_BUTTON_LEFT", 0)
        x, y = self.clamp_pointer_position(float(pyxel.mouse_x), float(pyxel.mouse_y))
        return PointerSnapshot(
            down=pyxel.btn(mouse_button),
            pressed=pyxel.btnp(mouse_button),
            x=x,
            y=y,
        )

    def read_browser_pointer_snapshot(self) -> PointerSnapshot | None:
        try:
            import js  # type: ignore[import-not-found]
        except ImportError:
            return None

        try:
            bridge = getattr(js.window, "__driftWithMePointer", None)
        except Exception:
            return None
        if bridge is None:
            return None

        try:
            down = bool(bridge.down)
            pressed_flag = bool(bridge.pressed)
            sequence = int(bridge.sequence)
            x = float(bridge.x)
            y = float(bridge.y)
        except Exception:
            return None
        if not math.isfinite(x) or not math.isfinite(y):
            return None

        pressed = pressed_flag and sequence != self.browser_pointer_sequence_seen
        if pressed:
            self.browser_pointer_sequence_seen = sequence
        x, y = self.clamp_pointer_position(x, y)
        return PointerSnapshot(down=down, pressed=pressed, x=x, y=y)

    def clamp_pointer_position(self, x: float, y: float) -> tuple[float, float]:
        max_x = float(self.runtime.screen_width - 1)
        max_y = float(self.runtime.screen_height - 1)
        return max(0.0, min(max_x, x)), max(0.0, min(max_y, y))

    def pointer_intent(self, elapsed: float) -> InputIntent:
        pointer = self.pointer_snapshot
        return self.pointer.update(
            down=pointer.down,
            x=pointer.x,
            y=pointer.y,
            dt=elapsed,
            ui_rects=self.active_ui_rects(),
        )

    def ground_pointer_cancel_intent(self) -> InputIntent:
        pointer = self.pointer_snapshot
        if not pointer.pressed:
            return InputIntent()
        if any(rect.contains(pointer.x, pointer.y) for rect in self.active_ui_rects()):
            return InputIntent()
        return InputIntent(cancel_auto_move=True)

    def double_tap_move_intent(
        self, elapsed: float, camera: CameraState | AffineCameraState
    ) -> InputIntent:
        if not bool(self.runtime.raw.get("auto_move", {}).get("enabled", False)):
            return InputIntent()
        pointer = self.pointer_snapshot
        request = self.double_tap_move.update(
            down=pointer.down,
            x=pointer.x,
            y=pointer.y,
            dt=elapsed,
            ui_rects=self.active_ui_rects(),
            camera=camera,
            accepting_world_input=self.hitstop_remaining <= 0.0,
        )
        if request is None:
            return InputIntent()

        point = self.screen_to_ground(request.camera, request.screen_x, request.screen_y)
        if point is None or not self.world.walkable_rect.contains_point(point.x, point.y):
            self.reject_auto_move_goal("auto_move_blocked")
            return InputIntent()
        if self.foreground_object_blocks_ground_pick(
            request.camera, request.screen_x, request.screen_y, point.x, point.y
        ):
            self.reject_auto_move_goal("auto_move_blocked")
            return InputIntent()
        return InputIntent(auto_move_goal_x=point.x, auto_move_goal_z=point.y)

    def screen_to_ground(
        self, camera: CameraState | AffineCameraState, screen_x: float, screen_y: float
    ):
        if isinstance(camera, AffineCameraState):
            return screen_to_ground_affine(camera, screen_x, screen_y)
        return screen_to_ground_point(camera, screen_x, screen_y)

    def foreground_object_blocks_ground_pick(
        self,
        camera: CameraState | AffineCameraState,
        screen_x: float,
        screen_y: float,
        ground_x: float,
        ground_z: float,
    ) -> bool:
        auto_move = self.runtime.raw.get("auto_move", {})
        if not bool(auto_move.get("foreground_pick_block_enabled", True)):
            return False
        renderer = self.renderer
        if renderer is None:
            return False
        ground_projection = camera.project(Vec3(ground_x, 0.0, ground_z))
        if ground_projection is None:
            return False
        margin = self.foreground_pick_margin_px()
        for obj in self.world.objects:
            if not (obj.solid or obj.occludes_player or obj.inspectable):
                continue
            obj_depth = renderer.object_occlusion_depth(obj, camera)
            if obj_depth is None or obj_depth > ground_projection.depth + 1e-6:
                continue
            bounds = renderer.object_ground_pick_block_bounds(obj, camera)
            if bounds is not None and bounds.contains(screen_x, screen_y, margin):
                return True
        return False

    def foreground_pick_margin_px(self) -> float:
        auto_move = self.runtime.raw.get("auto_move", {})
        ui_scale = self.runtime.screen_height / float(
            self.runtime.raw["display"]["reference_ui_height"]
        )
        return float(auto_move.get("foreground_pick_margin_ref_px", 2.0)) * ui_scale

    def reject_auto_move_goal(self, reason: str) -> None:
        self.set_denied_reason(reason)
        self.audio.play_preview("action_denied")

    def set_denied_reason(self, reason: str) -> None:
        self.last_denied_reason = reason
        self.last_denied_remaining = self.denied_feedback_duration()

    def update_denied_feedback(self, elapsed: float) -> None:
        if not self.last_denied_reason:
            self.last_denied_remaining = 0.0
            return
        remaining = getattr(self, "last_denied_remaining", 0.0)
        if remaining <= 0.0:
            self.last_denied_reason = ""
            self.last_denied_remaining = 0.0
            return
        self.last_denied_remaining = max(0.0, remaining - max(0.0, elapsed))
        if self.last_denied_remaining <= 0.0:
            self.last_denied_reason = ""

    def denied_feedback_duration(self) -> float:
        return max(0.0, float(self.runtime.raw.get("ui", {}).get("denied_feedback_sec", 1.2)))

    def location_label_duration(self) -> float:
        return max(0.0, float(self.runtime.raw.get("ui", {}).get("location_label_sec", 2.4)))

    def show_location_label(self) -> None:
        self.location_label_remaining = self.location_label_duration()

    def update_location_label(self, elapsed: float) -> None:
        remaining = getattr(self, "location_label_remaining", 0.0)
        if remaining <= 0.0:
            self.location_label_remaining = 0.0
            return
        self.location_label_remaining = max(0.0, remaining - max(0.0, elapsed))

    def location_label_visible(self) -> bool:
        return (
            bool(getattr(self, "debug_enabled", False))
            or getattr(self, "location_label_remaining", 0.0) > 0.0
        )

    def ui_button_intent(self) -> InputIntent:
        action_mode = self.action_button_mode()
        if action_mode == "GUARD":
            return InputIntent(barrier=self.mouse_down_in(self.action_button_rect()))
        return InputIntent(
            action_pressed=self.mouse_pressed_in(self.action_button_rect()),
            interact_pressed=self.mouse_pressed_in(self.interact_button_rect()),
        )

    def mouse_pressed_in(self, rect: Rect) -> bool:
        pointer = self.pointer_snapshot
        return pointer.pressed and rect.contains(pointer.x, pointer.y)

    def mouse_down_in(self, rect: Rect) -> bool:
        pointer = self.pointer_snapshot
        return pointer.down and rect.contains(pointer.x, pointer.y)

    def inspect_completion_requested(self) -> bool:
        pyxel = self.pyxel
        if pyxel.btnp(pyxel.KEY_RETURN):
            return True
        pointer = self.pointer_snapshot
        if not pointer.pressed:
            return False
        if self.interaction_done_button_rect().contains(pointer.x, pointer.y):
            return True
        return not self.inspect_panel_rect().contains(pointer.x, pointer.y)

    def active_ui_rects(self) -> tuple[Rect, ...]:
        if getattr(self, "screen", AppScreen.PLAY) == AppScreen.WATER_STUDY:
            return (self.water_study_close_rect(),)
        interaction = self.model.interaction
        if interaction is not None and interaction.kind == "inspect":
            return (
                self.pause_button_rect(),
                self.sound_button_rect(),
                self.inspect_panel_rect(),
                self.interaction_done_button_rect(),
            )
        rects = [
            self.action_button_rect(),
            self.interact_button_rect(),
            self.pause_button_rect(),
            self.sound_button_rect(),
            self.minimap_rect(),
            self.water_study_menu_button_rect(),
        ]
        if getattr(self, "water_study_menu_open", False):
            rects.append(self.water_study_menu_panel_rect())
            rects.append(self.water_study_menu_item_rect())
        if interaction is not None and interaction.kind in {"water_refill", "energy_refill"}:
            rects.append(self.interaction_chip_rect())
        elif self.last_denied_reason:
            rects.append(self.tooltip_rect(two_lines=False))
        return tuple(rects)

    def ui_numeric_layout(self) -> dict:
        layout = getattr(self, "_ui_numeric_layout", None)
        if layout is None:
            layout = config.load_data_json("ui_numeric_layout.json")
            self._ui_numeric_layout = layout
        return layout

    def ui_profile_layout(self) -> dict:
        profiles = self.ui_numeric_layout()["profiles"]
        return profiles.get(self.runtime.profile.name, profiles["medium"])

    def ui_theme(self) -> dict:
        return self.ui_numeric_layout()["theme"]

    def ui_rect(self, name: str) -> Rect:
        rect = self.ui_profile_layout()["rects"][name]
        return Rect(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))

    def optional_ui_rect(self, name: str, fallback: str) -> Rect:
        rects = self.ui_profile_layout()["rects"]
        rect = rects.get(name, rects[fallback])
        return Rect(float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))

    def action_button_rect(self) -> Rect:
        return self.ui_rect("primary_action")

    def action_button_visual_rect(self) -> Rect:
        return self.optional_ui_rect("primary_action_visual", "primary_action")

    def interact_button_rect(self) -> Rect:
        return self.ui_rect("context_action")

    def interact_button_visual_rect(self) -> Rect:
        return self.optional_ui_rect("context_action_visual", "context_action")

    def pause_button_rect(self) -> Rect:
        return self.ui_rect("pause_hit")

    def sound_button_rect(self) -> Rect:
        return self.ui_rect("sound_hit")

    def pause_visual_rect(self) -> Rect:
        return self.ui_rect("pause_visual")

    def sound_visual_rect(self) -> Rect:
        return self.ui_rect("sound_visual")

    def resource_panel_rect(self) -> Rect:
        return self.ui_rect("resource")

    def minimap_rect(self) -> Rect:
        return self.ui_rect("minimap")

    def minimap_visual_rect(self) -> Rect:
        return self.optional_ui_rect("minimap_visual", "minimap")

    def location_rect(self) -> Rect:
        return self.ui_rect("location")

    def wordmark_rect(self) -> Rect:
        return self.ui_rect("wordmark")

    def tooltip_rect(self, two_lines: bool) -> Rect:
        return self.ui_rect("tooltip_two" if two_lines else "tooltip_one")

    def start_button_rect(self) -> Rect:
        return Rect(self.runtime.screen_width / 2 - 70, 88, 140, 46)

    def pause_panel_rect(self) -> Rect:
        return self.ui_rect("pause_panel")

    def pause_control_rect(self, column: int, row: int) -> Rect:
        ids = (("resume", "reset"), ("pause_audio", "dev_entry"))
        return self.ui_rect(ids[row][column])

    def resume_button_rect(self) -> Rect:
        return self.ui_rect("resume")

    def pause_reset_button_rect(self) -> Rect:
        return self.ui_rect("reset")

    def pause_audio_button_rect(self) -> Rect:
        return self.ui_rect("pause_audio")

    def pause_dev_entry_button_rect(self) -> Rect:
        return self.ui_rect("dev_entry")

    def pause_fill_button_rect(self) -> Rect:
        return self.pause_audio_button_rect()

    def pause_zero_button_rect(self) -> Rect:
        return self.pause_dev_entry_button_rect()

    def pause_culling_button_rect(self) -> Rect:
        return self.pause_audio_button_rect()

    def pause_debug_button_rect(self) -> Rect:
        return self.pause_dev_entry_button_rect()

    def interaction_done_button_rect(self) -> Rect:
        return self.ui_rect("inspect_done")

    def inspect_panel_rect(self) -> Rect:
        return self.ui_rect("inspect_panel")

    def inspect_title_rect(self) -> Rect:
        return self.ui_rect("inspect_title")

    def inspect_text_rect(self) -> Rect:
        return self.ui_rect("inspect_text")

    def inspect_page_rect(self) -> Rect:
        return self.ui_rect("inspect_page")

    def interaction_chip_rect(self) -> Rect:
        profile = self.ui_profile_layout()
        rects = profile.get("rects", {})
        if "progress_chip" in rects:
            return self.ui_rect("progress_chip")
        progress_w, progress_h = profile.get("progress", [160, 64])
        width = float(progress_w)
        height = float(progress_h)
        interaction = getattr(self.model, "interaction", None)
        if interaction is None:
            return self.fallback_progress_rect(width, height)
        target_rect = self.progress_target_screen_rect(interaction)
        if target_rect is None:
            return self.fallback_progress_rect(width, height)

        gap = 12.0 if self.runtime.profile.name != "high" else 15.0
        center_x = target_rect.x + target_rect.width / 2
        center_y = target_rect.y + target_rect.height / 2
        candidates = (
            Rect(center_x - width / 2, target_rect.y - height - gap, width, height),
            Rect(target_rect.x + target_rect.width + gap, center_y - height / 2, width, height),
            Rect(target_rect.x - width - gap, center_y - height / 2, width, height),
            Rect(center_x - width / 2, target_rect.y + target_rect.height + gap, width, height),
        )
        blockers = self.progress_popup_blockers(target_rect)
        for candidate in candidates:
            rect = self.clamp_ui_rect(candidate, margin=4.0)
            if not any(self.rects_overlap(rect, blocker) for blocker in blockers):
                return rect
        return self.fallback_progress_rect(width, height)

    def fallback_progress_rect(self, width: float, height: float) -> Rect:
        x = self.runtime.screen_width / 2 - width / 2
        y = self.runtime.screen_height - height - 8.0
        return self.clamp_ui_rect(Rect(x, y, width, height), margin=4.0)

    def water_study_menu_button_rect(self) -> Rect:
        width = 58.0 if self.runtime.profile.name != "high" else 70.0
        height = 22.0 if self.runtime.profile.name != "high" else 26.0
        x = float(self.runtime.screen_width) - width - 8.0
        y = self.build_label_rect().y + self.build_label_rect().height + 5.0
        return self.clamp_ui_rect(Rect(x, y, width, height), margin=4.0)

    def water_study_menu_panel_rect(self) -> Rect:
        width = 124.0 if self.runtime.profile.name != "high" else 150.0
        height = 54.0 if self.runtime.profile.name != "high" else 62.0
        button = self.water_study_menu_button_rect()
        x = float(self.runtime.screen_width) - width - 8.0
        y = button.y + button.height + 4.0
        return self.clamp_ui_rect(Rect(x, y, width, height), margin=4.0)

    def water_study_menu_item_rect(self) -> Rect:
        panel = self.water_study_menu_panel_rect()
        return Rect(panel.x + 8.0, panel.y + 16.0, panel.width - 16.0, panel.height - 24.0)

    def water_study_close_rect(self) -> Rect:
        width = 64.0 if self.runtime.profile.name != "high" else 78.0
        height = 24.0 if self.runtime.profile.name != "high" else 28.0
        return Rect(float(self.runtime.screen_width) - width - 8.0, 10.0, width, height)

    def progress_target_screen_rect(self, interaction) -> Rect | None:
        camera = self.scene_camera(self.camera())
        if interaction.kind == "energy_refill":
            point = camera.project(self.buddy_focus_point())
            half_w = 14.0
            half_h = 18.0
        else:
            point = camera.project(self.player_focus_point())
            half_w = 16.0
            half_h = 18.0
        if point is None:
            return None
        return Rect(point.x - half_w, point.y - half_h, half_w * 2.0, half_h * 2.0)

    def progress_popup_blockers(self, target_rect: Rect) -> tuple[Rect, ...]:
        return (
            self.expand_rect(target_rect, 6.0),
            self.resource_panel_rect(),
            self.pause_button_rect(),
            self.sound_button_rect(),
            self.interact_button_rect(),
            self.action_button_rect(),
            self.minimap_rect(),
            self.location_rect(),
        )

    def clamp_ui_rect(self, rect: Rect, margin: float) -> Rect:
        x = max(margin, min(float(self.runtime.screen_width) - rect.width - margin, rect.x))
        y = max(margin, min(float(self.runtime.screen_height) - rect.height - margin, rect.y))
        return Rect(x, y, rect.width, rect.height)

    def expand_rect(self, rect: Rect, amount: float) -> Rect:
        return Rect(
            rect.x - amount,
            rect.y - amount,
            rect.width + amount * 2.0,
            rect.height + amount * 2.0,
        )

    def rects_overlap(self, a: Rect, b: Rect) -> bool:
        return (
            a.x < b.x + b.width
            and a.x + a.width > b.x
            and a.y < b.y + b.height
            and a.y + a.height > b.y
        )

    def preview_button_rects(self) -> tuple[tuple[str, Rect], ...]:
        names = self.audio.preview_events
        start_x = self.runtime.screen_width / 2 - 132
        y = 150
        return tuple(
            (name, Rect(start_x + index * 54, y, 48, 36)) for index, name in enumerate(names)
        )

    def draw(self) -> None:
        if self.screen == AppScreen.START:
            self.draw_start()
        elif self.screen == AppScreen.PAUSE:
            self.draw_play()
            self.draw_pause()
        elif self.screen == AppScreen.WATER_STUDY:
            self.draw_water_study()
        else:
            self.draw_play()
        if self.build_label_visible():
            self.draw_build_label()

    def build_label_visible(self) -> bool:
        mode = str(self.runtime.raw.get("ui", {}).get("build_label_mode", "always"))
        if mode == "hidden":
            return False
        if mode == "debug":
            return bool(getattr(self, "debug_enabled", False))
        return True

    def build_label_rect(self) -> Rect:
        text = BUILD_LABEL.upper()
        scale = 1
        text_width, text_height = pixel_text_size(text, scale)
        box_width = text_width + 6
        box_height = text_height + 5
        x = self.runtime.screen_width - box_width - 4
        y = 42
        return Rect(float(x), float(y), float(box_width), float(box_height))

    def draw_build_label(self) -> None:
        text = BUILD_LABEL.upper()
        scale = 1
        rect = self.build_label_rect()
        x = int(rect.x)
        y = int(rect.y)
        box_width = int(rect.width)
        box_height = int(rect.height)
        self.pyxel.rect(x, y, box_width, box_height, 0)
        self.pyxel.rectb(x, y, box_width, box_height, 13)
        draw_pixel_text(self.pyxel, x + 3, y + 2, text, 7, scale=scale)

    def draw_combat_chance_cues(self) -> None:
        active_cues = [
            cue
            for cue in self.effects.screen_cues
            if cue.kind in {"combat_bubble_chance", "combat_zap_chance"}
        ]
        if not active_cues:
            return
        cue = active_cues[-1]
        if cue.kind == "combat_bubble_chance":
            text = "捕縛チャンス！"
            color = 12
        else:
            text = "電撃チャンス！"
            color = 10
        progress = cue.progress
        text_width = self.ui_renderer.text_width(text, "tooltip")
        text_height = self.ui_renderer.text_height("tooltip")
        width = max(116, min(178, text_width + 24))
        height = max(26, text_height + 12)
        x = int((self.runtime.screen_width - width) / 2)
        y = int(self.runtime.screen_height * 0.52 - height / 2 - (1.0 - progress) * 5)
        rect = Rect(float(x), float(y), float(width), float(height))
        self.draw_panel_frame(rect, fill=0, inner=color)
        if progress < 0.18:
            pulse_w = int(width * (1.0 - progress / 0.18))
            self.pyxel.line(x - pulse_w // 3, y + height // 2, x - 4, y + height // 2, color)
            self.pyxel.line(
                x + width + 4,
                y + height // 2,
                x + width + pulse_w // 3,
                y + height // 2,
                color,
            )
        self.draw_ui_text_center(
            int(rect.x + rect.width / 2),
            int(rect.y + rect.height / 2 - text_height / 2 + 4),
            text,
            color,
            "tooltip",
        )

    def draw_start(self) -> None:
        pyxel = self.pyxel
        pyxel.cls(1)
        self.draw_text_center(self.runtime.screen_width // 2, 28, "DriftWithMe", 7, scale=3)
        self.draw_text_center(self.runtime.screen_width // 2, 54, "Jack World P0 JWP007", 10)
        self.draw_button(self.start_button_rect(), self.ui("ui.start"), 11)
        self.draw_system_button(self.sound_button_rect(), self.sound_visual_rect(), "sound")
        self.draw_ui_text_center(
            self.runtime.screen_width // 2, 124, self.ui("ui.se_preview"), 7, "label"
        )
        for index, (event_name, rect) in enumerate(self.preview_button_rects(), start=1):
            self.draw_button(rect, str(index), 5)
            label = event_name.split("_", maxsplit=1)[0][:6]
            self.draw_text_center(
                int(rect.x + rect.width / 2),
                int(rect.y + rect.height + 5),
                label,
                7,
                scale=1,
            )
        self.draw_ui_text_center(
            self.runtime.screen_width // 2,
            self.runtime.screen_height - 18,
            self.ui("ui.start_hint"),
            13,
            "hint",
        )

    def draw_water_study(self) -> None:
        pyxel = self.pyxel
        started_at = time.perf_counter()
        t = self.water_study_clock
        profile = self.water_study_profile()
        layer_count = 0
        wrap_calls = 0
        for layer_id in profile.layer_ids:
            calls = self.draw_water_study_plane(layer_id, t)
            if calls > 0:
                layer_count += 1
                wrap_calls += calls
        if profile.name == "FULL_SIX_OBSERVE":
            self.draw_water_study_simple_bubbles(t, 10)
            layer_count += 1
        self.water_study_last_draw_ms = (time.perf_counter() - started_at) * 1000.0
        self.water_study_last_layer_count = layer_count
        self.water_study_last_wrap_calls = wrap_calls

        title = "WATER STUDY"
        width, height = pixel_text_size(title, 1)
        draw_pixel_text(
            pyxel,
            int(self.runtime.screen_width / 2 - width / 2),
            int(self.runtime.screen_height / 2 - height / 2),
            title,
            7,
            scale=1,
        )
        if self.debug_enabled:
            self.draw_water_study_debug_overlay(profile)
        self.draw_button(
            self.water_study_close_rect(), "CLOSE", 5, text_color=7, style_name="label"
        )

    def draw_water_study_plane(self, layer_id: str, t: float) -> int:
        pyxel = self.pyxel
        plane = self.water_study_planes.get(layer_id)
        if plane is None:
            return 0
        speed_x, speed_y, sine_amp, orbit_x, orbit_y, phase = WATER_STUDY_LAYER_MOTION[layer_id]
        offset_x, offset_y = self.water_study_layer_offset(
            t,
            speed_x=speed_x,
            speed_y=speed_y,
            sine_amp=sine_amp,
            orbit_x=orbit_x,
            orbit_y=orbit_y,
            phase=phase,
        )
        start_x = -int(offset_x) % plane.logical_width - plane.logical_width
        start_y = -int(offset_y) % plane.logical_height - plane.logical_height
        calls = 0
        for plane_y in range(
            start_y, self.runtime.screen_height + plane.logical_height, plane.logical_height
        ):
            for plane_x in range(
                start_x, self.runtime.screen_width + plane.logical_width, plane.logical_width
            ):
                for chunk in plane.chunks:
                    x = plane_x + chunk.origin_x
                    y = plane_y + chunk.origin_y
                    if (
                        x >= self.runtime.screen_width
                        or y >= self.runtime.screen_height
                        or x + chunk.width <= 0
                        or y + chunk.height <= 0
                    ):
                        continue
                    if plane.colkey is None:
                        pyxel.blt(x, y, chunk.image, 0, 0, chunk.width, chunk.height)
                    else:
                        pyxel.blt(
                            x, y, chunk.image, 0, 0, chunk.width, chunk.height, colkey=plane.colkey
                        )
                    calls += 1
        return calls

    def draw_water_study_simple_bubbles(self, t: float, bubble_count: int) -> None:
        pyxel = self.pyxel
        width = self.runtime.screen_width
        height = self.runtime.screen_height
        for index in range(bubble_count):
            lifetime = 5.0 + (index % 5) * 0.75
            u = ((t + index * 0.47) % lifetime) / lifetime
            base_x = (index * 41 + (index % 4) * 19) % max(1, width)
            x = int(base_x + math.sin(t * 0.9 + index) * (1.0 + u * 4.0))
            y = int(height + 8 - u * (height + 24))
            radius = 1 + int(u * 2.0)
            color = 5 if u < 0.35 else (12 if u < 0.78 else 6)
            pyxel.circb(x, y, radius, color)

    def draw_water_study_debug_overlay(self, profile: WaterStudyProfile) -> None:
        pyxel = self.pyxel
        lines = (
            f"WTR PROFILE: {profile.name}",
            f"DRAW: {self.water_study_last_draw_ms:.2f} ms",
            f"WRAP BLT: {self.water_study_last_wrap_calls}",
            f"LAYERS: {self.water_study_last_layer_count}/{len(profile.layer_ids)}",
            f"PLANE: {WATER_STUDY_LOGICAL_SIZE[0]}x{WATER_STUDY_LOGICAL_SIZE[1]}",
            f"CHUNK: {WATER_STUDY_CHUNK_SIZE}x{WATER_STUDY_CHUNK_SIZE}",
            "1/2/3/4 PROFILE",
        )
        x = 8
        y = self.runtime.screen_height - 55
        pyxel.rect(x - 3, y - 3, 126, 53, 0)
        pyxel.rectb(x - 3, y - 3, 126, 53, 13)
        for index, line in enumerate(lines):
            pyxel.text(x, y + index * 8, line, 7)

    def draw_play(self) -> None:
        assert self.renderer is not None
        scene_camera = self.scene_camera(self.camera())
        self.renderer.draw_scene(
            self.model, scene_camera, self.presentation_time, self.debug_enabled, self.effects
        )
        self.draw_hud()
        if self.model.interaction is not None:
            self.draw_interaction_chip()
        self.draw_combat_chance_cues()

    def scene_camera(self, camera: CameraState) -> CameraState | AffineCameraState:
        camera = self.combat_scene_camera(camera)
        camera = self.combat_restore_scene_camera(camera)
        if self.projection_mode != "affine":
            return self.presentation_camera(camera)
        return self.affine_scene_camera(camera)

    def combat_scene_camera(self, camera: CameraState) -> CameraState:
        session = self.model.combat_session
        if session is None:
            return camera
        combat = self.runtime.raw.get("combat_v1", {})
        entry = combat.get("entry", {}) if isinstance(combat, dict) else {}
        multiplier = self.combat_camera_zoom_multiplier(session)
        if multiplier <= 0.0:
            return camera
        transition = max(
            1e-6,
            float(
                entry.get(
                    "camera_transition_sec",
                    self.combat_dynamic_camera_duration("enter_push", 0.14)
                    + self.combat_dynamic_camera_duration("enter_settle", 0.12),
                )
            ),
        )
        progress = _smoothstep(min(1.0, max(session.elapsed_sec, 1.0 / 60.0) / transition))
        enemy = self.model.enemy_by_id(session.enemy_id)
        if enemy is None:
            enemy_x = session.snapshot.enemy.x
            enemy_z = session.snapshot.enemy.z
        else:
            enemy_x, enemy_z = self.model.enemy_presentation_position(enemy)
        combat_target = Vec3(
            (self.model.player.x + enemy_x) * 0.5,
            0.0,
            (self.model.player.z + enemy_z) * 0.5,
        )
        camera_config = self.runtime.raw["camera"]
        base_distance = float(camera_config["base_distance"])
        snapshot_zoom = self.combat_snapshot_zoom(camera)
        target_zoom = snapshot_zoom * multiplier
        next_zoom = self.clamp_combat_zoom(target_zoom, snapshot_zoom)
        combat_camera = CameraState(
            target=_lerp_vec3(camera.target, combat_target, progress),
            yaw_deg=camera.yaw_deg,
            pitch_deg=camera.pitch_deg,
            horizontal_fov_deg=camera.horizontal_fov_deg,
            distance=base_distance / next_zoom,
            near=camera.near,
            far=camera.far,
            anchor_x=camera.anchor_x,
            anchor_y=self.combat_camera_anchor_y(camera.anchor_y),
            viewport_width=camera.viewport_width,
            viewport_height=camera.viewport_height,
        )
        self.last_combat_scene_camera = combat_camera
        return combat_camera

    def camera_zoom(self, camera: CameraState) -> float:
        base_distance = float(self.runtime.raw["camera"]["base_distance"])
        return base_distance / camera.distance

    def combat_snapshot_zoom(self, camera: CameraState) -> float:
        if self.combat_camera_snapshot_zoom is None:
            self.combat_camera_snapshot_zoom = self.camera_zoom(camera)
        return self.combat_camera_snapshot_zoom

    def combat_dynamic_camera_config(self) -> dict:
        combat = self.runtime.raw.get("combat_v1", {})
        if not isinstance(combat, dict):
            return {}
        dynamic = combat.get("dynamic_camera", {})
        return dynamic if isinstance(dynamic, dict) else {}

    def combat_dynamic_camera_multipliers(self) -> dict:
        dynamic = self.combat_dynamic_camera_config()
        values = dynamic.get("multipliers", {})
        return values if isinstance(values, dict) else {}

    def combat_dynamic_camera_durations(self) -> dict:
        dynamic = self.combat_dynamic_camera_config()
        values = dynamic.get("durations_sec", {})
        return values if isinstance(values, dict) else {}

    def combat_dynamic_camera_multiplier(self, key: str, default: float) -> float:
        return float(self.combat_dynamic_camera_multipliers().get(key, default))

    def combat_dynamic_camera_duration(self, key: str, default: float) -> float:
        return max(0.0, float(self.combat_dynamic_camera_durations().get(key, default)))

    def clamp_combat_zoom(self, zoom: float, snapshot_zoom: float) -> float:
        dynamic = self.combat_dynamic_camera_config()
        min_multiplier = float(dynamic.get("min_multiplier", 0.9))
        max_multiplier = float(dynamic.get("max_multiplier", 1.85))
        return max(snapshot_zoom * min_multiplier, min(snapshot_zoom * max_multiplier, zoom))

    def combat_camera_anchor_y(self, fallback: float) -> float:
        dynamic = self.combat_dynamic_camera_config()
        try:
            value = float(dynamic.get("screen_anchor_y", fallback))
        except (TypeError, ValueError):
            value = fallback
        if not math.isfinite(value):
            value = fallback
        return max(0.0, min(1.0, value))

    def combat_camera_zoom_multiplier(self, session) -> float:
        hold = self.combat_dynamic_camera_multiplier("combat_hold", 1.45)
        preimpact = self.combat_dynamic_camera_multiplier("preimpact", 1.6)
        phase = session.phase
        elapsed = max(0.0, session.phase_elapsed_sec)
        if phase == "COMBAT_ENTRY":
            return self.combat_entry_zoom_multiplier(elapsed)
        if phase in {"COMBAT_READY", "ENEMY_WINDUP", "ENEMY_CHARGE"}:
            return hold
        if phase == "PREIMPACT_SLOW":
            duration = self.combat_dynamic_camera_duration("preimpact_push", 0.18)
            return _smooth_lerp(hold, preimpact, elapsed / max(1e-6, duration))
        if phase == "PARRY_TIMING":
            return preimpact
        if phase == "PARRY_RESOLVE":
            return self.combat_result_zoom_multiplier(session, elapsed)
        if phase in {"PERFECT_FREEZE", "PERFECT_BUBBLE_WINDOW"}:
            return self.combat_dynamic_camera_multiplier("perfect_hold", 1.62)
        if phase == "PERFECT_ZAP_WINDOW":
            return self.combat_bubble_settle_zoom_multiplier(elapsed)
        if phase == "COMBAT_EXIT_COUNTER":
            return self.combat_counter_exit_zoom_multiplier(session, elapsed)
        if phase == "COMBAT_EXIT_DEFLECT":
            duration = self.combat_dynamic_camera_duration("deflect_pullback", 0.22)
            target = self.combat_dynamic_camera_multiplier("deflect_pullback", 1.32)
            return _smooth_lerp(hold, target, elapsed / max(1e-6, duration))
        if phase == "COMBAT_EXIT_PLAYER_KNOCKBACK":
            duration = self.combat_dynamic_camera_duration("failure_recover", 0.13)
            target = self.combat_dynamic_camera_multiplier("failure_pullback", 1.39)
            return _smooth_lerp(hold, target, elapsed / max(1e-6, duration))
        if phase == "VICTORY_CUE":
            return self.combat_victory_zoom_multiplier(elapsed)
        if phase == "COMBAT_RESTORE_JUMP":
            return self.combat_dynamic_camera_multiplier("restore", 1.0)
        return hold

    def combat_entry_zoom_multiplier(self, elapsed: float) -> float:
        peak = self.combat_dynamic_camera_multiplier("enter_peak", 1.52)
        hold = self.combat_dynamic_camera_multiplier("combat_hold", 1.45)
        push = self.combat_dynamic_camera_duration("enter_push", 0.14)
        settle = self.combat_dynamic_camera_duration("enter_settle", 0.12)
        if elapsed < push:
            return _smooth_lerp(1.0, peak, elapsed / max(1e-6, push))
        if elapsed < push + settle:
            return _smooth_lerp(peak, hold, (elapsed - push) / max(1e-6, settle))
        return hold

    def combat_result_zoom_multiplier(self, session, elapsed: float) -> float:
        preimpact = self.combat_dynamic_camera_multiplier("preimpact", 1.6)
        hold = self.combat_dynamic_camera_multiplier("combat_hold", 1.45)
        result = session.result
        if result == "failure":
            pullback = self.combat_dynamic_camera_multiplier("failure_pullback", 1.39)
            down = self.combat_dynamic_camera_duration("failure_pullback", 0.07)
            recover = self.combat_dynamic_camera_duration("failure_recover", 0.13)
            return _two_segment_smooth_lerp(preimpact, pullback, hold, down, recover, elapsed)
        if result == "perfect":
            peak = self.combat_dynamic_camera_multiplier("perfect_peak", 1.8)
            settle = self.combat_dynamic_camera_multiplier("perfect_hold", 1.62)
            up = self.combat_dynamic_camera_duration("perfect_push", 0.08)
            down = self.combat_dynamic_camera_duration("perfect_settle", 0.18)
            return _two_segment_smooth_lerp(preimpact, peak, settle, up, down, elapsed)
        pulse = self.combat_dynamic_camera_multiplier("success_pulse", 1.66)
        up = self.combat_dynamic_camera_duration("success_pulse_up", 0.05)
        down = self.combat_dynamic_camera_duration("success_recover", 0.12)
        return _two_segment_smooth_lerp(preimpact, pulse, hold, up, down, elapsed)

    def combat_bubble_settle_zoom_multiplier(self, elapsed: float) -> float:
        start = self.combat_dynamic_camera_multiplier("perfect_hold", 1.62)
        target = self.combat_dynamic_camera_multiplier("counter_hold", 1.56)
        duration = self.combat_dynamic_camera_duration("bubble_settle", 0.1)
        return _smooth_lerp(start, target, elapsed / max(1e-6, duration))

    def combat_counter_exit_zoom_multiplier(self, session, elapsed: float) -> float:
        hold = self.combat_dynamic_camera_multiplier("counter_hold", 1.56)
        if session.outcome != "defeat":
            return hold
        peak = self.combat_dynamic_camera_multiplier("zap_pulse", 1.68)
        up = self.combat_dynamic_camera_duration("zap_pulse_up", 0.04)
        down = self.combat_dynamic_camera_duration("zap_pulse_down", 0.1)
        return _two_segment_smooth_lerp(hold, peak, hold, up, down, elapsed)

    def combat_victory_zoom_multiplier(self, elapsed: float) -> float:
        hold = self.combat_dynamic_camera_multiplier("victory_hold", 1.36)
        restore = self.combat_dynamic_camera_multiplier("restore", 1.0)
        delay = self.combat_dynamic_camera_duration("victory_restore_delay", 0.4)
        duration = self.combat_dynamic_camera_duration("victory_restore", 0.32)
        if elapsed < delay:
            return hold
        return _smooth_lerp(hold, restore, (elapsed - delay) / max(1e-6, duration))

    def start_combat_camera_restore(self) -> None:
        from_camera = self.last_combat_scene_camera
        if from_camera is None:
            return
        combat = self.runtime.raw.get("combat_v1", {})
        exit_config = combat.get("exit", {}) if isinstance(combat, dict) else {}
        duration = max(0.0, float(exit_config.get("camera_restore_sec", 0.35)))
        if duration <= 0.0:
            self.combat_camera_restore = None
            self.last_combat_scene_camera = None
            self.combat_camera_snapshot_zoom = None
            return
        self.combat_camera_restore = CombatCameraRestore(
            from_camera=from_camera,
            elapsed_sec=0.0,
            duration_sec=duration,
        )

    def update_combat_camera_restore(self, elapsed: float) -> None:
        restore = self.combat_camera_restore
        if restore is None:
            return
        restore.elapsed_sec += max(0.0, elapsed)
        if restore.elapsed_sec >= restore.duration_sec:
            self.combat_camera_restore = None
            self.last_combat_scene_camera = None
            self.combat_camera_snapshot_zoom = None

    def combat_restore_scene_camera(self, camera: CameraState) -> CameraState:
        restore = self.combat_camera_restore
        if restore is None:
            return camera
        progress = _smoothstep(restore.elapsed_sec / max(1e-6, restore.duration_sec))
        from_camera = restore.from_camera
        distance = from_camera.distance + (camera.distance - from_camera.distance) * progress
        return CameraState(
            target=_lerp_vec3(from_camera.target, camera.target, progress),
            yaw_deg=camera.yaw_deg,
            pitch_deg=camera.pitch_deg,
            horizontal_fov_deg=camera.horizontal_fov_deg,
            distance=distance,
            near=camera.near,
            far=camera.far,
            anchor_x=camera.anchor_x,
            anchor_y=from_camera.anchor_y + (camera.anchor_y - from_camera.anchor_y) * progress,
            viewport_width=camera.viewport_width,
            viewport_height=camera.viewport_height,
        )

    def affine_scene_camera(self, camera: CameraState) -> AffineCameraState:
        transform = self.effects.camera_transform(camera.viewport_width, camera.viewport_height)
        if not self.combat_camera_reactions_allowed():
            transform = type(transform)()
        camera_config = self.runtime.raw["camera"]
        base_distance = float(camera_config["base_distance"])
        current_zoom = base_distance / camera.distance
        target_zoom = current_zoom * transform.zoom_multiplier
        if self.model.combat_session is not None or self.combat_camera_restore is not None:
            target_zoom = self.clamp_combat_zoom(
                target_zoom, self.combat_camera_snapshot_zoom or current_zoom
            )
        else:
            target_zoom = min(
                float(camera_config["zoom_max"]),
                max(float(camera_config["zoom_min"]), target_zoom),
            )
        affine_camera = affine_camera_from_perspective(
            camera,
            self.affine_projection_profile,
            base_distance=base_distance,
            fx_offset_x=transform.offset_x,
            fx_offset_y=transform.offset_y,
        )
        return replace(
            affine_camera,
            zoom=target_zoom,
            distance=base_distance / target_zoom,
        )

    def presentation_camera(self, camera: CameraState) -> CameraState:
        if not self.combat_camera_reactions_allowed():
            return camera
        transform = self.effects.camera_transform(camera.viewport_width, camera.viewport_height)
        if (
            abs(transform.offset_x) <= 1e-6
            and abs(transform.offset_y) <= 1e-6
            and abs(transform.zoom_multiplier - 1.0) <= 1e-6
        ):
            return camera
        camera_config = self.runtime.raw["camera"]
        base_distance = float(camera_config["base_distance"])
        current_zoom = base_distance / camera.distance
        target_zoom = current_zoom * transform.zoom_multiplier
        if self.model.combat_session is not None or self.combat_camera_restore is not None:
            target_zoom = self.clamp_combat_zoom(
                target_zoom, self.combat_camera_snapshot_zoom or current_zoom
            )
        else:
            target_zoom = min(
                float(camera_config["zoom_max"]),
                max(float(camera_config["zoom_min"]), target_zoom),
            )
        return CameraState(
            target=camera.target,
            yaw_deg=camera.yaw_deg,
            pitch_deg=camera.pitch_deg,
            horizontal_fov_deg=camera.horizontal_fov_deg,
            distance=base_distance / target_zoom,
            near=camera.near,
            far=camera.far,
            anchor_x=camera.anchor_x + transform.offset_x / camera.viewport_width,
            anchor_y=camera.anchor_y + transform.offset_y / camera.viewport_height,
            viewport_width=camera.viewport_width,
            viewport_height=camera.viewport_height,
        )

    def draw_pause(self) -> None:
        pyxel = self.pyxel
        panel = self.pause_panel_rect()
        pyxel.dither(0.5)
        pyxel.rect(0, 0, self.runtime.screen_width, self.runtime.screen_height, 0)
        pyxel.dither(1.0)
        self.draw_panel_frame(panel, fill=0, inner=5)
        title_rect = self.ui_rect("pause_title")
        self.draw_ui_text_center(
            int(title_rect.x + title_rect.width / 2),
            int(title_rect.y),
            self.ui("ui.pause"),
            7,
            "title",
        )
        culling_status = "ON" if self.model.culling_enabled else "OFF"
        status = f"{self.runtime.profile.name.upper()} CULL {culling_status}"
        self.draw_button(
            self.resume_button_rect(),
            self.ui("ui.resume"),
            10,
            text_color=0,
            style_name="button",
        )
        self.draw_button(
            self.pause_reset_button_rect(), self.ui("ui.reset"), 8, style_name="button"
        )
        self.draw_button(
            self.pause_audio_button_rect(),
            self.ui("ui.sound_off") if self.audio.muted else self.ui("ui.sound_on"),
            5,
            style_name="button",
        )
        self.draw_button(
            self.pause_dev_entry_button_rect(),
            self.ui("ui.debug"),
            1,
            text_color=13 if self.debug_enabled else 7,
            style_name="button",
        )
        self.draw_ui_text_center(
            int(panel.x + panel.width / 2),
            int(panel.y + panel.height - 16),
            status,
            13,
            "auxiliary",
        )

    def draw_hud(self) -> None:
        pyxel = self.pyxel
        self.draw_resource_panel()
        self.draw_system_button(self.sound_button_rect(), self.sound_visual_rect(), "sound")
        self.draw_system_button(self.pause_button_rect(), self.pause_visual_rect(), "pause")

        interaction = self.model.interaction
        inspect_modal = interaction is not None and interaction.kind == "inspect"
        resource_modal = interaction is not None and interaction.kind in {
            "water_refill",
            "energy_refill",
        }
        if not inspect_modal:
            self.draw_wordmark()
            self.draw_minimap()
            if self.location_label_visible():
                self.draw_location_label()
            self.draw_action_button(
                self.interact_button_visual_rect(),
                self.interact_button_token(),
                slot="context",
                enabled=True,
            )
            primary_enabled = not resource_modal and self.action_button_mode() != "NONE"
            self.draw_action_button(
                self.action_button_visual_rect(),
                self.action_button_mode(),
                slot="primary",
                enabled=primary_enabled,
            )
            self.draw_tooltip()
            self.draw_combat_timing_bar()
            self.draw_water_study_menu()
        if self.debug_enabled:
            render_stats = self.renderer.last_stats if self.renderer is not None else None
            pyxel.text(8, 48, f"pos={self.model.player.x:.1f},{self.model.player.z:.1f}", 7)
            pyxel.text(8, 58, f"steps={self.model.debug.fixed_steps_last_callback}", 7)
            pyxel.text(8, 68, f"input={self.pointer.state.name}", 7)
            pyxel.text(8, 78, f"discard={self.model.debug.discarded_elapsed_count}", 7)
            pyxel.text(8, 88, f"camera={self.camera_controller.mode_name}", 7)
            pyxel.text(8, 98, f"repel={self.model.debug.barrier_repels}", 7)
            pyxel.text(8, 108, f"contact={self.model.debug.player_contacts}", 7)
            pyxel.text(
                8,
                118,
                f"bubble={self.model.debug.bubbles_fired}/{self.model.debug.enemies_captured}",
                7,
            )
            pyxel.text(8, 128, f"zap={self.model.debug.discharges}", 7)
            pyxel.text(8, 138, f"inspect={self.model.debug.inspected_count}", 7)
            pyxel.text(8, 148, f"fx={len(self.effects.particles)}/{len(self.effects.emotes)}", 7)
            if render_stats is not None:
                chunks_text = (
                    f"chunks={render_stats.candidate_chunks}/64 "
                    f"detail={render_stats.visible_ground_details} "
                    f"baked={render_stats.visible_baked_ground_patches}"
                )
                pyxel.text(
                    184,
                    48,
                    f"vis={render_stats.visible_static_objects}/{render_stats.candidate_static_objects}/{render_stats.total_static_objects}",
                    7,
                )
                pyxel.text(
                    184,
                    58,
                    chunks_text,
                    7,
                )
                pyxel.text(
                    184,
                    68,
                    f"active={self.model.debug.active_enemies}/{len(self.model.enemies)}",
                    7,
                )
            pyxel.text(8, 158, "F focus / P pan", 7)
            pyxel.text(8, 168, f"proj={self.projection_mode} / V toggle", 7)

    def draw_water_study_menu(self) -> None:
        button = self.water_study_menu_button_rect()
        self.draw_button(button, "MENU", 5, text_color=7, style_name="label")
        if not self.water_study_menu_open:
            return
        panel = self.water_study_menu_panel_rect()
        item = self.water_study_menu_item_rect()
        self.draw_panel_frame(panel, fill=0, inner=5)
        self.draw_button(item, "WATER STUDY", 11, text_color=0, style_name="label")

    def draw_meter(
        self, x: int, y: int, width: int, height: int, value: float, maximum: float, color: int
    ) -> None:
        filled = 0 if maximum <= 0.0 else int(width * max(0.0, min(value / maximum, 1.0)))
        self.pyxel.rect(x, y, width, height, 1)
        self.pyxel.rect(x, y, filled, height, color)
        self.pyxel.rectb(x, y, width, height, 7)

    def interact_button_label(self) -> str:
        return self.ui_token(self.interact_button_token())

    def interact_button_token(self) -> str:
        if self.model.interaction is not None:
            if self.model.interaction.kind == "water_refill":
                return "CANCEL_REFILL"
            if self.model.interaction.kind == "energy_refill":
                return "CANCEL_CHARGE"
            return "DONE"
        target = (
            None if self.model.world_paused else self.model.interaction_candidate(self.camera())
        )
        if target is None:
            return "CHECK"
        if target.kind == "water_station" and target.supply == "working":
            return "REFILL"
        if target.kind == "solar_station":
            return "CHARGE"
        return "CHECK"

    def action_button_label(self) -> str:
        return self.ui_token(self.action_button_mode())

    def action_button_mode(self) -> str:
        session = self.model.combat_session
        if session is not None:
            counter_mode = self.model.combat_counter_action_mode()
            if counter_mode != "NONE":
                return counter_mode
            if session.phase in {
                "COMBAT_ENTRY",
                "COMBAT_READY",
                "PARRY_RESOLVE",
                "PERFECT_FREEZE",
                "COMBAT_EXIT_DEFLECT",
                "COMBAT_EXIT_PLAYER_KNOCKBACK",
                "COMBAT_EXIT_COUNTER",
                "VICTORY_CUE",
                "COMBAT_RESTORE_JUMP",
            }:
                return "NONE"
            return "GUARD"
        if self.model.world_paused:
            return "NONE"
        camera = self.camera()
        if self.model.captured_enemy(camera) is not None:
            return "ZAP"
        if self.model.bubble is not None:
            return "NONE"
        if self.model.guard_threat() is not None:
            return "GUARD"
        if self.model.bubble_target(camera) is not None:
            return "BUBBLE"
        return "NONE"

    def combat_timing_bar_rect(self, session=None) -> Rect:
        raw_rect = self.model.combat_parry_timing_bar_rect_ref(session=session)
        scale_x = self.runtime.screen_width / 512.0
        scale_y = self.runtime.screen_height / 236.0
        return Rect(
            float(raw_rect[0]) * scale_x,
            float(raw_rect[1]) * scale_y,
            float(raw_rect[2]) * scale_x,
            float(raw_rect[3]) * scale_y,
        )

    def draw_combat_timing_bar(self) -> None:
        session = self.model.combat_session
        if session is None or session.phase not in {
            "COMBAT_READY",
            "PARRY_TIMING",
            "PARRY_RESOLVE",
        }:
            return
        pyxel = self.pyxel
        rect = self.combat_timing_bar_rect(session)
        self.draw_panel_frame(rect, fill=0, inner=5)
        scale_y = self.runtime.screen_height / 236.0
        padding = float(self.model.combat_parry_value("track_padding_px", 12, session=session)) * (
            self.runtime.screen_width / 512.0
        )
        track_x = int(rect.x + padding)
        track_w = max(8, int(rect.width - padding * 2))
        track_h = max(6, int(8 * scale_y))
        track_y = int(rect.y + rect.height - max(17, round(18 * scale_y)))
        slider = self.model.combat_timing_slider_position(session)
        progress_w = int(track_w * slider) if slider is not None else 0
        pyxel.rect(track_x - 1, track_y - 1, track_w + 2, track_h + 2, 0)
        pyxel.rect(track_x, track_y, track_w, track_h, 1)
        if progress_w > 0:
            pyxel.rect(track_x, track_y, progress_w, track_h, 5)
            pyxel.rect(track_x, track_y, max(1, progress_w), max(1, track_h // 2), 6)
        pyxel.rectb(track_x, track_y, track_w, track_h, 7)
        for index, marker in enumerate(session.marker_positions):
            judgement = (
                session.marker_judgements[index] if index < len(session.marker_judgements) else None
            )
            color = 11 if judgement == "HIT" else 8 if judgement == "MISS" else 7
            marker_x = int(track_x + marker * track_w)
            marker_y = int(track_y + track_h / 2)
            if judgement == "HIT":
                pyxel.circ(marker_x, marker_y, 4, 11)
                pyxel.circb(marker_x, marker_y, 5, 7)
            elif judgement == "MISS":
                pyxel.circb(marker_x, marker_y, 5, 8)
                pyxel.line(marker_x - 3, marker_y - 3, marker_x + 3, marker_y + 3, 8)
                pyxel.line(marker_x - 3, marker_y + 3, marker_x + 3, marker_y - 3, 8)
            else:
                pyxel.circb(marker_x, marker_y, 5, color)
                pyxel.circb(marker_x, marker_y, 3, 13)
        if slider is not None:
            slider_x = int(track_x + slider * track_w)
            slider_y = int(track_y + track_h / 2)
            pyxel.line(slider_x, track_y - 4, slider_x, track_y + track_h + 4, 0)
            pyxel.circ(slider_x, slider_y, 4, 10)
            pyxel.circb(slider_x, slider_y, 6, 7)
        label = "PERFECT" if session.result == "perfect" else "GOOD" if session.result else "PARRY"
        label_scale = 2
        self.draw_spaced_pixel_text_center(
            int(rect.x + rect.width / 2),
            int(rect.y + max(5, round(6 * scale_y))),
            label,
            10 if session.result == "perfect" else 7,
            scale=label_scale,
            gap=1,
        )
        self.draw_combat_countdown_cue(session)

    def draw_combat_countdown_cue(self, session) -> None:
        cue = self.combat_countdown_cue_text(session)
        if cue is None:
            return
        cue_scale = 3
        cue_gap = 2
        cue_width = self.spaced_pixel_text_width(cue, cue_scale, cue_gap)
        _, cue_h = pixel_text_size(cue, cue_scale)
        width = max(92, cue_width + 28)
        height = max(44, cue_h + 24)
        x = int((self.runtime.screen_width - width) / 2)
        y = int(self.runtime.screen_height * 0.38 - height / 2)
        rect = Rect(float(x), float(y), float(width), float(height))
        self.draw_panel_frame(rect, fill=0, inner=5)
        self.draw_spaced_pixel_text_center(
            int(rect.x + rect.width / 2),
            int(rect.y + rect.height / 2 - cue_h / 2),
            cue,
            10 if cue == "GO!" else 7,
            scale=cue_scale,
            gap=cue_gap,
        )

    def combat_countdown_cue_text(self, session) -> str | None:
        combat = self.runtime.raw.get("combat_v1", {})
        ready = combat.get("ready_sequence", {}) if isinstance(combat, dict) else {}
        if not isinstance(ready, dict):
            ready = {}
        ready_sec = max(0.0, float(ready.get("ready_sec", 0.45)))
        step_sec = max(1.0 / 60.0, float(ready.get("count_step_sec", 0.38)))
        go_sec = max(0.0, float(ready.get("go_sec", 0.22)))
        if session.phase == "COMBAT_READY":
            elapsed = max(0.0, session.phase_elapsed_sec)
            if elapsed < ready_sec:
                return "READY!"
            index = int((elapsed - ready_sec) / step_sec)
            if 0 <= index < 3:
                return str(3 - index)
            return None
        if session.phase == "PARRY_TIMING" and session.timing_elapsed_sec < go_sec:
            return "GO!"
        return None

    def draw_interaction_chip(self) -> None:
        interaction = self.model.interaction
        if interaction is None:
            return
        if interaction.kind == "inspect":
            self.draw_inspect_panel(interaction)
            return
        self.draw_progress_popup(interaction)

    def draw_progress_popup(self, interaction) -> None:
        pyxel = self.pyxel
        rect = self.interaction_chip_rect()
        accent = 10 if interaction.kind == "energy_refill" else 12
        self.draw_panel_frame(rect, fill=0, inner=5)
        if rect.height <= 32:
            self.draw_compact_progress_slot(rect, interaction, accent)
            return
        profile = self.runtime.profile.name
        scale = 1.25 if profile == "high" else 1.0
        compact = rect.height <= 50
        pad_x = int(round(8 * scale))
        title_x = int(rect.x + pad_x)
        title_y = int(rect.y + round(5 * scale))
        pct_w = int(round(42 * scale))
        title_w = max(24, int(rect.width - pad_x * 2 - pct_w))
        pct_text = f"{int(round(interaction.progress * 100)):03d}%"
        self.draw_ui_text(
            pyxel,
            title_x,
            title_y,
            self.fit_ui_text_to_width(self.interaction_title(interaction), title_w, "body"),
            7,
            "body",
        )
        self.draw_text_right(
            int(rect.x + rect.width - round(8 * scale)),
            title_y,
            pct_text,
            13,
            "numeric",
        )
        meter_x = title_x
        meter_y = int(rect.y + rect.height - round((12 if compact else 28) * scale))
        meter_w = int(rect.width - round(16 * scale))
        meter_h = max(4, int(round((5 if compact else 6) * scale)))
        self.draw_meter(
            meter_x,
            meter_y,
            meter_w,
            meter_h,
            interaction.progress,
            1.0,
            accent,
        )
        lines = self.interaction_lines(interaction)
        if lines and not compact:
            line = self.fit_ui_text_to_width(lines[0], meter_w, "body")
            self.draw_ui_text(
                pyxel,
                meter_x,
                int(rect.y + round(42 * scale)),
                line,
                13,
                "body",
            )

    def draw_compact_progress_slot(self, rect: Rect, interaction, accent: int) -> None:
        icon_size = 12 if self.runtime.profile.name != "high" else 14
        icon_x = int(rect.x + 7)
        icon_y = int(rect.y + rect.height / 2 - icon_size / 2)
        icon_token = "CHARGE" if interaction.kind == "energy_refill" else "REFILL"
        self.draw_button_icon_at(icon_token, icon_x, icon_y, icon_size, accent)

        label_x = icon_x + icon_size + 5
        meter_x = int(rect.x + 74)
        meter_w = max(24, int(rect.x + rect.width - meter_x - 8))
        label_w = max(12, meter_x - label_x - 5)
        label = self.fit_ui_text_to_width(self.interaction_title(interaction), label_w, "button")
        text_h = self.ui_renderer.text_height("button")
        text_y = int(rect.y + rect.height / 2 - text_h / 2 + 3)
        self.draw_ui_text(self.pyxel, label_x, text_y, label, 7, "button")
        self.draw_meter(
            meter_x,
            int(rect.y + rect.height / 2 - 3),
            meter_w,
            6,
            interaction.progress,
            1.0,
            accent,
        )

    def draw_inspect_panel(self, interaction) -> None:
        panel = self.inspect_panel_rect()
        title_rect = self.inspect_title_rect()
        text_rect = self.inspect_text_rect()
        page_rect = self.inspect_page_rect()
        done_rect = self.interaction_done_button_rect()
        self.draw_panel_frame(panel, fill=0, inner=5)
        title = self.fit_ui_text_to_width(
            self.interaction_title(interaction),
            int(title_rect.width),
            "title",
        )
        self.draw_ui_text(self.pyxel, int(title_rect.x), int(title_rect.y), title, 7, "title")
        lines = self.interaction_lines(interaction)
        line_height = 25 if self.runtime.profile.name == "high" else 20
        max_lines = max(1, int(text_rect.height // line_height))
        wrapped = self.wrap_ui_lines(lines, int(text_rect.width), "body")
        for index, line in enumerate(wrapped[:max_lines]):
            self.draw_ui_text(
                self.pyxel,
                int(text_rect.x),
                int(text_rect.y + index * line_height),
                line,
                13,
                "body",
            )
        if len(wrapped) > max_lines:
            self.draw_ui_text_center(
                int(page_rect.x + page_rect.width / 2),
                int(page_rect.y),
                "1/2",
                13,
                "auxiliary",
            )
        self.draw_button(done_rect, self.ui_token("DONE"), 5, style_name="button")

    def draw_button(
        self,
        rect: Rect,
        label: str,
        color: int,
        text_color: int = 0,
        style_name: str = "label",
    ) -> None:
        pyxel = self.pyxel
        pyxel.rect(int(rect.x), int(rect.y), int(rect.width), int(rect.height), color)
        pyxel.rectb(int(rect.x), int(rect.y), int(rect.width), int(rect.height), 7)
        text = self.fit_ui_text_to_width(label, int(rect.width) - 8, style_name)
        self.draw_ui_text_in_rect(rect, text, text_color, style_name, align="center")

    def draw_panel_frame(self, rect: Rect, fill: int, inner: int | None = None) -> None:
        pyxel = self.pyxel
        x = int(rect.x)
        y = int(rect.y)
        width = int(rect.width)
        height = int(rect.height)
        pyxel.rect(x, y, width, height, fill)
        pyxel.rectb(x, y, width, height, 7)
        chamfer = 5 if self.runtime.profile.name == "high" else 4
        pyxel.line(x, y + chamfer, x + chamfer, y, 6)
        pyxel.line(x + width - 1 - chamfer, y, x + width - 1, y + chamfer, 6)
        pyxel.line(
            x + width - 1,
            y + height - 1 - chamfer,
            x + width - 1 - chamfer,
            y + height - 1,
            6,
        )
        pyxel.line(x + chamfer, y + height - 1, x, y + height - 1 - chamfer, 6)
        if inner is not None and width > 10 and height > 10:
            inset = 3 if self.runtime.profile.name != "high" else 4
            pyxel.rectb(x + inset, y + inset, width - inset * 2, height - inset * 2, inner)

    def draw_action_button(self, rect: Rect, token: str, slot: str, enabled: bool) -> None:
        theme = self.ui_theme()
        fill = theme["context_fill"] if slot == "context" else theme["primary_fill"]
        text_color = theme["context_text"] if slot == "context" else theme["primary_text"]
        if not enabled:
            fill = theme["disabled_fill"]
            text_color = theme["disabled_text"]
        inner_key = "context_light" if slot == "context" else "primary_light"
        self.draw_panel_frame(rect, fill=fill, inner=theme[inner_key])
        if (
            enabled
            and slot == "primary"
            and token in {"BUBBLE", "ZAP"}
            and self.model.combat_counter_action_mode() == token
            and (self.frame // 8) % 2 == 0
        ):
            self.pyxel.rectb(
                int(rect.x) + 2,
                int(rect.y) + 2,
                max(1, int(rect.width) - 4),
                max(1, int(rect.height) - 4),
                10,
            )
        if rect.height <= 30:
            self.draw_compact_action_button_content(rect, token, text_color)
            return
        self.draw_button_icon(token, rect, text_color)
        label_rect = self.action_button_label_rect(rect)
        label = self.fit_ui_text_to_width(self.ui_token(token), int(label_rect.width), "button")
        self.draw_ui_text_in_rect(
            label_rect,
            label,
            text_color,
            "button",
            align="center",
        )

    def draw_compact_action_button_content(self, rect: Rect, token: str, color: int) -> None:
        icon_size = 12 if self.runtime.profile.name != "high" else 14
        pad_x = 6
        gap = 4
        icon_x = int(rect.x + pad_x)
        icon_y = int(rect.y + rect.height / 2 - icon_size / 2)
        self.draw_button_icon_at(token, icon_x, icon_y, icon_size, color)
        label_x = icon_x + icon_size + gap
        label_w = max(8, int(rect.x + rect.width - label_x - 4))
        label = self.fit_ui_text_to_width(self.ui_token(token), label_w, "button")
        text_h = self.ui_renderer.text_height("button")
        text_y = int(rect.y + rect.height / 2 - text_h / 2 + 3)
        self.draw_ui_text(self.pyxel, label_x, text_y, label, color, "button")

    def action_button_label_rect(self, rect: Rect) -> Rect:
        if rect.height <= 30:
            icon_size = 12 if self.runtime.profile.name != "high" else 14
            pad_x = 6
            gap = 4
            label_x = rect.x + pad_x + icon_size + gap
            return Rect(label_x, rect.y, rect.x + rect.width - label_x - 4, rect.height)
        pad_x = 8 if self.runtime.profile.name == "high" else 6
        label_h = 20 if self.runtime.profile.name == "high" else 16
        bottom_pad = 8 if self.runtime.profile.name == "high" else 6
        return Rect(
            rect.x + pad_x,
            rect.y + rect.height - label_h - bottom_pad,
            rect.width - pad_x * 2,
            label_h,
        )

    def draw_button_icon(self, token: str, rect: Rect, color: int) -> None:
        if self.runtime.profile.name == "high":
            icon_size = 16
            y_offset = 5
        elif self.runtime.profile.name == "low":
            icon_size = 12
            y_offset = 4
        else:
            icon_size = 14
            y_offset = 4
        x = int(rect.x + rect.width / 2 - icon_size / 2)
        y = int(rect.y + y_offset)
        self.draw_button_icon_at(token, x, y, icon_size, color)

    def draw_button_icon_at(self, token: str, x: int, y: int, icon_size: int, color: int) -> None:
        pyxel = self.pyxel
        cx = x + icon_size // 2
        cy = y + icon_size // 2
        if token in {"CHECK", "DONE", "NEXT"}:
            pyxel.circb(cx - 2, cy - 2, max(4, icon_size // 4), color)
            pyxel.line(cx + 2, cy + 2, cx + icon_size // 2 - 1, cy + icon_size // 2 - 1, color)
        elif token in {"GUARD", "CANCEL_REFILL", "CANCEL_CHARGE"}:
            pyxel.line(cx, y, x + icon_size - 3, y + 4, color)
            pyxel.line(x + icon_size - 3, y + 4, x + icon_size - 5, y + icon_size - 3, color)
            pyxel.line(x + icon_size - 5, y + icon_size - 3, cx, y + icon_size - 1, color)
            pyxel.line(cx, y + icon_size - 1, x + 3, y + icon_size - 3, color)
            pyxel.line(x + 3, y + icon_size - 3, x + 2, y + 4, color)
            pyxel.line(x + 2, y + 4, cx, y, color)
        elif token == "BUBBLE":
            pyxel.circb(cx - 3, cy, 4, color)
            pyxel.circb(cx + 4, cy - 4, 3, color)
        elif token in {"ZAP", "CHARGE"}:
            pyxel.line(cx, y, x + 3, cy, color)
            pyxel.line(x + 3, cy, cx, cy, color)
            pyxel.line(cx, cy, x + 6, y + icon_size - 1, color)
        elif token == "REFILL":
            pyxel.circ(cx, cy + 2, max(4, icon_size // 4), color)
            pyxel.line(cx, y + 1, cx - 4, cy, color)
            pyxel.line(cx, y + 1, cx + 4, cy, color)
        else:
            pyxel.rect(cx - 1, y + 2, 3, icon_size - 4, color)

    def draw_system_button(self, hit_rect: Rect, visual_rect: Rect, icon: str) -> None:
        theme = self.ui_theme()
        self.draw_panel_frame(visual_rect, fill=theme["system_fill"], inner=theme["system_hover"])
        x = int(visual_rect.x)
        y = int(visual_rect.y)
        width = int(visual_rect.width)
        height = int(visual_rect.height)
        cx = x + width // 2
        cy = y + height // 2
        if icon == "pause":
            bar_w = max(3, width // 7)
            pyxel = self.pyxel
            pyxel.rect(cx - bar_w - 2, y + height // 4, bar_w, height // 2, 7)
            pyxel.rect(cx + 2, y + height // 4, bar_w, height // 2, 7)
        else:
            self.pyxel.rect(x + width // 4, cy - 4, 4, 8, 7)
            self.pyxel.line(x + width // 4 + 4, cy - 4, cx + 2, cy - 8, 7)
            self.pyxel.line(x + width // 4 + 4, cy + 4, cx + 2, cy + 8, 7)
            if not self.audio.muted:
                self.pyxel.circb(cx + 6, cy, 5, 7)

    def draw_text_right(self, right_x: int, y: int, text: str, color: int, style_name: str) -> None:
        self.draw_ui_text(
            self.pyxel,
            right_x - self.ui_renderer.text_width(text, style_name),
            y,
            text,
            color,
            style_name,
        )

    def draw_ui_text_in_rect(
        self,
        rect: Rect,
        text: str,
        color: int,
        style_name: str,
        align: str = "left",
    ) -> None:
        text_width = self.ui_renderer.text_width(text, style_name)
        text_height = self.ui_renderer.text_height(style_name)
        if align == "right":
            x = int(rect.x + rect.width - text_width)
        elif align == "center":
            x = int(rect.x + rect.width / 2 - text_width / 2)
        else:
            x = int(rect.x)
        y_float = rect.y + max(0.0, (rect.height - text_height) / 2.0)
        y_float += self.ui_text_vertical_offset(style_name)
        max_y = rect.y + rect.height - text_height
        if max_y >= rect.y:
            y_float = min(max(y_float, rect.y), max_y)
        y = int(y_float)
        self.draw_ui_text(self.pyxel, x, y, text, color, style_name)

    def ui_text_vertical_offset(self, style_name: str) -> int:
        if style_name == "button":
            return -2
        if style_name in {"tooltip", "resource", "numeric"}:
            return -1
        return 0

    def draw_resource_panel(self) -> None:
        rect = self.resource_panel_rect()
        self.draw_panel_frame(rect, fill=0, inner=5)
        profile = self.runtime.profile.name
        compact = rect.width <= 170
        if compact:
            rows = (
                (6, 5, 24, 3, 28, 56, 8, 68),
                (6, 22, 24, 20, 28, 56, 25, 68),
            )
        elif profile == "high":
            rows = (
                (10, 10, 30, 8, 42, 75, 8, 35, 120, 15, 80),
                (10, 35, 30, 33, 42, 75, 33, 35, 120, 40, 80),
            )
        elif profile == "low":
            rows = (
                (8, 6, 24, 4, 34, 60, 4, 28, 96, 10, 52),
                (8, 26, 24, 24, 34, 60, 24, 28, 96, 30, 52),
            )
        else:
            rows = (
                (8, 8, 24, 6, 34, 60, 6, 28, 96, 12, 64),
                (8, 28, 24, 26, 34, 60, 26, 28, 96, 32, 64),
            )
        resources = (
            (self.ui("hud.water"), int(self.model.water), self.model.water_max, 12, "water"),
            (self.ui("hud.energy"), int(self.model.energy), self.model.energy_max, 10, "energy"),
        )
        row_text_height = 22 if profile == "high" else 18
        for index, (label, value, maximum, color, icon) in enumerate(resources):
            x = int(rect.x)
            y = int(rect.y)
            if compact:
                icon_x, icon_y, value_x, value_y, value_w, meter_x, meter_y, meter_w = rows[index]
                self.draw_resource_icon(x + icon_x, y + icon_y, icon, color)
                self.draw_ui_text_in_rect(
                    Rect(x + value_x, y + value_y, value_w, row_text_height),
                    f"{value:03d}",
                    7,
                    "numeric",
                    align="right",
                )
                self.draw_meter(x + meter_x, y + meter_y, meter_w, 6, value, maximum, color)
            else:
                (
                    icon_x,
                    icon_y,
                    label_x,
                    label_y,
                    label_w,
                    value_x,
                    value_y,
                    value_w,
                    meter_x,
                    meter_y,
                    meter_w,
                ) = rows[index]
                self.draw_resource_icon(x + icon_x, y + icon_y, icon, color)
                self.draw_ui_text_in_rect(
                    Rect(x + label_x, y + label_y, label_w, row_text_height),
                    label,
                    color,
                    "resource",
                    align="left",
                )
                self.draw_ui_text_in_rect(
                    Rect(x + value_x, y + value_y, value_w, row_text_height),
                    f"{value:03d}",
                    7,
                    "numeric",
                    align="right",
                )
                self.draw_meter(x + meter_x, y + meter_y, meter_w, 7, value, maximum, color)

    def draw_resource_icon(self, x: int, y: int, icon: str, color: int) -> None:
        if icon == "water":
            self.pyxel.circ(x + 6, y + 7, 5, color)
            self.pyxel.tri(x + 6, y, x + 2, y + 8, x + 10, y + 8, color)
        else:
            self.pyxel.line(x + 7, y, x + 2, y + 7, color)
            self.pyxel.line(x + 2, y + 7, x + 7, y + 7, color)
            self.pyxel.line(x + 7, y + 7, x + 4, y + 13, color)

    def draw_wordmark(self) -> None:
        rect = self.wordmark_rect()
        if rect.x < self.resource_panel_rect().x + self.resource_panel_rect().width + 8:
            return
        self.draw_text_center(
            int(rect.x + rect.width / 2), int(rect.y + 1), "DRIFTWITHME", 7, scale=2
        )
        baseline = int(rect.y + rect.height - 2)
        self.pyxel.line(int(rect.x + 8), baseline, int(rect.x + rect.width - 8), baseline, 6)

    def draw_location_label(self) -> None:
        rect = self.location_rect()
        self.draw_panel_frame(rect, fill=1, inner=None)
        text = self.fit_ui_text_to_width(self.ui("hud.location"), int(rect.width) - 8, "auxiliary")
        self.draw_ui_text_center(
            int(rect.x + rect.width / 2),
            int(rect.y + 3),
            text,
            7,
            "auxiliary",
        )

    def draw_minimap(self) -> None:
        rect = self.minimap_visual_rect()
        x = int(rect.x)
        y = int(rect.y)
        size = int(rect.width)
        radius = size // 2 - 2
        cx = x + size // 2
        cy = y + size // 2
        self.pyxel.circ(cx, cy, radius, 1)
        self.pyxel.circb(cx, cy, radius, 7)
        for offset in range(-radius + 6, radius, 8):
            span = int(math.sqrt(max(0, radius * radius - offset * offset)))
            self.pyxel.line(cx - span, cy + offset, cx + span, cy + offset, 5)
            self.pyxel.line(cx + offset, cy - span, cx + offset, cy + span, 5)
        map_side = max(16, int((size - 12) / math.sqrt(2)))
        map_x = cx - map_side // 2
        map_y = cy - map_side // 2
        for obj in self.world.objects:
            px, py = self.minimap_point(obj.x, obj.z, map_x, map_y, map_side)
            if obj.kind == "water_station":
                color = 12
            elif obj.kind == "solar_station":
                color = 10
            elif obj.inspectable:
                color = 7
            else:
                color = 5
            self.pyxel.pset(px, py, color)
        px, py = self.minimap_point(
            self.model.player.x,
            self.model.player.z,
            map_x,
            map_y,
            map_side,
        )
        self.pyxel.circ(px, py, 2, 7)

    def minimap_point(
        self,
        world_x: float,
        world_z: float,
        map_x: int,
        map_y: int,
        map_side: int,
    ) -> tuple[int, int]:
        rect = self.world.minimap_rect
        u = 0.0 if rect.width <= 0 else max(0.0, min((world_x - rect.min_x) / rect.width, 1.0))
        v = 1.0
        if rect.depth > 0:
            normalized_z = max(0.0, min((world_z - rect.min_z) / rect.depth, 1.0))
            v = 1.0 - normalized_z
        return map_x + round(u * (map_side - 1)), map_y + round(v * (map_side - 1))

    def draw_tooltip(self) -> None:
        text = self.current_tooltip_text()
        if not text:
            return
        rect = self.tooltip_rect(two_lines=False)
        self.draw_panel_frame(rect, fill=0, inner=5)
        fitted = self.fit_ui_text_to_width(text, int(rect.width) - 16, "tooltip")
        if rect.height <= 24:
            text_w = self.ui_renderer.text_width(fitted, "tooltip")
            text_h = self.ui_renderer.text_height("tooltip")
            x = int(rect.x + rect.width / 2 - text_w / 2)
            y = int(rect.y + rect.height / 2 - text_h / 2 + 3)
            self.draw_ui_text(
                self.pyxel,
                x,
                y,
                fitted,
                8 if self.last_denied_reason else 7,
                "tooltip",
            )
            return
        self.draw_ui_text_in_rect(
            Rect(rect.x + 8, rect.y + 4, rect.width - 16, rect.height - 8),
            fitted,
            8 if self.last_denied_reason else 7,
            "tooltip",
            align="center",
        )

    def current_tooltip_text(self) -> str:
        if self.model.world_paused:
            return ""
        if self.last_denied_reason:
            return self.denied_reason_text(self.last_denied_reason)
        if self.model.player.barrier_active:
            return self.ui("hint.guard_hold")
        token = self.action_button_mode()
        if token == "NONE":
            token = self.interact_button_token()
            if token == "CHECK" and self.model.interaction_candidate(self.camera()) is None:
                return ""
        return self.tooltip_for_token(token)

    def tooltip_for_token(self, token: str) -> str:
        mapping = {
            "CHECK": "tooltip.check",
            "REFILL": "tooltip.refill",
            "CHARGE": "tooltip.charge",
            "GUARD": "tooltip.guard",
            "BUBBLE": "tooltip.bubble",
            "ZAP": "tooltip.zap",
            "NONE": "tooltip.none",
        }
        key = mapping.get(token)
        return self.ui(key) if key is not None else ""

    def wrap_ui_lines(self, lines: tuple[str, ...], max_width: int, style_name: str) -> list[str]:
        wrapped: list[str] = []
        for line in lines:
            current = ""
            for char in line:
                candidate = current + char
                if current and self.ui_renderer.text_width(candidate, style_name) > max_width:
                    wrapped.append(current)
                    current = char
                else:
                    current = candidate
            if current:
                wrapped.append(current)
        return wrapped

    def draw_text_center(self, x: int, y: int, text: str, color: int, scale: int = 2) -> None:
        text = text.upper()
        text_width, _ = pixel_text_size(text, scale)
        draw_pixel_text(self.pyxel, x - text_width // 2, y, text, color, scale=scale)

    def draw_spaced_pixel_text_center(
        self, x: int, y: int, text: str, color: int, scale: int = 1, gap: int = 1
    ) -> None:
        text = text.upper()
        glyphs = tuple(text)
        if not glyphs:
            return
        widths = tuple(pixel_text_size(char, scale)[0] for char in glyphs)
        total_width = sum(widths) + gap * max(0, len(glyphs) - 1)
        cursor_x = x - total_width // 2
        for char, width in zip(glyphs, widths, strict=True):
            draw_pixel_text(self.pyxel, cursor_x, y, char, color, scale=scale)
            cursor_x += width + gap

    def spaced_pixel_text_width(self, text: str, scale: int = 1, gap: int = 1) -> int:
        glyphs = tuple(text.upper())
        if not glyphs:
            return 0
        return sum(pixel_text_size(char, scale)[0] for char in glyphs) + gap * (len(glyphs) - 1)

    def fit_text_to_width(self, text: str, max_width: int, scale: int) -> str:
        text = text.upper()
        if pixel_text_size(text, scale)[0] <= max_width:
            return text
        suffix = ".."
        while text and pixel_text_size(text + suffix, scale)[0] > max_width:
            text = text[:-1]
        return text + suffix if text else suffix

    @property
    def ui_renderer(self) -> UITextRenderer:
        renderer = getattr(self, "ui_text", None)
        if renderer is None:
            renderer = load_ui_text_renderer(self.pyxel, self.runtime)
            self.ui_text = renderer
        return renderer

    def ui(self, key: str) -> str:
        return self.ui_renderer.resources.text(key)

    def ui_token(self, token: str) -> str:
        return self.ui_renderer.resources.token(token)

    def denied_reason_text(self, reason: str) -> str:
        return self.ui_renderer.resources.reason(reason)

    def draw_ui_text(self, pyxel, x: int, y: int, text: str, color: int, style_name: str) -> None:
        y = self.ui_text_language_y(y, text)
        self.ui_renderer.draw(pyxel, x, y, text, color, style_name)

    def draw_ui_text_center(self, x: int, y: int, text: str, color: int, style_name: str) -> None:
        y = self.ui_text_language_y(y, text)
        self.ui_renderer.draw_centered(self.pyxel, x, y, text, color, style_name)

    def fit_ui_text_to_width(self, text: str, max_width: int, style_name: str) -> str:
        return self.ui_renderer.fit_text(text, max_width, style_name)

    def ui_text_language_y(self, y: int, text: str) -> int:
        return y - 8 if self.ui_text_has_japanese(text) else y

    @staticmethod
    def ui_text_has_japanese(text: str) -> bool:
        return any("\u3040" <= char <= "\u30ff" or "\u3400" <= char <= "\u9fff" for char in text)

    def interaction_title(self, interaction) -> str:
        if interaction.kind == "water_refill":
            return self.ui("interaction.water_refill.title")
        if interaction.kind == "energy_refill":
            return self.ui("interaction.energy_charge.title")
        if interaction.kind == "inspect" and interaction.title == "NO WATER":
            return self.ui("interaction.no_water.title")
        return self.ui_renderer.resources.raw_text(interaction.title)

    def interaction_lines(self, interaction) -> tuple[str, ...]:
        if interaction.kind == "water_refill":
            return (self.ui("interaction.water_refill.line"),)
        if interaction.kind == "energy_refill":
            return (self.ui("interaction.energy_charge.line"),)
        if interaction.kind == "inspect" and interaction.title == "NO WATER":
            return (self.ui("interaction.no_water.line"),)
        if interaction.kind == "inspect":
            obj = self.world.object_by_id(interaction.object_id)
            if obj is not None and obj.text_key is not None:
                text = self.world.texts.get(obj.text_key, {})
                lines = tuple(str(line) for line in text.get(self.ui_renderer.resources.locale, ()))
                if lines:
                    return lines
        return tuple(self.ui_renderer.resources.raw_text(line) for line in interaction.lines)


def _smoothstep(value: float) -> float:
    amount = max(0.0, min(1.0, value))
    return amount * amount * (3.0 - 2.0 * amount)


def _smooth_lerp(origin: float, target: float, amount: float) -> float:
    eased = _smoothstep(amount)
    return origin + (target - origin) * eased


def _two_segment_smooth_lerp(
    origin: float,
    peak: float,
    target: float,
    first_duration: float,
    second_duration: float,
    elapsed: float,
) -> float:
    if elapsed < first_duration:
        return _smooth_lerp(origin, peak, elapsed / max(1e-6, first_duration))
    return _smooth_lerp(
        peak,
        target,
        (elapsed - first_duration) / max(1e-6, second_duration),
    )


def _lerp_vec3(origin: Vec3, target: Vec3, amount: float) -> Vec3:
    return Vec3(
        origin.x + (target.x - origin.x) * amount,
        origin.y + (target.y - origin.y) * amount,
        origin.z + (target.z - origin.z) * amount,
    )


def main() -> None:
    DriftWithMeApp()


if __name__ == "__main__":
    main()
