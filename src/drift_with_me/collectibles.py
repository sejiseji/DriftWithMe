"""Optional summer keepsakes. No additional story-completion requirements."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass


@dataclass(frozen=True)
class Collectible:
    id: str
    name: str
    description: str
    week: tuple[int, int]
    position: tuple[int, int] | None
    location: str


CATALOG = (
    Collectible(
        "herb_fine",
        "ローズマリー",
        "針のように細い葉。乾かして夏の香りを残そう。",
        (6, 1),
        (456, 568),
        "北側浅瀬へ向かう草地",
    ),
    Collectible(
        "stone_marble",
        "青白マーブルの石",
        "青と白の筋が重なる、なめらかな小石。",
        (6, 2),
        (890, 262),
        "東側水路の岸",
    ),
    Collectible(
        "pinecone",
        "大きな松ぼっくり",
        "手のひらより大きい、よく乾いた松ぼっくり。",
        (6, 3),
        (208, 652),
        "北西の木陰",
    ),
    Collectible(
        "herb_round",
        "スペアミント",
        "幅広い葉の縁がぎざぎざね。乾かして残しておきましょう。",
        (6, 4),
        (300, 430),
        "フジの作業地近くの草地",
    ),
    Collectible(
        "fuji_pot",
        "フジの寄せ植え鉢",
        "手伝いのお礼にもらった、六月の野草の寄せ植え。",
        (7, 1),
        None,
        "既存のフジのお礼会話",
    ),
    Collectible(
        "stone_lavender",
        "淡紫色の結晶原石",
        "淡い紫の小さな結晶が残る、自然の原石。",
        (7, 2),
        (292, 732),
        "北西の調査地点そば",
    ),
    Collectible(
        "sunglasses",
        "ヒューズのサングラス",
        "輪の仕掛けを解いた記念。夏の日差しに似合いそう。",
        (7, 3),
        None,
        "既存の輪パズル報酬",
    ),
    Collectible(
        "winged_seed",
        "羽根付きの種",
        "薄い羽根がついた種。風に運ばれてきたのかな。",
        (7, 4),
        (856, 878),
        "北東公園の園路脇",
    ),
    Collectible(
        "herb_flower",
        "マリーゴールド",
        "黄色や橙色の花。乾かして夏の思い出にしましょう。",
        (8, 1),
        (778, 850),
        "南東の草地",
    ),
    Collectible(
        "stone_honey",
        "蜂蜜色の半透明原石",
        "光を通す蜂蜜色の原石。角を大事に持ち帰ろう。",
        (8, 2),
        (186, 706),
        "北西の木々のそば",
    ),
    Collectible(
        "driftwood",
        "面白い形の流木",
        "雨に洗われた流木。曲がり方が小さな生き物みたい。",
        (8, 3),
        (878, 216),
        "東側水路の岸辺",
    ),
    Collectible(
        "crayon_drawing",
        "クレパスのタコの絵",
        "モリスとルビィからもらった、色鮮やかな夏の絵。",
        (8, 4),
        None,
        "最終巡回でモリス／ルビィに話す",
    ),
)
BY_ID = {item.id: item for item in CATALOG}
PREFIX = "collectible_"


def validate_collectibles(raw):
    if not isinstance(raw, list) or any(type(x) is not str or x not in BY_ID for x in raw):
        raise ValueError("invalid collectible IDs")
    if len(raw) != len(set(raw)):
        raise ValueError("duplicate collectible IDs")
    return set(raw)


def legacy_gifts(offices):
    result = set()
    for office in offices:
        july = getattr(office, "july_progress", None)
        if july is not None and july.souvenir_received:
            result.add("fuji_pot")
        week3 = getattr(office, "week3_progress", None)
        if week3 is not None and week3.rewards.sunglasses_received:
            result.add("sunglasses")
    return result


def owned_collectibles(app):
    offices = dict(getattr(app, "week_office_history", {}))
    if getattr(app, "office", None) is not None:
        offices[getattr(app, "work_week", None)] = app.office
    sites = getattr(app, "east_site_progress", None)
    return set(getattr(sites, "collectibles", ())) | legacy_gifts(offices.values())


class CollectibleMixin:
    def install_collectibles(self):
        if not hasattr(self, "world") or not hasattr(self, "work_week"):
            return
        from drift_with_me.world import WorldData

        week = (self.work_week.month, self.work_week.number)
        owned = owned_collectibles(self)
        wanted = [
            item for item in CATALOG if item.week == week and item.position and item.id not in owned
        ]
        current = {o.id for o in self.world.objects if o.id.startswith(PREFIX)}
        if current == {PREFIX + item.id for item in wanted}:
            return
        raw = deepcopy(self.world.raw)
        raw["objects"] = [o for o in raw["objects"] if not o["id"].startswith(PREFIX)]
        for key in list(raw["texts"]):
            if key.startswith(PREFIX):
                del raw["texts"][key]
        for item in wanted:
            x, z = item.position
            ident = PREFIX + item.id
            raw["objects"].append(
                dict(
                    id=ident,
                    kind="collectible",
                    position=[x, 0, z],
                    solid=False,
                    inspectable=True,
                    half_size=[12, 12],
                    height=8,
                    visual="collection_sparkle",
                    text_key=ident,
                )
            )
            raw["texts"][ident] = dict(title="ひかるもの", lines=["足元の光を調べる"])
        access = getattr(self.world, "east_site_access_ready", False)
        self.world = WorldData(
            raw,
            self.world.chunk_size,
            self.world.static_visual_max_height,
            self.world.visual_detail_per_chunk,
        )
        self.world.east_site_access_ready = access
        self.model.world = self.world

    def claim_collectible(self, ident, *, source="map"):
        from drift_with_me.app import AppScreen
        from drift_with_me.save_state import snapshot

        item = BY_ID.get(ident)
        if item is None or self.screen != AppScreen.PLAY:
            return False
        if ident in owned_collectibles(self):
            return source == "gift"
        if (self.work_week.month, self.work_week.number) != item.week:
            return False
        if source == "map":
            interaction = self.model.interaction
            if (
                not item.position
                or interaction is None
                or interaction.kind != "inspect"
                or interaction.object_id != PREFIX + ident
            ):
                return False
        elif source != "gift" or ident != "crayon_drawing":
            return False
        else:
            dialogue = getattr(self, "patrol_dialogue", None)
            if dialogue is None or dialogue.target_id not in {
                "aug_patrol_morris",
                "aug_patrol_ruby",
            }:
                return False
        before = set(self.east_site_progress.collectibles)
        self.east_site_progress.collectibles.add(ident)
        payload = snapshot(self)
        store = getattr(self, "progress_store", None)
        from drift_with_me.week_debug import TemporaryProgressStore

        wrong_debug_store = getattr(self, "week_debug_active", False) and not isinstance(
            store, TemporaryProgressStore
        )
        if store is None or wrong_debug_store or not store.write(payload):
            self.east_site_progress.collectibles = before
            return False
        self.last_checkpoint = payload
        self.install_collectibles()
        return True

    def begin_collectible_conversation(self, target_id):
        from drift_with_me.field_visit import FieldConversation

        if not target_id.startswith(PREFIX) or target_id[len(PREFIX) :] not in BY_ID:
            return False
        item = BY_ID[target_id[len(PREFIX) :]]
        self.field_conversation = FieldConversation(
            target_id, (("ジャック", item.name), ("ヒューズ", item.description))
        )
        return True

    def advance_collectible_conversation(self):
        from drift_with_me.field_visit import FieldConversation

        c = self.field_conversation
        if c.index + 1 < len(c.lines):
            c.index += 1
        elif self.claim_collectible(c.target_id[len(PREFIX) :]):
            self.process_events(self.model.complete_interaction())
            self.field_conversation = None
            self.camera_controller.cancel_focus()
        else:
            self.field_conversation = FieldConversation(
                c.target_id, (("ジャック", "保存できません。もう一度お試しください。"),)
            )
        return True

    def draw_collectible_notice(self):
        from drift_with_me.app import AppScreen

        if self.screen != AppScreen.PLAY:
            return
        owned = owned_collectibles(self)
        known = getattr(self, "collection_announced", None)
        self.collection_announced = owned
        if known is None:
            return
        added = owned - known
        if added:
            item = BY_ID[sorted(added)[0]]
            self.collection_notice = (
                item.name,
                item.description,
                getattr(self, "presentation_time", 0) + 4,
            )
        notice = getattr(self, "collection_notice", None)
        if notice and getattr(self, "presentation_time", 0) < notice[2]:
            self.draw_panel_frame(self.office_rect(104, 4, 304, 49), fill=1, inner=10)
            self.draw_office_wrapped_lines(self.office_rect(112, 8, 288, 42), notice[:2], 7)

    def open_collection_room(self):
        from drift_with_me.app import AppScreen

        if (
            self.work_week.month != 8
            or self.work_week.number != 4
            or self.office.august_progress.phase != "done"
        ):
            return False
        self.screen = AppScreen.COLLECTION_ROOM
        self.clear_world_input_latches()
        return True

    def begin_ending(self):
        from drift_with_me.ending_playback import begin

        return begin(self)

    def update_ending(self, elapsed):
        from drift_with_me.ending_playback import update

        update(self, elapsed)

    def draw_ending(self):
        from drift_with_me.ending_playback import draw

        draw(self)

    def update_collection_room(self):
        from drift_with_me.app import AppScreen

        if getattr(self, "collection_room_wait_release", False):
            if not self.travel_input_held():
                self.collection_room_wait_release = False
            return

        if self.key_pressed("KEY_ESCAPE", "KEY_X") or self.mouse_pressed_in(
            self.office_rect(3, 210, 40, 23)
        ):
            self.screen = AppScreen.OFFICE
            self.clear_world_input_latches()

    def draw_collection_room(self):
        from drift_with_me.collection_room import draw_room

        draw_room(self, owned_collectibles(self))
        self.draw_office_button(self.office_rect(3, 210, 40, 23), "戻る", 1, text_color=7)
