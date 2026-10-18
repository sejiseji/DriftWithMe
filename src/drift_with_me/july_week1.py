"""Authored July week one patrol; later July weeks remain unavailable."""

from copy import deepcopy
from dataclasses import dataclass, field

from drift_with_me.office import (
    CaseState,
    OfficePrototype,
    parse_case_definitions,
    parse_counter_script_definitions,
)
from drift_with_me.world import WorldData

TASK_CASE = "OFF-JUL-W1-PEST"
FUJI_ID = "jul_w1_fuji"
WATER_ID = "jul_w1_water"
PROFESSOR_ID = "jul_w1_yumesaki"
STUDENT_ID = "jul_w1_miyano"
RESEARCHER_MAP_SPRITES = {
    PROFESSOR_ID: "jul_w1_yumesaki_map",
    STUDENT_ID: "jul_w1_miyano_map",
}
TARGET_IDS = frozenset((FUJI_ID, WATER_ID, PROFESSOR_ID, STUDENT_ID))
ENEMY_IDS = frozenset(
    f"july_nudibranch_{kind}_{n}" for kind in ("normal", "abnormal") for n in (1, 2)
)
JULY_FACTS = frozenset(("pest_removed", "materials_checked", "water_checked", "researchers_guided"))
SPEAKERS = {FUJI_ID: "フジ", PROFESSOR_ID: "ユメサキ", STUDENT_ID: "ミヤノ"}
LABELS = {**SPEAKERS, WATER_ID: "水源の流入確認"}
AFTER_CLEAR = (
    ("ジャック", "付近のウミウシは、これで片づいたね。"),
    ("ヒューズ", "ええ。調査に来るお二人を案内しましょう。"),
)
RESEARCHERS = (
    ("ユメサキ", "住民課の方、ですよね。ユメサキです。今日は植物の共生関係を調べに来ました。"),
    ("ミヤノ", "院生のミヤノです。よろしくお願いします！ 巨木の周りを見せていただく予定です。"),
    ("ジャック", "ジャックです。こちらがヒューズ。巨木の周辺と、整備中の区画をご案内します。"),
    ("ヒューズ", "足元の仮ラインは、工事の位置を確かめるためのものです。"),
    ("ジャック", "付近のウミウシは駆除しておきました。調査が終わる頃まで周りを見回っています。"),
    ("ジャック", "もし見かけたら、近づかずに声をかけてください。"),
    ("ユメサキ", "あ、ありがとうございます。では、まず木陰の植物から見てみます。"),
    ("ミヤノ", "了解です。先生、記録は私が取りますね！"),
)


