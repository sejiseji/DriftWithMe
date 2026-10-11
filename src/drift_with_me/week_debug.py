"""Explicit, temporary week testing. Never uses a persistent save namespace."""

from __future__ import annotations

import sys
from urllib.parse import parse_qs

from drift_with_me.nudibranch_preview import NudibranchPreview
from drift_with_me.week_cycle import WorkWeek, load_week_office


def debug_launch_requested() -> bool:
    if sys.platform != "emscripten":
        return False
    import js

    return parse_qs(str(js.location.search).lstrip("?")).get("debug") == ["weeks"]


class TemporaryProgressStore:
    available = True
    has_record = False
    enabled = False
    message = "テスト中の進行は保存されません。"

    def load(self):
        return None

    def write(self, _payload) -> bool:
        return False

    def authorize_new_game(self) -> None:
        pass


class WeekDebugMixin:
    def initialize_week_debug(self, enabled: bool) -> None:
        self.week_debug_active = enabled
        self.week_debug_menu_open = enabled
        self.week_debug_wait_release = False
        self.week_debug_month = 6
        self.week_debug_selection = 1
        self.nudibranch_preview = None
        self.normal_progress_store = self.progress_store
        if enabled:
            self.progress_store = TemporaryProgressStore()
            self.saved_progress = None

    def week_debug_badge_rect(self):
        return self.office_rect(8, 32, 112, 24)

    def week_debug_rects(self):
        return {
            **{f"month{m}": self.office_rect(32 + (m - 6) * 152, 48, 144, 30) for m in (6, 7, 8)},
            **{
                f"week{n}": self.office_rect(
                    32 + ((n - 1) % 2) * 228, 86 + ((n - 1) // 2) * 34, 220, 30
                )
                for n in range(1, 5)
            },
            "start": self.office_rect(32, 158, 220, 30),
            "sprites": self.office_rect(260, 158, 220, 30),
            "cancel": self.office_rect(32, 196, 220, 30),
            "normal": self.office_rect(260, 196, 220, 30),
        }

    def jump_to_debug_week(self, week: WorkWeek) -> bool:
        if not getattr(self, "week_debug_active", False) or week.month != 6:
            return False
        from drift_with_me.app import (
            CameraController,
            EffectSystem,
            GameModel,
            Vec3,
            install_week4_world,
            load_world_data,
        )
        from drift_with_me.east_site import SITE_FACTS

        # A fresh world/model removes map flags, combat, interactions and enemy state.
        self.world = load_world_data()
        self.nudibranch_preview = None
        self.model = GameModel(self.runtime.raw, self.world)
        self.camera_controller = CameraController(
            self.runtime.raw,
            self.world,
            self.runtime.screen_width,
            self.runtime.screen_height,
            Vec3(self.model.player.x, 0, self.model.player.z),
        )
        self.effects = EffectSystem(self.runtime.raw)
        self.start_game(new_game=True)
        self.work_week = self.map_work_week = week
        if week.number > 1:
            self.office = load_week_office(week)
        self.week_office_history = {week: self.office}
        if week.number >= 3:
            self.east_site_progress.facts = set(SITE_FACTS.values())
            self.world.east_site_access_ready = True
        install_week4_world(self, enabled=week.number == 4)
        self.pending_week_office = None
        self.week_input_wait_for_release = self.field_input_wait_for_release = False
        self.office_focus = "questions"
        self.office_question_index = self.office_classification_index = 0
        self._processed_hitstop_event_ids.clear()
        self.clear_world_input_latches()
        self.week_debug_menu_open = False
        self.week_debug_wait_release = True
        return True

    def return_from_week_debug(self) -> None:
        from drift_with_me.app import AppScreen

        # Rebuild the map while the temporary store is still attached.
        self.jump_to_debug_week(WorkWeek())
        # Disable checkpointing before attaching the real store.
        self.screen = AppScreen.START
        self.session_started = False
        self.field_transition = self.week_transition = self.field_conversation = None
        self.first_sight_conversation = None
        self.new_game_confirmation = False
        self.last_checkpoint = None
        self.progress_store = self.normal_progress_store
        self.saved_progress = self.progress_store.load()
        self.week_debug_active = self.week_debug_menu_open = False
        self.pointer.cancel()
        self.week_debug_wait_release = True
        if sys.platform == "emscripten":
            import js

            url = js.URL.new(str(js.location.href))
            url.searchParams.delete("debug")
            js.history.replaceState(None, "", str(url.href))

    def update_week_debug(self) -> bool:
        preview = getattr(self, "nudibranch_preview", None)
        if preview is not None:
            preview.tick(self.presentation_time)
        if getattr(self, "week_debug_wait_release", False):
            if not self.pointer_snapshot.down:
                self.week_debug_wait_release = False
            return True
        if not getattr(self, "week_debug_active", False):
            return False
        if preview is not None:
            self.update_nudibranch_preview()
            return True
        if not self.week_debug_menu_open:
            if self.mouse_pressed_in(self.week_debug_badge_rect()):
                self.week_debug_menu_open = True
                self.week_debug_wait_release = True
                return True
            return False
        for action, rect in self.week_debug_rects().items():
            if not self.mouse_pressed_in(rect):
                continue
            if action.startswith("month"):
                self.week_debug_month = int(action[-1])
            elif action.startswith("week") and self.week_debug_month == 6:
                self.week_debug_selection = int(action[-1])
            elif action == "start" and self.week_debug_month == 6:
                self.jump_to_debug_week(WorkWeek(6, self.week_debug_selection))
            elif action == "sprites":
                self.start_nudibranch_preview()
            elif action == "cancel" and self.session_started:
                self.week_debug_menu_open = False
            elif action == "normal":
                self.return_from_week_debug()
            self.week_debug_wait_release = True
            break
        return True

    def draw_week_debug_button(self, rect, text: str, selected=False, disabled=False):
        self.pyxel.rect(
            int(rect.x),
            int(rect.y),
            int(rect.width),
            int(rect.height),
            5 if disabled else 3 if selected else 1,
        )
        self.draw_office_text_in_rect(rect, text, 6 if disabled else 7, align="center")

    def draw_week_debug_menu(self) -> None:
        self.pyxel.cls(0)
        self.draw_office_text_in_rect(
            self.office_rect(32, 4, 448, 20), "週移動テスト", 7, align="center"
        )
        self.draw_office_text_in_rect(
            self.office_rect(32, 26, 448, 18),
            "保存なし・再読込でテストの進行は消えます",
            10,
            align="center",
        )
        rects = self.week_debug_rects()
        for month in (6, 7, 8):
            self.draw_week_debug_button(
                rects[f"month{month}"], f"{month}月", selected=self.week_debug_month == month
            )
        for week in range(1, 5):
            self.draw_week_debug_button(
                rects[f"week{week}"],
                f"第{week}週" if self.week_debug_month == 6 else "準備中",
                selected=week == self.week_debug_selection,
                disabled=self.week_debug_month != 6,
            )
        self.draw_week_debug_button(
            rects["start"], "選んだ週の最初から始める", disabled=self.week_debug_month != 6
        )
        self.draw_week_debug_button(rects["sprites"], "Nudibranch sprite test")
        self.draw_week_debug_button(
            rects["cancel"], "取消・テストに戻る", disabled=not self.session_started
        )
        self.draw_week_debug_button(rects["normal"], "通常プレイへ戻る")

    def start_nudibranch_preview(self) -> bool:
        if not getattr(self, "week_debug_active", False):
            return False
        from drift_with_me.app import AppScreen
        from drift_with_me.math3d import Vec3

        self.jump_to_debug_week(WorkWeek())
        self.nudibranch_preview = NudibranchPreview(previous_time=self.presentation_time)
        self.model.nudibranch_preview = self.nudibranch_preview
        x, z = self.nudibranch_preview.center
        self.model.player.x, self.model.player.z = x, z
        self.camera_controller.reset(Vec3(x, 0.0, z))
        self.model.snap_buddy(self.camera_controller.current)
        self.screen = AppScreen.PLAY
        return True

    def nudibranch_preview_rects(self):
        return {
            name: self.office_rect(8 + i * 84, 200, 80, 28)
            for i, name in enumerate(("next", "auto", "pause", "terrain", "menu", "normal"))
        }

    def update_nudibranch_preview(self) -> None:
        from drift_with_me.math3d import Vec3

        state = self.nudibranch_preview
        for action, rect in self.nudibranch_preview_rects().items():
            if not self.mouse_pressed_in(rect):
                continue
            if action == "next":
                state.freeze_direction()
                state.direction = (state.direction + 1) % 8
            elif action == "auto":
                if state.automatic:
                    state.freeze_direction()
                else:
                    state.automatic = True
            elif action == "pause":
                state.paused = not state.paused
            elif action == "terrain":
                state.terrain = "grass" if state.terrain == "water" else "water"
                x, z = state.center
                self.model.player.x, self.model.player.z = x, z
                self.camera_controller.reset(Vec3(x, 0.0, z))
                self.model.snap_buddy(self.camera_controller.current)
            elif action == "menu":
                self.jump_to_debug_week(WorkWeek(6, self.week_debug_selection))
                self.week_debug_menu_open = True
            elif action == "normal":
                self.return_from_week_debug()
            self.week_debug_wait_release = True
            break

    def draw_nudibranch_preview(self) -> None:
        state = self.nudibranch_preview
        self.renderer.draw_scene(
            self.model,
            self.scene_camera(self.camera()),
            self.presentation_time,
            False,
            self.effects,
        )
        self.draw_week_debug_button(
            self.office_rect(8, 4, 496, 24),
            f"SPRITE TEST / NO SAVE / {state.direction_name} / {state.frame_index + 1}/4 / 6fps",
        )
        self.draw_week_debug_button(self.office_rect(8, 32, 496, 24), "NORMAL / ABNORMAL")
        labels = {
            "next": "Next dir",
            "auto": "Auto ON" if state.automatic else "Auto OFF",
            "pause": "Resume" if state.paused else "Pause",
            "terrain": state.terrain.upper(),
            "menu": "Week menu",
            "normal": "Normal play",
        }
        for name, rect in self.nudibranch_preview_rects().items():
            self.draw_week_debug_button(rect, labels[name])
