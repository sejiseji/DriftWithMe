"""Optional August W4 conversations. Preview lines do not author the ending."""

from copy import deepcopy
from dataclasses import dataclass

from drift_with_me.field_visit import FieldConversation
from drift_with_me.week_cycle import WorkWeek
from drift_with_me.world import WorldData


@dataclass(frozen=True)
class PatrolNPC:
    key: str
    name: str
    position: tuple[float, float]
    map_asset: str
    portrait: str
    line: str
    large: bool = False
    map_size: float = 32


NPCS = (
    PatrolNPC(
        "yumesaki",
        "ユメサキ",
        (80, 636),
        "aug_npc_yumesaki",
        "yumesaki_map_knees",
        "今日は木陰の植物を見ています",
        True,
    ),
    PatrolNPC(
        "miyano",
        "ミヤノ",
        (104, 614),
        "aug_npc_miyano",
        "miyano_map_knees",
        "先生と一緒に、記録を取っています！",
        True,
    ),
    PatrolNPC(
        "iwama",
        "イワマ",
        (795, 902),
        "aug_npc_iwama",
        "iwama_bust_normal",
        "今日はここで少し休んどる",
    ),
    PatrolNPC(
        "merrill",
        "メリル",
        (824, 854),
        "aug_npc_merrill",
        "merrill_matte",
        "花を眺めていたところなんです",
    ),
    PatrolNPC(
        "morris",
        "モリス",
        (836, 832),
        "aug_npc_morris",
        "morris_matte",
        "今日は二人で来ています",
        map_size=28,
    ),
    PatrolNPC(
        "ruby",
        "ルビィ",
        (848, 822),
        "aug_npc_ruby",
        "ruby_matte",
        "お花、いっぱいあるね！",
        map_size=24,
    ),
    PatrolNPC(
        "fuji",
        "フジ",
        (214, 362),
        "aug_npc_fuji",
        "fuji_map_knees",
        "花壇の様子を見ていたところだ",
        True,
    ),
    PatrolNPC(
        "ramel",
        "ラメル",
        (480, 280),
        "aug_npc_ramel",
        "nervous_elf_woodsman",
        "今日は岸から様子を見ています",
    ),
    PatrolNPC(
        "hero",
        "旅の勇者",
        (950, 286),
        "aug_npc_hero",
        "smug_blond_hero",
        "今日は水路沿いを歩いていたところだ",
    ),
    PatrolNPC(
        "mina",
        "ミナ",
        (108, 124),
        "aug_npc_mina",
        "succubus_green",
        "こんにちは。少し散歩に来たんです",
    ),
    PatrolNPC(
        "grow", "グロウ", (202, 256), "aug_npc_grow", "tired_gray_oldman", "ここで少し休んでいくよ"
    ),
    PatrolNPC(
        "takanashi",
        "タカナシ",
        (274, 342),
        "aug_npc_takanashi",
        "takanashi_matte",
        "今日はゆっくり歩いています",
    ),
    PatrolNPC(
        "yoake",
        "ヨアケ",
        (286, 454),
        "aug_npc_yoake",
        "yoake_matte",
        "このあたりも、歩いてみようと思って",
    ),
    PatrolNPC(
        "sagan",
        "サガン",
        (394, 450),
        "aug_npc_sagan",
        "sagan_matte",
        "道の様子を見に来たところです",
    ),
    PatrolNPC(
        "ura",
        "ウラ",
        (904, 144),
        "aug_npc_ura",
        "ura_matte",
        "点検口の周りを見ていました。ふたは開けていません",
    ),
)
BY_ID = {"aug_patrol_" + n.key: n for n in NPCS}
# W4-only art aliases; original counter identities and save/dialogue data stay intact.
W4_DIALOGUE_PORTRAITS = {
    "iwama": "w4_iwama_dialogue_normal",
    "merrill": "w4_merrill_dialogue_normal",
    "morris": "w4_morris_dialogue_normal",
    "ruby": "w4_ruby_dialogue_normal",
    "ramel": "w4_ramel_dialogue_normal",
    "hero": "w4_hero_dialogue_normal",
    "mina": "w4_mina_dialogue_normal",
    "grow": "w4_grow_dialogue_normal",
    "takanashi": "w4_takanashi_dialogue_normal",
    "yoake": "w4_yoake_dialogue_normal",
    "sagan": "w4_sagan_dialogue_normal",
    "ura": "w4_ura_dialogue_normal",
}


