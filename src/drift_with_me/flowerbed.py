"""Five fixed garden plots: transactional editing and persistent map arrangement."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field, replace
from math import hypot

from drift_with_me.math3d import AffineCameraState, Vec3
from drift_with_me.office import OfficePrototype
from drift_with_me.week_cycle import WorkWeek
from drift_with_me.world import WorldData

FLOWERS = (
    ("jun_w4_north", "白い小花"),
    ("jun_w4_east", "黄色い丸花"),
    ("jun_w4_south", "赤橙の星花"),
    ("jun_w4_west", "紫の穂花"),
    ("jun_w4_tree", "青い釣鐘"),
)
FLOWER_IDS = tuple(ident for ident, _ in FLOWERS)
BED_ID = "jul_w2_flowerbed"
FUJI_ID = "jul_w2_fuji"
BED_CENTER = (184, 382)


def validate_order(raw):
    if (
        not isinstance(raw, (tuple, list))
        or not (
            len(raw) == 0
            or len(raw) == 5
            and all(isinstance(v, str) for v in raw)
            and set(raw) == set(FLOWER_IDS)
        )
        or any(not isinstance(v, str) for v in raw)
    ):
        raise ValueError("invalid flowerbed order")
    return tuple(raw)


class FlowerbedPrototypeOffice(OfficePrototype):
    """No counter story is authored for this isolated July week2 prototype."""

    def __init__(self):
        self.cases = ()
        self.sessions = {}
        self.counter_scripts = {}
        self.current_index = 0
        self.active_field_task = None


class FlowerbedLayoutStore:
    key = "driftwithme.flowerbed.prototype.v1"

    def __init__(self, backend=None):
        from drift_with_me.save_state import ProgressStore

        self.backend = backend if backend is not None else ProgressStore()

    def load(self):
        return self.load_state()[0]

    def load_state(self):
        from drift_with_me.flowerbed_visit import FlowerbedVisit

        try:
            backend = self.backend
            if not backend.available:
                return (), FlowerbedVisit()
            if backend.browser is not None:
                raw = backend.browser.getItem(self.key)
            else:
                path = backend.path.with_name("flowerbed-prototype.json")
                raw = path.read_text(encoding="utf-8") if path.exists() else None
            if not raw or not isinstance(raw, str) or len(raw) > 2048:
                return (), FlowerbedVisit()
            record = json.loads(raw)
            if type(record.get("version")) is not int:
                raise ValueError("invalid garden record")
            order = validate_order(record["order"])
            if record["version"] == 1 and set(record) == {"version", "order"}:
                return order, FlowerbedVisit()
            if record["version"] != 2 or set(record) != {"version", "order", "visit"}:
                raise ValueError("invalid garden record")
            visit = FlowerbedVisit.restore(record["visit"])
            if visit.stage in {"thanks", "complete"} and not order:
                raise ValueError("unplanted garden completion")
            return order, visit
        except Exception:
            return (), FlowerbedVisit()

    def write(self, order):
        return self.write_state(order, self.load_state()[1])

    def write_state(self, order, visit):
        from drift_with_me.flowerbed_visit import FlowerbedVisit

        try:
            order = validate_order(order)
            visit = FlowerbedVisit.restore(visit.snapshot())
            if visit.stage in {"thanks", "complete"} and not order:
                return False
            backend = self.backend
            if not backend.available:
                return False
            raw = json.dumps({"version": 2, "order": order, "visit": visit.snapshot()})
            if backend.browser is not None:
                backend.browser.setItem(self.key, raw)
            else:
                path = backend.path.with_name("flowerbed-prototype.json")
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".tmp")
                temporary.write_text(raw, encoding="utf-8")
                temporary.replace(path)
            return True
        except Exception:
            return False


@dataclass
class FlowerbedEditor:
    draft: list[str] = field(default_factory=list)
    wait_release: bool = True
    error: str = ""

    @property
    def confirming(self):
        return len(self.draft) == 5

    def choose(self, ident):
        if ident not in FLOWER_IDS or ident in self.draft or self.confirming:
            return False
        self.draft.append(ident)
        self.error = ""
        return True

    def undo(self):
        if self.draft:
            self.draft.pop()
        self.error = ""

    def restart(self):
        self.draft.clear()
        self.error = ""


def install_flowerbed_world(app):
    """Remove old prototype objects on week changes, keep committed map layout."""
    if not hasattr(app, "world"):
        return
    raw = deepcopy(app.world.raw)
    raw["objects"] = [o for o in raw["objects"] if not o["id"].startswith("jul_w2_")]
    active = getattr(app, "work_week", WorkWeek()).month >= 7 and (
        app.work_week.month > 7 or app.work_week.number >= 2
    )
    app.model.flowerbed_visible = active
    order = validate_order(getattr(app.east_site_progress, "flowerbed_order", ()))
    app.model.flowerbed_order = order if active else ()
    if active:
        raw["objects"].extend(
            [
                {
                    "id": BED_ID,
                    "kind": "construction_collision",
                    "position": [184, 0, 400],
                    "inspectable": True,
                    "solid": False,
                    "height": 4,
                },
                {
                    "id": FUJI_ID,
                    "kind": "sprite_prop",
                    "visual": "jun_w4_fuji",
                    "position": [240, 0, 398],
                    "sprite_world_size": [32, 32],
                    "inspectable": True,
                    "solid": False,
                    "height": 24,
                },
            ]
        )
    app.world = WorldData(
        raw,
        app.world.chunk_size,
        app.world.static_visual_max_height,
        app.world.visual_detail_per_chunk,
    )
    app.model.world = app.world
    from drift_with_me.northeast_park import install_park_world

    install_park_world(app)
    from drift_with_me.july_week2 import install_week2_world

    install_week2_world(app)
    from drift_with_me.july_week3 import install_week3_world

    install_week3_world(app)
    from drift_with_me.july_week4 import install_week4_world

    install_week4_world(app)


def draw_flowerbed_ground(renderer, model, camera):
    if not getattr(model, "flowerbed_visible", False):
        return
    renderer.draw_ground_rect(camera, (138, 363, 230, 399), 13)
    for i in range(5):
        x = 140 + i * 18
        renderer.draw_ground_rect(camera, (x, 365, x + 16, 397), 4)


def flowerbed_draw_commands(renderer, model, camera):
    from drift_with_me.garden_props_preview import GardenProp, garden_preview_draw_commands
    from drift_with_me.july_construction import ConstructionLayout

    draft = getattr(model, "flowerbed_draft", None)
    order = tuple(draft) if draft is not None else getattr(model, "flowerbed_order", ())
    if not getattr(model, "flowerbed_visible", False) or not order:
        return []
    props = tuple(
        GardenProp(
            ident,
            144 + i * 18 + column * 8,
            366 + row * 9,
            f"flowerbed:{i}:{column}:{row}",
            world_scale=1.15,
        )
        for i, ident in enumerate(order)
        for column in range(2)
        for row in range(3)
    )
    return garden_preview_draw_commands(renderer, model, camera, ConstructionLayout(props, ()))


class FlowerbedMixin:
    def flowerbed_rects(self):
        return {
            **{
                ident: self.office_rect(16 + i * 98, 130, 88, 48)
                for i, (ident, _) in enumerate(FLOWERS)
            },
            "undo": self.office_rect(16, 184, 144, 48),
            "cancel": self.office_rect(352, 184, 144, 48),
            "yes": self.office_rect(16, 184, 230, 48),
            "no": self.office_rect(266, 184, 230, 48),
        }

    def flowerbed_entry_rect(self):
        return self.office_rect(8, 120, 144, 54)

    def flowerbed_entry_available(self):
        if getattr(self, "patrol_active", lambda: False)():
            return False
        from drift_with_me.app import AppScreen

        return (
            getattr(self.model, "flowerbed_visible", False)
            and self.screen == AppScreen.PLAY
            and self.model.interaction is None
            and getattr(self, "flowerbed_dialogue", None) is None
            and self.model.combat_session is None
            and not self.model.danger_blocks_interaction()
            and self.field_transition is None
            and self.week_transition is None
            and hypot(self.model.player.x - BED_CENTER[0], self.model.player.z - BED_CENTER[1]) < 90
        )

    def start_flowerbed_editor(self):
        if (
            not getattr(self.model, "flowerbed_visible", False)
            or self.model.combat_session
            or self.model.danger_blocks_interaction()
        ):
            return False
        self.flowerbed_editor = FlowerbedEditor()
        self.model.flowerbed_draft = self.flowerbed_editor.draft
        self.flowerbed_camera_before = self.camera()
        self.model.cancel_auto_move()
        self.clear_world_input_latches()
        self.map_objective_open = False
        return True

    def close_flowerbed_editor(self):
        self.flowerbed_editor = None
        self.model.flowerbed_draft = None
        self.flowerbed_visit_editing = False
        self.flowerbed_input_wait_release = True
        self.camera_controller.current = self.flowerbed_camera_before
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        self.previous_time = None

    def confirm_flowerbed(self):
        editor = self.flowerbed_editor
        if not editor.confirming:
            return False
        if getattr(self, "flowerbed_visit_editing", False):
            return self.confirm_flowerbed_visit()
        previous = self.east_site_progress.flowerbed_order
        self.east_site_progress.flowerbed_order = validate_order(editor.draft)
        if getattr(self, "week_debug_active", False):
            if not self.flowerbed_layout_store.write(self.east_site_progress.flowerbed_order):
                self.east_site_progress.flowerbed_order = previous
                editor.error = "保存できません。再試行するか、キャンセルしてください。"
                return False
        else:
            from drift_with_me.save_state import snapshot

            store = getattr(self, "progress_store", None)
            if store is None or not store.write(snapshot(self)):
                self.east_site_progress.flowerbed_order = previous
                editor.error = "保存できません。再試行するか、キャンセルしてください。"
                return False
            self.last_checkpoint = snapshot(self)
        self.model.flowerbed_order = self.east_site_progress.flowerbed_order
        self.close_flowerbed_editor()
        return True

    def update_flowerbed_modal(self):
        if getattr(self, "flowerbed_dialogue", None) is not None:
            return self.update_flowerbed_visit_dialogue()
        editor = getattr(self, "flowerbed_editor", None)
        if getattr(self, "flowerbed_input_wait_release", False):
            if not self.travel_input_held():
                self.flowerbed_input_wait_release = False
            return True
        if editor is None:
            return False
        if editor.wait_release:
            if not self.travel_input_held():
                editor.wait_release = False
            return True
        if self.key_pressed("KEY_ESCAPE") or self.key_pressed("KEY_X"):
            self.close_flowerbed_editor()
            return True
        rects = self.flowerbed_rects()
        if editor.confirming:
            if self.mouse_pressed_in(rects["yes"]):
                self.confirm_flowerbed()
            elif self.mouse_pressed_in(rects["no"]):
                editor.restart()
            return True
        else:
            for ident, _ in FLOWERS:
                if self.mouse_pressed_in(rects[ident]):
                    editor.choose(ident)
                    break
        if self.flowerbed_editor is not None:
            if self.mouse_pressed_in(rects["undo"]) and not editor.confirming:
                editor.undo()
            elif self.mouse_pressed_in(rects["cancel"]) and not editor.confirming:
                self.close_flowerbed_editor()
        return True

    def update_flowerbed_entry(self):
        if self.flowerbed_entry_available() and self.mouse_pressed_in(self.flowerbed_entry_rect()):
            if getattr(self, "week4_active", lambda: False)():
                self.begin_week4_target("fuji")
                return True
            if getattr(self, "week3_active", lambda: False)():
                return self.begin_week3_target("fuji")
            return self.start_flowerbed_visit()
        return False

    def draw_flowerbed_entry(self):
        if self.flowerbed_entry_available():
            self.draw_flowerbed_button(self.flowerbed_entry_rect(), "フジと話す")
            self.draw_office_text_in_rect(
                self.office_rect(8, 174, 144, 24),
                "花壇配置済み" if self.flowerbed_visit_state().complete else "花壇の並びを確認",
                10,
                align="center",
            )

    def draw_flowerbed_button(self, rect, text, selected=False, disabled=False):
        self.pyxel.rect(
            rect.x, rect.y, rect.width, rect.height, 1 if disabled else 3 if selected else 5
        )
        self.pyxel.rectb(rect.x, rect.y, rect.width, rect.height, 13)
        self.draw_office_text_in_rect(rect, text, 13 if disabled else 7, align="center")

    def draw_flowerbed_sprite(self, ident, rect, scale=1.8):
        asset = self.sprite_assets.get(ident)
        if asset is None:
            return
        frame = asset.frame()
        scale *= rect.width / 88
        # Pyxel scales around the source-frame center.
        self.pyxel.blt(
            rect.x + rect.width / 2 - frame.width / 2,
            rect.y + rect.height / 2 - frame.height / 2,
            frame.image,
            frame.u,
            frame.v,
            frame.width,
            frame.height,
            colkey=asset.definition.colkey,
            scale=scale,
        )

    def flowerbed_closeup_camera(self):
        # The same calibrated world projection, with a local framing/zoom only.
        camera = self.scene_camera(self.flowerbed_camera_before)
        common = dict(target=Vec3(BED_CENTER[0], 0, BED_CENTER[1]), anchor_x=0.5, anchor_y=0.35)
        if isinstance(camera, AffineCameraState):
            return replace(
                camera,
                **common,
                zoom=2.0,
                distance=float(self.runtime.raw["camera"]["base_distance"]) / 2.0,
                fx_offset_x=0,
                fx_offset_y=0,
            )
        return replace(
            camera, **common, distance=float(self.runtime.raw["camera"]["base_distance"]) / 2.0
        )

    def draw_flowerbed_editor(self):
        editor = self.flowerbed_editor
        camera = self.flowerbed_closeup_camera()
        self.renderer.draw_scene(
            self.model,
            camera,
            self.presentation_time,
            False,
            self.effects,
            exploration_markers=False,
        )
        # Numbers label the actual ground plots, never a second diagram.
        for i in range(5):
            point = camera.project(Vec3(148 + i * 18, 0, 392))
            if point is not None:
                self.pyxel.text(round(point.x) - 2, round(point.y), str(i + 1), 7)
        header = self.office_rect(0, 0, 512, 20)
        self.pyxel.rect(header.x, header.y, header.width, header.height, 1)
        title = (
            "この並びでいい？" if editor.confirming else "フジ：下地はできた。6月の花を並べてくれ。"
        )
        self.draw_office_text_in_rect(header, title, 7, align="center")
        panel = self.office_rect(0, 126, 512, 110)
        self.pyxel.rect(panel.x, panel.y, panel.width, panel.height, 1)
        rects = self.flowerbed_rects()
        if editor.confirming:
            self.draw_office_text_in_rect(
                self.office_rect(16, 130, 480, 48),
                editor.error or "はいで確定・保存。いいえで選び直します。",
                10,
                align="center",
            )
            self.draw_flowerbed_button(rects["yes"], "はい・確定")
            self.draw_flowerbed_button(rects["no"], "いいえ・選び直す")
        else:
            for ident, label in FLOWERS:
                selected = ident in editor.draft
                self.draw_flowerbed_button(rects[ident], "", selected=selected)
                icon = self.office_rect(16 + FLOWER_IDS.index(ident) * 98, 130, 88, 28)
                self.draw_flowerbed_sprite(ident, icon, scale=1.3)
                text = f"{editor.draft.index(ident) + 1} 選択済" if selected else label
                r = rects[ident]
                self.draw_office_text_in_rect(
                    type(r)(r.x, r.y + r.height * 0.6, r.width, r.height * 0.4),
                    text,
                    7,
                    align="center",
                )
            self.draw_flowerbed_button(rects["undo"], "ひとつ戻す", disabled=not editor.draft)
            self.draw_flowerbed_button(rects["cancel"], "キャンセル")
            self.draw_office_text_in_rect(
                self.office_rect(164, 184, 184, 48),
                f"選択 {len(editor.draft)}/5・未確定",
                10,
                align="center",
            )
