"""July W4: physical handoff, a bounded complaint, and a small park inspection."""

from copy import deepcopy
from dataclasses import dataclass

from drift_with_me.field_transition import FieldTransition
from drift_with_me.field_visit import FieldConversation
from drift_with_me.office import (
    SUPERVISOR_NAME,
    CaseState,
    Classification,
    FieldResult,
    OfficePrototype,
    parse_case_definitions,
    parse_counter_script_definitions,
)
from drift_with_me.week_cycle import WorkWeek
from drift_with_me.world import WorldData

HANDOFF = "OFF-JUL-W4-HANDOFF"
SENIOR = "OFF-JUL-W4-COMPLAINT"
TASK = "OFF-JUL-W4-PARK"
PARK = "jul_w4_park_check"
PARK_POSITION = (920, 906)
FOLLOW = (
    (SUPERVISOR_NAME, "いつだって、ああいう手合いはおるもんじゃ……。お疲れさん"),
    ("ジャック", "遊具がないと分かっても、あまり納得されてないようでした"),
    (SUPERVISOR_NAME, "静かに過ごしたい気持ちは分かる。じゃが、子供が元気に遊べる場所も要るじゃろ"),
    (
        SUPERVISOR_NAME,
        "誰も来ん公園にしても、しょうがなかろう。お前さんは、ちゃんと説明できとったよ",
    ),
)
REPORT = (
    (
        "ジャック",
        "フジさんと話して、北東公園の花壇・ベンチ・園路を確認しました。花の並びも記録どおりです",
    ),
    (SUPERVISOR_NAME, "ご苦労さん。見てきた整備の状況を記録しておこう。みんなが使う場所じゃからな"),
    (
        "ジャック",
        "回収した機械はユメサキ先生にお渡ししました。調査で分からない点は、そのまま残しています",
    ),
    (
        SUPERVISOR_NAME,
        "うむ。別部署への相談も続けとる。機械の中身や影響は、まだ決めつけんでおこう。今週はここまでじゃ",
    ),
)
FIELD_LINES = {
    "fuji": (
        (
            "フジ",
            "花壇もベンチも園路も形になった。花の並びはそのままに、通る人の足元を確かめているところだ",
        ),
    ),
    PARK: (
        (
            "ジャック",
            "花壇とベンチ、それにつながる園路を確認できた。今の計画にも現地にも、遊具はないね",
        ),
        ("ヒューズ", "花の並びの記録も残っているわ。見えた整備状況をそのまま伝えましょう"),
    ),
}


@dataclass
class Week4Progress:
    phase: str = "counter"
    handoff_received: bool = False
    fuji_seen: bool = False
    park_seen: bool = False
    dialogue_target: str | None = None
    dialogue_index: int = 0
    report_index: int = 0
    return_prompt_seen: bool = False
    follow_index: int | None = None

    @property
    def ready(self):
        return self.fuji_seen and self.park_seen

    def snapshot(self):
        return dict(vars(self))

    @classmethod
    def restore(cls, raw):
        if not isinstance(raw, dict) or set(raw) != set(cls().snapshot()):
            raise ValueError("invalid July W4 fields")
        p = cls(**raw)
        if (
            type(p.phase) is not str
            or p.phase not in {"counter", "field", "office", "report", "done"}
            or any(
                type(getattr(p, k)) is not bool
                for k in ("handoff_received", "fuji_seen", "park_seen", "return_prompt_seen")
            )
            or (p.dialogue_target is not None and type(p.dialogue_target) is not str)
            or p.dialogue_target not in {None, *FIELD_LINES}
            or type(p.dialogue_index) is not int
            or not 0 <= p.dialogue_index < len(FIELD_LINES.get(p.dialogue_target, (None,)))
            or type(p.report_index) is not int
            or not 0 <= p.report_index < len(REPORT)
            or (
                p.follow_index is not None
                and (type(p.follow_index) is not int or not 0 <= p.follow_index < len(FOLLOW))
            )
            or (p.follow_index is not None and p.phase != "counter")
            or (p.dialogue_target is not None and p.phase != "field")
            or (p.phase in {"report", "done"} and not p.ready)
            or (p.return_prompt_seen and not p.ready)
            or (p.phase not in {"report", "done"} and p.report_index != 0)
            or (p.phase == "done" and p.report_index != len(REPORT) - 1)
            or (p.phase != "counter" and not p.handoff_received)
        ):
            raise ValueError("inconsistent July W4 progress")
        return p


