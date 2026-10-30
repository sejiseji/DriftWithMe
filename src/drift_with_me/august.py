"""August W1-W3 office/state foundation. Field producers arrive in Wave 2."""

from copy import deepcopy
from dataclasses import dataclass, field

from drift_with_me.field_transition import FieldTransition
from drift_with_me.office import (
    SUPERVISOR_NAME,
    CaseState,
    FieldResult,
    OfficePrototype,
    parse_case_definitions,
    parse_counter_script_definitions,
)
from drift_with_me.week_cycle import WorkWeek

SITES = frozenset({"northwest", "northeast", "southeast"})
OPENING = {
    4: (SUPERVISOR_NAME, "保護区の最終巡回を頼む。戻る時刻は任せるよ"),
    1: (
        "フジ",
        "このごろウニやウミウシが荒っぽいんだ。小さいのを見かける数も増えている。現地を見てもらえるか",
    ),
    2: ("フジ", "今度は小さいのが群れで囲んでくる。先週の三か所だ。俺も現地で援護する"),
    3: (SUPERVISOR_NAME, "先週の三か所をもう一度見てきてくれ。群れの様子を確かめてほしい"),
}
REPORTS = {
    # Preview wording only; the vacation/ending script is deliberately unauthored.
    4: (("ジャック", "最終巡回を終えました"), (SUPERVISOR_NAME, "お疲れさま。報告を受け取ったよ")),
    1: (
        (
            "ジャック",
            "三か所で幼体を見ました。複数の場所で数が増え、ウニもウミウシも凶暴化しています",
        ),
        (
            SUPERVISOR_NAME,
            "薬剤を撒いとった機材は、もう撤去したはずじゃが……。まだ、どこかに残っとるんかのう",
        ),
        (SUPERVISOR_NAME, "原因はまだ分からん。引き続き、異変の様子を確かめていこう"),
    ),
    2: (
        ("ジャック", "三か所の群れをすべて撃退しました。フジさんにも援護していただきました"),
        (
            SUPERVISOR_NAME,
            "ご苦労じゃった。危険は減ったが、原因はまだ分からん。来週も様子を確かめよう",
        ),
    ),
    3: (
        ("ジャック", "雨の中、三か所の群れを撃退しました"),
        (
            SUPERVISOR_NAME,
            "雨で残った薬剤の影響が薄れたのかもしれんな。まだ断定はできんが、群れの発生は収まってきたようじゃ",
        ),
    ),
}


@dataclass
class AugustProgress:
    phase: str = "counter"
    sites: list[str] = field(default_factory=list)
    report_index: int = 0
    pending_sighting: str | None = None
    sighting_index: int = 0

    @property
    def ready(self):
        return set(self.sites) == SITES

    def snapshot(self):
        return {
            "phase": self.phase,
            "sites": list(self.sites),
            "report_index": self.report_index,
            "pending_sighting": self.pending_sighting,
            "sighting_index": self.sighting_index,
        }

    @classmethod
    def restore(cls, raw, number):
        required = {"phase", "sites", "report_index"}
        optional = {"pending_sighting", "sighting_index"}
        if not isinstance(raw, dict) or not required <= set(raw) or set(raw) - required - optional:
            raise ValueError("invalid August progress")
        p = cls(**raw)
        if (
            type(p.phase) is not str
            or p.phase not in {"counter", "field", "office", "report", "done"}
            or not isinstance(p.sites, list)
            or any(type(x) is not str for x in p.sites)
            or len(p.sites) != len(set(p.sites))
            or set(p.sites) - SITES
            or type(p.report_index) is not int
            or not 0 <= p.report_index < len(REPORTS[number])
        ):
            raise ValueError("invalid August state")
        if (
            p.phase in {"report", "done"}
            and not p.ready
            and number != 4
            or p.phase == "counter"
            and p.sites
            or p.phase not in {"report", "done"}
            and p.report_index
            or p.phase == "done"
            and p.report_index != len(REPORTS[number]) - 1
        ):
            raise ValueError("premature August completion")
        if number == 4 and p.sites:
            raise ValueError("final patrol has no required sites")
        if p.pending_sighting is not None and (
            type(p.pending_sighting) is not str
            or number != 1
            or p.phase != "field"
            or p.pending_sighting not in SITES
            or p.pending_sighting in p.sites
        ):
            raise ValueError("invalid pending sighting")
        if (
            type(p.sighting_index) is not int
            or not 0 <= p.sighting_index < 2
            or p.pending_sighting is None
            and p.sighting_index != 0
        ):
            raise ValueError("invalid sighting dialogue position")
        return p


