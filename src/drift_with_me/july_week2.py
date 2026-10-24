"""July W2 counter day and four observations; later summer days stay unauthored."""

from copy import deepcopy
from dataclasses import dataclass, field

from drift_with_me.field_transition import FieldTransition
from drift_with_me.field_visit import FieldConversation
from drift_with_me.math3d import Vec3
from drift_with_me.office import (
    CaseState,
    Classification,
    FieldResult,
    OfficePrototype,
    parse_case_definitions,
    parse_counter_script_definitions,
)
from drift_with_me.week_cycle import WorkWeek
from drift_with_me.world import WorldData

TASK = "OFF-JUL-W2-RESEARCH"
SITES = {
    "jul_w2_obs_fuji": ("フジ付近", (288, 416), (288, 440)),
    "jul_w2_obs_giant": ("巨木周辺", (648, 600), (632, 592)),
    "jul_w2_obs_nw": ("北西草むら", (252, 758), (240, 744)),
    "jul_w2_obs_ne": ("北東広場", (912, 888), (936, 904)),
}
LINES = {
    "jul_w2_obs_fuji": (
        ("ジャック", "周りには緑の葉もあるけど、ここの一部ははっきりマゼンタになってるね"),
        ("ヒューズ", "花ではなく、葉そのものね。位置と色を記録しましょう"),
    ),
    "jul_w2_obs_giant": (
        ("ジャック", "見える根元には、同じマゼンタの色は見当たらないね"),
        ("ヒューズ", "変化が見えない所も、比較のために記録しておきましょう"),
    ),
    "jul_w2_obs_nw": (
        ("ジャック", "この草むらは、葉がまとまってマゼンタになってる。根元の茎は倒れているね"),
        ("ヒューズ", "色と茎の状態は分けて記録しましょう。関係はまだ分からないわ"),
    ),
    "jul_w2_obs_ne": (
        ("ジャック", "木を切った跡と、ならした土だね。靴跡のそばに細い筋もある"),
        ("ヒューズ", "杭と張り糸は無事ね。何の筋かは、これだけでは分からないわ"),
    ),
}
REPORT = (
    ("ジャック", "花の並びはフジさんに見てもらったよ。四か所の記録もそろった"),
    (
        "ヒューズ",
        "葉の色や地面の筋、それから変化が見えなかった場所も。原因はまだ分からない、と添えましょう",
    ),
    ("ジャック", "うん。確認できたことを記録して、今日はここまでにしよう"),
)


@dataclass
class Week2Progress:
    checked: set[str] = field(default_factory=set)
    positions: dict[str, int] = field(default_factory=dict)
    phase: str = "counter"
    report_index: int = 0
    return_prompt_seen: bool = False

    def snapshot(self):
        return dict(
            checked=sorted(self.checked),
            positions=dict(self.positions),
            phase=self.phase,
            report_index=self.report_index,
            return_prompt_seen=self.return_prompt_seen,
        )

    @classmethod
    def restore(cls, raw):
        if isinstance(raw, dict):
            raw = {"return_prompt_seen": False, **raw}
        if not isinstance(raw, dict) or set(raw) != {
            "checked",
            "positions",
            "phase",
            "report_index",
            "return_prompt_seen",
        }:
            raise ValueError("invalid July W2 progress")
        checked, positions = raw["checked"], raw["positions"]
        if (
            not isinstance(checked, list)
            or any(not isinstance(k, str) or k not in SITES for k in checked)
            or len(set(checked)) != len(checked)
            or not isinstance(positions, dict)
            or any(
                k not in SITES or k in checked or type(v) is not int or not 0 <= v < len(LINES[k])
                for k, v in positions.items()
            )
            or not isinstance(raw["phase"], str)
            or raw["phase"] not in {"counter", "field", "office", "report", "done"}
            or type(raw["return_prompt_seen"]) is not bool
            or type(raw["report_index"]) is not int
            or not 0 <= raw["report_index"] < len(REPORT)
        ):
            raise ValueError("invalid July W2 cursor")
        if raw["phase"] in {"report", "done"} and set(checked) != set(SITES):
            raise ValueError("unfinished July W2 observations")
        return cls(
            set(checked),
            dict(positions),
            raw["phase"],
            raw["report_index"],
            raw["return_prompt_seen"],
        )


