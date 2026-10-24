"""Main-app field/test entry and rendering; no new narrative content."""

from __future__ import annotations

from copy import copy
from dataclasses import replace

from drift_with_me.math3d import Vec3
from drift_with_me.model import InputIntent
from drift_with_me.swarm_field import SwarmField
from drift_with_me.swarm_render import SwarmScene


class SwarmAppMixin:
    def ensure_swarm_field(self):
        story = self.august_swarm_active()
        if not getattr(self, "swarm_field_enabled", False) and not story:
            if (
                getattr(getattr(self, "model", None), "swarm_field", None) is not None
                and self.model.swarm_field.battle is None
            ):
                self.model.swarm_field = None
            return None
        key = f"{self.work_week.month}:{self.work_week.number}"
        field = getattr(self.model, "swarm_field", None)
        if field is None or field.week_key != key:
            config = None
            if story:
                from drift_with_me.config import load_data_json

                config = load_data_json("swarm_config.json")
                config.update(capture_water=12, finish_water=12, finish_energy=20)
                config["compositions"] = {
                    "northwest": ["urchin"] * 6,
                    "northeast": ["slug"] * 6,
                    "southeast": ["urchin", "slug"] * 3,
                }
            field = SwarmField(self.model, key, self.east_site_progress.swarm_progress, config)
            self.model.swarm_field = field
        return field

    def enter_swarm_test_field(self):
        from drift_with_me.app import AppScreen

        if not getattr(self, "swarm_field_enabled", False):
            return False
        if self.screen not in (AppScreen.START, AppScreen.OFFICE):
            return False
        if self.screen == AppScreen.START:
            self.start_game()
        if self.field_transition is not None or self.week_transition is not None:
            return False
        self.screen = AppScreen.PLAY
        self.swarm_test_field_active = True
        self.clear_world_input_latches()
        self.camera_controller.cancel_focus()
        self.ensure_swarm_field()
        return True

    def update_swarm_frame(self, elapsed):
        from drift_with_me.app import AppScreen

        if self.august_swarm_active() and (
            getattr(self, "field_transition", None) is not None
            or getattr(self, "week_transition", None) is not None
        ):
            return False

        if not getattr(self, "swarm_field_enabled", False) and not self.august_swarm_active():
            self.ensure_swarm_field()
            return False
        if self.key_pressed("KEY_F5") and self.enter_swarm_test_field():
            return True
        field = self.ensure_swarm_field()
        if field is None:
            return False
        if self.screen == AppScreen.PAUSE and field.battle is not None:
            self.update_pause_screen()
            return True
        if self.screen != AppScreen.PLAY:
            return False
        if field.battle is not None:
            if self.mouse_pressed_in(self.sound_button_rect()):
                self.audio.toggle_mute()
                return True
            if self.key_pressed("KEY_ESCAPE") or self.mouse_pressed_in(self.pause_button_rect()):
                self.screen = AppScreen.PAUSE
                self.clear_world_input_latches()
                return True
            self.clear_world_input_latches()
            down = self.travel_input_held()
            if getattr(self, "swarm_wait_release", False):
                if not down:
                    self.swarm_wait_release = False
                    self.swarm_action_down = False
                pressed = False
            else:
                keyboard, button = self.keyboard_intent(), self.ui_button_intent()
                action_down = keyboard.barrier or button.barrier
                pressed = (
                    keyboard.action_pressed
                    or button.action_pressed
                    or action_down
                    and not getattr(self, "swarm_action_down", False)
                )
                self.swarm_action_down = action_down
            events = self.model.step(
                InputIntent(action_pressed=pressed), self.camera(), min(max(0, elapsed), 0.1)
            )
            self.process_events(events)
            self.effects.update(elapsed, self.model)
            return True
        if getattr(self, "combat_camera_restore", None) is not None:
            self.update_combat_camera_restore(elapsed)
        if getattr(self, "swarm_return_fade", 0) > 0:
            self.clear_world_input_latches()
            self.swarm_return_fade = max(0, self.swarm_return_fade - elapsed)
            return True
        if getattr(self, "swarm_wait_release", False):
            self.clear_world_input_latches()
            if not self.travel_input_held():
                self.swarm_wait_release = False
            return True
        if self.august_swarm_active():
            self.sync_august_swarm_sites()
            self.update_play_screen(elapsed)
            return True
        if not getattr(self, "swarm_test_field_active", False):
            return False
        # Explicit shortcuts move the real player, then normal proximity starts combat.
        if self.model.combat_session is None and not self.model.world_paused:
            for key, site in zip(
                ("KEY_F6", "KEY_F7", "KEY_F8"), field.config["sites"], strict=True
            ):
                if self.key_pressed(key):
                    x, z = field.config["sites"][site]
                    if not self.world.collides_player(
                        x, z, self.model.player_solid_half_x, self.model.player_solid_half_z
                    ):
                        self.model.player.x, self.model.player.z = x, z
                        self.camera_controller.reset(Vec3(x, 0, z))
                        self.model.snap_buddy(self.camera())
                    break
        self.update_play_screen(elapsed)
        return True

    def process_swarm_event(self, event):
        if event.kind == "swarm_site_cleared" and self.august_swarm_active():
            self.sync_august_swarm_sites()
        if event.kind not in {"swarm_started", "swarm_restored"}:
            return
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        self.swarm_wait_release = True
        self.swarm_action_down = False
        if event.kind == "swarm_started":
            self.combat_camera_restore = None
            self.combat_camera_snapshot_zoom = self.camera_zoom(self.camera())
        if event.kind == "swarm_restored":
            if not event.payload.get("won", False):
                self.camera_controller.cancel_focus()
                self.camera_controller.reset(Vec3(self.model.player.x, 0, self.model.player.z))
                self.model.snap_buddy(self.camera())
                self.swarm_return_fade = 0.4
                self.combat_camera_restore = None
                self.last_combat_scene_camera = None
                self.combat_camera_snapshot_zoom = None
            else:
                self.start_combat_camera_restore()
            self.swarm_view = None

    def draw_swarm_battle(self):
        field = getattr(self.model, "swarm_field", None)
        if field is None or field.battle is None:
            return False
        view = getattr(self, "swarm_view", None)
        if view is None or view.battle is not field.battle:
            layout = copy(field.presentation_session())
            layout.phase, layout.elapsed_sec = "PARRY_TIMING", 10
            view = self.swarm_view = SwarmScene(
                field, self.renderer, self.swarm_scene_camera(layout)
            )
        view.camera = self.swarm_scene_camera(field.presentation_session())
        view.draw(self)
        return True

    def swarm_scene_camera(self, session):
        camera = self.combat_camera_for_session(
            self.camera(), session, Vec3(self.model.player.x, 0, self.model.player.z)
        )
        field = self.model.swarm_field
        base_anchor = self.camera().anchor_y
        desired_anchor = float(field.config.get("camera_player_anchor_y", 0.70))
        entry_sec = float(self.runtime.raw["combat_v1"]["entry"]["camera_transition_sec"])
        amount = min(1, max(0, session.elapsed_sec / max(1e-6, entry_sec)))
        amount = amount * amount * (3 - 2 * amount)
        if session.phase == "VICTORY_CUE":
            delay = self.combat_dynamic_camera_duration("victory_restore_delay", 0.4)
            duration = self.combat_dynamic_camera_duration("victory_restore", 0.32)
            restore = min(1, max(0, (session.phase_elapsed_sec - delay) / max(1e-6, duration)))
            amount *= 1 - restore * restore * (3 - 2 * restore)
        camera = replace(camera, anchor_y=base_anchor + (desired_anchor - base_anchor) * amount)
        self.last_combat_scene_camera = camera
        return (
            self.affine_scene_camera(camera)
            if self.projection_mode == "affine"
            else self.presentation_camera(camera)
        )

    def draw_swarm_sites(self, camera):
        if self.august_active():
            return
        field = getattr(self.model, "swarm_field", None)
        if field is None:
            return
        for site, (x, z) in field.config["sites"].items():
            point = camera.project(Vec3(x, 0, z))
            if point is not None:
                color = 11 if site in field.cleared else 10
                self.pyxel.circb(point.x, point.y, 12, color)
                self.pyxel.text(
                    point.x - 12, point.y - 20, "CLEAR" if site in field.cleared else "SWARM", color
                )
        self.pyxel.text(
            8,
            self.runtime.screen_height - 10,
            f"SWARM {len(field.cleared)}/3  F6:NW F7:NE F8:SE"
            + ("  COMPLETE" if field.complete else ""),
            10,
        )

    def draw_swarm_return_fade(self):
        remaining = getattr(self, "swarm_return_fade", 0)
        if remaining > 0:
            self.pyxel.dither(min(1, remaining / 0.4))
            self.pyxel.rect(0, 0, self.runtime.screen_width, self.runtime.screen_height, 0)
            self.pyxel.dither(1)