@dataclass
class JulyWeek1Progress:
    defeated: set[str] = field(default_factory=set)
    materials_checked: bool = False
    water_checked: bool = False
    researchers_arrived: bool = False
    researchers_talked: bool = False
    souvenir_received: bool = False
    departed: bool = False
    positions: dict[str, int] = field(default_factory=dict)
    stage: str = "patrol"
    scene_index: int = 0
    pending_completion: str | None = None

    @property
    def cleared(self):
        return self.defeated == ENEMY_IDS

    @property
    def complete(self):
        return (
            self.cleared
            and self.materials_checked
            and self.water_checked
            and self.researchers_talked
        )

    def snapshot(self):
        return {
            "defeated": sorted(self.defeated),
            **{
                name: getattr(self, name)
                for name in (
                    "materials_checked",
                    "water_checked",
                    "researchers_arrived",
                    "researchers_talked",
                    "souvenir_received",
                    "departed",
                )
            },
            "positions": dict(self.positions),
            "stage": self.stage,
            "scene_index": self.scene_index,
        }

    @classmethod
    def from_snapshot(cls, raw):
        expected = set(cls().snapshot())
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("invalid July progress shape")
        defeated = raw["defeated"]
        if not isinstance(defeated, list) or any(type(v) is not str for v in defeated):
            raise ValueError("invalid July enemies")
        if len(set(defeated)) != len(defeated) or not set(defeated) <= ENEMY_IDS:
            raise ValueError("unknown July enemy")
        bools = expected - {"defeated", "positions", "stage", "scene_index"}
        if any(type(raw[k]) is not bool for k in bools):
            raise ValueError("invalid July flags")
        if raw["stage"] not in {
            "patrol",
            "after_clear",
            "arrival_fade",
            "researchers",
            "return_pending",
        }:
            raise ValueError("invalid July stage")
        if type(raw["scene_index"]) is not int or not 0 <= raw["scene_index"] < len(RESEARCHERS):
            raise ValueError("invalid July scene index")
        positions = raw["positions"]
        if not isinstance(positions, dict) or any(
            k not in TARGET_IDS or type(v) is not int or not 0 <= v < 8
            for k, v in positions.items()
        ):
            raise ValueError("invalid July conversation cursor")
        obj = cls(**{k: raw[k] for k in expected - {"defeated"}}, defeated=set(defeated))
        if obj.stage == "after_clear" and obj.scene_index >= len(AFTER_CLEAR):
            raise ValueError("invalid after-clear cursor")
        if obj.stage == "return_pending" and not obj.complete:
            raise ValueError("return without completion")
        if obj.researchers_talked and not obj.researchers_arrived:
            raise ValueError("researchers not arrived")
        if obj.researchers_arrived and not obj.cleared:
            raise ValueError("researchers before clearance")
        if (
            obj.stage in {"after_clear", "arrival_fade", "researchers", "return_pending"}
            and not obj.cleared
        ):
            raise ValueError("scene before clearance")
        # Re-entering a fade starts a fresh fade; no saved transient elapsed/camera state.
        if obj.stage == "arrival_fade" and obj.researchers_arrived:
            obj.stage, obj.scene_index = "researchers", 0
        if obj.stage == "researchers" and not obj.researchers_arrived:
            raise ValueError("missing researchers")
        return obj

    def lines_for(self, target):
        if target == FUJI_ID:
            if self.materials_checked:
                return (("フジ", "追加の資材はない。計画どおり進めているよ。"),)
            lines = (
                ("ジャック", "追加の資材は出ていますか？ サガンに伝えます。"),
                ("フジ", "今のところ追加はない。この計画で進められる。"),
            )
            if self.souvenir_received:
                return lines + (("ジャック", "わかりました。戻って伝えます。"),)
            return lines + (
                ("フジ", "6月の野草の寄せ植え鉢だ。手伝ってくれたお礼に、持っていってくれ。"),
                ("ジャック", "ありがとうございます。大事にします。"),
            )
        if target == WATER_ID:
            if self.water_checked:
                return (("ジャック", "水源の様子は変わらず、安定しているね。"),)
            return (
                ("ジャック", "新たな流入はないね。水の様子も落ち着いている。"),
                ("ヒューズ", "ええ。そのままサガンに伝えましょう。"),
            )
        return (
            (SPEAKERS[target], "調査を続けています。ご案内、ありがとうございます。"),
            ("ジャック", "何かあれば声をかけてください。近くを見回っています。"),
        )

    def begin(self, target):
        self.pending_completion = None
        lines = self.lines_for(target)
        return lines, min(self.positions.get(target, 0), len(lines) - 1)

    def complete_target(self, target):
        if target != self.pending_completion or target not in TARGET_IDS:
            return False
        self.pending_completion = None
        self.positions.pop(target, None)
        if target == FUJI_ID:
            self.materials_checked = self.souvenir_received = True
        elif target == WATER_ID:
            self.water_checked = True
        return True

    def travel_lines(self, direction):
        if direction == "out":
            return (
                ("ジャック", "巨木の周りを防除して、フジさんと水源も確認しよう。"),
                ("ヒューズ", "ええ。終わった所は、もう一度やり直さなくていいわ。"),
            )
        return (
            (
                "ジャック",
                "見回りもひと区切り。確認したことを、戻って伝えよう。"
                if self.complete
                else "いったん帰庁しよう。残りは、また出てきて確認するね。",
            ),
            (
                "ヒューズ",
                "ええ。調査の方も落ち着いていたわね。"
                if self.complete
                else "ええ。確認済みのことは、ちゃんと記録しておきましょう。",
            ),
        )


def office_data():
    case = {
        "case_id": TASK_CASE,
        "title": "巨木周辺の防除と調査案内",
        "visitor": {
            "id": "sagan",
            "name": "サガン",
            "kind": "建設課",
            "portrait_id": "sagan_matte",
        },
        "initial_purpose": "住民課の防除当番と現地確認",
        "document_status": "測量・仮ラインあり",
        "questions": [
            {
                "id": "talk",
                "label": "予定を確認する",
                "jack": "住民課の防除を済ませて、当日の調査をご案内します。",
                "reply": (
                    "助かる。今日は防除と調査案内に加え、フジの追加資材と水源の確認までが担当だ。"
                    "発注の判断はこちらでする。"
                ),
                "jack_speaker": "ジャック",
                "reply_speaker": "サガン",
                "memo": [],
            }
        ],
        "expected_classification": "FIELD_CHECK",
        "field_task": {
            "task_id": "FIELD-JUL-W1-PEST",
            "location_id": "giant_tree_patrol",
            "title": "巨木周辺の防除",
            "objective": "ウミウシ4体を駆除し、研究者を案内。フジと水源を確認して帰庁",
            "completion_condition_id": "july1_patrol_complete",
        },
    }
    opening = (
        ("上司", "ジャック、8月末に夏休み取るんじゃろ。申請、早めに出しとけよ。"),
        (
            "ジャック",
            "はい。ヒューズと夏の担当をやり切って、一人前として任せてもらいたいです。休暇の申請も早めに出します。",
        ),
        (
            "サガン",
            "今日はユメサキ先生と院生のミヤノさんが、巨木周辺の植物の共生関係を調べる予定だ。",
        ),
        (
            "サガン",
            "先に付近を駆除しておいてくれ。現地は研究や観光の人も普通に出入りする場所だからな。",
        ),
    )
    script = {
        "case_id": TASK_CASE,
        "opening": [
            {"turn_id": f"july_open_{i}", "jack": text, "reply": "", "jack_speaker": speaker}
            for i, (speaker, text) in enumerate(opening)
        ],
        "after_question": {"talk": []},
        "resolution": {
            "classification": "FIELD_CHECK",
            "requires_completed_questions": ["talk"],
            "if_requirements_missing": "当日の予定を確認しましょう。",
            "turns": [],
        },
        "feedback": {"FIELD_CHECK": "防除と現地確認に出動できます。"},
    }
    return {"version": "0.1.0", "cases": [case], "counter_scripts": {"cases": [script]}}