def office_data():
    specs = [
        (
            "OFF-JUL-W2-YOAKE",
            "ヨアケ",
            "yoake_matte",
            "印鑑証明の相談",
            [
                (
                    "ヨアケ",
                    "買い物の場所を教えてくださって、ありがとうございました。無事にそろいました",
                ),
                ("ジャック", "それはよかったです。今日はどのようなご相談でしょうか"),
            ],
            "ご相談を伺う",
            "印鑑証明を作りたいのですが、何から始めればよいでしょうか",
            [
                ("ジャック", "登録の状況を確認して、必要なお手続きと申請の流れをご案内しますね"),
                ("ヨアケ", "お願いします"),
            ],
        ),
        (
            "OFF-JUL-W2-MERRILL",
            "メリル",
            "merrill_matte",
            "集会所の次回利用相談",
            [
                (
                    "メリル",
                    "先日は集会所の件でありがとうございました。無事に使えて、みんなで手芸を楽しめました",
                )
            ],
            "次のご希望を伺う",
            "また同じ仲間で集まりたくて。次の申込みについて教えていただけますか",
            [
                ("ジャック", "承知しました。ご希望を伺って、担当へおつなぎしますね"),
                ("メリル", "お願いします。みんなも楽しみにしています"),
            ],
        ),
        (
            TASK,
            "ユメサキ",
            "yumesaki_map_knees",
            "植物とマウスの変化の報告",
            [
                (
                    "ユメサキ",
                    "あ、あの……先週の調査の、ご報告です。植物の葉の一部が、はっきりしたマゼンタに変色していまして……",
                )
            ],
            "観察した変化を伺う",
            "マウスを用いた実験でも、変異と、小さな触手のような部位が確認されました",
            [
                ("ミヤノ", "植物と同じ影響かは、まだ分かりません。記録はまとめてきました！"),
                ("ユメサキ", "げ、原因も、今は特定できていなくて……"),
                ("ジャック", "今週の仕事として花壇を仕上げ、周辺の四か所も確認して記録します"),
            ],
        ),
    ]
    cases = []
    scripts = []
    for ident, name, portrait, title, opening, label, reply, after in specs:
        classification = "FIELD_CHECK" if ident == TASK else "COUNTER_COMPLETE"
        case = dict(
            case_id=ident,
            title=title,
            visitor=dict(id=ident.lower(), name=name, kind="来訪者", portrait_id=portrait),
            initial_purpose=title,
            document_status="相談・報告",
            questions=[
                dict(
                    id="talk",
                    label=label,
                    jack="植物とマウスで確認された変化と、まだ分からない点を教えてください"
                    if ident == TASK
                    else "詳しく伺ってもよろしいですか",
                    reply=reply,
                    jack_speaker="ジャック",
                    reply_speaker="ミヤノ" if ident == TASK else name,
                    memo=[],
                )
            ],
            expected_classification=classification,
        )
        if ident == TASK:
            case["field_task"] = dict(
                task_id="FIELD-JUL-W2-RESEARCH",
                location_id="july2_four_sites",
                title="花壇と四地点の確認",
                objective="花壇を確認し、四地点を調べて帰庁",
                completion_condition_id="july2_complete",
            )
        cases.append(case)

        def turns(lines, prefix, ident=ident):
            return [
                dict(turn_id=ident + prefix + str(i), jack=text, reply="", jack_speaker=speaker)
                for i, (speaker, text) in enumerate(lines)
            ]

        scripts.append(
            dict(
                case_id=ident,
                opening=turns(opening, "open"),
                after_question={"talk": turns(after, "answer")},
                resolution=dict(
                    classification=classification,
                    requires_completed_questions=["talk"],
                    if_requirements_missing="お話を最後まで確認しましょう",
                    turns=[],
                ),
                feedback={
                    classification: "現地で確認します"
                    if ident == TASK
                    else "相談とご案内を終えました"
                },
            )
        )
    return dict(cases=cases, counter_scripts={"cases": scripts})


class JulyWeek2Office(OfficePrototype):
    def __init__(self):
        raw = office_data()
        cases = parse_case_definitions(raw)
        super().__init__(cases, parse_counter_script_definitions(raw["counter_scripts"], cases))
        self.week2_progress = Week2Progress()

    @property
    def requires_classification(self):
        return self.current_case is None or self.current_case.case_id == TASK

    def complete_pending_question(self):
        completed = super().complete_pending_question()
        session = self.current_session
        if (
            not self.requires_classification
            and session is not None
            and session.state in {CaseState.HEARING, CaseState.READY_TO_CLASSIFY}
            and "talk" in session.asked_question_ids
            and not session.pending_dialogue_steps
            and session.pending_question_id is None
        ):
            session.selected_classification = Classification.COUNTER_COMPLETE
            session.state = CaseState.CLOSED_COUNTER
            session.feedback = "相談とご案内を終えました"
        return completed

    def prepare_debug_field_task(self):
        from drift_with_me.office import Classification

        for case in self.cases[:2]:
            self.sessions[case.case_id].state = CaseState.RESOLVED
        self.current_index = 2
        self.begin_current_case()
        while self.has_pending_dialogue_step():
            self.advance_dialogue_step()
        self.ask_question("talk")
        while self.has_pending_dialogue_step():
            self.advance_dialogue_step()
        self.complete_pending_question()
        self.classify(Classification.FIELD_CHECK)
        task = self.prepare_field_task()
        self.week2_progress.phase = "field"
        return task

    def finish_week(self):
        session = self.sessions[TASK]
        session.state = CaseState.RESOLVED
        session.field_result = FieldResult(
            self.cases[-1].field_task.task_id, TASK, "JULY2_COMPLETED", tuple(sorted(SITES)), ()
        )
        session.pending_dialogue_steps.clear()
        self.active_field_task = None
        self.current_index = len(self.cases)
        self.week2_progress.phase = "done"


