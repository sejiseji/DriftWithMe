"""Explicit, temporary week testing. Never uses a persistent save namespace."""

from __future__ import annotations

import sys
from urllib.parse import parse_qs

from drift_with_me.nudibranch_preview import NudibranchPreview
from drift_with_me.ring_puzzle import RingPuzzlePreviewMixin
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


class WeekDebugMixin(RingPuzzlePreviewMixin):
    def initialize_week_debug(self, enabled: bool) -> None:
        self.week_debug_active = enabled
        self.week_debug_menu_open = enabled
        self.week_debug_wait_release = False
        self.week_debug_month = 6
        self.week_debug_selection = 1
        self.ring_preview = None
        self.portrait_preview = None
        self.nudibranch_preview = None
        self.garden_props_preview = None
        self.garden_props_previous_projection = None
        self.park_preview_week = None
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
            "sprites": self.office_rect(260, 158, 70, 30),
            "garden": self.office_rect(334, 158, 70, 30),
            "portraits": self.office_rect(408, 158, 72, 30),
            "cancel": self.office_rect(32, 196, 220, 30),
            "park": self.office_rect(260, 196, 106, 30),
            "normal": self.office_rect(374, 196, 106, 30),
            "rings": self.office_rect(8, 3, 100, 20),
            "solo_rings": self.office_rect(404, 3, 100, 20),
        }

    def jump_to_debug_week(self, week: WorkWeek) -> bool:
        if not getattr(self, "week_debug_active", False) or week not in {
            WorkWeek(6, n) for n in range(1, 5)
        } | {WorkWeek(7, 1), WorkWeek(7, 2), WorkWeek(7, 3)}:
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
        self.park_preview_week = None
        self.portrait_preview = None
        self.nudibranch_preview = None
        self.garden_props_preview = None
        previous_projection = getattr(self, "garden_props_previous_projection", None)
        if previous_projection is not None:
            self.projection_mode = previous_projection
        self.garden_props_previous_projection = None
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
        if week == WorkWeek(7, 2):
            from drift_with_me.flowerbed import FlowerbedLayoutStore

            self.office = load_week_office(week)
            if getattr(self, "flowerbed_layout_store", None) is None:
                self.flowerbed_layout_store = FlowerbedLayoutStore()
            order, visit = self.flowerbed_layout_store.load_state()
            self.east_site_progress.flowerbed_order = order
            self.east_site_progress.flowerbed_visit = visit.snapshot()
        elif week != WorkWeek():
            self.office = load_week_office(week)
        self.week_office_history = {week: self.office}
        if week.number >= 3:
            self.east_site_progress.facts = set(SITE_FACTS.values())
            self.world.east_site_access_ready = True
        from drift_with_me.week3 import install_week3_world

        install_week3_world(self, enabled=week == WorkWeek(6, 3))
        install_week4_world(self, enabled=week == WorkWeek(6, 4))
        self.pending_week_office = None
        self.week_input_wait_for_release = self.field_input_wait_for_release = False
        self.office_focus = "questions"
        self.office_question_index = self.office_classification_index = 0
        self._processed_hitstop_event_ids.clear()
        self.clear_world_input_latches()
        from drift_with_me.july_week1 import install_july_world

        install_july_world(self, enabled=week == WorkWeek(7, 1))
        from drift_with_me.flowerbed import install_flowerbed_world

        install_flowerbed_world(self)
        if week == WorkWeek(7, 2):
            from drift_with_me.app import AppScreen

            self.screen = AppScreen.OFFICE
            self.model.player.x, self.model.player.z = 184, 424
            self.model.player.last_move_x, self.model.player.last_move_z = 0, -1
            self.camera_controller.reset(Vec3(184, 0, 424))
            self.model.snap_buddy(self.camera())
            self.week2_dialogue = None
            self.week2_wait_release = False
        self.july_wait_release = True
        self.july_fade_elapsed = 0.0
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
        if getattr(self, "ring_preview", None) is not None:
            self.update_ring_preview()
            return True
        if getattr(self, "park_preview_week", None) is not None:
            self.update_park_preview()
            return True
        if getattr(self, "portrait_preview", None) is not None:
            self.update_portrait_preview()
            return True
        if getattr(self, "garden_props_preview", None) is not None:
            self.update_garden_props_preview()
            return True
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
                if self.week_debug_month == 7:
                    self.week_debug_selection = 1
            elif action.startswith("week") and (
                self.week_debug_month == 6
                or self.week_debug_month == 7
                and action in {"week1", "week2", "week3"}
            ):
                self.week_debug_selection = int(action[-1])
            elif action == "start" and (
                self.week_debug_month == 6
                or self.week_debug_month == 7
                and self.week_debug_selection in (1, 2, 3)
            ):
                self.jump_to_debug_week(WorkWeek(self.week_debug_month, self.week_debug_selection))
            elif action == "portraits":
                self.start_portrait_preview("ユメサキ")
            elif action == "sprites":
                self.start_nudibranch_preview()
            elif action == "garden":
                self.start_garden_props_preview()
            elif action == "solo_rings":
                self.start_ring_preview("independent")
            elif action == "rings":
                self.start_ring_preview()
            elif action == "park":
                self.start_park_preview()
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
                ("第2週・花壇と調査" if self.week_debug_month == 7 and week == 2 else f"第{week}週")
                if self.week_debug_month == 6 or (self.week_debug_month == 7 and week in (1, 2, 3))
                else "準備中",
                selected=week == self.week_debug_selection,
                disabled=self.week_debug_month != 6
                and not (self.week_debug_month == 7 and week in (1, 2, 3)),
            )
        self.draw_week_debug_button(
            rects["start"],
            "選んだ週の最初から始める",
            disabled=self.week_debug_month != 6
            and not (self.week_debug_month == 7 and self.week_debug_selection in (1, 2, 3)),
        )
        self.draw_week_debug_button(rects["sprites"], "Sprite test")
        self.draw_week_debug_button(rects["garden"], "Garden test")
        self.draw_week_debug_button(rects["portraits"], "立ち絵")
        self.draw_week_debug_button(rects["park"], "公園比較")
        self.draw_week_debug_button(rects["rings"], "5 Rings")
        self.draw_week_debug_button(rects["solo_rings"], "Solo rings")
        self.draw_week_debug_button(
            rects["cancel"], "取消・テストに戻る", disabled=not self.session_started
        )
        self.draw_week_debug_button(rects["normal"], "通常プレイへ戻る")

    def start_park_preview(self) -> bool:
        if not getattr(self, "week_debug_active", False):
            return False
        self.jump_to_debug_week(WorkWeek(7, 2))
        from drift_with_me.app import AppScreen

        self.screen = AppScreen.PLAY
        self.flowerbed_dialogue = self.flowerbed_editor = None
        self.flowerbed_input_wait_release = False
        self.set_park_preview(WorkWeek(7, 1))
        return True

    def set_park_preview(self, week) -> None:
        from drift_with_me.northeast_park import install_park_world

        self.park_preview_week = week
        install_park_world(self, week)
        self.week_debug_wait_release = True

    def park_preview_rects(self):
        return {
            name: self.office_rect(8 + i * 83, 202, 79, 27)
            for i, name in enumerate(("w1", "w2", "w3", "w4", "aug", "menu"))
        }

    def update_park_preview(self) -> None:
        from drift_with_me.northeast_park import PREVIEW_WEEKS

        if self.key_pressed("KEY_ESCAPE"):
            self.jump_to_debug_week(WorkWeek(7, 2))
            self.flowerbed_dialogue = None
            self.week_debug_menu_open = True
            return
        for i, (name, rect) in enumerate(self.park_preview_rects().items()):
            if self.mouse_pressed_in(rect):
                if name == "menu":
                    self.jump_to_debug_week(WorkWeek(7, 2))
                    self.flowerbed_dialogue = None
                    self.week_debug_menu_open = True
                else:
                    self.set_park_preview(PREVIEW_WEEKS[i])
                return

    def draw_park_preview(self) -> None:
        from dataclasses import replace

        from drift_with_me.math3d import Vec3

        camera = replace(
            self.affine_scene_camera(self.camera()),
            target=Vec3(852, 0, 876),
            zoom=2.0,
            anchor_x=0.5,
            anchor_y=0.48,
        )
        self.renderer.draw_scene(
            self.model,
            camera,
            self.presentation_time,
            False,
            self.effects,
            exploration_markers=False,
        )
        self.draw_week_debug_button(
            self.office_rect(8, 4, 496, 24),
            self.park_preview_week.label + " 公園景観比較・保存なし",
        )
        for name, rect in self.park_preview_rects().items():
            self.draw_week_debug_button(
                rect,
                {
                    "w1": "7月1週",
                    "w2": "7月2週",
                    "w3": "7月3週",
                    "w4": "7月4週",
                    "aug": "8月",
                    "menu": "週選択",
                }[name],
            )

    def start_garden_props_preview(self) -> bool:
        if not getattr(self, "week_debug_active", False):
            return False
        from drift_with_me.app import AppScreen
        from drift_with_me.garden_props_preview import GardenPropsPreview
        from drift_with_me.math3d import AffineProjectionProfile, Vec3

        self.jump_to_debug_week(WorkWeek())
        self.garden_props_previous_projection = getattr(self, "projection_mode", "affine")
        self.projection_mode = "affine"
        self.affine_projection_profile = AffineProjectionProfile.from_config(self.runtime.raw)
        self.model.player.x, self.model.player.z = 400, 600
        self.camera_controller.reset(Vec3(400, 0, 600))
        self.model.snap_buddy(self.camera_controller.current)
        state = GardenPropsPreview.for_camera(
            self.affine_scene_camera(self.camera()), getattr(self, "presentation_time", 0.0)
        )
        self.garden_props_preview = self.model.garden_props_preview = state
        self.screen = AppScreen.PLAY
        return True

    def garden_props_preview_rects(self):
        return {
            name: self.office_rect(8 + i * 84, 202, 80, 26)
            for i, name in enumerate(("layout", "less", "overlap", "parts", "menu", "normal"))
        }

    def update_garden_props_preview(self) -> None:
        from drift_with_me.math3d import Vec3, screen_to_world_direction

        state = self.garden_props_preview
        for action, rect in self.garden_props_preview_rects().items():
            if not self.mouse_pressed_in(rect):
                continue
            if action == "layout":
                state.layout = 1 - state.layout
                state.rebuild()
            elif action == "less":
                state.amount = (state.amount + 1) % 4
                state.rebuild()
            elif action == "parts":
                state.parts = not state.parts
            elif action == "overlap":
                state.overlap = (state.overlap + 1) % 3
                x, z = state.actor_start if state.overlap == 0 else state.trays[0]
                if state.overlap:
                    z += 8 if state.overlap == 1 else -8
                self.model.player.x, self.model.player.z = x, z
                self.model.snap_buddy(self.camera())
                self.camera_controller.reset(Vec3(x, 0, z))
            elif action == "menu":
                self.jump_to_debug_week(WorkWeek(6, self.week_debug_selection))
                self.week_debug_menu_open = True
            elif action == "normal":
                self.return_from_week_debug()
            self.week_debug_wait_release = True
            return
        elapsed = state.elapsed(self.presentation_time)
        if state.parts:
            return
        # Move presentation actors only. No model.step, interactions, combat,
        # field-task events, day clock or save payload is advanced in this view.
        intent = self.keyboard_intent()
        direction = screen_to_world_direction(
            self.scene_camera(self.camera()),
            self.model.player.x,
            self.model.player.z,
            intent.screen_x,
            intent.screen_y,
        )
        if intent.strength:
            self.model.player.x += direction.x * 64 * elapsed
            self.model.player.z += direction.y * 64 * elapsed
            self.model.player.last_move_x, self.model.player.last_move_z = direction.x, direction.y
            self.model.snap_buddy(self.camera())
        self.update_camera_controller(elapsed)

    def draw_garden_props_preview(self) -> None:
        from drift_with_me.garden_props_preview import ASSET_IDS

        state = self.garden_props_preview
        if state.parts:
            self.pyxel.cls(1)
            for i, asset_id in enumerate(ASSET_IDS):
                asset = self.sprite_assets.get(asset_id)
                if asset is None:
                    continue
                col, row = i % 6, i // 6
                rect = self.office_rect(8 + col * 84, 66 + row * 42, 80, 28)
                frame = asset.frame()
                scale = min(rect.width / frame.width, rect.height / frame.height, 1.0)
                self.pyxel.blt(
                    rect.x + rect.width / 2 - frame.width / 2,
                    rect.y + rect.height / 2 - frame.height / 2,
                    frame.image,
                    0,
                    0,
                    frame.width,
                    frame.height,
                    colkey=asset.definition.colkey,
                    scale=scale,
                )
                label = (
                    asset_id.removeprefix("jlp1_")
                    .replace("seedling_", "sd_")
                    .replace("tray_", "tr_")
                    .replace("stake_short", "short")
                    .replace("stake_tall", "tall")
                )
                label = (
                    label.replace("string_projected_layer", "string")
                    .replace("stakes_string_assembly", "assembly")
                    .replace("string_ground_source", "raw string")
                    .replace("material_", "")
                    .replace("redorange", "red")
                    .replace("bluebell", "blue")
                )
                self.draw_office_text_in_rect(
                    self.office_rect(8 + col * 84, 94 + row * 42, 80, 13),
                    label,
                    7,
                    align="center",
                )
        else:
            self.renderer.draw_scene(
                self.model,
                self.scene_camera(self.camera()),
                self.presentation_time,
                False,
                self.effects,
            )
        self.draw_week_debug_button(
            self.office_rect(8, 4, 496, 24), "GARDEN PROPS / DRAFT / NO SAVE"
        )
        layout = "RECTANGLE" if state.layout == 0 else "CORNER"
        overlap = ("FREE", "BEHIND", "FRONT")[state.overlap]
        self.draw_week_debug_button(
            self.office_rect(8, 32, 496, 24),
            "18 ASSETS / SD=SEED / TR=TRAY / RAW=TOP-DOWN"
            if state.parts
            else f"{layout} / MATERIALS {3 - state.amount}/3 / {overlap} / COLLISION OFF",
        )
        for action, rect in self.garden_props_preview_rects().items():
            self.draw_week_debug_button(
                rect,
                {
                    "layout": "Layout",
                    "less": "Less",
                    "overlap": "Overlap",
                    "parts": "Map" if state.parts else "Parts",
                    "menu": "Week menu",
                    "normal": "Normal play",
                }[action],
            )

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

    def focus_laser_rects(self):
        return {
            name: self.office_rect(8 + i * 126, 164, 122, 28)
            for i, name in enumerate(("mode", "fire", "kind", "cancel"))
        }

    def place_nudibranch_preview_actors(self) -> None:
        from drift_with_me.camera import camera_ground_axes
        from drift_with_me.math3d import Vec3

        state = self.nudibranch_preview
        state.focus_action = None
        x, z = state.center
        if state.mode == "laser" and state.terrain == "water":
            x += 48  # Keep Jack clear of the shoreline column in this fixed test staging.
        self.camera_controller.reset(Vec3(x, 0, z))
        if state.mode == "laser":
            right, forward = camera_ground_axes(self.camera())
            state.target_anchor = (x + right.x * 28, z + right.y * 28)
            self.model.player.x = x - right.x * 38 - forward.x * 10
            self.model.player.z = z - right.y * 38 - forward.y * 10
            self.model.buddy.x = x - right.x * 14 + forward.x * 12
            self.model.buddy.z = z - right.y * 14 + forward.y * 12
            self.model.player.last_move_x, self.model.player.last_move_z = right.x, right.y
        else:
            state.target_anchor = None
            self.model.player.x, self.model.player.z = x, z
            self.model.snap_buddy(self.camera_controller.current)

    def start_focus_laser(self) -> bool:
        if not getattr(self, "week_debug_active", False) or self.nudibranch_preview is None:
            return False
        from drift_with_me.camera import camera_ground_axes
        from drift_with_me.focus_laser import FocusLaserAction
        from drift_with_me.math3d import Vec3

        state = self.nudibranch_preview
        if state.mode != "laser":
            return False
        state.freeze_direction()
        state.paused = False
        state.previous_time = self.presentation_time
        right, _ = camera_ground_axes(self.camera())
        x, z = state.target_anchor
        state.focus_action = FocusLaserAction.create(
            Vec3(self.model.player.x + right.x * 3, 8, self.model.player.z + right.y * 3),
            Vec3(
                self.model.buddy.x + right.x * 4,
                self.model.buddy.y + 5,
                self.model.buddy.z + right.y * 4,
            ),
            Vec3(x, 6.5, z),
            right,
            state.target_kind,
            f"{state.direction_name}_{state.frame_index:02d}",
        )
        return True

    def update_nudibranch_preview(self) -> None:

        state = self.nudibranch_preview
        extra = self.focus_laser_rects()
        if state.mode == "sprites":
            extra = {"mode": extra["mode"]}
        actions = {**self.nudibranch_preview_rects(), **extra}
        for action, rect in actions.items():
            if not self.mouse_pressed_in(rect):
                continue
            if action == "next":
                state.focus_action = None
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
                self.place_nudibranch_preview_actors()
            elif action == "mode":
                state.mode = "laser" if state.mode == "sprites" else "sprites"
                if state.mode == "laser":
                    state.terrain = "grass"  # Clear default staging; water remains selectable.
                state.freeze_direction()
                self.place_nudibranch_preview_actors()
            elif action == "fire":
                self.start_focus_laser()
            elif action == "kind" and state.mode == "laser":
                state.target_kind = "normal" if state.target_kind == "abnormal" else "abnormal"
                state.focus_action = None
            elif action == "cancel":
                state.focus_action = None
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
        title = f"SPRITE TEST / NO SAVE / {state.direction_name} / {state.frame_index + 1}/4 / 6fps"
        if state.mode == "laser":
            phase = "READY" if state.focus_action is None else state.focus_action.phase
            title = f"LASER / NO SAVE / {state.target_kind.upper()} / {phase}"
        self.draw_week_debug_button(
            self.office_rect(8, 4, 496, 24),
            title,
        )
        self.draw_week_debug_button(
            self.office_rect(8, 32, 496, 24),
            "NORMAL / ABNORMAL"
            if state.mode == "sprites"
            else "FUSE > JACK BITS > CURVE > STRAIGHT > PIXEL BURN",
        )
        extra = {"mode": "Laser test" if state.mode == "sprites" else "Sprite test"}
        if state.mode == "laser":
            extra.update(
                {"fire": "Fire / Replay", "kind": state.target_kind.upper(), "cancel": "Cancel"}
            )
        for name, text in extra.items():
            self.draw_week_debug_button(self.focus_laser_rects()[name], text)
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

    def start_portrait_preview(self, speaker: str) -> bool:
        if not getattr(self, "week_debug_active", False) or speaker not in ("ユメサキ", "ミヤノ"):
            return False
        from drift_with_me.app import AppScreen, FieldConversation

        self.jump_to_debug_week(WorkWeek())
        self.screen = AppScreen.PLAY
        self.portrait_preview = FieldConversation(
            "portrait_preview",
            (
                (speaker, "立ち絵・本文色の表示確認です。"),
                ("ジャック", "話者切替の表示確認です。"),
                ("ヒューズ", "話者切替の表示確認です。"),
                (speaker, "立ち絵の復帰を確認します。"),
            ),
            target_speaker=speaker,
        )
        return True

    def portrait_preview_rects(self):
        return {
            name: self.office_rect(8 + i * 74, 6, 70, 20)
            for i, name in enumerate(("yumesaki", "miyano", "next", "close", "menu"))
        }

    def update_portrait_preview(self) -> None:
        rects = {
            **self.portrait_preview_rects(),
            "advance": self.office_rect(356, 204, 96, 16),
        }
        for action, rect in rects.items():
            if not self.mouse_pressed_in(rect):
                continue
            if action in ("yumesaki", "miyano"):
                self.start_portrait_preview("ユメサキ" if action == "yumesaki" else "ミヤノ")
            elif action in ("next", "advance"):
                conversation = self.portrait_preview
                if conversation.index + 1 < len(conversation.lines):
                    conversation.index += 1
                else:
                    self.portrait_preview = None
            else:
                self.portrait_preview = None
                self.week_debug_menu_open = action == "menu"
            self.week_debug_wait_release = True
            return

    def draw_portrait_preview(self) -> None:
        self.draw_play()
        self.draw_field_conversation(self.portrait_preview)
        labels = ("ユメサキ", "ミヤノ", "次へ", "閉じる", "週選択")
        for rect, label in zip(self.portrait_preview_rects().values(), labels, strict=True):
            self.draw_week_debug_button(rect, label)