class JulyWeek1Office(OfficePrototype):
    def __init__(self):
        raw = office_data()
        cases = parse_case_definitions(raw)
        super().__init__(cases, parse_counter_script_definitions(raw["counter_scripts"], cases))
        self.july_progress = JulyWeek1Progress()

    def complete_field_task(self, result):
        task, session = self.active_field_task, self.current_session
        if (
            task is None
            or session is None
            or session.state != CaseState.FIELD_ACTIVE
            or result.task_id != task.task_id
            or result.case_id != TASK_CASE
            or result.result_code != "JULY1_COMPLETED"
            or set(result.discovered_fact_ids) != JULY_FACTS
            or not self.july_progress.complete
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


def researcher_map_visual(app, target):
    """Activate only a supplied, registered map asset; never substitute a portrait."""
    asset_id = RESEARCHER_MAP_SPRITES[target]
    assets = getattr(app, "sprite_assets", None)
    asset = (
        assets.get(asset_id) if assets is not None and getattr(assets, "enabled", False) else None
    )
    if asset is not None:
        definition = asset.definition
        if (
            (definition.hex_width, definition.hex_height) == (32, 32)
            and tuple(definition.anchor_px) == (16, 32)
            and tuple(definition.world_size) == (32, 32)
            and definition.colkey == 0
            and definition.projection_mode == "upright_height_billboard_v1"
        ):
            app.model.config.setdefault("assets", {})[f"{asset_id}_asset"] = asset_id
            return "sprite_prop", asset_id
    return "july_placeholder", target


def install_july_world(app, *, enabled=True, combat=False):
    if not hasattr(app, "world") and not enabled:
        return
    from drift_with_me.july_construction import PREFIX, build_layout

    raw = deepcopy(app.world.raw)
    raw["objects"] = [
        o for o in raw["objects"] if o["id"] not in TARGET_IDS and not o["id"].startswith(PREFIX)
    ]
    app.model.july_construction = None
    if enabled:
        app.model.july_construction, colliders = build_layout()
        raw["objects"].extend(colliders)
    progress = getattr(app.office, "july_progress", None)
    positions = {FUJI_ID: (288, 384), WATER_ID: (928, 144)} if enabled else {}
    if enabled and progress and progress.researchers_arrived:
        positions.update({PROFESSOR_ID: (580, 480), STUDENT_ID: (620, 488)})
    for target, (x, z) in positions.items():
        kind, visual = (
            ("sprite_prop", "jun_w4_fuji") if target == FUJI_ID else ("july_placeholder", target)
        )
        if target in RESEARCHER_MAP_SPRITES:
            kind, visual = researcher_map_visual(app, target)
        raw["objects"].append(
            {
                "id": target,
                "kind": kind,
                "position": [x, 0, z],
                "visual": visual,
                "sprite_world_size": [32, 32],
                "solid": False,
                "inspectable": True,
                "height": 24,
                "text_key": target,
            }
        )
        raw["texts"][target] = {
            "title": LABELS[target],
            "lines": ["声をかける" if target in SPEAKERS else "水源を確認する"],
        }
    app.world = WorldData(
        raw,
        app.world.chunk_size,
        app.world.static_visual_max_height,
        app.world.visual_detail_per_chunk,
    )
    app.model.world = app.world
    if combat:
        from drift_with_me.july_combat import configure_july_enemies

        configure_july_enemies(app.model, progress.defeated)
    elif not enabled:
        from drift_with_me.july_combat import clear_july_enemies

        clear_july_enemies(app.model)
