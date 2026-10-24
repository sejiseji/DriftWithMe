"""July W3 field work: durable collection facts and resumable zero-energy scenes."""

import math
from copy import copy, deepcopy
from dataclasses import dataclass, field, replace

from drift_with_me.field_transition import FieldTransition
from drift_with_me.field_visit import FieldConversation
from drift_with_me.math3d import AffineCameraState, Vec3
from drift_with_me.office import (
    SUPERVISOR_NAME,
    CaseState,
    FieldResult,
    OfficePrototype,
    parse_case_definitions,
    parse_counter_script_definitions,
)
from drift_with_me.ring_linkage import ASSIST_ORDER
from drift_with_me.ring_puzzle import RingIdleHint, RingPuzzle
from drift_with_me.ring_rewards import RingRewardLedger
from drift_with_me.week_cycle import WorkWeek
from drift_with_me.world import WorldData

TASK = "OFF-JUL-W3-SURVEY"
SMALL = {"jul_w3_small_fuji": (274, 440), "jul_w3_small_nw": (278, 752)}
PARENT = "jul_w3_parent"
PARENT_POSITION = (948, 826)
DURATIONS = (0.45, 0.9, 0.65, 0.65, 0.45)
SMALL_LINES = (
    ("ジャック", "黒い面に白い枠の箱だ。葉の色が変わった場所の近くだね"),
    ("ヒューズ", "関係はまだ分からないわ。空中へ投げてくれたら、電撃で止めて回収しましょう"),
)
REPORT = (
    (
        "ジャック",
        "小さい装置二つと、大きな装置一つを止めて回収しました。葉の変化との関係は、まだ分かりません",
    ),
    (
        SUPERVISOR_NAME,
        "システムの担当にも頼んでみるが、専門外じゃろうし、まあ、あまり期待せんでくれ",
    ),
    (SUPERVISOR_NAME, "教授さんにも見てもらって、意見を聞く方を並行して進めてくれんか"),
    (
        "ジャック",
        "分かりました。ユメサキ先生に連絡してみます。次週、回収した実物を渡す予定にします",
    ),
    (
        SUPERVISOR_NAME,
        "ひとまず、動いとった三つを止めて持ち帰れたんじゃ。今日はそこまでで十分じゃろ。お疲れさん",
    ),
)


