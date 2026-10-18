"""Read-only goal presentation; visibility never changes field progression."""

from dataclasses import dataclass

from drift_with_me.east_site import SITE_FACTS, SITE_LABELS
from drift_with_me.input import Rect
from drift_with_me.week3 import LABELS
from drift_with_me.week3 import SITE_FACTS as W3_FACTS
from drift_with_me.week3 import TASK_CASE as W3_CASE
from drift_with_me.week4 import TASK_CASE as W4_CASE


@dataclass(frozen=True)
class Goal:
    text: str
    done: bool


def map_goals(app):
    office = getattr(app, "office", None)
    task = office.active_field_task if office is not None else None
    if task is None or office.current_session is None:
        return None, ()
    session = office.current_session
    if task.case_id == "OFF-JUL-W3-SURVEY":
        p = office.week3_progress
        small = (
            Goal("造園の進捗を確認", p.fuji_seen),
            Goal(f"小端末を回収 {len(p.recovered)}/2", len(p.recovered) == 2),
            Goal("親機を停止して回収", p.parent_recovered),
        )
        done = p.parent_recovered
    elif task.case_id == "OFF-JUL-W2-RESEARCH":
        from drift_with_me.july_week2 import SITES

        p = office.week2_progress
        small = (Goal("花壇を確認", app.flowerbed_visit_state().complete),) + tuple(
            Goal(label, ident in p.checked) for ident, (label, _, _) in SITES.items()
        )
        done = app.week2_ready()
    elif task.case_id == "OFF-JUL-W1-PEST":
        p = office.july_progress
        small = (
            Goal(f"ウミウシを駆除 {len(p.defeated)}/4", p.cleared),
            Goal("研究者を案内", p.researchers_talked),
            Goal("フジの追加資材を確認", p.materials_checked),
            Goal("水源の流入を確認", p.water_checked),
        )
        done = p.complete
    elif task.case_id == W4_CASE:
        p = office.plant_progress
        small = (
            Goal("フジの話を聞く", p.instructed),
            Goal(f"小株を集める {len(p.collected)}/5", len(p.collected) == 5),
            Goal(f"引き渡し {len(p.delivered)}/5", p.complete),
        )
        done = p.complete
    elif task.case_id in {W3_CASE, "OFF-JUN-W2-HERO"}:
        progress = office.site_progress if task.case_id == W3_CASE else app.east_site_progress
        facts = W3_FACTS if task.case_id == W3_CASE else SITE_FACTS
        small = tuple(
            Goal(
                LABELS[target] if task.case_id == W3_CASE else SITE_LABELS[target],
                fact in progress.facts,
            )
            for target, fact in facts.items()
        )
        done = set(facts.values()) <= progress.facts
    else:
        p = session.field_progress
        small = (Goal("記録", p.can_report), Goal("報告", session.field_result is not None))
        done = session.field_result is not None
    return Goal(task.objective, done), small


