"""Native one/two/three-voice music driven by presentation state; never writes saves."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from drift_with_me.audio_levels import OUTPUT_GAIN
from drift_with_me.config import load_data_json

MUSIC_CHANNELS = (0, 1, 2)
BATTLE_QUARTER_SEC = 26 / 60


@dataclass(frozen=True)
class MusicContext:
    active: bool
    paused: bool = False
    battle: object | None = None
    phase: str = ""
    victory: bool = False
    anchor_target: float | None = None
    phase_elapsed: float = 0.0
    ambient: str = "explore"


def context_for(app: Any) -> MusicContext:
    screen = getattr(getattr(app, "screen", None), "name", "")
    if screen == "PAUSE" or any(
        getattr(app, name, False) for name in ("_lifecycle_wait_draw", "_lifecycle_wait_release")
    ):
        return MusicContext(active=True, paused=True)
    active = screen in {"PLAY", "OFFICE"} and not any(
        getattr(app, name, None) for name in ("field_transition", "week_transition")
    )
    if not active:
        return MusicContext(active=False)
    if screen == "OFFICE":
        return MusicContext(True, ambient="office")
    model = app.model
    session = getattr(model, "combat_session", None)
    if session is not None:
        enemy = model.enemy_by_id(session.enemy_id)
        kind = getattr(enemy, "kind", "")
        # Normal parry points have .42s spacing plus one frame's hitstop per hit.
        target = (
            session.marker_positions[0] * model.combat_parry_sweep_sec()
            if session.phase == "PARRY_TIMING" and kind == "normal" and session.marker_positions
            else None
        )
        burst_finished = (
            session.phase == "COMBAT_RESTORE_JUMP"
            and session.outcome == "defeat"
            and session.zap_used
        )
        return MusicContext(
            True,
            battle=session,
            phase=session.phase,
            victory=burst_finished,
            anchor_target=target,
            phase_elapsed=session.timing_elapsed_sec,
        )
    field = getattr(model, "swarm_field", None)
    battle = getattr(field, "battle", None)
    if battle is not None:
        # One capture target, not a three-hit repeating parry rhythm.
        target = (
            battle.settings.target * battle.settings.sweep if battle.phase == "approach" else None
        )
        return MusicContext(
            True,
            battle=battle,
            phase=battle.phase,
            victory=battle.phase == "victory",
            anchor_target=target,
            phase_elapsed=battle.elapsed,
        )
    return MusicContext(True)


class MusicController:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.scores = load_data_json("bgm_score.json")
        self.pyxel = None
        # Keep combat/office slot identities stable; exploration leaves 33/34 unused.
        self.slots = {
            "explore": (32,),
            "battle": (35, 36, 37),
            "fanfare": (38, 39, 40),
            "office": (41, 42),
        }
        self.track: str | None = None
        self.position = 0.0
        self.fade_duration = 0.0
        self.fade_elapsed = 0.0
        self.battle = None
        self.phase = ""
        self.celebrated = False
        self.output_running = False
        self.base_gains = [0.125] * 3
        self.restore_win = False
        self.seen_native_position = False

    def setup(self, pyxel) -> None:
        self.pyxel = pyxel
        for name, score in self.scores.items():
            for slot, part in zip(self.slots[name], score["parts"], strict=True):
                pyxel.sounds[slot].set(
                    part["notes"], part["tones"], part["volumes"], part["effects"], part["speed"]
                )
        if hasattr(pyxel, "channels"):
            self.base_gains = [pyxel.channels[ch].gain for ch in MUSIC_CHANNELS]

    def observe_events(self, events) -> None:
        for event in events:
            if event.kind in {"combat_started", "swarm_started"}:
                self.restore_win = False
            elif event.kind == "combat_restored":
                self.restore_win = event.payload.get("combat_outcome") in {
                    "defeat",
                    "capture",
                    "deflect",
                }
            elif event.kind == "swarm_restored":
                self.restore_win = bool(event.payload.get("won"))

    def reset(self) -> None:
        self.stop_output()
        self.track = None
        self.position = 0.0
        self.battle = None
        self.phase = ""
        self.celebrated = False
        self.restore_win = False

    @property
    def active_channels(self) -> tuple[int, ...]:
        return MUSIC_CHANNELS[: len(self.slots.get(self.track, ()))]

    def stop_output(self) -> None:
        if self.pyxel is not None and self.output_running:
            pos = self.pyxel.play_pos(0)
            if pos is not None:
                self.position = float(pos[1])
        if self.pyxel is not None and self.output_running:
            for ch in self.active_channels:
                self.pyxel.stop(ch)
        self.output_running = False
        self._gain(1.0)

    def _gain(self, factor: float) -> None:
        if self.pyxel is not None and hasattr(self.pyxel, "channels"):
            for ch in self.active_channels:
                self.pyxel.channels[ch].gain = (
                    self.base_gains[ch] * OUTPUT_GAIN * max(0.0, min(1.0, factor))
                )

    def _start(self, name: str, fade: float = 0.0) -> None:
        self.stop_output()
        self.track = name
        self.position = 0.0
        self.fade_elapsed = 0.0
        self.fade_duration = fade
        self.seen_native_position = False

    def _play(self) -> None:
        score = self.scores[self.track]
        for ch, slot in zip(self.active_channels, self.slots[self.track], strict=True):
            self.pyxel.play(ch, slot, sec=self.position, loop=score["loop"])
        self.output_running = True

    def update(self, context: MusicContext, dt: float, *, muted: bool, suspended: bool) -> None:
        if not self.enabled or self.pyxel is None:
            return
        if not context.active:
            self.stop_output()
            self.track = None
            self.battle = None
            self.phase = ""
            self.celebrated = False
            self.restore_win = False
            return
        if context.paused or suspended:
            self.stop_output()
            return
        dt = max(0.0, float(dt))
        if context.ambient == "office":
            if self.track != "office":
                self._start("office", 1.2)
            # A return to the counter must not keep a field victory/battle pending.
            self.battle = None
            self.phase = ""
            self.celebrated = False
            self.restore_win = False
        elif self.track == "office":
            self._start("explore", 1.2)
        if context.battle is not None and context.battle is not self.battle:
            self.battle = context.battle
            self.phase = ""
            self.celebrated = False
            self._start("battle", 0.25)
        if context.victory and not self.celebrated:
            self.celebrated = True
            self._start("fanfare")
        elif context.battle is None and self.restore_win and not self.celebrated:
            # Finisher routes with no shared burst animation use actual victory restoration.
            self.celebrated = True
            self._start("fanfare")
        elif context.battle is None and self.track == "battle":
            self._start("explore", 1.2)  # Retreat/failed encounter: no victory phrase.
        if self.track is None:
            self._start("explore", 1.2)
        if (
            self.track == "battle"
            and context.phase != self.phase
            and context.anchor_target is not None
        ):
            # Anchor to the live round, never a hardcoded video timestamp.
            self.stop_output()
            self.position = (context.phase_elapsed - context.anchor_target) % BATTLE_QUARTER_SEC
            self.seen_native_position = False
        self.phase = context.phase
        self.restore_win = False
        if self.output_running and not muted:
            native_position = self.pyxel.play_pos(0)
            if native_position is not None:
                self.seen_native_position = True
                self.position = float(native_position[1])
            elif self.seen_native_position:
                if self.track == "fanfare":
                    self.position = self.scores["fanfare"]["seconds"]
                else:
                    self.output_running = False
        if self.track == "fanfare" and self.position >= self.scores["fanfare"]["seconds"]:
            self._start("explore", 1.2)
        if muted:
            self.stop_output()
        else:
            self._gain(self.fade_elapsed / self.fade_duration if self.fade_duration else 1.0)
            if not self.output_running:
                self._play()
        # UI music clock advances through hitstop/dialogue/mute, but freezes on pause/background.
        self.position += dt
        self.fade_elapsed += dt
        score = self.scores[self.track]
        if score["loop"]:
            self.position %= score["seconds"]