W4_LARGE_DIALOGUE_PORTRAITS = {
    "fuji": "w4_fuji_dialogue_identity_normal",
    "yumesaki": "w4_yumesaki_dialogue_identity_normal",
    "miyano": "w4_miyano_dialogue_identity_normal",
}


# Optional W4 expression assets; never extend the historical counter expression registry.
W4_DIALOGUE_SMILE_PORTRAITS = {
    "ramel": "w4_ramel_dialogue_smile",
    "hero": "w4_hero_dialogue_smile",
    "mina": "w4_mina_dialogue_smile",
    "grow": "w4_grow_dialogue_smile",
}


W4_BLINK_ORIGINAL_IDS = {
    "ramel": "nervous_elf_woodsman",
    "hero": "smug_blond_hero",
    "mina": "succubus_green",
    "grow": "tired_gray_oldman",
}


def patrol_dialogue_frame(app, key, asset_id):
    original_id = W4_BLINK_ORIGINAL_IDS.get(key)
    if (
        original_id is None
        or asset_id not in {W4_DIALOGUE_PORTRAITS.get(key), W4_DIALOGUE_SMILE_PORTRAITS.get(key)}
        or not asset_id.startswith("w4_")
    ):
        return None
    intervals = (
        app.runtime.raw.get("ui", {})
        .get("office_portrait_blink_interval_frames", {})
        .get(original_id)
    )
    options = {} if intervals is None else {"intervals": tuple(intervals)}
    pose = app.office_portrait_blink_pose(getattr(app, "frame", 0), original_id, **options)
    if asset_id == W4_DIALOGUE_SMILE_PORTRAITS[key]:
        return {None: "open", "half": "half", "closed": "normal"}[pose]
    return "normal" if pose is None else pose


