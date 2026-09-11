from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum, auto

from drift_with_me import config
from drift_with_me.audio import AudioEngine
from drift_with_me.camera import CameraController
from drift_with_me.effects import EffectSystem
from drift_with_me.input import PointerInput, Rect
from drift_with_me.math3d import CameraState, Vec3, normalize2
from drift_with_me.model import GameModel, InputIntent, merge_intents
from drift_with_me.pixel_font import draw_pixel_text, pixel_text_size
from drift_with_me.render import Renderer
from drift_with_me.world import load_world_data


class AppScreen(Enum):
    START = auto()
    PLAY = auto()
    PAUSE = auto()


@dataclass(frozen=True)
class PointerSnapshot:
    down: bool
    pressed: bool
    x: float
    y: float


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
        self.screen = AppScreen.START
        self.debug_enabled = False
        self.presentation_time = 0.0
        self.accumulator = 0.0
        self.previous_time: float | None = None
        self.frame = 0
        self.smoke_frames = smoke_frames
        input_config = self.runtime.raw["input"]
        ui_scale = self.runtime.screen_height / float(
            self.runtime.raw["display"]["reference_ui_height"]
        )
        self.pointer = PointerInput(
            hold_sec=float(input_config["hold_sec"]),
            drag_threshold_px=float(input_config["drag_threshold_ref_px"]) * ui_scale,
            deadzone_px=float(input_config["stick_deadzone_ref_px"]) * ui_scale,
            radius_px=float(input_config["stick_radius_ref_px"]) * ui_scale,
        )
        self.pending_action_pressed = False
        self.pending_interact_pressed = False
        self.last_denied_reason = ""
        self.pointer_snapshot = PointerSnapshot(False, False, 0.0, 0.0)
        self.browser_pointer_sequence_seen = 0

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
        self.audio.setup(pyxel)
        self.renderer = Renderer(pyxel)
        pyxel.run(self.update, self.draw)

    def camera(self) -> CameraState:
        return self.camera_controller.current

    def update(self) -> None:
        pyxel = self.pyxel
        elapsed = self.consume_elapsed()
        self.presentation_time += elapsed
        self.frame += 1
        self.pointer_snapshot = self.read_pointer_snapshot()

        f1_key = getattr(pyxel, "KEY_F1", None)
        if f1_key is not None and pyxel.btnp(f1_key):
            self.debug_enabled = not self.debug_enabled
        if pyxel.btnp(pyxel.KEY_M):
            self.audio.toggle_mute()

        if self.screen == AppScreen.START:
            self.update_start_screen()
        elif self.screen == AppScreen.PAUSE:
            self.update_pause_screen()
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
        self.previous_time = None
        self.accumulator = 0.0
        self.screen = AppScreen.PLAY

    def update_pause_screen(self) -> None:
        pyxel = self.pyxel
        self.pointer.cancel()
        if pyxel.btnp(pyxel.KEY_ESCAPE) or pyxel.btnp(pyxel.KEY_RETURN):
            self.screen = AppScreen.PLAY
            self.previous_time = None
            return
        if pyxel.btnp(pyxel.KEY_R):
            self.model.reset_scene()
            self.audio.reset_event_history()
            self.effects.reset()
            self.camera_controller.reset(Vec3(self.model.player.x, 0.0, self.model.player.z))
            self.model.snap_buddy(self.camera())
            self.previous_time = None
        if pyxel.btnp(pyxel.KEY_Q):
            pyxel.quit()
        if self.mouse_pressed_in(self.resume_button_rect()):
            self.screen = AppScreen.PLAY
            self.previous_time = None
        if self.mouse_pressed_in(self.sound_button_rect()):
            self.audio.toggle_mute()

    def update_play_screen(self, elapsed: float) -> None:
        pyxel = self.pyxel
        if pyxel.btnp(pyxel.KEY_ESCAPE):
            if self.model.world_paused:
                self.process_events(self.model.cancel_interaction())
                self.camera_controller.cancel_focus()
            self.screen = AppScreen.PAUSE
            self.pointer.cancel()
            return
        if self.mouse_pressed_in(self.pause_button_rect()):
            if self.model.world_paused:
                self.process_events(self.model.cancel_interaction())
                self.camera_controller.cancel_focus()
            self.screen = AppScreen.PAUSE
            self.pointer.cancel()
            return
        if self.mouse_pressed_in(self.sound_button_rect()):
            self.audio.toggle_mute()

        self.handle_debug_camera_shortcuts()
        if self.model.world_paused:
            self.pointer.cancel()
            if pyxel.btnp(pyxel.KEY_RETURN) or self.mouse_pressed_in(
                self.interaction_done_button_rect()
            ):
                self.process_events(self.model.complete_interaction())
                self.camera_controller.update(elapsed, self.model.player.x, self.model.player.z)
                return
            paused_events = self.model.update_paused(elapsed)
            self.camera_controller.update(elapsed, self.model.player.x, self.model.player.z)
            self.process_events(paused_events)
            self.effects.update(elapsed, self.model)
            return

        input_camera = self.camera()
        if self.camera_controller.freezes_world:
            self.pointer.cancel()
            self.camera_controller.update(elapsed, self.model.player.x, self.model.player.z)
            self.effects.update(elapsed, self.model)
            return

        keyboard_intent = self.keyboard_intent()
        pointer_intent = self.pointer_intent(elapsed)
        ui_button_intent = self.ui_button_intent()
        if keyboard_intent.action_pressed or ui_button_intent.action_pressed:
            self.pending_action_pressed = True
        if keyboard_intent.interact_pressed or ui_button_intent.interact_pressed:
            self.pending_interact_pressed = True
        base_intent = merge_intents(keyboard_intent, pointer_intent, ui_button_intent)

        self.accumulator += elapsed
        fixed_dt = self.runtime.fixed_dt
        max_steps = int(self.runtime.raw["simulation"]["max_steps_per_callback"])
        steps = 0
        all_events = []
        while self.accumulator >= fixed_dt and steps < max_steps:
            step_intent = InputIntent(
                screen_x=base_intent.screen_x,
                screen_y=base_intent.screen_y,
                strength=base_intent.strength,
                barrier=base_intent.barrier,
                action_pressed=self.pending_action_pressed,
                interact_pressed=self.pending_interact_pressed,
            )
            self.pending_action_pressed = False
            self.pending_interact_pressed = False
            events = self.model.step(step_intent, input_camera, fixed_dt)
            all_events.extend(events)
            self.accumulator -= fixed_dt
            steps += 1
            if self.model.world_paused:
                self.accumulator = 0.0
                break

        self.camera_controller.update(elapsed, self.model.player.x, self.model.player.z)

        if steps >= max_steps and self.accumulator >= fixed_dt:
            self.accumulator = 0.0
            self.model.debug.discarded_elapsed_count += 1
        self.model.debug.fixed_steps_last_callback = steps
        self.process_events(all_events)
        self.effects.update(elapsed, self.model)

    def process_events(self, events) -> None:
        if not events:
            return
        for event in events:
            if event.kind == "action_denied":
                self.last_denied_reason = str(event.payload.get("reason", "denied"))
            elif event.kind == "interaction_started" and event.target_id is not None:
                target = self.world.object_by_id(event.target_id)
                if target is not None:
                    hold_sec = float(event.payload.get("duration_sec", 0.8)) + 0.15
                    self.camera_controller.start_focus_demo(target, hold_sec=hold_sec)
        self.effects.process_events(events, self.model)
        self.audio.play_events(events)

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
        screen_x = float(pyxel.btn(pyxel.KEY_RIGHT) or pyxel.btn(pyxel.KEY_D))
        screen_x -= float(pyxel.btn(pyxel.KEY_LEFT) or pyxel.btn(pyxel.KEY_A))
        screen_y = float(pyxel.btn(pyxel.KEY_DOWN) or pyxel.btn(pyxel.KEY_S))
        screen_y -= float(pyxel.btn(pyxel.KEY_UP) or pyxel.btn(pyxel.KEY_W))
        direction = normalize2(screen_x, screen_y)
        strength = 1.0 if abs(screen_x) > 0.0 or abs(screen_y) > 0.0 else 0.0
        return InputIntent(
            screen_x=direction.x,
            screen_y=direction.y,
            strength=strength,
            barrier=pyxel.btn(pyxel.KEY_SPACE),
            action_pressed=pyxel.btnp(pyxel.KEY_X),
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

    def ui_button_intent(self) -> InputIntent:
        return InputIntent(
            action_pressed=self.mouse_pressed_in(self.action_button_rect()),
            interact_pressed=self.mouse_pressed_in(self.interact_button_rect()),
        )

    def mouse_pressed_in(self, rect: Rect) -> bool:
        pointer = self.pointer_snapshot
        return pointer.pressed and rect.contains(pointer.x, pointer.y)

    def active_ui_rects(self) -> tuple[Rect, ...]:
        rects = [
            self.action_button_rect(),
            self.interact_button_rect(),
            self.pause_button_rect(),
            self.sound_button_rect(),
        ]
        if self.model.world_paused:
            rects.append(self.interaction_done_button_rect())
        return tuple(rects)

    def action_button_rect(self) -> Rect:
        return Rect(self.runtime.screen_width - 102, self.runtime.screen_height - 72, 90, 60)

    def interact_button_rect(self) -> Rect:
        return Rect(self.runtime.screen_width - 204, self.runtime.screen_height - 72, 90, 60)

    def pause_button_rect(self) -> Rect:
        return Rect(self.runtime.screen_width - 86, 8, 74, 44)

    def sound_button_rect(self) -> Rect:
        return Rect(10, self.runtime.screen_height - 50, 90, 40)

    def start_button_rect(self) -> Rect:
        return Rect(self.runtime.screen_width / 2 - 70, 88, 140, 46)

    def resume_button_rect(self) -> Rect:
        return Rect(self.runtime.screen_width / 2 - 70, 140, 140, 38)

    def interaction_done_button_rect(self) -> Rect:
        return Rect(self.runtime.screen_width / 2 + 82, 68, 42, 18)

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
        else:
            self.draw_play()

    def draw_start(self) -> None:
        pyxel = self.pyxel
        pyxel.cls(1)
        self.draw_text_center(self.runtime.screen_width // 2, 28, "DriftWithMe", 7, scale=3)
        self.draw_text_center(self.runtime.screen_width // 2, 54, "Jack World P0 JWP006", 10)
        self.draw_button(self.start_button_rect(), "START", 11)
        self.draw_button(
            self.sound_button_rect(), "SOUND OFF" if self.audio.muted else "SOUND ON", 12
        )
        self.draw_text_center(self.runtime.screen_width // 2, 132, "SE PREVIEW 1-5", 7)
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
        self.draw_text_center(
            self.runtime.screen_width // 2,
            self.runtime.screen_height - 18,
            "ENTER/TAP START",
            13,
        )

    def draw_play(self) -> None:
        assert self.renderer is not None
        self.renderer.draw_scene(
            self.model, self.camera(), self.presentation_time, self.debug_enabled, self.effects
        )
        self.draw_hud()
        if self.model.interaction is not None:
            self.draw_interaction_panel()

    def draw_pause(self) -> None:
        pyxel = self.pyxel
        x = self.runtime.screen_width // 2 - 128
        y = 38
        pyxel.rect(x, y, 256, 154, 0)
        pyxel.rectb(x, y, 256, 154, 7)
        self.draw_text_center(self.runtime.screen_width // 2, y + 14, "PAUSE", 7, scale=3)
        self.draw_text_center(self.runtime.screen_width // 2, y + 48, "ENTER/ESC RESUME", 13)
        self.draw_text_center(self.runtime.screen_width // 2, y + 68, "R RESET SCENE", 13)
        self.draw_text_center(self.runtime.screen_width // 2, y + 88, "Q QUIT", 13)
        self.draw_button(self.resume_button_rect(), "RESUME", 11)

    def draw_hud(self) -> None:
        pyxel = self.pyxel
        pyxel.rect(6, 6, 164, 48, 0)
        pyxel.rectb(6, 6, 164, 48, 7)
        water = int(self.model.water)
        energy = int(self.model.energy)
        draw_pixel_text(pyxel, 14, 14, f"WATER {water:03d}", 12)
        draw_pixel_text(pyxel, 14, 32, f"ENERGY {energy:03d}", 10)
        self.draw_meter(94, 15, 66, 6, self.model.water, self.model.water_max, 12)
        self.draw_meter(94, 33, 66, 6, self.model.energy, self.model.energy_max, 10)
        self.draw_button(self.interact_button_rect(), self.interact_button_label(), 10)
        self.draw_button(self.action_button_rect(), self.action_button_label(), 8)
        self.draw_button(self.pause_button_rect(), "PAUSE", 5)
        self.draw_button(self.sound_button_rect(), "MUTE" if self.audio.muted else "SOUND", 12)
        if self.model.player.barrier_active:
            draw_pixel_text(pyxel, 184, 12, "BARRIER HOLD", 12)
        if self.last_denied_reason:
            draw_pixel_text(pyxel, 184, 30, f"DENIED:{self.last_denied_reason}", 8)
        if self.debug_enabled:
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
            pyxel.text(8, 158, "F focus / P pan", 7)

    def draw_meter(
        self, x: int, y: int, width: int, height: int, value: float, maximum: float, color: int
    ) -> None:
        filled = 0 if maximum <= 0.0 else int(width * max(0.0, min(value / maximum, 1.0)))
        self.pyxel.rect(x, y, width, height, 1)
        self.pyxel.rect(x, y, filled, height, color)
        self.pyxel.rectb(x, y, width, height, 7)

    def interact_button_label(self) -> str:
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
        if self.model.world_paused:
            return "ACTION"
        camera = self.camera()
        if self.model.captured_enemy(camera) is not None:
            return "ZAP"
        if self.model.bubble is not None:
            return "WAIT"
        if self.model.bubble_target(camera) is not None:
            return "BUBBLE"
        return "ACTION"

    def draw_interaction_panel(self) -> None:
        interaction = self.model.interaction
        if interaction is None:
            return
        pyxel = self.pyxel
        rect = Rect(self.runtime.screen_width / 2 - 132, 62, 264, 76)
        pyxel.rect(int(rect.x), int(rect.y), int(rect.width), int(rect.height), 0)
        pyxel.rectb(int(rect.x), int(rect.y), int(rect.width), int(rect.height), 7)
        self.draw_text_center(
            self.runtime.screen_width // 2,
            int(rect.y + 10),
            interaction.title,
            7,
            scale=2,
        )
        for index, line in enumerate(interaction.lines[:2]):
            self.draw_text_center(
                self.runtime.screen_width // 2,
                int(rect.y + 31 + index * 14),
                line,
                13,
                scale=1,
            )
        meter_x = int(rect.x + 20)
        meter_y = int(rect.y + rect.height - 14)
        meter_w = int(rect.width - 40)
        pyxel.rect(meter_x, meter_y, meter_w, 6, 1)
        pyxel.rect(meter_x, meter_y, int(meter_w * interaction.progress), 6, 12)
        pyxel.rectb(meter_x, meter_y, meter_w, 6, 7)
        self.draw_button(self.interaction_done_button_rect(), "DONE", 5)

    def draw_button(self, rect: Rect, label: str, color: int) -> None:
        pyxel = self.pyxel
        pyxel.rect(int(rect.x), int(rect.y), int(rect.width), int(rect.height), color)
        pyxel.rectb(int(rect.x), int(rect.y), int(rect.width), int(rect.height), 7)
        text = label.upper()
        scale = 2
        text_width, text_height = pixel_text_size(text, scale)
        while scale > 1 and (
            text_width > int(rect.width) - 8 or text_height > int(rect.height) - 8
        ):
            scale -= 1
            text_width, text_height = pixel_text_size(text, scale)
        text_x = int(rect.x + rect.width / 2 - text_width / 2)
        text_y = int(rect.y + rect.height / 2 - text_height / 2)
        draw_pixel_text(pyxel, text_x, text_y, text, 0, scale=scale)

    def draw_text_center(self, x: int, y: int, text: str, color: int, scale: int = 2) -> None:
        text = text.upper()
        text_width, _ = pixel_text_size(text, scale)
        draw_pixel_text(self.pyxel, x - text_width // 2, y, text, color, scale=scale)


def main() -> None:
    DriftWithMeApp()


if __name__ == "__main__":
    main()
