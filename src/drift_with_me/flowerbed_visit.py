"""The authored July week2 field fragment; no counter day or investigation invented."""

from dataclasses import dataclass, replace

from drift_with_me.field_visit import FieldConversation

REQUEST = (
    ("フジ", "花壇の下地ができた。今週中に5区画を仕上げてくれ。6月の花を植える順番は任せる"),
    ("ジャック", "5つの区画に、1種類ずつですね"),
    ("フジ", "この湿地じゃあまり見ん生き物がおるな。あれ、大丈夫なんか？"),
    ("ジャック", "今、調べています。どの辺りで見かけましたか？"),
    ("フジ", "資材置き場の奥だ。木陰の方へ動いていった"),
    ("ジャック", "場所を確認します。近づかず、見かけたら教えてください"),
    ("フジ", "分かった。いざとなりゃ身は守れるが、仕事中に寄って来られても困るからな"),
    ("ジャック", "そちらは住民課で確認します。まず、花の並びを見ていただけますか"),
    (
        "フジ",
        "北東の広場も、木を切って花壇の区画を整えている。そっちの作業でも、ウニやウミウシを見かけた",
    ),
    ("ジャック", "北側の作業場所も回って、見えたことを記録します"),
)
THANKS = (
    ("フジ", "……ああ、よくまとまったな。ありがとう。あとはこっちで見ておく"),
    ("ジャック", "よろしくお願いします。生き物を見かけた場所も、確認しておきます"),
)
RETRY = (("フジ", "まだ決まらんか。並べ直してみてくれ"), ("ジャック", "はい。もう一度、見てみます"))
REPEAT = (("フジ", "花はこっちで見ておくよ。何かあれば、また声をかける"),)


@dataclass(frozen=True)
class FlowerbedVisit:
    stage: str = "request"
    index: int = 0

    @property
    def sighting_recorded(self):
        return self.stage != "request"

    @property
    def complete(self):
        return self.stage == "complete"

    def snapshot(self):
        return {"stage": self.stage, "index": self.index}

    @classmethod
    def restore(cls, raw):
        if raw == {}:
            return cls()
        if not isinstance(raw, dict) or set(raw) != {"stage", "index"}:
            raise ValueError("invalid flowerbed visit")
        stage, index = raw["stage"], raw["index"]
        limits = {"request": len(REQUEST), "plant": 1, "thanks": len(THANKS), "complete": 1}
        if (
            not isinstance(stage, str)
            or stage not in limits
            or type(index) is not int
            or not 0 <= index < limits[stage]
        ):
            raise ValueError("invalid flowerbed visit")
        return cls(stage, index)


@dataclass
class VisitDialogue(FieldConversation):
    kind: str = "flowerbed_visit"
    action: str = "request"
    wait_release: bool = True
    error: str = ""


