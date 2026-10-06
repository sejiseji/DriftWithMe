from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GameEvent:
    event_id: int
    world_tick: int
    kind: str
    actor_id: str
    target_id: str | None
    world_position: tuple[float, float, float]
    payload: dict[str, Any] = field(default_factory=dict)


class EventQueue:
    def __init__(self) -> None:
        self._next_event_id = 1

    def emit(
        self,
        world_tick: int,
        kind: str,
        actor_id: str,
        world_position: tuple[float, float, float],
        target_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> GameEvent:
        event = GameEvent(
            event_id=self._next_event_id,
            world_tick=world_tick,
            kind=kind,
            actor_id=actor_id,
            target_id=target_id,
            world_position=world_position,
            payload=payload or {},
        )
        self._next_event_id += 1
        return event

    def reset(self) -> None:
        self._next_event_id = 1
