"""Passive save results and shared office toolbar controls; no input ownership."""

from __future__ import annotations


def publish_save_notice(store, kind):
    # A failing checkpoint can retry every frame. Keep one stable failure event.
    if (
        kind in {"failure", "temporary_failure"}
        and getattr(store, "save_notice_kind", None) == kind
    ):
        return
    store.save_notice_kind = kind
    store.save_notice_revision = getattr(store, "save_notice_revision", 0) + 1


class OfficeHeaderMixin:
    def sync_office_save_notice(self):
        store = getattr(self, "progress_store", None)
        revision = getattr(store, "save_notice_revision", 0)
        if store is not None and revision != getattr(store, "_notice_seen_revision", None):
            store._notice_seen_revision = revision
            store._notice_seen_at = float(getattr(self, "presentation_time", 0))
        self._office_save_notice_started = getattr(store, "_notice_seen_at", 0.0)

    def office_save_notice(self):
        self.sync_office_save_notice()
        store = getattr(self, "progress_store", None)
        kind = getattr(store, "save_notice_kind", None)
        age = float(getattr(self, "presentation_time", 0)) - self._office_save_notice_started
        if kind == "temporary_failure":
            return "一時保存できません（デバッグ）", 8
        if kind == "failure":
            return "進行をセーブできません", 8
        if kind == "saved" and age < 4:
            return "進行をセーブしました", 10
        if kind == "temporary" and age < 4:
            return "一時保存しました（デバッグ）", 12
        if getattr(self, "week_debug_active", False):
            return "デバッグ中・通常セーブは変更しません", 12
        if store is not None and (
            not store.available or "できません" in store.message or "前の保存" in store.message
        ):
            return store.message, 8
        return "", 13

    def office_consultation_available(self):
        if getattr(self, "office_consultation", None) is not None:
            return True
        if self.office_dialogue_requires_advance():
            return False
        return self.week4_follow_available() or self.office.supervisor_advice() is not None

    def draw_office_save_notice(self):
        area = self.office_rect(6, 3, 316, 21)
        self.pyxel.rect(int(area.x), int(area.y), int(area.width), int(area.height), 1)
        text, color = self.office_save_notice()
        if not text:
            office = self.office
            session = office.current_session
            if self.office_story_report_active():
                lines, index = self.office_story_report()
                text = f"外勤報告  {index + 1}/{len(lines)}"
            elif session is not None:
                text = (
                    f"案件 {office.current_index + 1}/{len(office.cases)}  "
                    + self.office_state_label(session.state)
                )
        self.draw_office_text_in_rect(area, text, color)

    def draw_office_consultation_icon(self):
        area = self.office_consultation_button_rect()
        enabled = self.office_consultation_available()
        active = getattr(self, "office_consultation", None) is not None
        color = 10 if active else 7 if enabled else 13
        self.pyxel.rect(int(area.x), int(area.y), int(area.width), int(area.height), 1)
        # One speech balloon, with a head/shoulders inside. Back arrow while consulting.
        parts = (
            ((439, 6, 21, 13), (439, 18, 4, 3))
            if not active
            else (
                (443, 12, 16, 3),
                (440, 9, 3, 3),
                (440, 15, 3, 3),
                (443, 6, 3, 3),
                (443, 18, 3, 3),
            )
        )
        for x, y, w, h in parts:
            r = self.office_rect(x, y, w, h)
            self.pyxel.rect(int(r.x), int(r.y), int(r.width), int(r.height), color)
        if not active:
            for x, y, w, h in ((441, 8, 17, 9), (448, 9, 4, 3), (445, 13, 10, 3)):
                r = self.office_rect(x, y, w, h)
                self.pyxel.rect(
                    int(r.x), int(r.y), int(r.width), int(r.height), 1 if w == 17 else color
                )
        else:
            r = self.office_rect(437, 12, 3, 3)
            self.pyxel.rect(int(r.x), int(r.y), int(r.width), int(r.height), color)