def office_data():
    specs = [
        (
            HANDOFF,
            "ユメサキ",
            "yumesaki_bust_normal",
            "回収した機械の調査依頼",
            [
                (
                    "ジャック",
                    "先週、動いていた三つの機械を停止して回収しました。実物の調査をお願いできますか",
                ),
                ("ユメサキ", "は、はい。まずは実物と、回収したときの記録を確認させてください"),
            ],
            [
                (
                    "request",
                    "調査を依頼する",
                    "構造や影響、置いた人はまだ分かっていません。分からない点も含めて、調べていただきたいです",
                    "薬剤や攻撃性との関係も、まだ断定できません。調べたことと、不明なことを分けてお伝えします",
                )
            ],
            [
                (
                    "ジャック",
                    "エトウさんも別部署へ相談しています。こちらは回収した三つの実物と記録です",
                ),
                ("ユメサキ", "あ、ありがとうございます。実物は私がお預かりして、調査を進めます"),
            ],
            "COUNTER_COMPLETE",
        ),
        (
            SENIOR,
            "イワマ",
            "iwama_bust_normal",
            "公園整備へのご心配",
            [("イワマ", "遊具なんぞ置くんじゃないぞ。子供がわあわあ騒いで、かなわん")],
            [
                (
                    "plan",
                    "現在の計画を確認",
                    "今の計画に、遊具の設置はありません。花壇・ベンチ・園路の整備です",
                    "本当か？ あとから置くんじゃろ",
                ),
                (
                    "concern",
                    "心配な点を伺う",
                    "ご心配の点を伺います。公園は皆さんが使う場所なので、子供の立入禁止や、いつも静かであることはお約束できません",
                    "わしは静かにしてほしいだけじゃ。ちゃんと言うておけよ",
                ),
            ],
            [
                ("ジャック", "今の計画に、遊具の設置はありません。ご心配の点は伺いました"),
                ("イワマ", "わしが釘を刺しておいたからな。勝手に遊具なんぞ置くなよ"),
                ("ジャック", "計画を確認して説明しただけなんだけど……少し釈然としないな"),
            ],
            "COUNTER_COMPLETE",
        ),
        (
            TASK,
            SUPERVISOR_NAME,
            "office_supervisor",
            "北東公園の整備確認",
            [
                (
                    SUPERVISOR_NAME,
                    "北東公園の整備が進んどる。フジさんに一声かけて、現地の花壇・ベンチ・園路を確かめてきてくれ",
                )
            ],
            [
                (
                    "check",
                    "確認する範囲を聞く",
                    "フジさんとの確認と、現地の整備状況の記録ですね",
                    "そうじゃ。新しい調査を増やす必要はない。見えたところを報告してくれ",
                )
            ],
            [],
            "FIELD_CHECK",
        ),
    ]
    cases, scripts = [], []
    for ident, name, portrait, title, opening, questions, closing, classification in specs:
        case = dict(
            case_id=ident,
            title=title,
            visitor=dict(
                id=ident.lower(),
                name=name,
                kind="来庁",
                portrait_id=portrait,
            ),
            initial_purpose=title,
            document_status="相談・記録",
            questions=[
                dict(id=q, label=label, jack=jack, reply=reply, jack_speaker="ジャック", memo=[])
                for q, label, jack, reply in questions
            ],
            expected_classification=classification,
        )
        if ident == TASK:
            case["field_task"] = dict(
                task_id="FIELD-JUL-W4-PARK",
                location_id="northeast_park",
                title=title,
                objective="フジと話し、北東公園の整備状況を確認",
                completion_condition_id="july4_park_checked",
            )

        def turns(lines, prefix, ident=ident):
            return [
                dict(turn_id=f"{ident}_{prefix}_{i}", jack=text, reply="", jack_speaker=speaker)
                for i, (speaker, text) in enumerate(lines)
            ]

        cases.append(case)
        scripts.append(
            dict(
                case_id=ident,
                opening=turns(opening, "open"),
                after_question={q[0]: [] for q in questions},
                resolution=dict(
                    classification=classification,
                    requires_completed_questions=[q[0] for q in questions],
                    if_requirements_missing="お話を確認してから進めましょう",
                    turns=turns(closing, "close"),
                ),
                feedback={
                    classification: "説明と記録を終えました"
                    if ident != TASK
                    else "現地で確認します"
                },
            )
        )
    return dict(cases=cases, counter_scripts=dict(cases=scripts))


