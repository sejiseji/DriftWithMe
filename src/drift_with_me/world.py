from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from drift_with_me.config import load_data_json


@dataclass(frozen=True)
class StaticObject:
    id: str
    kind: str
    x: float
    z: float
    solid: bool
    half_x: float = 0.0
    half_z: float = 0.0
    height: float = 0.0
    visual: str = ""
    inspectable: bool = False
    text_key: str | None = None
    supply: str | None = None

    @property
    def min_x(self) -> float:
        return self.x - self.half_x

    @property
    def max_x(self) -> float:
        return self.x + self.half_x

    @property
    def min_z(self) -> float:
        return self.z - self.half_z

    @property
    def max_z(self) -> float:
        return self.z + self.half_z


@dataclass(frozen=True)
class EnemySpawn:
    id: str
    kind: str
    x: float
    z: float


@dataclass(frozen=True)
class SafeZone:
    id: str
    x: float
    z: float
    radius: float


class WorldData:
    def __init__(self, raw: dict[str, Any], chunk_size: float = 128.0) -> None:
        self.raw = raw
        ground = raw["ground"]
        self.width = float(ground["width_cells"] * ground["cell_size"])
        self.depth = float(ground["depth_cells"] * ground["cell_size"])
        self.cell_size = float(ground["cell_size"])
        self.chunk_size = chunk_size
        self.spawn_x = float(raw["spawn"]["player"][0])
        self.spawn_z = float(raw["spawn"]["player"][2])
        self.objects = tuple(self._load_object(item) for item in raw["objects"])
        self.enemies = tuple(
            EnemySpawn(
                id=str(item["id"]),
                kind=str(item["kind"]),
                x=float(item["position"][0]),
                z=float(item["position"][2]),
            )
            for item in raw["enemies"]
        )
        self.safe_zones = tuple(
            SafeZone(
                id=str(item["id"]),
                x=float(item["center_xz"][0]),
                z=float(item["center_xz"][1]),
                radius=float(item["radius"]),
            )
            for item in raw["safe_zones"]
        )
        self.texts = raw["texts"]
        self._solid_index = self._build_solid_index()

    def _load_object(self, item: dict[str, Any]) -> StaticObject:
        position = item["position"]
        half_x, half_z = item.get("half_extents_xz", [0.0, 0.0])
        return StaticObject(
            id=str(item["id"]),
            kind=str(item["kind"]),
            x=float(position[0]),
            z=float(position[2]),
            solid=bool(item.get("solid", False)),
            half_x=float(half_x),
            half_z=float(half_z),
            height=float(item.get("height", 0.0)),
            visual=str(item.get("visual", "")),
            inspectable=bool(item.get("inspectable", False)),
            text_key=item.get("text_key"),
            supply=item.get("supply"),
        )

    @property
    def solid_objects(self) -> tuple[StaticObject, ...]:
        return tuple(obj for obj in self.objects if obj.solid)

    def _chunk_span(
        self, min_x: float, min_z: float, max_x: float, max_z: float
    ) -> tuple[range, range]:
        min_cx = max(0, int(math.floor(min_x / self.chunk_size)))
        min_cz = max(0, int(math.floor(min_z / self.chunk_size)))
        max_cx = max(0, int(math.floor(max_x / self.chunk_size)))
        max_cz = max(0, int(math.floor(max_z / self.chunk_size)))
        return range(min_cx, max_cx + 1), range(min_cz, max_cz + 1)

    def _build_solid_index(self) -> dict[tuple[int, int], list[StaticObject]]:
        index: dict[tuple[int, int], list[StaticObject]] = {}
        for obj in self.solid_objects:
            x_range, z_range = self._chunk_span(obj.min_x, obj.min_z, obj.max_x, obj.max_z)
            for cx in x_range:
                for cz in z_range:
                    index.setdefault((cx, cz), []).append(obj)
        return index

    def query_solids(
        self, min_x: float, min_z: float, max_x: float, max_z: float
    ) -> tuple[StaticObject, ...]:
        result: dict[str, StaticObject] = {}
        x_range, z_range = self._chunk_span(min_x, min_z, max_x, max_z)
        for cx in x_range:
            for cz in z_range:
                for obj in self._solid_index.get((cx, cz), ()):
                    if aabb_overlap(
                        min_x, min_z, max_x, max_z, obj.min_x, obj.min_z, obj.max_x, obj.max_z
                    ):
                        result[obj.id] = obj
        return tuple(result.values())

    def collides_player(self, x: float, z: float, half_x: float, half_z: float) -> bool:
        min_x = x - half_x
        max_x = x + half_x
        min_z = z - half_z
        max_z = z + half_z
        if min_x < 0.0 or max_x > self.width or min_z < 0.0 or max_z > self.depth:
            return True
        return bool(self.query_solids(min_x, min_z, max_x, max_z))

    def move_player_sliding(
        self,
        x: float,
        z: float,
        delta_x: float,
        delta_z: float,
        half_x: float,
        half_z: float,
        max_step: float = 4.0,
    ) -> tuple[float, float]:
        steps = max(1, math.ceil(max(abs(delta_x), abs(delta_z)) / max_step))
        step_x = delta_x / steps
        step_z = delta_z / steps
        current_x = x
        current_z = z
        for _ in range(steps):
            next_x = clamp(current_x + step_x, half_x, self.width - half_x)
            if not self.collides_player(next_x, current_z, half_x, half_z):
                current_x = next_x
            next_z = clamp(current_z + step_z, half_z, self.depth - half_z)
            if not self.collides_player(current_x, next_z, half_x, half_z):
                current_z = next_z
        return current_x, current_z


def load_world_data(chunk_size: float = 128.0) -> WorldData:
    config = load_data_json("game_config.json")
    raw = load_data_json("prototype_world.json")
    return WorldData(raw, chunk_size=float(config["culling"]["chunk_size"]))


def aabb_overlap(
    a_min_x: float,
    a_min_z: float,
    a_max_x: float,
    a_max_z: float,
    b_min_x: float,
    b_min_z: float,
    b_max_x: float,
    b_max_z: float,
) -> bool:
    return a_min_x < b_max_x and a_max_x > b_min_x and a_min_z < b_max_z and a_max_z > b_min_z


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)