@dataclass
class Week3Progress:
    phase: str = "counter"
    found: set = field(default_factory=set)
    recovered: set = field(default_factory=set)
    active_scene: str | None = None
    scene_step: int = 0
    dialogue_target: str | None = None
    dialogue_index: int = 0
    fuji_seen: bool = False
    parent_seen: bool = False
    parent_recovered: bool = False
    parent_stopped: bool = False
    ring_help: list = field(default_factory=list)
    ring_unlocked: bool = False
    ring_forfeited: bool = False
    rewards: RingRewardLedger = field(default_factory=RingRewardLedger)
    report_index: int = 0
    return_prompt_seen: bool = False
    professor_handoff_pending: bool = False
    professor_handoff_completed: bool = False

    def snapshot(self):
        return {
            **{k: v for k, v in vars(self).items() if k not in {"found", "recovered", "rewards"}},
            "found": sorted(self.found),
            "recovered": sorted(self.recovered),
            "rewards": self.rewards.snapshot(),
        }

    @classmethod
    def restore(cls, raw):
        if isinstance(raw, dict):
            raw = {
                "parent_stopped": False,
                "report_index": 0,
                "return_prompt_seen": False,
                "professor_handoff_pending": False,
                "professor_handoff_completed": False,
                **raw,
            }
        if not isinstance(raw, dict) or set(raw) != set(cls().snapshot()):
            raise ValueError("invalid July W3 fields")
        p = cls()
        for k, v in raw.items():
            if k not in {"found", "recovered", "rewards"}:
                setattr(p, k, v)
        for k in ("found", "recovered"):
            v = raw[k]
            if (
                not isinstance(v, list)
                or any(type(x) is not str or x not in SMALL for x in v)
                or len(set(v)) != len(v)
            ):
                raise ValueError("invalid terminal collection")
            setattr(p, k, set(v))
        p.rewards = RingRewardLedger.restore(raw["rewards"])
        if (
            type(p.phase) is not str
            or p.phase not in {"counter", "field", "office", "report", "done"}
            or any(
                type(getattr(p, k)) is not bool
                for k in (
                    "fuji_seen",
                    "parent_seen",
                    "parent_recovered",
                    "parent_stopped",
                    "ring_unlocked",
                    "ring_forfeited",
                    "return_prompt_seen",
                    "professor_handoff_pending",
                    "professor_handoff_completed",
                )
            )
            or not p.recovered <= p.found
            or type(p.scene_step) is not int
            or not 0 <= p.scene_step < len(DURATIONS)
            or (p.active_scene is not None and type(p.active_scene) is not str)
            or p.active_scene not in {None, *SMALL, PARENT}
            or p.active_scene in p.recovered
            or (p.active_scene in SMALL and p.active_scene not in p.found)
            or (p.dialogue_target is not None and type(p.dialogue_target) is not str)
            or p.dialogue_target not in {None, *SMALL, PARENT, "fuji"}
            or p.dialogue_target in p.recovered
            or type(p.dialogue_index) is not int
            or p.dialogue_index not in (0, 1)
            or not isinstance(p.ring_help, list)
            or p.ring_help != list(ASSIST_ORDER[: len(p.ring_help)])
            or len(p.ring_help) > 5
            or any(type(i) is not int for i in p.ring_help)
            or (p.ring_help and not p.ring_forfeited)
            or (
                p.parent_recovered
                and (
                    p.recovered != set(SMALL)
                    or not p.ring_unlocked
                    or not p.parent_stopped
                    or not p.rewards.sunglasses_received
                )
            )
            or (p.parent_stopped and (not p.ring_unlocked or p.recovered != set(SMALL)))
            or (p.parent_stopped and not p.parent_recovered and p.active_scene != PARENT)
            or (p.rewards.sunglasses_received and not p.ring_unlocked)
            or (p.active_scene == PARENT and (p.recovered != set(SMALL) or not p.ring_unlocked))
            or (p.active_scene is not None and p.dialogue_target is not None)
            or (p.dialogue_target in {None, "fuji"} and p.dialogue_index != 0)
            or type(p.report_index) is not int
            or not 0 <= p.report_index < len(REPORT)
            or (p.phase in {"report", "done"} and not p.parent_recovered)
            or p.professor_handoff_pending
            != (p.phase == "done" and not p.professor_handoff_completed)
            or (p.professor_handoff_completed and p.phase != "done")
            or (p.return_prompt_seen and not p.parent_recovered)
            or (
                p.phase != "field" and (p.active_scene is not None or p.dialogue_target is not None)
            )
            or (p.phase == "done" and p.report_index != len(REPORT) - 1)
            or (p.phase not in {"report", "done"} and p.report_index != 0)
        ):
            raise ValueError("inconsistent July W3 progress")
        if p.phase == "counter" and (p.found or p.active_scene or p.parent_seen):
            raise ValueError("premature July W3 field progress")
        return p


def office_data():
    opening = (
        "今日の保護区調査の件な、9時には調査開始してくれてええらしいわ。"
        "例によってフジさんも現地おるかもしれん、造園の進捗も確認しつつよろしく頼むわ"
    )
    case = dict(
        case_id=TASK,
        title="保護区の予定調査",
        visitor=dict(
            id="supervisor", name=SUPERVISOR_NAME, kind="予定確認", portrait_id="office_supervisor"
        ),
        initial_purpose="保護区の予定調査",
        document_status="当日の予定",
        questions=[
            dict(
                id="talk",
                label="担当する確認を聞く",
                jack="フジさんの造園の進み具合と、葉が変色した辺りを見てきます。見慣れない物があれば、安全を確かめて持ち帰ります",
                reply="頼むわ。分かったことと、まだ分からんことは分けて記録してな",
                memo=[],
            )
        ],
        expected_classification="FIELD_CHECK",
        field_task=dict(
            task_id="FIELD-JUL-W3-SURVEY",
            location_id="reserve_survey",
            title="保護区の予定調査",
            objective="造園の進捗と変色箇所を調査。見つけた装置を停止して回収",
            completion_condition_id="july3_field_recovered",
        ),
    )
    script = dict(
        case_id=TASK,
        opening=[dict(turn_id="jul3_open", jack=opening, reply="", jack_speaker=SUPERVISOR_NAME)],
        after_question={"talk": []},
        resolution=dict(
            classification="FIELD_CHECK",
            requires_completed_questions=["talk"],
            if_requirements_missing="当日の担当を確認しましょう",
            turns=[],
        ),
        feedback={"FIELD_CHECK": "9時は調査予定の時刻です。準備ができたら出発できます"},
    )
    return dict(cases=[case], counter_scripts={"cases": [script]})


