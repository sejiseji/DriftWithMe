"""Bounded, transient presentation only; never changes movement or input geometry."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from drift_with_me.exploration_motion import ExplorationMotion
from drift_with_me.math3d import Vec3


@dataclass
class Pulse:
    kind: str
    origin: tuple[float, float, float]
    destination: tuple[float, float, float]
    age: float = 0.0


class ExplorationFeedback:
    LIMIT = 4
    DURATION = 0.42

    def __init__(self):
        self.enabled = True
        self.motion = ExplorationMotion()
        self.recent_ids = deque(maxlen=64)
        self.pulses: list[Pulse] = []
        self.target_id = None
        self.target_age = 1.0
        self.cooldown = 0.0
        self.flashes = {"water": 0.0, "energy": 0.0}

    def reset(self):
        enabled = self.enabled
        motion_enabled = self.motion.enabled
        self.__init__()
        self.enabled = enabled
        self.motion.enabled = motion_enabled

    def update(self, dt, model, camera, active=True):
        dt = max(0.0, min(dt, 0.1))
        self.cooldown = max(0.0, self.cooldown - dt)
        self.target_age += dt
        for key in self.flashes:
            self.flashes[key] = max(0.0, self.flashes[key] - dt)
        for pulse in self.pulses:
            pulse.age += dt
        self.pulses[:] = [p for p in self.pulses if p.age < self.DURATION]
        target = model.interaction_candidate(camera) if active and self.enabled else None
        ident = target.id if target else None
        if ident != self.target_id:
            if ident is not None and self.cooldown == 0:
                self.target_age = 0.0
                self.cooldown = 0.45
            self.target_id = ident
        if not active:
            self.pulses.clear()
            self.target_age = 1.0
            for key in self.flashes:
                self.flashes[key] = 0.0

    def marker_offset(self, ident):
        if not self.enabled or ident != self.target_id or self.target_age >= 0.24:
            return 0
        return -round(2 * math.sin(math.pi * self.target_age / 0.24))

    def process(self, events, model):
        if not self.enabled:
            return
        for event in events:
            if event.event_id in self.recent_ids:
                continue
            self.recent_ids.append(event.event_id)
            if event.kind == "resource_refilled" and event.payload.get("amount", 0) > 0:
                resource = event.payload["resource"]
                actor = model.player if resource == "water" else model.buddy
                destination = (actor.x, getattr(actor, "y", 12.0), actor.z)
                self.flashes[resource] = 0.28
                pulse = Pulse(resource, event.world_position, destination)
            elif event.kind == "collectible_claimed":
                destination = (model.player.x, 16.0, model.player.z)
                pulse = Pulse("pickup", destination, destination)
            else:
                continue
            self.pulses.append(pulse)
            del self.pulses[: -self.LIMIT]

    def draw(self, pyxel, camera):
        if not self.enabled:
            return
        for pulse in self.pulses:
            t = pulse.age / self.DURATION
            color = 12 if pulse.kind == "water" else 10
            for index in range(3):
                u = max(0.0, min(1.0, t * 1.35 - index * 0.12))
                if pulse.kind == "pickup":
                    angle = index * math.tau / 3
                    point = Vec3(
                        pulse.origin[0] + math.cos(angle) * 8 * t,
                        pulse.origin[1] + 12 * t,
                        pulse.origin[2] + math.sin(angle) * 8 * t,
                    )
                else:
                    point = Vec3(
                        *(
                            a + (b - a) * u
                            for a, b in zip(pulse.origin, pulse.destination, strict=True)
                        )
                    )
                screen = camera.project(point)
                if screen is not None and t < 0.85:
                    pyxel.pset(round(screen.x), round(screen.y) - index, color)
