"""June week three: a separate confirmation record and ordered office reports."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace

from drift_with_me import config
from drift_with_me.office import (
    CaseSession,
    CaseState,
    OfficePrototype,
    parse_case_definitions,
    parse_counter_script_definitions,
)

KEY_ID = "jun_w3_old_key"
KEY_POSITION = (954, 170)
KEY_LINES = (
    ("ジャック", "これ、鍵じゃない？ さっきのふたのかな"),
    ("ヒューズ", "番号が同じね。ウラさんに見せてみましょうか"),
)
KEY_FIRST_LINES = (
    ("ジャック", "これ、鍵じゃない？ 札に番号がついてる"),
    ("ヒューズ", "古そうね。ウラさんに見せてみましょうか"),
)

TASK_CASE = "OFF-JUN-W3-SAGAN"
SITE_FACTS = {
    "jun_w2_canal_bank": "route_bank",
    "jun_w2_shade": "route_stone",
    "jun_w2_old_hatch": "hatch_matched",
}
FACTS = frozenset(SITE_FACTS.values())
LABELS = {
    KEY_ID: "点検口そばの草むら",
    "jun_w2_canal_bank": "水源近くの陥没面",
    "jun_w2_shade": "木陰の通路",
    "jun_w2_old_hatch": "点検口",
}
LINES = {
    "jun_w2_canal_bank": (
        ("ジャック", "足元がへこんでる。荷物を抱えてここを通るのは、ちょっと大変そうだな"),
        ("ヒューズ", "そうね。足元を確かめながら運ぶことになりそう。ここは伝えておきましょう"),
    ),
    "jun_w2_old_hatch": (
        ("ジャック", "水源から見て、この位置……うん、記録と合ってる"),
        ("ヒューズ", "ふたの縁に草がかかってるわね。開けるなら、先に周りを片づけることになりそう"),
        ("ジャック", "鍵穴がある。横には管理番号……記録しておこう"),
        ("ヒューズ", "ええ。今日は開けずに、ウラさんに伝えましょう"),
    ),
    "jun_w2_shade": (
        ("ジャック", "この石、荷車だと引っかかりそうじゃない？"),
        ("ヒューズ", "そうね。どこにあるか、道の曲がり角も一緒に覚えておきましょう"),
    ),
}


@dataclass
class Week3Progress:
    facts: set[str] = field(default_factory=set)
    positions: dict[str, int] = field(default_factory=dict)
    reported: set[str] = field(default_factory=set)
    pending_completion: str | None = None

    key_seen: bool = False
    key_collected: bool = False
    key_consulted: bool = False
    legacy_complete: bool = False

    @property
    def ready(self):
        return self.facts == FACTS and (self.key_consulted or self.legacy_complete)

    def lines_for(self, target):
        if target == KEY_ID:
            if self.key_collected:
                return (("ジャック", "ここにあった鍵は、もう持ってるね"),)
            return KEY_LINES if "hatch_matched" in self.facts else KEY_FIRST_LINES
        if SITE_FACTS[target] in self.facts:
            return (("ジャック", "ここは、さっき確認したとおりだね。"),)
        if target == "jun_w2_old_hatch" and self.key_collected:
            return LINES[target][:2] + (
                ("ジャック", "鍵穴がある。ここにも、鍵の札と同じ管理番号だ"),
                ("ヒューズ", "このふたの鍵かもしれないわね。ウラさんに確かめましょう"),
            )
        return LINES[target]

    def begin(self, target):
        self.pending_completion = None
        if target == KEY_ID:
            self.key_seen = True
        lines = self.lines_for(target)
        return lines, min(self.positions.get(target, 0), len(lines) - 1)

    def complete(self, target):
        if target != self.pending_completion or target not in (set(SITE_FACTS) | {KEY_ID}):
            return False
        if target == KEY_ID:
            if self.key_collected:
                self.pending_completion = None
                return False
            self.key_seen = self.key_collected = True
        else:
            self.facts.add(SITE_FACTS[target])
        self.positions.pop(target, None)
        self.pending_completion = None
        return True

    def travel_lines(self, direction):
        if direction == "out":
            return (
                ("ジャック", "点検口と、資材を運ぶ道。今日は二つだね"),
                ("ヒューズ", "ええ。近い所でよかったわ。順に見ていきましょう"),
            )
        if self.key_collected and not self.key_consulted:
            return (
                (
                    "ジャック",
                    "この鍵、ウラさんに見せよう。道で気になった所も伝えないとね"
                    if self.facts == FACTS
                    else "この鍵、ウラさんに見せよう。まだ見てない所は、また来てからだね",
                ),
                ("ヒューズ", "ええ。まずは札の番号を確かめてもらいましょう"),
            )
        if self.facts == FACTS and not self.key_collected:
            return (
                ("ジャック", "点検口と道は見られた。鍵はまだ見つかってないね"),
                ("ヒューズ", "一度戻りましょう。続きは、また来てからでいいわ"),
            )
        if self.facts == FACTS:
            return (
                ("ジャック", "点検口は記録どおり。道も、気になる所が二つあったね"),
                (
                    "ヒューズ",
                    "ええ。戻ってサガンたちに聞いてもらいましょう。どう運ぶか考えやすくなるわ",
                ),
            )
        seen = "、".join(LABELS[t] for t, f in SITE_FACTS.items() if f in self.facts)
        missing = "、".join(LABELS[t] for t, f in SITE_FACTS.items() if f not in self.facts)
        jack = (
            f"{seen}は見られたけど、{missing}はまだだね"
            if seen
            else "まだ確認できていないけど、一度戻ろうか"
        )
        return (
            ("ジャック", jack),
            (
                "ヒューズ",
                "続きはまたにしましょう。どこまで見たか、忘れないうちに伝えておけばいいわ",
            ),
        )


class Week3Office(OfficePrototype):
    def __init__(self):
        raw = config.load_data_json("office_week3.json")
        cases = parse_case_definitions(raw)
        super().__init__(cases, parse_counter_script_definitions(raw["counter_scripts"], cases))
        self.site_progress = Week3Progress()
        self.full_report_cases = self.cases
        self.full_report_scripts = dict(self.counter_scripts)

    def refresh_reports(self):
        facts = self.site_progress.facts
        cases = list(self.full_report_cases)
        progress = self.site_progress
        if progress.key_collected:
            text = (
                "点検口の近くで鍵を拾いました。札には、ふたと同じ管理番号がついています"
                if "hatch_matched" in facts
                else "古い鍵を拾いました。札の番号を、記録で見てもらえますか？"
            )
            reply = (
                "ああ、この番号ですね。記録の続きに、点検の控えがあります。そちらも探しておきますね"
                if "hatch_matched" in facts
                else "記録では、あの点検口の番号ですね。現地の番号も確かめてもらえますか？"
            )
            if progress.key_consulted:
                reply = "はい。その番号の控えは、こちらでも引き続き探しておきますね"
            cases[4] = replace(
                cases[4],
                questions=(
                    replace(
                        cases[4].questions[0],
                        jack_text=text,
                        visitor_reply=reply,
                        answer_summary="鍵の札の番号を照会",
                    ),
                ),
            )
        if not {"route_bank", "route_stone"} <= facts:
            parts = []
            if "route_bank" in facts:
                parts.append("水源の近くで地面がへこんでて、荷物を持つと通りにくそうだった。")
            if "route_stone" in facts:
                parts.append("木陰までの道に石が出てる。")
            text = "".join(parts) or (
                "点検口は確認できた。道のほうは、まだだよ。"
                if "hatch_matched" in facts
                else "まだ確認できてない。改めて見てくるよ。"
            )
            q = replace(
                cases[5].questions[0],
                jack_text=text,
                visitor_reply="了解。残りも、見られたら教えてくれ",
                answer_summary="確認できた内容だけを報告",
            )
            cases[5] = replace(cases[5], questions=(q,))
        if facts != FACTS and {"route_bank", "route_stone"} <= facts:
            q = replace(cases[5].questions[0], visitor_reply="了解。残りも、見られたら教えてくれ")
            cases[5] = replace(cases[5], questions=(q,))
        script = self.full_report_scripts[cases[5].case_id]
        if not progress.ready:
            script = replace(script, resolution=replace(script.resolution, turns=()))
        self.counter_scripts[cases[5].case_id] = script
        self.cases = tuple(cases)

    def complete_field_task(self, result):
        task = self.active_field_task
        session = self.current_session
        if (
            task is None
            or session is None
            or session.state != CaseState.FIELD_ACTIVE
            or result.case_id != TASK_CASE
            or result.task_id != task.task_id
            or result.result_code != "WEEK3_CONFIRMED"
            or set(result.discovered_fact_ids) != self.site_progress.facts
        ):
            return False
        session.field_result = result
        session.state = CaseState.RESOLVED
        self.active_field_task = None
        for case in self.cases[4:]:
            self.sessions[case.case_id] = CaseSession(case.case_id)
        self.refresh_reports()
        self.current_index = (
            4
            if ("hatch_matched" in self.site_progress.facts or self.site_progress.key_collected)
            else 5
        )
        if self.current_index == 5:
            self.sessions[self.cases[4].case_id].state = CaseState.RESOLVED
        self.begin_current_case()
        return True

    def classify(self, classification):
        if self.current_index in (4, 5):
            if self.sessions[TASK_CASE].field_result is None:
                return False
            if self.current_index == 4 and not (
                "hatch_matched" in self.site_progress.facts or self.site_progress.key_collected
            ):
                return False
        return super().classify(classification)

    def advance_case(self):
        index = self.current_index
        if not super().advance_case():
            return False
        if index == 4:
            if "hatch_matched" in self.site_progress.facts:
                self.site_progress.reported.add("hatch_matched")
            if self.site_progress.key_collected:
                self.site_progress.key_consulted = True
            self.refresh_reports()
        elif index == 5:
            self.site_progress.reported.update(
                self.site_progress.facts & {"route_bank", "route_stone"}
            )
            if not self.site_progress.ready or self.site_progress.reported != FACTS:
                self.current_index = 3
                session = self.current_session
                session.state = CaseState.FIELD_CHECK_REQUIRED
                session.field_result = None
                session.dialogue.clear()
                session.active_dialogue_line_count = 0
                session.pending_dialogue_steps.clear()
                self.prepare_field_task()
        return True


def install_week3_world(app, *, enabled=True):
    """A non-solid inspection target; authored terrain and enemies stay intact."""
    from drift_with_me.world import WorldData

    if not hasattr(app, "world"):
        return
    if not enabled and app.world.object_by_id(KEY_ID) is None:
        return
    access_ready = app.world.east_site_access_ready
    raw = deepcopy(app.world.raw)
    raw["objects"] = [o for o in raw["objects"] if o["id"] != KEY_ID]
    if enabled:
        x, z = KEY_POSITION
        raw["objects"].append(
            {
                "id": KEY_ID,
                "kind": "sprite_prop",
                "position": [x, 0, z],
                "visual": KEY_ID,
                "solid": False,
                "inspectable": True,
                "height": 4,
                "sprite_world_size": [8, 8],
                "text_key": KEY_ID,
            }
        )
        raw["texts"][KEY_ID] = {"title": "点検口そばの草むら", "lines": ["草むらを調べる"]}
    else:
        raw["texts"].pop(KEY_ID, None)
    app.world = WorldData(
        raw,
        app.world.chunk_size,
        app.world.static_visual_max_height,
        app.world.visual_detail_per_chunk,
    )
    app.world.east_site_access_ready = access_ready
    app.model.world = app.world


def draw_week3_key(app, camera):
    """Reuse palette primitives, with a quiet cue only while approaching."""
    from drift_with_me.math3d import Vec3

    if app.work_week != app.map_work_week or app.work_week.month != 6 or app.work_week.number != 3:
        return
    if app.office.site_progress.key_collected:
        return
    x, z = KEY_POSITION
    point = camera.project(Vec3(x, 1, z))
    if point is None:
        return
    pyxel = app.pyxel
    px, py = round(point.x), round(point.y)
    player = app.model.player
    if (player.x - x) ** 2 + (player.z - z) ** 2 <= 72**2:
        pyxel.circb(px, py, 6, 6)
        pyxel.pset(px - 8, py - 2, 7)
    pyxel.circb(px - 2, py, 2, 9)
    pyxel.line(px, py, px + 4, py, 9)
    pyxel.line(px + 3, py, px + 3, py + 2, 9)
    pyxel.rect(px + 4, py - 3, 3, 2, 6)