class JulyWeek3Office(OfficePrototype):
    def __init__(self):
        raw = office_data()
        cases = parse_case_definitions(raw)
        super().__init__(cases, parse_counter_script_definitions(raw["counter_scripts"], cases))
        self.week3_progress = Week3Progress()

    def finish_week(self):
        p = self.week3_progress
        if p.phase != "report" or not p.parent_recovered or p.report_index != len(REPORT) - 1:
            return False
        session = self.sessions[TASK]
        session.state = CaseState.RESOLVED
        session.field_result = FieldResult(
            self.cases[0].field_task.task_id,
            TASK,
            "JULY3_COMPLETED",
            tuple(sorted([*SMALL, PARENT])),
            (),
        )
        session.pending_dialogue_steps.clear()
        self.active_field_task = None
        self.current_index = len(self.cases)
        p.phase = "done"
        p.professor_handoff_pending = True
        return True

    def prepare_debug_field_task(self):
        from drift_with_me.office import Classification

        self.begin_current_case()
        while self.has_pending_dialogue_step():
            self.advance_dialogue_step()
        self.ask_question("talk")
        while self.has_pending_dialogue_step():
            self.advance_dialogue_step()
        self.complete_pending_question()
        self.classify(Classification.FIELD_CHECK)
        self.week3_progress.phase = "field"
        return self.prepare_field_task()


def install_week3_world(app):
    if not hasattr(app, "world"):
        return
    raw = deepcopy(app.world.raw)
    raw["objects"] = [o for o in raw["objects"] if not o["id"].startswith("jul_w3_")]
    if getattr(app, "work_week", None) == WorkWeek(7, 3) and hasattr(app.office, "week3_progress"):
        progress = app.office.week3_progress
        # Keep observed leaf discoloration; stopping devices does not establish recovery/causation.
        app.model.week2_scenery_enabled = True
        positions = {k: v for k, v in SMALL.items() if k not in progress.recovered}
        if not progress.parent_recovered:
            positions[PARENT] = PARENT_POSITION
        for ident, (x, z) in positions.items():
            raw["objects"].append(
                dict(
                    id=ident,
                    kind="construction_collision",
                    position=[x, 0, z],
                    inspectable=True,
                    solid=False,
                    height=12,
                )
            )
            raw["texts"][ident] = dict(
                title="白枠の装置" if ident != PARENT else "大きな白枠の装置",
                lines=["様子を確かめる"],
            )
    world = WorldData(
        raw,
        app.world.chunk_size,
        app.world.static_visual_max_height,
        app.world.visual_detail_per_chunk,
    )
    world.east_site_access_ready = app.world.east_site_access_ready
    app.world = app.model.world = world