class JulyWeek4Office(OfficePrototype):
    def __init__(self):
        raw = office_data()
        cases = parse_case_definitions(raw)
        super().__init__(cases, parse_counter_script_definitions(raw["counter_scripts"], cases))
        self.week4_progress = Week4Progress()

    def prepare_debug_field_task(self):
        self.current_index = 2
        for ident in (HANDOFF, SENIOR):
            self.sessions[ident].state = CaseState.RESOLVED
        self.week4_progress.handoff_received = True
        self.begin_current_case()
        while self.has_pending_dialogue_step():
            self.advance_dialogue_step()
        self.ask_question("check")
        while self.has_pending_dialogue_step():
            self.advance_dialogue_step()
        self.complete_pending_question()
        self.classify(Classification.FIELD_CHECK)
        self.week4_progress.phase = "field"
        return self.prepare_field_task()

    def finish_week(self):
        p = self.week4_progress
        if p.phase != "report" or not p.ready or p.report_index != len(REPORT) - 1:
            return False
        session = self.sessions[TASK]
        session.state = CaseState.RESOLVED
        session.field_result = FieldResult(
            self.cases[-1].field_task.task_id, TASK, "JULY4_COMPLETED", ("fuji", PARK), ()
        )
        self.current_index = len(self.cases)
        self.active_field_task = None
        p.phase = "done"
        return True


def install_week4_world(app):
    if not hasattr(app, "world"):
        return
    raw = deepcopy(app.world.raw)
    raw["objects"] = [o for o in raw["objects"] if o["id"] != PARK]
    if getattr(app, "work_week", None) == WorkWeek(7, 4):
        app.model.week2_scenery_enabled = True
        raw["objects"].append(
            dict(
                id=PARK,
                kind="construction_collision",
                position=[*PARK_POSITION[:1], 0, PARK_POSITION[1]],
                inspectable=True,
                solid=False,
                height=0,
            )
        )
        raw["texts"][PARK] = dict(title="公園の整備状況", lines=["花壇・ベンチ・園路を確認"])
    world = WorldData(
        raw,
        app.world.chunk_size,
        app.world.static_visual_max_height,
        app.world.visual_detail_per_chunk,
    )
    world.east_site_access_ready = app.world.east_site_access_ready
    app.world = app.model.world = world