class AugustOffice(OfficePrototype):
    def __init__(self, number):
        from drift_with_me.july_week4 import TASK, office_data

        raw = deepcopy(office_data())
        case = next(c for c in raw["cases"] if c["case_id"] == TASK)
        script = next(c for c in raw["counter_scripts"]["cases"] if c["case_id"] == TASK)
        ident = f"OFF-AUG-W{number}-SURVEY"
        speaker, text = OPENING[number]
        case.update(case_id=ident, title="保護区の異変確認", initial_purpose="保護区の異変確認")
        case["visitor"].update(
            id="fuji" if number < 3 else "supervisor",
            name=speaker,
            portrait_id="fuji_matte" if number < 3 else "office_supervisor",
        )
        case["questions"] = [
            dict(
                id="check",
                label="現地確認の範囲を聞く",
                jack="北西・北東・南東の三か所ですね",
                reply="ああ。その三か所の様子を確認してほしい",
                jack_speaker="ジャック",
                memo=[],
            )
        ]
        case["field_task"].update(
            task_id=f"FIELD-AUG-W{number}-SURVEY",
            title="保護区の異変確認",
            objective="北西・北東・南東の様子を確認",
            completion_condition_id=f"august_{number}_sites",
        )
        if number == 4:
            case.update(title="保護区の最終巡回", initial_purpose="保護区の最終巡回")
            case["questions"][0].update(
                jack="落ち着いた保護区を見て回ります", reply="ああ。好きな順に回ってきてくれ"
            )
            case["field_task"].update(
                title="保護区の最終巡回", objective="自由に巡回し、任意の時点で帰庁"
            )
        script["case_id"] = ident
        script["opening"] = [
            dict(turn_id=f"{ident}_open", jack=text, reply="", jack_speaker=speaker)
        ]
        script["resolution"]["turns"] = []
        raw = dict(cases=[case], counter_scripts=dict(cases=[script]))
        cases = parse_case_definitions(raw)
        super().__init__(cases, parse_counter_script_definitions(raw["counter_scripts"], cases))
        self.august_number = number
        self.august_progress = AugustProgress()

    def finish_august(self):
        p = self.august_progress
        if (
            p.phase != "report"
            or (not p.ready and self.august_number != 4)
            or p.report_index != len(REPORTS[self.august_number]) - 1
        ):
            return False
        c = self.cases[0]
        s = self.sessions[c.case_id]
        s.state = CaseState.RESOLVED
        s.field_result = FieldResult(
            c.field_task.task_id,
            c.case_id,
            "AUGUST_COMPLETED",
            tuple(sorted(SITES)) if self.august_number != 4 else (),
            (),
        )
        self.current_index = 1
        self.active_field_task = None
        p.phase = "done"
        return True