def draw_cube(p, camera, x, z, height=0, half=5, spin=0.0):
    # Eight rigid vertices, six faces: no textures, mesh assets or depth buffer.
    yaw = spin * 0.35
    tilt = 0.22 + 0.10 * math.sin(spin * 0.21)
    cy, sy, ct, st = math.cos(yaw), math.sin(yaw), math.cos(tilt), math.sin(tilt)
    world = []
    for dx, dy, dz in (
        (-1, -1, -1),
        (1, -1, -1),
        (1, -1, 1),
        (-1, -1, 1),
        (-1, 1, -1),
        (1, 1, -1),
        (1, 1, 1),
        (-1, 1, 1),
    ):
        ty, tz = dy * ct - dz * st, dy * st + dz * ct
        world.append(
            Vec3(
                x + half * (dx * cy + tz * sy),
                height + half * (1.3 + ty),
                z + half * (-dx * sy + tz * cy),
            )
        )
    vertices = [camera.project(v) for v in world]
    if any(v is None for v in vertices):
        return
    faces = []
    for face in (
        (0, 4, 5, 1),
        (3, 2, 6, 7),
        (0, 3, 7, 4),
        (1, 5, 6, 2),
        (0, 1, 2, 3),
        (4, 7, 6, 5),
    ):
        # Outward winding; cull in world space for both affine and perspective.
        a, b, c = (world[i] for i in face[:3])
        u, v = b - a, c - a
        normal = Vec3(u.y * v.z - u.z * v.y, u.z * v.x - u.x * v.z, u.x * v.y - u.y * v.x)
        toward = (
            camera.profile.fixed_forward
            if isinstance(camera, AffineCameraState)
            else a - camera.basis[0]
        )
        if normal.x * toward.x + normal.y * toward.y + normal.z * toward.z < -1e-9:
            faces.append(face)
    edges = set()
    for face in faces:
        a, b, c, d = [vertices[i] for i in face]
        p.tri(a.x, a.y, b.x, b.y, c.x, c.y, 0)
        p.tri(a.x, a.y, c.x, c.y, d.x, d.y, 0)
        for i, j in zip(face, face[1:] + face[:1], strict=True):
            edges.add(tuple(sorted((i, j))))
    # Draw visible edges once, after all opaque faces; no rear wireframe bleed.
    for i, j in sorted(edges):
        a, b = vertices[i], vertices[j]
        p.line(a.x, a.y, b.x, b.y, 7)