class JulyWeek4Mixin:
    def office_story_report_active(self):
        return self.week3_office_report_active() or self.week4_office_report_active()

    def office_story_report(self):
        if self.week4_active():
            return REPORT, self.office.week4_progress.report_index
        from drift_with_me.july_week3 import REPORT as W3_REPORT

        return W3_REPORT, self.office.week3_progress.report_index

    def week4_active(self):
        return getattr(self, "work_week", None) == WorkWeek(7, 4) and hasattr(
            self.office, "week4_progress"
        )

    def week4_office_report_active(self):
        from drift_with_me.app import AppScreen

        return (
            self.week4_active()
            and self.screen == AppScreen.OFFICE
            and self.office.week4_progress.phase == "report"
        )

    def save_week4(self, previous, previous_week3=None):
        if getattr(self, "week_debug_active", False):
            return True
        from drift_with_me.save_state import snapshot

        data = snapshot(self)
        if self.progress_store.write(data):
            self.last_checkpoint = data
            self.week4_error = ""
            return True
        self.office = previous
        self.week_office_history[self.work_week] = previous
        if previous_week3 is not None:
            self.week_office_history[WorkWeek(7, 3)] = previous_week3
        self.week4_error = "保存できません。前の記録から再開してください"
        return False

    def advance_week4_case(self):
        office = self.office
        case, session = office.current_case, office.current_session
        if case is None or session is None or case.case_id == TASK:
            return False
        if office.week4_progress.follow_index is not None:
            return False
        before = deepcopy(office)
        old3 = self.week_office_history.get(WorkWeek(7, 3))
        before3 = deepcopy(old3) if old3 else None
        if (
            case.case_id == HANDOFF
            and not getattr(self, "week_debug_active", False)
            and (old3 is None or not old3.week3_progress.professor_handoff_pending)
        ):
            return False
        if not office.advance_case():
            return False
        if case.case_id == HANDOFF:
            office.week4_progress.handoff_received = True
            if old3:
                old3.week3_progress.professor_handoff_pending = False
                old3.week3_progress.professor_handoff_completed = True
        if not self.save_week4(before, before3):
            return False
        self.office_focus = "questions"
        self.office_question_index = self.office_classification_index = 0
        return True

    def week4_follow_available(self):
        return (
            self.week4_active()
            and self.office.current_case is not None
            and self.office.current_case.case_id == SENIOR
            and self.office.current_session.state == CaseState.CLOSED_COUNTER
            and not self.office_dialogue_requires_advance()
        )

    def begin_week4_follow(self, restoring=False):
        from drift_with_me.app import (
            OFFICE_DIALOGUE_LINES_PER_PAGE,
            OfficeDialogueLine,
            OfficeDialoguePlayback,
        )

        p = self.office.week4_progress
        if not restoring and not self.week4_follow_available():
            return False
        if restoring:
            playback = self.sync_office_dialogue_playback()
            playback.page_index = max(0, len(playback.pages) - 1)
            playback.revealed_chars = float(
                sum(len(line.text) for line in self.office_dialogue_current_page(playback))
            )
        if not restoring:
            before = deepcopy(self.office)
            p.follow_index = 0
            if not self.save_week4(before):
                return False
        pages = []
        for speaker, text in FOLLOW:
            lines = tuple(
                OfficeDialogueLine(line.text, False, line.indent_px, speaker=speaker)
                for line in self.wrap_office_hanging_text(
                    f"{speaker}: {text}", int(self.office_dialogue_content_rect().width)
                )
            )
            assert len(lines) <= OFFICE_DIALOGUE_LINES_PER_PAGE
            pages.append(lines)
        self.office_consultation_visible_questions = self.office_visible_question_count()
        self.office_consultation_started_at = getattr(self, "presentation_time", 0.0)
        self.office_consultation = OfficeDialoguePlayback(
            pages=tuple(pages), page_index=p.follow_index
        )
        return True

    def advance_week4_follow(self, close=False):
        before = deepcopy(self.office)
        p = self.office.week4_progress
        if p.follow_index is None:
            return False
        p.follow_index = None if close or p.follow_index == len(FOLLOW) - 1 else p.follow_index + 1
        if not self.save_week4(before):
            return False
        if p.follow_index is None:
            self.office_consultation = None
        else:
            self.office_consultation.page_index = p.follow_index
            self.office_consultation.revealed_chars = 0.0
        return True

    def begin_week4_target(self, ident):
        if (
            not self.week4_active()
            or ident not in FIELD_LINES
            or self.office.week4_progress.phase != "field"
            or self.model.combat_session is not None
            or getattr(self, "week4_dialogue", None)
        ):
            return False
        before = deepcopy(self.office)
        self.office.week4_progress.dialogue_target = ident
        self.office.week4_progress.dialogue_index = 0
        if not self.save_week4(before):
            return False
        self.week4_dialogue = FieldConversation(ident, FIELD_LINES[ident])
        self.week4_wait_release = True
        self.model.cancel_auto_move()
        return True

    def advance_week4_dialogue(self):
        d = self.week4_dialogue
        if d is None:
            return False
        before = deepcopy(self.office)
        p = self.office.week4_progress
        last = d.index + 1 == len(d.lines)
        if d.target_id == "week4_report":
            if last:
                if not self.office.finish_week():
                    return False
            else:
                p.report_index += 1
        elif last:
            if d.target_id == "fuji":
                p.fuji_seen = True
            else:
                p.park_seen = True
            p.dialogue_target, p.dialogue_index = None, 0
        else:
            p.dialogue_index += 1
        if not self.save_week4(before):
            return False
        if last:
            self.week4_dialogue = None
        else:
            d.index += 1
        self.week4_wait_release = True
        return True

    def return_week4(self):
        if (
            not self.week4_active()
            or self.office.week4_progress.phase != "field"
            or getattr(self, "week4_dialogue", None)
            or self.field_transition
            or self.model.combat_session
            or self.model.interaction
            or self.model.world_paused
        ):
            return False
        before = deepcopy(self.office)
        p = self.office.week4_progress
        p.phase = "report" if p.ready else "office"
        if not self.save_week4(before):
            return False
        self.field_transition = FieldTransition(
            "back",
            (
                (
                    "ジャック",
                    "フジさんと公園の確認を終えたね。戻って報告しよう"
                    if p.ready
                    else "いったん戻ろう。残りの確認は、また外勤に出よう",
                ),
                ("ヒューズ", "ええ。確認したことを記録しておきましょう"),
            ),
        )
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        return True

    def cancel_week4_return(self):
        before = deepcopy(self.office)
        self.office.week4_progress.phase = "field"
        return self.save_week4(before)

    def update_july_week4(self, elapsed):
        from drift_with_me.app import AppScreen

        if (
            not self.week4_active()
            or self.field_transition is not None
            or self.week_transition is not None
        ):
            return False
        p = self.office.week4_progress
        if self.screen == AppScreen.OFFICE:
            if p.follow_index is not None and self.office_consultation is None:
                self.begin_week4_follow(restoring=True)
            if p.phase == "done":
                return True
            if p.phase == "office":
                if self.key_pressed("KEY_RETURN", "KEY_Z") or self.mouse_pressed_in(
                    self.office_footer_action_rect()
                ):
                    self.enter_exploration_from_office()
                return True
            if p.phase != "report":
                return False
            if getattr(self, "week4_dialogue", None) is None:
                self.week4_dialogue = FieldConversation("week4_report", REPORT, p.report_index)
            self.update_office_dialogue_playback(elapsed)
            if getattr(self, "week4_wait_release", False):
                if not self.travel_input_held():
                    self.week4_wait_release = False
                return True
            if (
                self.key_pressed("KEY_RETURN", "KEY_Z")
                or self.mouse_pressed_in(self.office_dialog_rect())
                or self.mouse_pressed_in(self.office_footer_action_rect())
            ):
                self.advance_office_dialogue_page()
                self.week4_wait_release = True
            return True
        if self.screen != AppScreen.PLAY:
            return False
        d = getattr(self, "week4_dialogue", None)
        if d is None and p.dialogue_target:
            self.week4_dialogue = d = FieldConversation(
                p.dialogue_target, FIELD_LINES[p.dialogue_target], p.dialogue_index
            )
        if d is None:
            if (
                p.ready
                and not p.return_prompt_seen
                and self.model.combat_session is None
                and not self.model.world_paused
                and not self.travel_input_held()
            ):
                before = deepcopy(self.office)
                p.return_prompt_seen = True
                if not self.save_week4(before):
                    return True
                self.week4_dialogue = FieldConversation(
                    "week4_return_choice",
                    (("ジャック", "今日の確認は済んだね。帰庁して報告しようか？"),),
                )
                self.week4_wait_release = True
                self.model.cancel_auto_move()
                return True
            return False
        self.clear_world_input_latches()
        if getattr(self, "week4_wait_release", False):
            if not self.travel_input_held():
                self.week4_wait_release = False
            return True
        if d.target_id == "week4_return_choice":
            go, stay = self.week2_return_choice_rects()
            if self.mouse_pressed_in(stay) or self.key_pressed("KEY_ESCAPE", "KEY_X"):
                self.week4_dialogue = None
            elif self.mouse_pressed_in(go) or self.key_pressed("KEY_RETURN", "KEY_Z"):
                self.week4_dialogue = None
                if not self.return_week4():
                    self.week4_dialogue = d
            return True
        if self.key_pressed("KEY_RETURN", "KEY_Z") or self.mouse_pressed_in(
            self.office_rect(40, 126, 432, 100)
        ):
            self.advance_week4_dialogue()
        elif self.key_pressed("KEY_ESCAPE", "KEY_X") or self.mouse_pressed_in(
            self.site_cancel_rect()
        ):
            before = deepcopy(self.office)
            p.dialogue_target, p.dialogue_index = None, 0
            if self.save_week4(before):
                self.week4_dialogue = None
        return True

    def draw_week4_marker(self, camera):
        if not self.week4_active() or self.office.week4_progress.park_seen:
            return
        from drift_with_me.math3d import Vec3

        point = camera.project(Vec3(PARK_POSITION[0], 4, PARK_POSITION[1]))
        if point:
            self.pyxel.circb(point.x, point.y, 5, 10)

    def draw_week4_overlay(self):
        from drift_with_me.app import AppScreen

        if not self.week4_active():
            return False
        p = self.office.week4_progress
        if self.week4_office_report_active():
            self.draw_office()
            return True
        if self.screen == AppScreen.OFFICE and p.phase == "office":
            self.draw_office()
            self.draw_panel_frame(self.office_dialog_rect(), fill=0, inner=5)
            self.draw_office_section_title(self.office_dialog_rect(), "公園の確認は継続中")
            self.draw_office_wrapped_lines(
                self.office_rect(144, 84, 208, 64),
                ("フジとの会話と、公園の現地確認が残っています。記録を保って外勤を再開できます",),
                7,
            )
            self.draw_office_button(
                self.office_footer_action_rect(), "外勤を再開", 11, text_color=0
            )
            return True
        if self.screen == AppScreen.PLAY and getattr(self, "week4_dialogue", None):
            self.draw_play()
            self.draw_field_conversation(self.week4_dialogue)
            if self.week4_dialogue.target_id == "week4_return_choice":
                go, stay = self.week2_return_choice_rects()
                self.draw_office_button(go, "帰庁する", 11)
                self.draw_office_button(stay, "もう少し見る", 5)
            return True
        return False