class PatrolMixin:
    def patrol_active(self):
        return getattr(self, "work_week", None) == WorkWeek(8, 4)

    def install_patrol(self):
        if not self.patrol_active() or not hasattr(self, "world"):
            return
        from drift_with_me.northeast_park import install_park_world

        install_park_world(self)
        raw = deepcopy(self.world.raw)
        raw["objects"] = [
            o
            for o in raw["objects"]
            if not o["id"].startswith("aug_patrol_") and o["id"] != "jul_w2_fuji"
        ]
        for obj in raw["objects"]:
            if obj["id"] == "jul_w2_flowerbed":
                obj["inspectable"] = False
        for ident, n in BY_ID.items():
            # Missing art is an explicit build error, never a generic tree/figure fallback.
            if (
                getattr(self, "sprite_assets", None) is not None
                and self.sprite_assets.get(n.map_asset) is None
            ):
                raise ValueError(f"Missing patrol sprite: {n.name} / {n.map_asset}")
            self.model.config.setdefault("assets", {})[n.map_asset + "_asset"] = n.map_asset
            raw["objects"].append(
                dict(
                    id=ident,
                    kind="sprite_prop",
                    position=[*n.position[:1], 0, n.position[1]],
                    visual=n.map_asset,
                    sprite_world_size=[n.map_size, n.map_size],
                    solid=False,
                    inspectable=True,
                    height=n.map_size - 2,
                    text_key=ident,
                )
            )
            raw["texts"][ident] = dict(title=n.name, lines=["声をかける"])
        self.world = self.model.world = WorldData(
            raw,
            self.world.chunk_size,
            self.world.static_visual_max_height,
            self.world.visual_detail_per_chunk,
        )
        # Remove actors only, preserving defeat counters and resources; reloading restores
        # normal actors through reset_scene before this W4-only installation.
        self.model.enemies = []
        self.model.combat_session = None
        self.model.august_recovered = True
        self.model.august_rain = False
        self.patrol_dialogue = None
        self.model.patrol_talking = None
        self.patrol_wait_release = True

    def begin_patrol_target(self, ident):
        if not self.patrol_active() or ident not in BY_ID:
            return False
        n = BY_ID[ident]
        self.model.cancel_interaction()
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        self.model.face_actor_toward(*n.position)
        self.patrol_dialogue = FieldConversation(ident, ((n.name, n.line),), target_speaker=n.name)
        self.patrol_wait_release = True
        self.model.patrol_talking = ident
        self.model.set_sighting_lock(True)
        self.accumulator = 0
        return True

    def update_patrol(self, elapsed):
        from drift_with_me.app import AppScreen

        if not self.patrol_active():
            return False
        if self.screen == AppScreen.PLAY and getattr(self, "patrol_dialogue", None):
            self.clear_world_input_latches()
            self.model.cancel_auto_move()
            self.accumulator = 0
            if self.patrol_wait_release:
                if not self.travel_input_held():
                    self.patrol_wait_release = False
                return True
            if self.key_pressed(
                "KEY_RETURN", "KEY_Z", "KEY_ESCAPE", "KEY_X"
            ) or self.mouse_pressed_in(self.office_rect(40, 126, 432, 100)):
                self.patrol_dialogue = None
                self.model.patrol_talking = None
                self.model.set_sighting_lock(False)
                self.field_input_wait_for_release = True
                self.clear_world_input_latches()
            return True
        if self.screen != AppScreen.OFFICE or self.field_transition or self.week_transition:
            return False
        p = self.office.august_progress
        if p.phase == "office" and (
            self.key_pressed("KEY_F") or self.mouse_pressed_in(self.office_next_week_rect())
        ):
            before = deepcopy(self.office)
            p.phase = "report"
            self.save_august(before)
            return True
        return False

    def draw_patrol_dialogue(self):
        if not self.patrol_active() or not getattr(self, "patrol_dialogue", None):
            return
        c = self.patrol_dialogue
        n = BY_ID[c.target_id]
        if n.large:
            self.draw_field_character_portrait(W4_LARGE_DIALOGUE_PORTRAITS.get(n.key, n.portrait))
        else:
            rect = self.office_rect(40, 48, 74, 74)
            self.draw_panel_frame(rect, fill=0, inner=12)
            portrait = W4_DIALOGUE_PORTRAITS.get(n.key, n.portrait)
            frame_id = patrol_dialogue_frame(self, n.key, portrait)
            options = {} if frame_id is None else {"frame_id": frame_id}
            self.draw_office_portrait(self.office_rect(44, 52, 66, 66), portrait, **options)
        panel = self.office_rect(40, 126, 432, 100)
        self.draw_panel_frame(panel, fill=0, inner=12)
        self.draw_office_text_in_rect(self.office_rect(50, 133, 300, 18), n.name, 12)
        self.draw_office_wrapped_lines(
            self.office_rect(50, 154, 300 if n.large else 400, 48), (n.line,), 7
        )
        self.draw_office_text_in_rect(self.office_rect(356, 204, 96, 16), "閉じる →", 10)


def patrol_pose(model, ident):
    """Brief staggered head glances, feet and world roots never move."""
    if ident not in BY_ID or getattr(model, "patrol_talking", None) == ident:
        return "normal"
    seed = sum((i + 1) * ord(c) for i, c in enumerate(ident))
    phase = (model.world_tick / 60 + seed % 17) % 18
    return "look_left" if 7 <= phase < 8.2 else "look_right" if 15 <= phase < 16.2 else "normal"
