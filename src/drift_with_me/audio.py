from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from drift_with_me.config import load_data_json
from drift_with_me.events import GameEvent


@dataclass(frozen=True)
class AudioEventDef:
    event: str
    sound_key: str
    channel: int
    priority: int


SOUND_SHAPES = {
    "bubble_launch": ("c2e2", "tt", "65", "nn", 6),
    "capture_success": ("e2g2c3", "sss", "567", "nns", 7),
    "barrier_repel": ("g1c2g1", "ppp", "764", "nfn", 6),
    "discharge_success": ("c3g2c3e3", "nnnn", "7764", "ffff", 5),
    "action_denied": ("c1", "t", "4", "f", 5),
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
        self._sound_slots: dict[str, int] = {}
        self._processed_event_ids: set[int] = set()

    def setup(self, pyxel_module) -> None:
        self._pyxel = pyxel_module
        for index, sound_key in enumerate(SOUND_SHAPES):
            notes, tones, volumes, effects, speed = SOUND_SHAPES[sound_key]
            pyxel_module.sounds[index].set(notes, tones, volumes, effects, speed)
            self._sound_slots[sound_key] = index

    def toggle_mute(self) -> bool:
        self.muted = not self.muted
        return self.muted

    def reset_event_history(self) -> None:
        self._processed_event_ids.clear()

    def play_preview(self, event_name: str) -> None:
        if self._pyxel is None or self.muted or event_name not in self.defs:
            return
        definition = self.defs[event_name]
        self._pyxel.play(definition.channel, self._sound_slots[definition.sound_key])

    def play_events(self, events: list[GameEvent]) -> None:
        if self._pyxel is None or self.muted:
            return
        selected: dict[int, tuple[int, int, AudioEventDef]] = {}
        for event in events:
            if event.event_id in self._processed_event_ids or event.kind not in self.defs:
                continue
            self._processed_event_ids.add(event.event_id)
            definition = self.defs[event.kind]
            previous = selected.get(definition.channel)
            candidate = (definition.priority, event.event_id, definition)
            if previous is None or candidate > previous:
                selected[definition.channel] = candidate

        for channel, (_priority, _event_id, definition) in selected.items():
            self._pyxel.play(channel, self._sound_slots[definition.sound_key])

    @property
    def preview_events(self) -> tuple[str, ...]:
        return tuple(self.defs)