class MapObjectivesMixin:
    def map_objective_button_rect(self):
        return self.office_rect(432, 60, 72, 54)

    def map_objective_panel_rect(self):
        panel = self.office_rect(254, 60, 250, 124)
        bottom = min(
            panel.y + panel.height,
            self.action_button_rect().y - 4,
            self.interact_button_rect().y - 4,
        )
        return Rect(panel.x, panel.y, panel.width, bottom - panel.y)

    def map_objective_footer_rect(self):
        panel = self.map_objective_panel_rect()
        scale = self.runtime.screen_height / 236.0
        return Rect(
            panel.x + 8 * scale,
            panel.y + panel.height - 16 * scale,
            panel.width - 16 * scale,
            14 * scale,
        )

    def map_objective_content_rect(self):
        base = self.office_rect(262, 118, 234, 1)
        return Rect(
            base.x,
            base.y,
            base.width,
            self.map_objective_footer_rect().y - base.y - 4 * self.runtime.screen_height / 236.0,
        )

    def map_objective_mode_rect(self, mode):
        return self.office_rect(264 + mode * 86, 60, 74, 54)

    def map_objectives_available(self):
        return map_goals(self)[0] is not None

    def map_objectives_blocked(self):
        return bool(
            self.model.combat_session is not None
            or self.model.world_paused
            or getattr(self, "field_conversation", None) is not None
            or getattr(self, "first_sight_conversation", None) is not None
            or getattr(self, "field_transition", None) is not None
            or getattr(self, "week_transition", None) is not None
            or (
                getattr(
                    getattr(getattr(self, "office", None), "july_progress", None), "stage", "patrol"
                )
                != "patrol"
            )
        )

    def map_objective_pages(self):
        major, small = map_goals(self)
        if major is None:
            return (), False
        mode = getattr(self, "map_objective_mode", 0)
        goals = (major,) if mode == 0 else small
        rect = self.map_objective_content_rect()
        style = self.office_text_style(rect)
        height = self.ui_renderer.visual_vertical_metrics(style)[1]
        capacity = max(1, int(rect.height // height))
        lines = tuple(
            line
            for goal in goals
            for line in self.wrap_office_dialogue_text(
                ("済 " if goal.done else "未 ") + goal.text, int(rect.width), style
            )
        )
        pages = tuple(lines[i : i + capacity] for i in range(0, len(lines), capacity))
        signature = (self.office.active_field_task.task_id, major.text, mode, goals)
        if getattr(self, "map_objective_signature", None) != signature:
            self.map_objective_signature = signature
            self.map_objective_page = 0
        return pages, all(goal.done for goal in goals)

    def sync_map_objective_context(self):
        office = getattr(self, "office", None)
        task = office.active_field_task if office is not None else None
        ident = task.task_id if task is not None else None
        previous = getattr(self, "map_objective_task_id", ident)
        self.map_objective_task_id = ident
        if previous != ident:
            self.map_objective_open = False
            self.map_objective_page = 0

    def update_map_objectives(self):
        self.sync_map_objective_context()
        if not self.map_objectives_available() or self.map_objectives_blocked():
            return False
        consumed = False
        if self.mouse_pressed_in(self.map_objective_button_rect()):
            self.map_objective_open = not getattr(self, "map_objective_open", False)
            consumed = True
        elif getattr(self, "map_objective_open", False):
            for mode in (0, 1):
                if self.mouse_pressed_in(self.map_objective_mode_rect(mode)):
                    self.map_objective_mode = mode
                    self.map_objective_page = 0
                    consumed = True
                    break
            if not consumed and self.mouse_pressed_in(self.map_objective_panel_rect()):
                pages, _ = self.map_objective_pages()
                self.map_objective_page = (getattr(self, "map_objective_page", 0) + 1) % max(
                    1, len(pages)
                )
                consumed = True
        if consumed:
            self.clear_world_input_latches()
            self.model.cancel_auto_move()
        return consumed

    def draw_map_objectives(self):
        self.sync_map_objective_context()
        if not self.map_objectives_available() or self.map_objectives_blocked():
            return
        opened = getattr(self, "map_objective_open", False)
        if opened:
            pages, done = self.map_objective_pages()
            self.draw_panel_frame(self.map_objective_panel_rect(), fill=1 if done else 4, inner=13)
            mode = getattr(self, "map_objective_mode", 0)
            for candidate, label in enumerate(("大目標", "小目標")):
                self.draw_office_button(
                    self.office_rect(264 + candidate * 86, 72, 74, 26),
                    label,
                    12 if mode == candidate else 5,
                )
            if pages:
                page = getattr(self, "map_objective_page", 0) % len(pages)
                self.draw_office_wrapped_lines(self.map_objective_content_rect(), pages[page], 7)
                if len(pages) > 1:
                    self.draw_office_text_in_rect(
                        self.map_objective_footer_rect(), f"{page + 1}/{len(pages)} >", 7
                    )
        self.draw_office_button(
            (self.office_rect(440, 72, 56, 26) if opened else self.office_rect(450, 72, 46, 26)),
            "閉じる" if opened else "目標",
            12,
        )
