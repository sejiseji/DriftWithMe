"""Small deterministic sampling patrol; a held inspection never advances it."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drift_with_me.world import StaticObject, WorldData


@dataclass
class MaintenanceRobot:
    clock: float = 0.0

    @property
    def phase(self) -> str:
        t = self.clock % 12.0
        return "OUTBOUND" if t < 4 else "MEASURE" if t < 6 else "RETURN" if t < 10 else "REST"

    @property
    def offset(self) -> float:
        t = self.clock % 12.0
        return t * 8 if t < 4 else 32.0 if t < 6 else (10 - t) * 8 if t < 10 else 0.0

    def presentation(self, anchor: StaticObject) -> StaticObject:
        return replace(anchor, x=anchor.x + self.offset, height=18.0)

    def update(self, dt: float, world: WorldData) -> None:
        anchor = world.object_by_id("maintenance_unit")
        if anchor is None:
            return
        previous = self.clock
        self.clock += max(0.0, dt)
        obj = self.presentation(anchor)
        safe = world.walkable_rect.contains_aabb(obj.x - 6, obj.z - 6, obj.x + 6, obj.z + 6)
        safe = safe and not world.query_solids(obj.x - 6, obj.z - 6, obj.x + 6, obj.z + 6)
        safe = safe and not any(
            obj.x + 6 > a.min_x
            and obj.x - 6 < a.max_x
            and obj.z + 6 > a.min_z
            and obj.z - 6 < a.max_z
            for a in world.shallow_water_areas
        )
        if not safe:
            self.clock = previous
