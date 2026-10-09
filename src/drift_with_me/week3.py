"""June week three: a separate confirmation record and ordered office reports."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from drift_with_me import config
from drift_with_me.office import (
    CaseSession,
    CaseState,
    OfficePrototype,
    parse_case_definitions,
    parse_counter_script_definitions,
)

TASK_CASE = "OFF-JUN-W3-SAGAN"
SITE_FACTS = {
    "jun_w2_canal_bank": "route_bank",
    "jun_w2_shade": "route_stone",
    "jun_w2_old_hatch": "hatch_matched",
}
FACTS = frozenset(SITE_FACTS.values())
LABELS = {
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
        ("ジャック", "そこもウラさんに伝えよう。今日は開けない約束だしね"),
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

    def begin(self, target):
        self.pending_completion = None
        if SITE_FACTS[target] in self.facts:
            return (("ジャック", "ここは、さっき確認したとおりだね。"),), 0
        return LINES[target], self.positions.get(target, 0)

    def complete(self, target):
        if target != self.pending_completion or target not in SITE_FACTS:
            return False
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
        if facts != FACTS:
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
        self.current_index = 4 if "hatch_matched" in self.site_progress.facts else 5
        if self.current_index == 5:
            self.sessions[self.cases[4].case_id].state = CaseState.RESOLVED
        self.begin_current_case()
        return True

    def classify(self, classification):
        if self.current_index in (4, 5):
            if self.sessions[TASK_CASE].field_result is None:
                return False
            if self.current_index == 4 and "hatch_matched" not in self.site_progress.facts:
                return False
        return super().classify(classification)

    def advance_case(self):
        index = self.current_index
        if not super().advance_case():
            return False
        if index == 4:
            self.site_progress.reported.add("hatch_matched")
        elif index == 5:
            self.site_progress.reported.update(
                self.site_progress.facts & {"route_bank", "route_stone"}
            )
            if self.site_progress.facts != FACTS or self.site_progress.reported != FACTS:
                self.current_index = 3
                session = self.current_session
                session.state = CaseState.FIELD_CHECK_REQUIRED
                session.field_result = None
                session.dialogue.clear()
                session.active_dialogue_line_count = 0
                session.pending_dialogue_steps.clear()
                self.prepare_field_task()
        return True