class JulyWeek3Mixin:
    def week3_office_report_active(self):
        from drift_with_me.app import AppScreen

        return (
            self.week3_active()
            and self.screen == AppScreen.OFFICE
            and self.office.week3_progress.phase == "report"
        )

    def week3_active(self):
        return getattr(self, "work_week", None) == WorkWeek(7, 3) and hasattr(
            self.office, "week3_progress"
        )

    def save_week3(self, previous):
        if getattr(self, "week_debug_active", False):
            return True
        from drift_with_me.save_state import snapshot

        data = snapshot(self)
        if self.progress_store.write(data):
            self.last_checkpoint = data
            self.week3_error = ""
            return True
        self.office.week3_progress = previous
        self.week3_error = "保存できません。もう一度お試しください"
        return False

    def week3_lines(self, target):
        if target in SMALL:
            return SMALL_LINES
        if target == PARENT:
            p = self.office.week3_progress
            if p.recovered == set(SMALL):
                if p.ring_unlocked:
                    return (("ヒューズ", "ロックは外れているわ。接続を止めて持ち帰りましょう"),)
                return (
                    ("ジャック", "小さい箱は二つとも回収した。でも親機のふたは開かないな"),
                    (
                        "ヒューズ",
                        "中が複雑ね。直接ショートさせず、リングのロックを外してから接続を止めましょう",
                    ),
                )
            return (
                ("ジャック", "同じ白い枠だけど、こちらは大きくて複雑そうだ"),
                (
                    "ヒューズ",
                    "小さい装置が二つあるわ。まずそちらを止めてから、この装置を調べましょう",
                ),
            )
        return (
            ("フジ", "北東の広場は、通路と花壇の区画を整えている。足元に気をつけて見ていってくれ"),
        )

    def begin_week3_target(self, target):
        if (
            not self.week3_active()
            or target not in {*SMALL, PARENT, "fuji"}
            or self.model.combat_session is not None
            or self.office.week3_progress.phase != "field"
        ):
            return False
        p = self.office.week3_progress
        if target in p.recovered or target == PARENT and p.parent_recovered:
            return False
        if p.active_scene or getattr(self, "week3_dialogue", None):
            return False
        before = deepcopy(p)
        lines = self.week3_lines(target)
        p.dialogue_target = target
        p.dialogue_index = 0
        if target in SMALL:
            p.found.add(target)
        elif target == PARENT:
            p.parent_seen = True
        else:
            p.fuji_seen = True
        if not self.save_week3(before):
            return False
        self.week3_dialogue = FieldConversation(target, lines)
        self.week3_wait_release = True
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        return True

    def advance_week3_dialogue(self):
        p = self.office.week3_progress
        d = self.week3_dialogue
        if d is None:
            return False
        before = deepcopy(p)
        last = d.index + 1 == len(d.lines)
        if d.target_id == "week3_report":
            office_before = deepcopy(
                (self.office.sessions, self.office.current_index, self.office.active_field_task)
            )
            if last:
                if not self.office.finish_week():
                    return False
            else:
                p.report_index += 1
            if not self.save_week3(before):
                self.office.sessions, self.office.current_index, self.office.active_field_task = (
                    office_before
                )
                return False
            if last:
                self.week3_dialogue = None
            else:
                d.index += 1
            self.week3_wait_release = True
            return True
        if not last:
            p.dialogue_index = d.index + 1
        else:
            p.dialogue_target = None
            p.dialogue_index = 0
            if d.target_id in SMALL:
                p.active_scene = d.target_id
                p.scene_step = 0
        if not self.save_week3(before):
            return False
        if last:
            self.week3_dialogue = None
            self.week3_scene_elapsed = 0.0
            if d.target_id in SMALL:
                self.week3_cube_spin_origin = (d.target_id, getattr(self, "presentation_time", 0.0))
            if d.target_id == PARENT and p.recovered == set(SMALL):
                if p.ring_unlocked:
                    return self.begin_parent_disconnect()
                return self.open_story_ring()
        else:
            d.index += 1
        self.week3_wait_release = True
        return True

    def return_week3(self):
        if (
            not self.week3_active()
            or self.office.week3_progress.phase != "field"
            or getattr(self, "week3_dialogue", None)
            or self.office.week3_progress.active_scene
            or self.model.combat_session
            or self.model.interaction
            or self.field_transition
            or getattr(self, "flowerbed_dialogue", None)
            or getattr(self, "flowerbed_editor", None)
            or self.model.world_paused
        ):
            return False
        p = self.office.week3_progress
        before = deepcopy(p)
        ready = p.parent_recovered
        p.phase = "report" if ready else "office"
        if not self.save_week3(before):
            return False
        self.field_transition = FieldTransition(
            "back",
            (
                (
                    "ジャック",
                    "三つとも止めて回収できたね。戻って上司に報告しよう"
                    if ready
                    else "いったん戻ろう。残りの装置は、また調査に出て確かめよう",
                ),
                ("ヒューズ", "ええ。分かったところを分けて残しましょう"),
            ),
        )
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        return True

    def cancel_week3_return(self):
        p = self.office.week3_progress
        before = deepcopy(p)
        p.phase = "field"
        return self.save_week3(before)

    def update_july_week3(self, elapsed):
        if not self.week3_active():
            return False
        from drift_with_me.app import AppScreen

        p = self.office.week3_progress
        if self.field_transition is not None or self.week_transition is not None:
            return False
        if self.screen == AppScreen.OFFICE and p.phase == "done":
            self.clear_world_input_latches()
            if self.can_begin_next_week() and (
                self.key_pressed("KEY_RETURN", "KEY_Z")
                or self.mouse_pressed_in(self.office_next_week_rect())
            ):
                self.begin_next_week()
            return True
        if self.screen == AppScreen.OFFICE and p.phase == "office" and p.parent_recovered:
            before = deepcopy(p)
            p.phase = "report"
            if not self.save_week3(before):
                return True
        if self.screen == AppScreen.OFFICE and p.phase == "office":
            self.clear_world_input_latches()
            if self.key_pressed("KEY_RETURN", "KEY_Z") or self.mouse_pressed_in(
                self.office_footer_action_rect()
            ):
                self.enter_exploration_from_office()
            return True
        if (
            self.screen == AppScreen.OFFICE
            and p.phase == "report"
            and not getattr(self, "week3_dialogue", None)
        ):
            self.week3_dialogue = FieldConversation("week3_report", REPORT, p.report_index)
            self.week3_wait_release = True
        if self.week3_office_report_active():
            self.clear_world_input_latches()
            self.update_office_dialogue_playback(elapsed)
            if getattr(self, "week3_wait_release", False):
                if not self.travel_input_held():
                    self.week3_wait_release = False
                return True
            if (
                self.key_pressed("KEY_RETURN", "KEY_Z")
                or self.mouse_pressed_in(self.office_dialog_rect())
                or self.mouse_pressed_in(self.office_footer_action_rect())
            ):
                self.advance_office_dialogue_page()
                self.week3_wait_release = True
            return True
        if self.screen not in {AppScreen.PLAY, AppScreen.OFFICE}:
            return False
        if getattr(self, "story_ring_active", False) and self.ring_preview is not None:
            self.update_ring_preview()
            return True
        if p.active_scene:
            self.clear_world_input_latches()
            self.model.cancel_auto_move()
            self.week3_scene_elapsed = getattr(self, "week3_scene_elapsed", 0.0) + elapsed
            if self.week3_scene_elapsed >= DURATIONS[p.scene_step]:
                before = deepcopy(p)
                if p.scene_step == len(DURATIONS) - 1:
                    if p.active_scene == PARENT:
                        p.parent_recovered = True
                    else:
                        p.recovered.add(p.active_scene)
                    p.active_scene = None
                    p.scene_step = 0
                else:
                    if p.active_scene == PARENT and p.scene_step == 1:
                        p.parent_stopped = True
                    p.scene_step += 1
                if self.save_week3(before):
                    self.week3_scene_elapsed = 0.0
                    install_week3_world(self)
            return True
        d = getattr(self, "week3_dialogue", None)
        if d is None and p.dialogue_target:
            self.week3_dialogue = d = FieldConversation(
                p.dialogue_target, self.week3_lines(p.dialogue_target), p.dialogue_index
            )
            self.week3_wait_release = True
        if d is None:
            if (
                self.screen == AppScreen.PLAY
                and p.phase == "field"
                and p.parent_recovered
                and not p.return_prompt_seen
                and self.model.combat_session is None
                and not self.model.world_paused
                and not getattr(self, "flowerbed_dialogue", None)
                and not getattr(self, "flowerbed_editor", None)
                and not self.travel_input_held()
            ):
                before = deepcopy(p)
                p.return_prompt_seen = True
                if not self.save_week3(before):
                    return True
                self.week3_dialogue = FieldConversation(
                    "week3_return_choice",
                    (("ジャック", "三つとも止めて回収できたね。帰庁して報告しようか？"),),
                )
                self.week3_wait_release = True
                self.clear_world_input_latches()
                self.model.cancel_auto_move()
                return True
            return False
        if getattr(self, "week3_wait_release", False):
            if not self.travel_input_held():
                self.week3_wait_release = False
            return True
        self.clear_world_input_latches()
        if d.target_id == "week3_return_choice":
            go, stay = self.week2_return_choice_rects()
            if self.key_pressed("KEY_ESCAPE", "KEY_X") or self.mouse_pressed_in(stay):
                self.week3_dialogue = None
                self.week3_wait_release = True
            elif self.key_pressed("KEY_RETURN", "KEY_Z") or self.mouse_pressed_in(go):
                self.week3_dialogue = None
                if not self.return_week3():
                    self.week3_dialogue = d
            return True
        if self.key_pressed("KEY_ESCAPE", "KEY_X") or self.mouse_pressed_in(
            self.site_cancel_rect()
        ):
            if d.target_id == "week3_report":
                return True
            before = deepcopy(p)
            p.dialogue_target = None
            p.dialogue_index = 0
            if self.save_week3(before):
                self.week3_dialogue = None
        elif self.key_pressed("KEY_RETURN", "KEY_Z") or self.mouse_pressed_in(
            self.office_rect(40, 126, 432, 100)
        ):
            self.advance_week3_dialogue()
        return True

    def draw_week3_devices(self, camera):
        if not self.week3_active():
            return
        p = self.office.week3_progress
        for ident, (x, z) in {**SMALL, PARENT: PARENT_POSITION}.items():
            if (
                ident in p.recovered
                or ident == PARENT
                and p.parent_recovered
                or ident == p.active_scene
            ):
                continue
            draw_cube(
                self.pyxel,
                camera,
                x,
                z,
                half=8 if ident == PARENT else 5,
                spin=self.presentation_time,
            )

    def week3_cube_scene_spin(self):
        p = self.office.week3_progress
        ident, origin = getattr(self, "week3_cube_spin_origin", (None, 0.0))
        if ident != p.active_scene:
            origin = 0.0  # Resumed scenes need no new persistent animation fields.
        elapsed = sum(DURATIONS[: p.scene_step]) + getattr(self, "week3_scene_elapsed", 0.0)
        stop = sum(DURATIONS[: 2 if p.active_scene == PARENT else 3])
        return origin + min(elapsed, stop)

    def draw_week3_scene(self):
        p = self.office.week3_progress
        ident = p.active_scene
        if ident == PARENT:
            self.draw_week3_parent_scene()
            return
        x, z = SMALL[ident]
        step = p.scene_step
        t = min(1.0, getattr(self, "week3_scene_elapsed", 0.0) / DURATIONS[step])
        amount = t if step == 0 else 1 - t if step == 4 else 1
        original = self.scene_camera(self.camera())
        target = Vec3((self.model.player.x + x) / 2, 8, (self.model.player.z + z) / 2)
        camera = replace(original, target=original.target * (1 - amount) + target * amount)
        camera = (
            replace(camera, zoom=camera.zoom * (1 + 0.5 * amount))
            if isinstance(camera, AffineCameraState)
            else replace(camera, distance=camera.distance / (1 + 0.5 * amount))
        )
        # A presentation copy keeps both real actor transforms/resources untouched.
        view = copy(self.model)
        view.player = replace(
            self.model.player,
            x=self.model.player.x * (1 - amount) + (x - 18) * amount,
            z=self.model.player.z * (1 - amount) + (z + 14) * amount,
        )
        view.buddy = replace(
            self.model.buddy,
            x=self.model.buddy.x * (1 - amount) + (x + 22) * amount,
            z=self.model.buddy.z * (1 - amount) + (z + 8) * amount,
        )
        self.renderer.draw_scene(
            view, camera, self.presentation_time, False, self.effects, exploration_markers=False
        )
        self.draw_week3_devices(camera)
        player = view.player
        if step == 0:
            cx, cz, h = x * (1 - t) + player.x * t, z * (1 - t) + player.z * t, 18 * t
        elif step == 1:
            cx, cz, h = (
                player.x * (1 - t) + (x + 8) * t,
                player.z * (1 - t) + z * t,
                18 + 32 * math.sin(t * math.pi / 2),
            )
        elif step == 2:
            cx, cz, h = x + 8, z, 50
        elif step == 3:
            cx, cz, h = (
                (x + 8) * (1 - t) + player.x * t,
                z * (1 - t) + player.z * t,
                50 * (1 - t) + 8 * t,
            )
        else:
            cx, cz, h = player.x, player.z, 8
        if step < 4:
            draw_cube(self.pyxel, camera, cx, cz, h, spin=self.week3_cube_scene_spin())
        if step == 2:
            a = camera.project(Vec3(view.buddy.x, view.buddy.y + 6, view.buddy.z))
            b = camera.project(Vec3(cx, h + 6, cz))
            if a and b:
                points = (
                    [(a.x, a.y)]
                    + [
                        (
                            a.x + (b.x - a.x) * i / 5,
                            a.y
                            + (b.y - a.y) * i / 5
                            + math.sin(i * 2 + self.presentation_time * 8) * 4,
                        )
                        for i in range(1, 5)
                    ]
                    + [(b.x, b.y)]
                )
                for u, v in zip(points, points[1:], strict=False):
                    self.pyxel.line(*u, *v, 7 if int(self.presentation_time * 6) % 2 else 12)
        label = (
            "近くで確かめる",
            "ジャックが投げる",
            "ヒューズがショートさせる",
            "回収する",
            "調査へ戻る",
        )[step]
        self.draw_office_text_in_rect(self.office_rect(48, 208, 416, 24), label, 7, align="center")

    def open_story_ring(self):
        p = self.office.week3_progress
        if (
            p.recovered != set(SMALL)
            or p.parent_recovered
            or self.model.combat_session is not None
            or p.phase != "field"
        ):
            return False
        if p.ring_unlocked:
            return self.begin_parent_disconnect()
        puzzle = RingPuzzle.create()
        puzzle.disabled_links = p.ring_help[:]
        puzzle.help_history = p.ring_help[:]
        puzzle.eligibility_forfeited = p.ring_forfeited
        self.ring_preview = puzzle
        self.ring_preview_store = StoryRingStore(self)
        self.ring_preview_time = self.presentation_time
        self.ring_idle_hint = RingIdleHint(self.presentation_time)
        self.ring_intro_started = None
        self.ring_intro_done = False
        self.ring_intro_entry = self.presentation_time
        self.story_ring_active = True
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        return True

    def close_story_ring(self):
        puzzle = self.ring_preview
        if not self.ring_preview_store.save_progress(puzzle):
            return False
        cleared = puzzle.phase == "unlocked"
        self.restore_ring_grid_palette()
        self.ring_preview = None
        self.story_ring_active = False
        self.clear_world_input_latches()
        if cleared:
            return self.begin_parent_disconnect()
        return True

    def begin_parent_disconnect(self):
        p = self.office.week3_progress
        if p.recovered != set(SMALL) or not p.ring_unlocked or p.parent_recovered:
            return False
        before = deepcopy(p)
        completed = RingPuzzle.create()
        completed.angles = [0] * 5
        completed.phase = "unlocked"
        p.rewards.claim(completed)
        p.active_scene = PARENT
        p.scene_step = 0
        if not self.save_week3(before):
            return False
        self.week3_scene_elapsed = 0.0
        self.week3_cube_spin_origin = (PARENT, getattr(self, "presentation_time", 0.0))
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        return True

    def draw_week3_parent_scene(self):
        p = self.office.week3_progress
        x, z = PARENT_POSITION
        step = p.scene_step
        t = min(1.0, getattr(self, "week3_scene_elapsed", 0.0) / DURATIONS[step])
        amount = t if step == 0 else 1 - t if step == 4 else 1
        original = self.scene_camera(self.camera())
        target = Vec3(x, 8, z + 8)
        camera = replace(original, target=original.target * (1 - amount) + target * amount)
        camera = (
            replace(camera, zoom=camera.zoom * (1 + 0.5 * amount))
            if isinstance(camera, AffineCameraState)
            else replace(camera, distance=camera.distance / (1 + 0.5 * amount))
        )
        view = copy(self.model)
        view.player = replace(
            self.model.player,
            x=self.model.player.x * (1 - amount) + (x - 18) * amount,
            z=self.model.player.z * (1 - amount) + (z + 14) * amount,
        )
        view.buddy = replace(
            self.model.buddy,
            x=self.model.buddy.x * (1 - amount) + (x + 22) * amount,
            z=self.model.buddy.z * (1 - amount) + (z + 8) * amount,
        )
        self.renderer.draw_scene(
            view, camera, self.presentation_time, False, self.effects, exploration_markers=False
        )
        self.draw_week3_devices(camera)
        if step < 3:
            draw_cube(self.pyxel, camera, x, z, 0, 8, spin=self.week3_cube_scene_spin())
        elif step == 3:
            draw_cube(
                self.pyxel,
                camera,
                x * (1 - t) + view.player.x * t,
                z * (1 - t) + view.player.z * t,
                12 * math.sin(t * math.pi),
                8,
                spin=self.week3_cube_scene_spin(),
            )
        # A steady connection lead is disconnected, never an electric short/attack.
        if step == 0 or step == 1 and t < 0.6:
            a = camera.project(Vec3(view.buddy.x, view.buddy.y + 4, view.buddy.z))
            b = camera.project(Vec3(x, 8, z))
            if a and b:
                self.pyxel.line(a.x, a.y, b.x, b.y, 10)
        label = (
            "親機へ接続する",
            "ヒューズが接続を止める",
            "停止を確認する",
            "親機を回収する",
            "調査へ戻る",
        )[step]
        self.draw_office_text_in_rect(self.office_rect(48, 208, 416, 24), label, 7, align="center")


class StoryRingStore:
    """Main-story facts only; never use debug storage or persist the rotating board."""

    def __init__(self, app):
        self.app = app

    def save_progress(self, puzzle):
        app = self.app
        p = app.office.week3_progress
        previous = deepcopy(p)
        p.ring_help = puzzle.help_history[:]
        p.ring_forfeited = p.ring_forfeited or puzzle.eligibility_forfeited
        if puzzle.phase in {"solved", "unlocking", "celebrating", "unlocked"} and not any(
            puzzle.angles
        ):
            p.ring_unlocked = True
            settled = deepcopy(puzzle)
            settled.phase = "unlocked"
            p.rewards.claim(settled)
        return app.save_week3(previous)
