"""Field speech presentation only; authored progress remains owned by each scene."""

from __future__ import annotations

from dataclasses import dataclass

from drift_with_me.dialogue_voice import voice_for_speaker
from drift_with_me.field_visit import FieldConversation


@dataclass
class FieldDialoguePlayback:
    signature: tuple | None = None
    revealed_chars: float = 0.0


@dataclass(frozen=True)
class FieldVoiceLine:
    text: str
    speaker: str
    voice_preset: str | None


def signature_for(conversation) -> tuple:
    # Some authored scenes reconstruct a FieldConversation every draw. Do not key by id().
    return (
        getattr(conversation, "target_id", "travel_" + getattr(conversation, "direction", "")),
        tuple(conversation.lines),
        conversation.index,
    )


class FieldDialogueMixin:
    def active_field_dialogue(self):
        """Return the visible field-style speech and its input owner, never office speech."""
        screen = getattr(getattr(self, "screen", None), "name", "")
        if screen not in {"PLAY", "OFFICE"} or getattr(self, "week_debug_menu_open", False):
            return None
        transition = getattr(self, "field_transition", None)
        if transition is not None:
            return ("field_transition", transition) if transition.phase == "dialogue" else None
        if getattr(self, "week_transition", None) is not None:
            return None
        preview = getattr(self, "portrait_preview", None)
        if preview is not None:
            return "portrait_preview", preview
        if any(
            getattr(self, name, None) is not None
            for name in (
                "ring_preview",
                "park_preview_week",
                "garden_props_preview",
                "nudibranch_preview",
            )
        ):
            return None
        flowerbed = getattr(self, "flowerbed_dialogue", None)
        if flowerbed is not None:
            return "flowerbed_dialogue", flowerbed
        if getattr(self, "flowerbed_editor", None) is not None:
            return None
        for name in ("week2_dialogue", "week3_dialogue", "week4_dialogue"):
            conversation = getattr(self, name, None)
            if conversation is not None and (screen == "PLAY" or name == "week2_dialogue"):
                return name, conversation
        if screen != "PLAY":
            return None
        for name in ("patrol_dialogue", "first_sight_conversation", "field_conversation"):
            conversation = getattr(self, name, None)
            if conversation is not None:
                return name, conversation
        week = getattr(self, "work_week", None)
        office = getattr(self, "office", None)
        if (getattr(week, "month", 0), getattr(week, "number", 0)) == (7, 1):
            progress = getattr(office, "july_progress", None)
            if getattr(progress, "stage", None) in {"after_clear", "researchers"}:
                from drift_with_me.july_week1 import AFTER_CLEAR, RESEARCHERS

                lines = AFTER_CLEAR if progress.stage == "after_clear" else RESEARCHERS
                return "july_story", FieldConversation("july_story", lines, progress.scene_index)
        if (getattr(week, "month", 0), getattr(week, "number", 0)) == (8, 1):
            progress = getattr(office, "august_progress", None)
            if getattr(progress, "pending_sighting", None) and not getattr(
                self, "august_crossing", None
            ):
                from drift_with_me.august_sightings import LINES

                target = progress.pending_sighting
                return "august_sighting", FieldConversation(
                    "august_" + target, LINES[target], progress.sighting_index
                )
        return None

    def sync_field_dialogue_playback(self, conversation):
        playback = getattr(self, "field_dialogue_playback", None)
        if playback is None:
            playback = self.field_dialogue_playback = FieldDialoguePlayback()
        signature = signature_for(conversation)
        if playback.signature != signature:
            self.stop_field_dialogue_voice()
            playback.signature = signature
            playback.revealed_chars = 0.0
        return playback

    def stop_field_dialogue_voice(self):
        stop = getattr(getattr(self, "audio", None), "stop_dialogue_reveal", None)
        if stop is not None:
            stop()

    def field_dialogue_waiting(self, owner, conversation):
        wait_name = {
            "portrait_preview": "week_debug_wait_release",
            "week2_dialogue": "week2_wait_release",
            "week3_dialogue": "week3_wait_release",
            "week4_dialogue": "week4_wait_release",
            "patrol_dialogue": "patrol_wait_release",
            "july_story": "july_wait_release",
            "august_sighting": "august_sighting_wait_release",
        }.get(owner, "")
        return getattr(conversation, "wait_release", False) or any(
            getattr(self, name, False)
            for name in (wait_name, "field_input_wait_for_release", "week_input_wait_for_release")
        )

    def field_dialogue_confirm_pressed(self, owner, conversation):
        # Match the actual owner's cancel hit area. An invisible cancel rectangle
        # must not bypass reveal-all on scenes accepting a tap anywhere in the panel.
        if owner == "portrait_preview":
            rects = self.portrait_preview_rects()
            return self.mouse_pressed_in(rects["next"]) or self.mouse_pressed_in(
                self.office_rect(356, 204, 96, 16)
            )
        target = getattr(conversation, "target_id", "")
        if target in {"week2_return_choice", "week3_return_choice", "week4_return_choice"}:
            go, stay = self.week2_return_choice_rects()
            if self.key_pressed("KEY_ESCAPE", "KEY_X") or self.mouse_pressed_in(stay):
                return False
            return self.key_pressed("KEY_RETURN", "KEY_Z") or self.mouse_pressed_in(go)
        cancel_rect = None
        cancel_keys = ()
        if owner == "field_transition" and conversation.direction == "back":
            cancel_rect = self.field_travel_cancel_rect()
            cancel_keys = ("KEY_ESCAPE", "KEY_X")
        elif owner == "field_conversation":
            from drift_with_me.app import JULY_TARGETS, KEY_ID, SITE_FACTS, W4_TARGETS

            cancel_keys = ("KEY_ESCAPE",)
            if target in set(SITE_FACTS) | W4_TARGETS | JULY_TARGETS | {KEY_ID}:
                cancel_rect = self.site_cancel_rect()
                cancel_keys = ("KEY_ESCAPE", "KEY_X")
        elif owner in {
            "first_sight_conversation",
            "flowerbed_dialogue",
            "week2_dialogue",
            "week3_dialogue",
            "week4_dialogue",
            "patrol_dialogue",
        }:
            cancel_keys = ("KEY_ESCAPE", "KEY_X")
            if owner != "patrol_dialogue" and not (
                owner == "week2_dialogue" and target == "week2_report"
            ):
                cancel_rect = self.site_cancel_rect()
        if (cancel_keys and self.key_pressed(*cancel_keys)) or (
            cancel_rect is not None and self.mouse_pressed_in(cancel_rect)
        ):
            return False
        keys = (
            ("KEY_RETURN", "KEY_Z", "KEY_SPACE", "KEY_E")
            if owner == "august_sighting"
            else ("KEY_RETURN",)
            if owner in {"field_conversation", "flowerbed_dialogue"}
            else ("KEY_RETURN", "KEY_Z")
        )
        return self.key_pressed(*keys) or self.mouse_pressed_in(self.office_rect(40, 126, 432, 100))

    def update_field_dialogue_playback(self, elapsed):
        """Consume only a reveal-all action, before any scene can advance/save that line."""
        from drift_with_me.app import OFFICE_DIALOGUE_CHARS_PER_SEC

        if getattr(getattr(self, "screen", None), "name", "") == "PAUSE" or any(
            getattr(self, name, False)
            for name in ("_lifecycle_wait_draw", "_lifecycle_wait_release")
        ):
            if getattr(self, "field_dialogue_playback", None) is not None:
                self.stop_field_dialogue_voice()
            return False
        active = self.active_field_dialogue()
        if active is None:
            if getattr(self, "field_dialogue_playback", None) is not None:
                self.stop_field_dialogue_voice()
                self.field_dialogue_playback = None
            return False
        owner, conversation = active
        playback = self.sync_field_dialogue_playback(conversation)
        speaker, text = conversation.lines[conversation.index]
        if (
            int(playback.revealed_chars) < len(text)
            and not self.field_dialogue_waiting(owner, conversation)
            and self.field_dialogue_confirm_pressed(owner, conversation)
        ):
            playback.revealed_chars = float(len(text))
            self.stop_field_dialogue_voice()
            return True
        before = int(playback.revealed_chars)
        playback.revealed_chars = min(
            float(len(text)),
            playback.revealed_chars + max(0.0, elapsed) * OFFICE_DIALOGUE_CHARS_PER_SEC,
        )
        reveal = getattr(getattr(self, "audio", None), "play_dialogue_reveal", None)
        if reveal is not None:
            page = (FieldVoiceLine(text, speaker, voice_for_speaker(speaker) if speaker else None),)
            # Narration with no named speaker remains silent.
            if speaker:
                reveal(page, before, int(playback.revealed_chars), elapsed)
        return False

    def field_dialogue_is_revealing(self, conversation):
        playback = self.sync_field_dialogue_playback(conversation)
        return int(playback.revealed_chars) < len(conversation.lines[conversation.index][1])

    def draw_field_dialogue_text(self, rect, conversation, color):
        playback = self.sync_field_dialogue_playback(conversation)
        text = conversation.lines[conversation.index][1]
        style = self.office_text_style(rect)
        # Wrap the complete line first, so punctuation never moves an already visible glyph.
        wrapped = self.wrap_office_dialogue_text(text, max(1, int(rect.width)), style)
        remaining = int(playback.revealed_chars)
        visible = []
        for line in wrapped:
            visible.append(line[:remaining])
            remaining = max(0, remaining - len(line))
        self.draw_office_wrapped_lines(rect, tuple(visible), color)