class FlowerbedVisitMixin:
    def flowerbed_visit_state(self):
        return FlowerbedVisit.restore(getattr(self.east_site_progress, "flowerbed_visit", {}))

    def save_flowerbed_visit(self, state, order=None):
        sites = self.east_site_progress
        previous_order, previous_visit = sites.flowerbed_order, sites.flowerbed_visit
        sites.flowerbed_visit = state.snapshot()
        if order is not None:
            sites.flowerbed_order = tuple(order)
        if getattr(self, "week_debug_active", False):
            saved = self.flowerbed_layout_store.write_state(sites.flowerbed_order, state)
        else:
            from drift_with_me.save_state import snapshot

            payload = snapshot(self)
            saved = self.progress_store.write(payload)
            if saved:
                self.last_checkpoint = payload
        if not saved:
            sites.flowerbed_order, sites.flowerbed_visit = previous_order, previous_visit
        return saved

    def start_flowerbed_visit(self, target="jul_w2_fuji"):
        if (
            not getattr(self.model, "flowerbed_visible", False)
            or self.model.combat_session
            or self.model.danger_blocks_interaction()
        ):
            return False
        state = self.flowerbed_visit_state()
        if state.complete and target == "jul_w2_flowerbed":
            self.flowerbed_visit_editing = True
            return self.start_flowerbed_editor()
        lines, action = {
            "request": (REQUEST, "request"),
            "plant": (RETRY, "edit"),
            "thanks": (THANKS, "thanks"),
            "complete": (REPEAT, "repeat"),
        }[state.stage]
        if self.week2_active() and self.office.week2_progress.checked:
            if state.stage == "request":
                lines = tuple(
                    (
                        speaker,
                        "確認した場所もあります。残りを見て、記録をまとめます" if i == 5 else text,
                    )
                    for i, (speaker, text) in enumerate(lines)
                )
            elif state.stage == "thanks":
                lines = (
                    lines[0],
                    ("ジャック", "よろしくお願いします。確認したことを記録にまとめます"),
                )
        index = state.index if action in ("request", "thanks") else 0
        self.flowerbed_dialogue = VisitDialogue("jul_w2_fuji", lines, index, "フジ", action=action)
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        self.map_objective_open = False
        return True

    def resume_flowerbed_visit(self):
        state = self.flowerbed_visit_state()
        if state.stage == "thanks" or state.stage == "request" and state.index:
            self.start_flowerbed_visit()

    def advance_flowerbed_visit(self):
        dialogue = self.flowerbed_dialogue
        state = self.flowerbed_visit_state()
        last = dialogue.index + 1 == len(dialogue.lines)
        if dialogue.action in ("request", "thanks"):
            next_state = (
                FlowerbedVisit("plant" if dialogue.action == "request" else "complete")
                if last
                else replace(state, index=dialogue.index + 1)
            )
            if not self.save_flowerbed_visit(next_state):
                dialogue.error = "保存できません。再試行してください。"
                return False
        if not last:
            dialogue.index += 1
            dialogue.error = ""
            return True
        self.flowerbed_dialogue = None
        if dialogue.action in ("request", "edit"):
            self.flowerbed_visit_editing = True
            self.start_flowerbed_editor()
            if self.week2_active() and self.east_site_progress.flowerbed_order:
                self.flowerbed_editor.draft = list(self.east_site_progress.flowerbed_order)
        else:
            self.flowerbed_input_wait_release = True
            self.clear_world_input_latches()
            self.previous_time = None
        return True

    def update_flowerbed_visit_dialogue(self):
        dialogue = self.flowerbed_dialogue
        if dialogue.wait_release:
            if not self.travel_input_held():
                dialogue.wait_release = False
            return True
        if self.key_pressed("KEY_ESCAPE", "KEY_X") or self.mouse_pressed_in(
            self.site_cancel_rect()
        ):
            self.flowerbed_dialogue = None
            self.flowerbed_input_wait_release = True
            self.clear_world_input_latches()
            self.previous_time = None
        elif self.key_pressed("KEY_RETURN") or self.mouse_pressed_in(
            self.office_rect(40, 126, 432, 100)
        ):
            self.advance_flowerbed_visit()
        return True

    def confirm_flowerbed_visit(self):
        from drift_with_me.flowerbed import validate_order

        editor = self.flowerbed_editor
        order = validate_order(editor.draft)
        state = self.flowerbed_visit_state()
        next_state = FlowerbedVisit("complete" if state.complete else "thanks")
        if not self.save_flowerbed_visit(next_state, order):
            editor.error = "保存できません。再試行するか、キャンセルしてください。"
            return False
        self.model.flowerbed_order = order
        self.close_flowerbed_editor()
        if not next_state.complete:
            self.start_flowerbed_visit()
        return True

    def draw_flowerbed_visit_dialogue(self):
        self.draw_play()
        self.draw_field_conversation(self.flowerbed_dialogue)
        if self.flowerbed_dialogue.error:
            self.draw_office_text_in_rect(
                self.office_rect(40, 108, 432, 18), self.flowerbed_dialogue.error, 10
            )
