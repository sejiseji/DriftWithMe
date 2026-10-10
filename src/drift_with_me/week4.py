"""June's fourth week: permitted seedlings, carried separately from handed over."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from drift_with_me import config
from drift_with_me.office import (
    CaseState,
    OfficePrototype,
    parse_case_definitions,
    parse_counter_script_definitions,
)
from drift_with_me.world import WorldData

TASK_CASE = "OFF-JUN-W4-FUJI"
FUJI_ID = "jun_w4_fuji"
FLOWER_LABELS = {
    "jun_w4_north": "北：白い小花の房",
    "jun_w4_east": "東：黄色い丸い花",
    "jun_w4_south": "南：赤橙の星形の花",
    "jun_w4_west": "西：紫の穂状の花",
    "jun_w4_tree": "巨木近く：青い釣鐘形の花",
}
FLOWER_IDS = frozenset(FLOWER_LABELS)
TARGET_IDS = FLOWER_IDS | {FUJI_ID}
FLOWER_LINES = {
    "jun_w4_north": (
        ("ジャック", "小さな花が、ひとまとまりになってる"),
        ("ヒューズ", "印はその隣の小株ね。根元から、そっと"),
    ),
    "jun_w4_east": (
        ("ジャック", "丸いなあ。遠くからでも見つけやすかった"),
        ("ヒューズ", "花壇でも、いい目印になりそうね"),
    ),
    "jun_w4_south": (
        ("ジャック", "星みたいな形だね。こっちにも印がある"),
        ("ヒューズ", "ええ。その小さな株なら、土ごと運べそうね"),
    ),
    "jun_w4_west": (
        ("ジャック", "風が吹くと、順番に揺れるんだ"),
        ("ヒューズ", "花壇でも、こんなふうに揺れるといいわね"),
    ),
    "jun_w4_tree": (
        ("ジャック", "木陰にも咲いてる。小さな鐘みたい"),
        ("ヒューズ", "ここが好きなのね。木陰にあったことも、フジさんに伝えましょう"),
    ),
}
INTRO = (
    ("ジャック", "フジさん。何かお手伝いできることはありますか？"),
    ("フジ", "助かる。こちらは測量を進めたい。花を集めてもらえるか"),
    ("ジャック", "花、ですか？"),
    ("フジ", "花壇も作る。広く、自由に任せると言われていてね。"),
    ("フジ", "この辺りの野草を中心に、寄せ植えにしたい"),
    ("ジャック", "ここに咲いている花を使うんですね"),
    ("フジ", "ああ。必要なのは5種類。北、東、南、西、それから巨木の近くだ"),
    ("フジ", "ここは保護区だ。採取の許可を受けた株に印をつけてある。"),
    ("フジ", "その中から、種類ごとに小さな株を1株ずつ"),
    ("フジ", "根を傷めんように、土をつけたまま頼む"),
    ("ジャック", "印のある小株を、1種類につき1株ですね。土をつけたまま持ってきます"),
    ("フジ", "集まった分から持ってきてくれていい。植えるまではこちらで預かる"),
)
HANDOFF = (
    ("ジャック", "こちらを集めてきました。確認をお願いします"),
    ("フジ", "……ああ、これでいい。預かろう"),
)
FINISH = (
    ("フジ", "これで5種類、そろった。ありがとう。助かったよ"),
    ("ジャック", "青い釣鐘形の花は、巨木の木陰に咲いていました"),
    ("フジ", "……そうか。植える場所も、日陰を選んでやろう"),
    ("ジャック", "花壇になるのが楽しみです"),
    ("フジ", "ああ。まずは、ちゃんと根づかせないとな"),
)
WORLD_POSITIONS = {
    FUJI_ID: (288, 384),
    "jun_w4_north": (208, 256),
    "jun_w4_east": (576, 480),
    "jun_w4_south": (416, 624),
    "jun_w4_west": (176, 416),
    "jun_w4_tree": (624, 544),
}


@dataclass
class Week4Progress:
    instructed: bool = False
    carried: set[str] = field(default_factory=set)
    delivered: set[str] = field(default_factory=set)
    positions: dict[str, int] = field(default_factory=dict)
    pending_completion: str | None = None
    pending_delivery: frozenset[str] | None = None
    departed: bool = False

    @property
    def collected(self):
        return self.carried | self.delivered

    @property
    def complete(self):
        return self.delivered == FLOWER_IDS

    def lines_for(self, target):
        if target == FUJI_ID:
            if not self.instructed:
                return INTRO
            if self.carried:
                return HANDOFF + (
                    FINISH
                    if self.collected == FLOWER_IDS
                    else (("フジ", "残りも、同じように頼む"), ("ジャック", "はい。確認してきます"))
                )
            if self.complete:
                return (("フジ", "花は預かっている。根づくまでは、こちらで見ておくよ"),)
            return (
                ("ジャック", "まだ集めているところです"),
                ("フジ", "ああ。印のある小株だけでいい。頼む"),
            )
        if not self.instructed:
            return (("ジャック", "まずはフジさんに声をかけよう。採るのは、話を聞いてからだね"),)
        if target in self.collected:
            return (("ジャック", "必要な分は採った。残りはここで育ってもらおう"),)
        return FLOWER_LINES[target] + (
            ("ジャック", "印のある移植用の小株だ。土ごと、1株だけ採ろうか"),
        )

    def begin(self, target):
        self.pending_completion = None
        self.pending_delivery = (
            frozenset(self.carried) if target == FUJI_ID and self.instructed else None
        )
        lines = self.lines_for(target)
        return lines, min(self.positions.get(target, 0), len(lines) - 1)

    def complete_target(self, target):
        if target not in TARGET_IDS or target != self.pending_completion:
            return False
        self.pending_completion = None
        self.positions.pop(target, None)
        if target == FUJI_ID:
            if not self.instructed:
                self.instructed = True
                return True
            if self.pending_delivery is None or self.pending_delivery != self.carried:
                return False
            self.delivered.update(self.pending_delivery)
            self.carried.clear()
            self.pending_delivery = None
            return True
        if not self.instructed or target in self.collected:
            return False
        self.carried.add(target)
        return True

    def travel_lines(self, direction):
        if direction == "out":
            if not self.departed:
                return (
                    ("ジャック", "フジさん、もう測量を始めてるね"),
                    ("ヒューズ", "声をかけてみましょう。今なら手を借りたいことがあるかも"),
                )
            if self.collected == FLOWER_IDS:
                return (
                    ("ジャック", "あとは、手元の花をフジさんに渡せばいいね"),
                    ("ヒューズ", "ええ。待たせているし、先に届けましょう"),
                )
            return (
                ("ジャック", "さて、残りの花を探そう"),
                ("ヒューズ", "ええ。まだ見ていない場所から回りましょう"),
            )
        if self.complete:
            return (
                ("ジャック", "5種類とも渡せたね。今日はここまで"),
                ("ヒューズ", "ええ。どんな花壇になるか、楽しみが増えたわね"),
            )
        if self.collected == FLOWER_IDS:
            return (
                ("ジャック", "花はそろったけど、いったん戻らないと"),
                ("ヒューズ", "ええ。次に来たら、フジさんに届けましょう"),
            )
        return (
            ("ジャック", "いったん戻ろう。残りはまた来たときに"),
            ("ヒューズ", "ええ。慌てずに、続きはあとにしましょう"),
        )


class Week4Office(OfficePrototype):
    def __init__(self):
        raw = config.load_data_json("office_week4.json")
        cases = parse_case_definitions(raw)
        super().__init__(cases, parse_counter_script_definitions(raw["counter_scripts"], cases))
        self.plant_progress = Week4Progress()

    def complete_field_task(self, result):
        task, session = self.active_field_task, self.current_session
        if (
            task is None
            or session is None
            or session.state != CaseState.FIELD_ACTIVE
            or result.task_id != task.task_id
            or result.case_id != TASK_CASE
            or result.result_code != "WEEK4_DELIVERED"
            or set(result.discovered_fact_ids) != FLOWER_IDS
            or not self.plant_progress.complete
        ):
            return False
        session.field_result = result
        session.state = CaseState.RESOLVED
        session.pending_dialogue_steps.clear()
        session.dialogue.clear()
        session.active_dialogue_line_count = 0
        self.active_field_task = None
        self.current_index = len(self.cases)
        return True


def install_week4_world(app, *, enabled=True):
    """Add only non-solid W4 props; keep enemies, collisions and shared world facts."""
    if not enabled and not any(o.id in TARGET_IDS for o in app.world.objects):
        return
    raw = deepcopy(app.world.raw)
    raw["objects"] = [o for o in raw["objects"] if o["id"] not in TARGET_IDS]
    for target, (x, z) in WORLD_POSITIONS.items() if enabled else ():
        raw["objects"].append(
            {
                "id": target,
                "kind": "sprite_prop",
                "position": [x, 0, z],
                "visual": target,
                "solid": False,
                "inspectable": True,
                "height": 16,
                "sprite_world_size": [32, 32] if target == FUJI_ID else [16, 16],
                "text_key": target,
            }
        )
        raw["texts"][target] = {
            "title": "フジ" if target == FUJI_ID else FLOWER_LABELS[target],
            "lines": ["声をかける" if target == FUJI_ID else "印のある小株を確かめる"],
        }
    app.world = WorldData(
        raw,
        app.world.chunk_size,
        app.world.static_visual_max_height,
        app.world.visual_detail_per_chunk,
    )
    app.model.world = app.world