class AugustMixin:
    def august_active(self):
        return getattr(self, "work_week", None) in {
            WorkWeek(8, n) for n in (1, 2, 3, 4)
        } and hasattr(self.office, "august_progress")

    def save_august(self, previous):
        from drift_with_me.save_state import snapshot

        data = snapshot(self)
        if self.progress_store.write(data):
            self.last_checkpoint = data
            self.august_error = ""
            return True
        self.office = previous
        self.week_office_history[self.work_week] = previous
        self.august_error = "保存できません。もう一度お試しください"
        return False

    def record_august_site(self, site, source):
        # Only future sighting/combat producers call this; no timer or visit auto-completion.
        if (
            not self.august_active()
            or self.office.august_progress.phase != "field"
            or site not in SITES
            or source != ("sighting" if self.work_week.number == 1 else "swarm")
        ):
            return False
        p = self.office.august_progress
        if site in p.sites:
            return False
        before = deepcopy(self.office)
        p.sites = sorted([*p.sites, site])
        return self.save_august(before)

    def office_story_report_active(self):
        from drift_with_me.app import AppScreen

        if self.august_active():
            return self.screen == AppScreen.OFFICE and self.office.august_progress.phase == "report"
        return super().office_story_report_active()

    def office_story_report(self):
        if self.august_active():
            return REPORTS[self.work_week.number], self.office.august_progress.report_index
        return super().office_story_report()

    def advance_august_report(self):
        if not self.office_story_report_active():
            return False
        before = deepcopy(self.office)
        p = self.office.august_progress
        if p.report_index == len(REPORTS[self.work_week.number]) - 1:
            if not self.office.finish_august():
                return False
        else:
            p.report_index += 1
        if not self.save_august(before):
            return False
        from drift_with_me.app import OfficeDialoguePlayback

        self.office_dialogue_playback = OfficeDialoguePlayback()
        return True

    def return_august(self):
        if (
            not self.august_active()
            or self.office.august_progress.phase != "field"
            or self.field_transition
            or self.model.combat_session
            or self.model.interaction
            or self.model.world_paused
            or self.office.august_progress.pending_sighting is not None
        ):
            return False
        before = deepcopy(self.office)
        p = self.office.august_progress
        p.phase = "office" if self.work_week.number == 4 else "report" if p.ready else "office"
        if not self.save_august(before):
            return False
        self.field_transition = FieldTransition(
            "back",
            (
                ("ジャック", "確認したことを記録して戻ろう"),
                ("ヒューズ", "ええ。戻って報告しましょう"),
            ),
        )
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        return True

    def update_august(self, elapsed):
        from drift_with_me.app import AppScreen

        if getattr(self, "field_transition", None) or getattr(self, "week_transition", None):
            return False
        if (
            self.work_week == WorkWeek(7, 4)
            and self.screen == AppScreen.OFFICE
            and self.office.week4_progress.phase == "done"
        ):
            self.begin_next_week()
            return True
        if not self.august_active():
            return False
        p = self.office.august_progress
        if self.screen != AppScreen.OFFICE:
            return False
        if p.phase == "done":
            if self.work_week.number == 4 and (
                self.key_pressed("KEY_RETURN", "KEY_Z")
                or self.mouse_pressed_in(self.office_footer_action_rect())
            ):
                self.begin_ending()
                return True
            if self.work_week.number < 4 and (
                self.key_pressed("KEY_RETURN", "KEY_Z")
                or self.mouse_pressed_in(self.office_next_week_rect())
            ):
                self.begin_next_week()
            return True
        if p.phase == "office":
            if self.key_pressed("KEY_RETURN", "KEY_Z") or self.mouse_pressed_in(
                self.office_footer_action_rect()
            ):
                self.enter_exploration_from_office()
            return True
        return False

    def draw_august_overlay(self):
        from drift_with_me.app import AppScreen

        if not self.august_active() or self.screen != AppScreen.OFFICE:
            return False
        if self.work_week.number == 4 and self.office.august_progress.phase == "done":
            self.draw_office()
            self.draw_office_button(
                self.office_footer_action_rect(), "エンディングを見る", 11, text_color=0
            )
            return True
        if self.work_week.number == 3 and self.office.august_progress.phase == "done":
            from dataclasses import replace

            from drift_with_me.math3d import Vec3

            self.model.august_rain = False
            self.model.august_recovered = True
            shots = ((160, 200), (150, 680), (244, 382), (816, 256), (868, 848))
            beat = self.presentation_time / 6
            index = int(beat) % len(shots)
            t = (beat % 1) ** 2 * (3 - 2 * (beat % 1))
            a, b = shots[index], shots[(index + 1) % len(shots)]
            camera = replace(
                self.camera(), target=Vec3(a[0] + (b[0] - a[0]) * t, 0, a[1] + (b[1] - a[1]) * t)
            )
            camera = (
                self.affine_scene_camera(camera) if self.projection_mode == "affine" else camera
            )
            self.renderer.draw_scene(
                self.model,
                camera,
                self.presentation_time,
                False,
                self.effects,
                exploration_markers=False,
            )
            if self.can_begin_next_week():
                self.draw_office_button(self.office_next_week_rect(), "次の週へ", 11, text_color=0)
            return True
        if self.office.august_progress.phase == "office":
            self.draw_office()
            self.draw_office_button(
                self.office_footer_action_rect(), "外勤を再開", 11, text_color=0
            )
            if self.work_week.number == 4:
                self.draw_office_button(
                    self.office_next_week_rect(), "巡回を終える", 11, text_color=0
                )
            return True
        return False

    def august_swarm_active(self):
        return (
            self.august_active()
            and self.work_week.number in (2, 3)
            and self.office.august_progress.phase == "field"
        )

    def sync_august_swarm_sites(self):
        if not self.august_swarm_active():
            return
        field = getattr(self.model, "swarm_field", None)
        if field is None:
            return
        self.august_sync_failed = False
        for site in sorted(field.cleared - set(self.office.august_progress.sites)):
            if not self.record_august_site(site, "swarm"):
                self.august_sync_failed = True
                break

    def august_sighting_view(self):
        from drift_with_me.august_sightings import JuvenileSighting

        crossing = getattr(self, "august_crossing", None)
        if not self.august_active() or self.work_week.number != 1 or not crossing:
            return None
        return JuvenileSighting(*crossing)

    def draw_august_sighting_dialogue(self):
        from drift_with_me.august_sightings import LINES
        from drift_with_me.field_visit import FieldConversation

        if self.august_active() and self.work_week.number == 1:
            p = self.office.august_progress
            if p.pending_sighting and not getattr(self, "august_crossing", None):
                self.draw_field_conversation(
                    FieldConversation(
                        "august_" + p.pending_sighting, LINES[p.pending_sighting], p.sighting_index
                    )
                )

    def sync_august_sighting_lock(self):
        from drift_with_me.app import AppScreen

        locked = (
            self.august_active()
            and self.work_week.number == 1
            and self.office.august_progress.phase == "field"
            and self.office.august_progress.pending_sighting is not None
            and self.screen in (AppScreen.PLAY, AppScreen.PAUSE)
        ) or (
            getattr(self, "work_week", None) == WorkWeek(8, 4)
            and getattr(self, "patrol_dialogue", None) is not None
            and self.screen in (AppScreen.PLAY, AppScreen.PAUSE)
        )
        model = getattr(self, "model", None)
        if model is not None and (locked or getattr(model, "sighting_locked", False)):
            model.set_sighting_lock(locked)
        return locked

    def update_august_sightings(self, elapsed):
        import math

        from drift_with_me.app import AppScreen
        from drift_with_me.august_sightings import DURATION
        from drift_with_me.config import load_data_json

        if (
            not self.august_active()
            or self.work_week.number != 1
            or self.office.august_progress.phase != "field"
            or self.screen != AppScreen.PLAY
            or self.field_transition
            or self.week_transition
        ):
            return False
        self.sync_august_sighting_lock()
        p = self.office.august_progress
        if p.pending_sighting is None:
            if (
                self.model.combat_session
                or self.model.interaction
                or self.model.world_paused
                or getattr(self, "first_sight_conversation", None)
            ):
                return False
            for site, (x, z) in load_data_json("swarm_config.json")["sites"].items():
                if (
                    site not in p.sites
                    and math.hypot(self.model.player.x - x, self.model.player.z - z) <= 36
                ):
                    before = deepcopy(self.office)
                    p.pending_sighting = site
                    p.sighting_index = 0
                    if self.save_august(before):
                        self.sync_august_sighting_lock()
                        self.august_crossing = (site, 0.0)
                        self.august_sighting_wait_release = True
                        self.model.cancel_auto_move()
                        self.model.reset_manual_velocity()
                        self.clear_world_input_latches()
                    return True
            return False
        crossing = getattr(self, "august_crossing", None)
        if crossing:
            age = crossing[1] + max(0, min(0.1, elapsed))
            self.august_crossing = (crossing[0], age) if age < DURATION else None
            return True
        # A saved pending sighting resumes its dialogue, never spawns again.
        if getattr(self, "august_sighting_wait_release", False):
            if not self.travel_input_held():
                self.august_sighting_wait_release = False
            return True
        if self.key_pressed("KEY_RETURN", "KEY_Z", "KEY_SPACE", "KEY_E") or self.mouse_pressed_in(
            self.office_rect(40, 126, 432, 100)
        ):
            return self.advance_august_sighting()
        return True

    def advance_august_sighting(self):
        if not self.august_active() or self.work_week.number != 1:
            return False
        p = self.office.august_progress
        if not p.pending_sighting or getattr(self, "august_crossing", None):
            return False
        before = deepcopy(self.office)
        if p.sighting_index == 0:
            p.sighting_index = 1
        else:
            p.sites = sorted([*p.sites, p.pending_sighting])
            p.pending_sighting = None
            p.sighting_index = 0
        if not self.save_august(before):
            return False
        self.sync_august_sighting_lock()
        self.august_sighting_wait_release = True
        self.clear_world_input_latches()
        return True
