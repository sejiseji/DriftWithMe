from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from drift_with_me.events import GameEvent


@dataclass
class WorldParticle:
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    color: int
    lifetime: float
    age: float = 0.0

    @property
    def progress(self) -> float:
        if self.lifetime <= 1e-6:
            return 1.0
        return max(0.0, min(self.age / self.lifetime, 1.0))


@dataclass
class ActorEmote:
    anchor_kind: str
    anchor_id: str
    fallback_x: float
    fallback_z: float
    symbol: str
    color: int
    lifetime: float
    age: float = 0.0

    @property
    def progress(self) -> float:
        if self.lifetime <= 1e-6:
            return 1.0
        return max(0.0, min(self.age / self.lifetime, 1.0))


@dataclass
class ScreenCue:
    kind: str
    lifetime: float
    age: float = 0.0

    @property
    def progress(self) -> float:
        if self.lifetime <= 1e-6:
            return 1.0
        return max(0.0, min(self.age / self.lifetime, 1.0))


class EffectSystem:
    def __init__(self, config: dict[str, Any]) -> None:
        effects = config["effects"]
        self.max_particles = int(effects["max_particles"])
        self.max_emotes = int(effects["max_emotes"])
        self.max_screen_effects = int(effects["max_screen_effects"])
        self.max_particles_per_event = int(effects["max_particles_per_event"])
        self.concentration_line_count = int(effects["concentration_line_count"])
        self.particles: list[WorldParticle] = []
        self.emotes: list[ActorEmote] = []
        self.screen_cues: list[ScreenCue] = []
        self._grass_cooldowns: dict[str, float] = {}

    def reset(self) -> None:
        self.particles.clear()
        self.emotes.clear()
        self.screen_cues.clear()
        self._grass_cooldowns.clear()

    def process_events(self, events: list[GameEvent], model) -> None:
        for event in events:
            x, y, z = event.world_position
            if event.kind == "bubble_fired":
                self.spawn_burst(x, y, z, color=12, count=5, speed=16.0)
            elif event.kind == "enemy_captured":
                self.spawn_burst(x, y, z, color=12, count=7, speed=10.0)
                self.add_emote("enemy", event.target_id or "", x, z, "!", 12, 0.7)
            elif event.kind == "barrier_repelled":
                self.spawn_burst(x, y, z, color=12, count=6, speed=18.0)
                self.add_emote("enemy", event.target_id or "", x, z, "!", 7, 0.45)
            elif event.kind == "discharge_succeeded":
                self.spawn_burst(x, y, z, color=10, count=8, speed=22.0)
                self.add_emote("enemy", event.target_id or "", x, z, "!", 10, 0.6)
            elif event.kind == "action_denied":
                self.add_emote("player", "player", model.player.x, model.player.z, "?", 8, 0.45)
            elif event.kind == "inspection_completed":
                self.add_emote("object", event.target_id or "", x, z, "?", 7, 0.8)
                self.add_screen_cue("focus_lines", 0.35)
            elif event.kind == "resource_refilled":
                self.spawn_burst(
                    x,
                    y,
                    z,
                    color=10 if event.payload.get("resource") == "energy" else 12,
                    count=6,
                    speed=10.0,
                )

    def update(self, dt: float, model) -> None:
        dt = max(0.0, dt)
        for particle in self.particles:
            particle.age += dt
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            particle.z += particle.vz * dt
            particle.vy -= 18.0 * dt
        self.particles = [
            particle for particle in self.particles if particle.age < particle.lifetime
        ]

        for emote in self.emotes:
            emote.age += dt
        self.emotes = [emote for emote in self.emotes if emote.age < emote.lifetime]

        for cue in self.screen_cues:
            cue.age += dt
        self.screen_cues = [cue for cue in self.screen_cues if cue.age < cue.lifetime]

        for object_id in tuple(self._grass_cooldowns):
            self._grass_cooldowns[object_id] = max(0.0, self._grass_cooldowns[object_id] - dt)

        self.update_grass_reactions(model)

    def update_grass_reactions(self, model) -> None:
        for obj in model.world.objects:
            if obj.kind != "reactive_prop" or obj.reaction_radius <= 0.0:
                continue
            if self._grass_cooldowns.get(obj.id, 0.0) > 0.0:
                continue
            if math.hypot(model.player.x - obj.x, model.player.z - obj.z) > obj.reaction_radius:
                continue
            self.spawn_burst(obj.x, 0.0, obj.z, color=11, count=3, speed=5.0)
            self._grass_cooldowns[obj.id] = 0.8

    def spawn_burst(
        self, x: float, y: float, z: float, color: int, count: int, speed: float
    ) -> None:
        count = min(count, self.max_particles_per_event)
        for index in range(count):
            if len(self.particles) >= self.max_particles:
                return
            angle = index * math.tau / max(count, 1)
            self.particles.append(
                WorldParticle(
                    x=x,
                    y=y + 4.0,
                    z=z,
                    vx=math.cos(angle) * speed,
                    vy=8.0 + (index % 3) * 2.0,
                    vz=math.sin(angle) * speed,
                    color=color,
                    lifetime=0.45 + (index % 2) * 0.1,
                )
            )

    def add_emote(
        self,
        anchor_kind: str,
        anchor_id: str,
        fallback_x: float,
        fallback_z: float,
        symbol: str,
        color: int,
        lifetime: float,
    ) -> None:
        if len(self.emotes) >= self.max_emotes:
            self.emotes.pop(0)
        self.emotes.append(
            ActorEmote(anchor_kind, anchor_id, fallback_x, fallback_z, symbol, color, lifetime)
        )

    def add_screen_cue(self, kind: str, lifetime: float) -> None:
        if len(self.screen_cues) >= self.max_screen_effects:
            self.screen_cues.pop(0)
        self.screen_cues.append(ScreenCue(kind, lifetime))