def install_week2_world(app):
    if not hasattr(app, "world"):
        return
    raw = deepcopy(app.world.raw)
    raw["objects"] = [o for o in raw["objects"] if o["id"] not in SITES]
    if getattr(app, "work_week", None) == WorkWeek(7, 2) and hasattr(app.office, "week2_progress"):
        for ident, (label, (x, z), _) in SITES.items():
            raw["objects"].append(
                dict(
                    id=ident,
                    kind="construction_collision",
                    position=[x, 0, z],
                    inspectable=True,
                    solid=False,
                    height=2,
                )
            )
            raw["texts"][ident] = dict(title=label, lines=["周辺を確認する"])
    app.model.week2_scenery_enabled = any(o["id"] == "jul_w2_obs_fuji" for o in raw["objects"])
    world = WorldData(
        raw,
        app.world.chunk_size,
        app.world.static_visual_max_height,
        app.world.visual_detail_per_chunk,
    )
    world.east_site_access_ready = app.world.east_site_access_ready
    app.world = app.model.world = world


class JulyWeek2Mixin:
    def week2_field_header_enabled(self):
        if not self.week2_active() or getattr(self, "week_debug_active", False):
            return True
        session = self.office.current_session
        return (
            self.office.current_index == 2
            and session is not None
            and session.state in {CaseState.FIELD_CHECK_REQUIRED, CaseState.FIELD_ACTIVE}
        )

    def week2_active(self):
        return getattr(self, "work_week", None) == WorkWeek(7, 2) and hasattr(
            self.office, "week2_progress"
        )

    def save_week2(self, previous):
        from drift_with_me.save_state import snapshot

        if getattr(self, "week_debug_active", False):
            return True
        data = snapshot(self)
        if self.progress_store.write(data):
            self.last_checkpoint = data
            self.week2_save_error = ""
            return True
        self.office.week2_progress = previous
        self.week2_save_error = "保存できません。もう一度操作してください"
        return False

    def week2_ready(self):
        return self.flowerbed_visit_state().complete and self.office.week2_progress.checked == set(
            SITES
        )

    def begin_week2_observation(self, ident):
        if (
            not self.week2_active()
            or ident not in SITES
            or self.model.combat_session
            or self.model.danger_blocks_interaction()
        ):
            return False
        p = self.office.week2_progress
        lines = (
            (("ジャック", "ここは確認済み。記録は残してある"),)
            if ident in p.checked
            else LINES[ident]
        )
        self.week2_dialogue = FieldConversation(ident, lines, p.positions.get(ident, 0))
        self.week2_wait_release = True
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        return True

    def advance_week2_dialogue(self):
        dialogue = self.week2_dialogue
        p = self.office.week2_progress
        before = deepcopy(p)
        office_before = deepcopy(
            (self.office.sessions, self.office.current_index, self.office.active_field_task)
        )
        last = dialogue.index + 1 == len(dialogue.lines)
        if dialogue.target_id in SITES and dialogue.target_id not in p.checked:
            if last:
                p.checked.add(dialogue.target_id)
                p.positions.pop(dialogue.target_id, None)
            else:
                p.positions[dialogue.target_id] = dialogue.index + 1
        elif dialogue.target_id == "week2_report":
            if last:
                self.office.finish_week()
            else:
                p.report_index = dialogue.index + 1
        if not self.save_week2(before):
            self.office.sessions, self.office.current_index, self.office.active_field_task = (
                office_before
            )
            return False
        if last:
            self.week2_dialogue = None
        else:
            dialogue.index += 1
        self.week2_wait_release = True
        return True

    def return_week2(self):
        if (
            not self.week2_active()
            or self.field_transition is not None
            or self.model.combat_session
            or self.model.interaction
            or self.model.world_paused
            or getattr(self, "week2_dialogue", None) is not None
            or getattr(self, "flowerbed_dialogue", None) is not None
            or getattr(self, "flowerbed_editor", None) is not None
        ):
            return False
        p = self.office.week2_progress
        before = deepcopy(p)
        ready = self.week2_ready()
        p.phase = "report" if ready else "office"
        if not self.save_week2(before):
            return False
        self.field_transition = FieldTransition(
            "back",
            (
                (
                    "ジャック",
                    "花壇も四か所も確認できたね。戻って記録しよう"
                    if ready
                    else "いったん戻ろう。残りの確認は、また出てこよう",
                ),
                ("ヒューズ", "ええ。確認したことは記録しておきましょう"),
            ),
        )
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        return True

    def update_week2(self):
        from drift_with_me.app import AppScreen

        if not self.week2_active() or getattr(self, "park_preview_week", None) is not None:
            return False
        dialogue = getattr(self, "week2_dialogue", None)
        if getattr(self, "week2_wait_release", False):
            if not self.travel_input_held():
                self.week2_wait_release = False
            return True
        if dialogue is not None:
            self.clear_world_input_latches()
            if dialogue.target_id == "week2_return_choice":
                go, stay = self.week2_return_choice_rects()
                if self.key_pressed("KEY_ESCAPE", "KEY_X") or self.mouse_pressed_in(stay):
                    self.week2_dialogue = None
                    self.week2_wait_release = True
                elif self.key_pressed("KEY_RETURN", "KEY_Z") or self.mouse_pressed_in(go):
                    self.week2_dialogue = None
                    if not self.return_week2():
                        self.week2_dialogue = dialogue
                return True
            if (
                self.key_pressed("KEY_ESCAPE", "KEY_X")
                or self.mouse_pressed_in(self.site_cancel_rect())
            ) and dialogue.target_id != "week2_report":
                self.week2_dialogue = None
                self.week2_wait_release = True
            elif self.key_pressed("KEY_RETURN", "KEY_Z") or self.mouse_pressed_in(
                self.office_rect(40, 126, 432, 100)
            ):
                self.advance_week2_dialogue()
            return True
        p = self.office.week2_progress
        if self.field_transition is not None or self.week_transition is not None:
            return False
        if p.phase == "report" and self.screen == AppScreen.OFFICE:
            self.week2_dialogue = FieldConversation("week2_report", REPORT, p.report_index)
            self.week2_wait_release = True
            return True
        if (
            self.screen == AppScreen.PLAY
            and p.phase == "field"
            and self.week2_ready()
            and not p.return_prompt_seen
            and self.model.combat_session is None
            and not self.model.world_paused
            and not getattr(self, "flowerbed_dialogue", None)
            and not getattr(self, "flowerbed_editor", None)
            and not self.travel_input_held()
        ):
            before = deepcopy(p)
            p.return_prompt_seen = True
            if not self.save_week2(before):
                return False
            self.week2_dialogue = FieldConversation(
                "week2_return_choice", (("ジャック", "今日の用事は済んだね。帰ろうか？"),)
            )
            self.week2_wait_release = True
            self.model.cancel_auto_move()
            return True
        return False

    def week2_return_choice_rects(self):
        return self.office_rect(64, 190, 176, 30), self.office_rect(264, 190, 184, 30)


