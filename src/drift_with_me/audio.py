from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from drift_with_me.config import load_data_json
from drift_with_me.events import GameEvent
from drift_with_me.music import MusicController, context_for


@dataclass(frozen=True)
class AudioEventDef:
    event: str
    sound_key: str
    channel: int
    priority: int


SE_CHANNEL = 3  # Channels 0-2 are used for music.


SOUND_SHAPES = {
    "bubble_launch": ("c2e2", "tt", "65", "nn", 6),
    "capture_success": ("e2g2c3", "sss", "567", "nns", 7),
    "barrier_repel": ("g1c2g1", "ppp", "764", "nfn", 6),
    "discharge_success": ("c3g2c3e3", "nnnn", "7764", "ffff", 5),
    "action_denied": ("c1", "t", "4", "f", 5),
    "combat_marker_hit": ("e3", "t", "7", "n", 4),
    "combat_marker_miss": ("c2", "t", "4", "f", 6),
    "combat_perfect": ("e3g3c4", "ttt", "776", "nnn", 5),
    "combat_deflect": ("g2c3", "pp", "76", "nf", 5),
    "combat_victory": ("c3e3g3c4", "tttt", "6675", "nnnn", 5),
    "explore_inspect": ("e2", "t", "2", "f", 3),
    "explore_pickup": ("e4g4b4g4", "tttt", "2321", "nnvf", 7),
    "explore_water": ("c4e4b4g4", "ttpt", "1231", "ssnf", 5),
    "explore_energy": ("g4g4e4d4c4c4", "nntttt", "122211", "nnvvff", 7),
    "battle_entry_clash": ("c3c4b4f#4c4a3r", "nnppppt", "4322110", "fffffff", 3),
    "battle_position_zaza": ("c2c2rrd1c1c0rr", "nnnnnnnnn", "210032100", "fffffffff", 3),
}


class AudioEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        audio = load_data_json("audio_events.json")
        self.defs = {
            item["event"]: AudioEventDef(
                event=item["event"],
                sound_key=item["sound_key"],
                channel=int(item["channel"]),
                priority=int(item["priority"]),
            )
            for item in audio["events"]
        }
        self.muted = not bool(config["audio"]["enabled_by_default"])
        self._pyxel = None
        self._lifecycle_suspended = False
        self._sound_slots: dict[str, int] = {}
        self._processed_event_ids: set[int] = set()
        self._active_priority = 0
        self.music = MusicController(bool(config["audio"].get("bgm_enabled", True)))

    def setup(self, pyxel_module) -> None:
        self._pyxel = pyxel_module
        for index, sound_key in enumerate(SOUND_SHAPES):
            notes, tones, volumes, effects, speed = SOUND_SHAPES[sound_key]
            pyxel_module.sounds[index].set(notes, tones, volumes, effects, speed)
            self._sound_slots[sound_key] = index
        self.music.setup(pyxel_module)

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        if self.muted and self._pyxel is not None:
            self._pyxel.stop(SE_CHANNEL)
            self.music.stop_output()
            self._active_priority = 0
        return self.muted

    def suspend_for_lifecycle(self) -> None:
        if self._lifecycle_suspended:
            return
        self._lifecycle_suspended = True
        self.music.stop_output()
        self._active_priority = 0
        if self._pyxel is not None:
            self._pyxel.stop()

    def resume_from_lifecycle(self) -> None:
        self._lifecycle_suspended = False

    def reset_event_history(self) -> None:
        self.music.reset()
        self._processed_event_ids.clear()
        self._active_priority = 0

    def play_preview(self, event_name: str) -> None:
        if (
            self._pyxel is None
            or self.muted
            or self._lifecycle_suspended
            or event_name not in self.defs
        ):
            return
        definition = self.defs[event_name]
        busy = self._pyxel.play_pos(SE_CHANNEL) is not None
        if busy and definition.priority < self._active_priority:
            return
        self._pyxel.play(SE_CHANNEL, self._sound_slots[definition.sound_key])
        self._active_priority = definition.priority

    def play_events(self, events: list[GameEvent]) -> None:
        self.music.observe_events(events)
        if self._pyxel is None or self.muted or self._lifecycle_suspended:
            return
        selected: dict[int, tuple[int, int, AudioEventDef]] = {}
        for event in events:
            if (
                event.kind == "interaction_started"
                and event.payload.get("interaction_kind") != "inspect"
            ):
                continue
            if event.kind == "resource_refilled":
                if event.payload.get("amount", 0) <= 0:
                    continue
                from dataclasses import replace

                event = replace(event, kind="explore_" + event.payload["resource"])
            if event.event_id in self._processed_event_ids or event.kind not in self.defs:
                continue
            self._processed_event_ids.add(event.event_id)
            definition = self.defs[event.kind]
            if self.music.enabled and definition.sound_key == "combat_victory":
                continue  # The phrase starts after the burst, not at the earlier victory cue.
            previous = selected.get(definition.channel)
            candidate = (definition.priority, event.event_id, definition)
            if previous is None or candidate > previous:
                selected[definition.channel] = candidate

        for _channel, (_priority, _event_id, definition) in selected.items():
            busy = self._pyxel.play_pos(SE_CHANNEL) is not None
            if not busy:
                self._active_priority = 0
            # Quiet exploration never interrupts; other lower-priority cues are dropped.
            # No queue: late playback would detach an entry cue from the movement.
            if busy and (
                definition.sound_key.startswith("explore_")
                or definition.priority < self._active_priority
            ):
                continue
            self._pyxel.play(SE_CHANNEL, self._sound_slots[definition.sound_key])
            self._active_priority = definition.priority

    def update_music(self, app, elapsed: float) -> None:
        self.music.update(
            context_for(app), elapsed, muted=self.muted, suspended=self._lifecycle_suspended
        )

    @property
    def preview_events(self) -> tuple[str, ...]:
        return tuple(self.defs)
