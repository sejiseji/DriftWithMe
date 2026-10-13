"""July patrol scene coordinator; freezes input during one-time authored arrivals."""

from drift_with_me.field_visit import FieldConversation
from drift_with_me.july_week1 import (
    AFTER_CLEAR,
    FUJI_ID,
    JULY_FACTS,
    LABELS,
    PROFESSOR_ID,
    RESEARCHERS,
    SPEAKERS,
    STUDENT_ID,
    TASK_CASE,
    install_july_world,
)
from drift_with_me.math3d import Vec3
from drift_with_me.office import FieldResult
from drift_with_me.week_cycle import WorkWeek


class JulyStoryMixin:
    def july_active(self):
        return getattr(self, "work_week", WorkWeek()) == WorkWeek(7, 1) and hasattr(
            self.office, "july_progress"
        )

    def sync_july_progress(self):
        if self.july_active():
            from drift_with_me.july_combat import defeated_july_ids

            self.office.july_progress.defeated.update(defeated_july_ids(self.model))

    def update_july_story(self, elapsed):
        from drift_with_me.app import AppScreen

        if not self.july_active() or self.screen != AppScreen.PLAY:
            return False
        self.sync_july_progress()
        progress = self.office.july_progress
        if self.model.combat_session is not None or self.model.world_paused:
            return False
        if progress.cleared and not progress.researchers_arrived and progress.stage == "patrol":
            progress.stage, progress.scene_index = "after_clear", 0
            self.july_wait_release = True
            self.july_fade_elapsed = 0.0
        if progress.stage == "return_pending":
            if self.office.active_field_task is not None:
                self.complete_office_field_task()
            return self.field_transition is not None
        if progress.stage == "patrol":
            if progress.complete and self.office.active_field_task is not None:
                progress.stage = "return_pending"
                self.complete_office_field_task()
                return True
            return False
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        self.accumulator = 0.0
        if progress.stage == "arrival_fade":
            self.july_fade_elapsed = getattr(self, "july_fade_elapsed", 0.0) + elapsed
            if self.july_fade_elapsed >= 0.45:
                progress.researchers_arrived = True
                install_july_world(self)
                self.model.player.x, self.model.player.z = 520, 528
                self.camera_controller.reset(Vec3(520, 0, 528))
                self.model.snap_buddy(self.camera_controller.current)
                progress.stage, progress.scene_index = "researchers", 0
                self.july_wait_release = True
            self.checkpoint_progress()
            return True
        if getattr(self, "july_wait_release", True):
            if not self.travel_input_held():
                self.july_wait_release = False
            self.checkpoint_progress()
            return True
        if self.key_pressed("KEY_RETURN", "KEY_Z") or self.mouse_pressed_in(
            self.office_rect(40, 126, 432, 100)
        ):
            lines = AFTER_CLEAR if progress.stage == "after_clear" else RESEARCHERS
            if progress.scene_index + 1 < len(lines):
                progress.scene_index += 1
            elif progress.stage == "after_clear":
                progress.stage, progress.scene_index = "arrival_fade", 0
                self.july_fade_elapsed = 0.0
            else:
                progress.researchers_talked = True
                progress.stage, progress.scene_index = "patrol", 0
            self.july_wait_release = True
        self.checkpoint_progress()
        return True

    def draw_july_story(self):
        if not self.july_active():
            return
        progress = self.office.july_progress
        if progress.stage in {"after_clear", "researchers"}:
            lines = AFTER_CLEAR if progress.stage == "after_clear" else RESEARCHERS
            speaker = lines[progress.scene_index][0]
            self.draw_field_conversation(
                FieldConversation(
                    "july_story",
                    lines,
                    progress.scene_index,
                    target_speaker=speaker if speaker in SPEAKERS.values() else None,
                )
            )
        elif progress.stage == "arrival_fade":
            self.pyxel.dither(min(1, getattr(self, "july_fade_elapsed", 0) / 0.45))
            self.pyxel.rect(0, 0, self.runtime.screen_width, self.runtime.screen_height, 0)
            self.pyxel.dither(1)

    def draw_july_markers(self):
        if not self.july_active():
            return
        progress = self.office.july_progress
        # Explicit placeholder markers: no claim that walking sprites are finished.
        camera = self.scene_camera(self.camera())
        for target in (PROFESSOR_ID, STUDENT_ID):
            obj = self.world.object_by_id(target)
            if obj is None:
                continue
            p = camera.project(Vec3(obj.x, 24, obj.z))
            if p is None:
                continue
            x, y = round(p.x), round(p.y)
            self.pyxel.text(
                x - 12, y - 8, "YUMESAKI TEMP" if target == PROFESSOR_ID else "MIYANO TEMP", 13
            )
        if progress.researchers_arrived:
            self.draw_office_text_in_rect(
                self.office_rect(8, 30, 240, 16), "研究者のマップ表示は仮素材", 13
            )

    def july_field_result(self):
        task = self.office.active_field_task
        progress = self.office.july_progress
        if task is not None and task.case_id == TASK_CASE and progress.complete:
            return FieldResult(
                task.task_id, TASK_CASE, "JULY1_COMPLETED", tuple(sorted(JULY_FACTS)), ()
            )
        return None

    def july_target_speaker(self, target):
        return SPEAKERS.get(target)

    def july_target_label(self, target):
        return LABELS.get(target, "確認")

    def july_portrait_id(self, conversation):
        if self.july_active() and conversation.target_id == FUJI_ID:
            speaker = conversation.lines[conversation.index][0]
            return "fuji_map_knees" if speaker == "フジ" else None
        return None