def draw_week2_ground(renderer, model, camera):
    if not getattr(model, "week2_scenery_enabled", False):
        return
    pyxel = renderer.pyxel
    # 16..19 belong to grass wind; cloud shades start at 32. Mutate the native
    # Colors sequence in place: assigning a Python list would only shadow it.
    if len(pyxel.colors) < 22 or list(pyxel.colors[20:22]) != [0xFF00FF, 0xFF65F0]:
        from drift_with_me.grass_wind import SHADES

        colors = list(pyxel.colors)
        colors.extend(list(SHADES)[max(0, len(colors) - 16) :])
        colors.extend([0] * max(0, 22 - len(colors)))
        colors[20:22] = [0xFF00FF, 0xFF65F0]
        pyxel.colors[:] = colors
    # Broad pointed leaves and green stems, rather than flower heads or scattered pixels.
    for x, z in ((288, 416), (252, 758)):
        for dx, dz in ((-7, -3), (0, 0), (7, 3)):
            renderer.draw_world_line(camera, Vec3(x + dx, 0, z + dz), Vec3(x + dx, 8, z + dz), 11)
            points = [
                camera.project(p)
                for p in (
                    Vec3(x + dx, 3, z + dz),
                    Vec3(x + dx - 7, 10, z + dz),
                    Vec3(x + dx, 12, z + dz),
                    Vec3(x + dx + 4, 8, z + dz),
                )
            ]
            if all(p is not None for p in points):
                a, b, c, d = points
                pyxel.tri(int(a.x), int(a.y), int(b.x), int(b.y), int(c.x), int(c.y), 20)
                pyxel.tri(int(a.x), int(a.y), int(c.x), int(c.y), int(d.x), int(d.y), 21)
