from __future__ import annotations

import time
from enum import Enum, auto

from drift_with_me import config
from drift_with_me.audio import AudioEngine
from drift_with_me.input import PointerInput, Rect
from drift_with_me.math3d import CameraState, Vec3, normalize2
from drift_with_me.model import GameModel, InputIntent, merge_intents
from drift_with_me.render import Renderer
from drift_with_me.world import load_world_data


class AppScreen(Enum):
    START = auto()
    PLAY = auto()
    PAUSE = auto()


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
        self.last_denied_reason = ""

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
        return CameraState.from_config(
            self.runtime.raw,
            target=Vec3(self.model.player.x, 0.0, self.model.player.z),
            viewport_width=self.runtime.screen_width,
            viewport_height=self.runtime.screen_height,
            zoom=1.0,
        )

    def update(self) -> None:
        pyxel = self.pyxel
        elapsed = self.consume_elapsed()
        self.presentation_time += elapsed
        self.frame += 1

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
            self.previous_time = None
        if pyxel.btnp(pyxel.KEY_Q):
            pyxel.quit()
        if self.mouse_pressed_in(self.start_button_rect()):
            self.screen = AppScreen.PLAY
            self.previous_time = None
        if self.mouse_pressed_in(self.sound_button_rect()):
            self.audio.toggle_mute()

    def update_play_screen(self, elapsed: float) -> None:
        pyxel = self.pyxel
        if pyxel.btnp(pyxel.KEY_ESCAPE):
            self.screen = AppScreen.PAUSE
            self.pointer.cancel()
            return

        keyboard_intent = self.keyboard_intent()
        pointer_intent = self.pointer_intent(elapsed)
        ui_action_intent = self.ui_action_intent()
        if keyboard_intent.action_pressed or ui_action_intent.action_pressed:
            self.pending_action_pressed = True
        base_intent = merge_intents(keyboard_intent, pointer_intent, ui_action_intent)

        self.accumulator += elapsed
        fixed_dt = self.runtime.fixed_dt
        max_steps = int(self.runtime.raw["simulation"]["max_steps_per_callback"])
        steps = 0
        step_camera = self.camera()
        all_events = []
        while self.accumulator >= fixed_dt and steps < max_steps:
            step_intent = InputIntent(
                screen_x=base_intent.screen_x,
                screen_y=base_intent.screen_y,
                strength=base_intent.strength,
                barrier=base_intent.barrier,
                action_pressed=self.pending_action_pressed,
                interact_pressed=base_intent.interact_pressed,
            )
            self.pending_action_pressed = False
            events = self.model.step(step_intent, step_camera, fixed_dt)
            all_events.extend(events)
            step_camera = self.camera()
            self.accumulator -= fixed_dt
            steps += 1

        if steps >= max_steps and self.accumulator >= fixed_dt:
            self.accumulator = 0.0
            self.model.debug.discarded_elapsed_count += 1
        self.model.debug.fixed_steps_last_callback = steps
        if all_events:
            for event in all_events:
                if event.kind == "action_denied":
                    self.last_denied_reason = str(event.payload.get("reason", "denied"))
            self.audio.play_events(all_events)

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

    def pointer_intent(self, elapsed: float) -> InputIntent:
        pyxel = self.pyxel
        mouse_button = getattr(pyxel, "MOUSE_BUTTON_LEFT", 0)
        return self.pointer.update(
            down=pyxel.btn(mouse_button),
            x=float(pyxel.mouse_x),
            y=float(pyxel.mouse_y),
            dt=elapsed,
            ui_rects=self.active_ui_rects(),
        )

    def ui_action_intent(self) -> InputIntent:
        return InputIntent(action_pressed=self.mouse_pressed_in(self.action_button_rect()))

    def mouse_pressed_in(self, rect: Rect) -> bool:
        pyxel = self.pyxel
        mouse_button = getattr(pyxel, "MOUSE_BUTTON_LEFT", 0)
        return pyxel.btnp(mouse_button) and rect.contains(
            float(pyxel.mouse_x), float(pyxel.mouse_y)
        )

    def active_ui_rects(self) -> tuple[Rect, ...]:
        return (self.action_button_rect(), self.pause_button_rect(), self.sound_button_rect())

    def action_button_rect(self) -> Rect:
        return Rect(self.runtime.screen_width - 62, self.runtime.screen_height - 56, 52, 46)

    def pause_button_rect(self) -> Rect:
        return Rect(self.runtime.screen_width - 54, 6, 48, 34)

    def sound_button_rect(self) -> Rect:
        return Rect(8, self.runtime.screen_height - 36, 58, 28)

    def start_button_rect(self) -> Rect:
        return Rect(self.runtime.screen_width / 2 - 48, 96, 96, 32)

    def preview_button_rects(self) -> tuple[tuple[str, Rect], ...]:
        names = self.audio.preview_events
        start_x = self.runtime.screen_width / 2 - 117
        y = 146
        return tuple(
            (name, Rect(start_x + index * 48, y, 40, 30)) for index, name in enumerate(names)
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
        self.draw_text_center(self.runtime.screen_width // 2, 46, "DriftWithMe", 7)
        self.draw_text_center(self.runtime.screen_width // 2, 62, "Jack World P0 E0", 10)
        self.draw_button(self.start_button_rect(), "START", 11)
        self.draw_button(
            self.sound_button_rect(), "SOUND OFF" if self.audio.muted else "SOUND ON", 12
        )
        self.draw_text_center(self.runtime.screen_width // 2, 136, "SE PREVIEW 1-5", 7)
        for index, (event_name, rect) in enumerate(self.preview_button_rects(), start=1):
            self.draw_button(rect, str(index), 5)
            self.pyxel.text(int(rect.x - 2), int(rect.y + rect.height + 4), event_name[:7], 7)
        self.draw_text_center(
            self.runtime.screen_width // 2,
            self.runtime.screen_height - 18,
            "ENTER or TAP START",
            13,
        )

    def draw_play(self) -> None:
        assert self.renderer is not None
        self.renderer.draw_scene(
            self.model, self.camera(), self.presentation_time, self.debug_enabled
        )
        self.draw_hud()

    def draw_pause(self) -> None:
        pyxel = self.pyxel
        x = self.runtime.screen_width // 2 - 86
        y = 58
        pyxel.rect(x, y, 172, 84, 0)
        pyxel.rectb(x, y, 172, 84, 7)
        self.draw_text_center(self.runtime.screen_width // 2, y + 14, "PAUSE", 7)
        self.draw_text_center(self.runtime.screen_width // 2, y + 34, "ENTER/ESC RESUME", 13)
        self.draw_text_center(self.runtime.screen_width // 2, y + 48, "R RESET SCENE", 13)
        self.draw_text_center(self.runtime.screen_width // 2, y + 62, "Q QUIT", 13)
        self.draw_button(self.start_button_rect(), "RESUME", 11)

    def draw_hud(self) -> None:
        pyxel = self.pyxel
        pyxel.rect(6, 6, 132, 36, 0)
        pyxel.rectb(6, 6, 132, 36, 7)
        water = int(self.model.water)
        energy = int(self.model.energy)
        pyxel.text(12, 12, f"WATER {water:03d}", 12)
        pyxel.text(12, 24, f"ENERGY {energy:03d}", 10)
        self.draw_button(self.action_button_rect(), "ACTION", 8)
        self.draw_button(self.pause_button_rect(), "PAUSE", 5)
        self.draw_button(self.sound_button_rect(), "MUTE" if self.audio.muted else "SOUND", 12)
        if self.model.player.barrier_active:
            pyxel.text(148, 12, "BARRIER HOLD", 12)
        if self.last_denied_reason:
            pyxel.text(148, 24, f"DENIED:{self.last_denied_reason}", 8)
        if self.debug_enabled:
            pyxel.text(8, 48, f"pos={self.model.player.x:.1f},{self.model.player.z:.1f}", 7)
            pyxel.text(8, 58, f"steps={self.model.debug.fixed_steps_last_callback}", 7)
            pyxel.text(8, 68, f"input={self.pointer.state.name}", 7)
            pyxel.text(8, 78, f"discard={self.model.debug.discarded_elapsed_count}", 7)

    def draw_button(self, rect: Rect, label: str, color: int) -> None:
        pyxel = self.pyxel
        pyxel.rect(int(rect.x), int(rect.y), int(rect.width), int(rect.height), color)
        pyxel.rectb(int(rect.x), int(rect.y), int(rect.width), int(rect.height), 7)
        text_x = int(rect.x + rect.width / 2 - len(label) * 2)
        text_y = int(rect.y + rect.height / 2 - 3)
        pyxel.text(text_x, text_y, label, 0)

    def draw_text_center(self, x: int, y: int, text: str, color: int) -> None:
        self.pyxel.text(x - len(text) * 2, y, text, color)


def main() -> None:
    DriftWithMeApp()


if __name__ == "__main__":
    main()
