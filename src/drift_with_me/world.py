from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from drift_with_me.config import load_data_json
from drift_with_me.math3d import CameraState, Vec3


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
    occludes_player: bool = False
    sprite_world_width: float = 0.0
    sprite_world_height: float = 0.0
    reaction_radius: float = 0.0

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
class ObjectVisualBounds:
    min_x: float
    min_z: float
    max_x: float
    max_z: float
    height: float


@dataclass(frozen=True)
class GroundDetail:
    id: str
    chunk_id: tuple[int, int]
    x: float
    z: float
    phase: int
    color: int


@dataclass(frozen=True)
class StaticVisibilityQuery:
    chunk_ids: tuple[tuple[int, int], ...]
    objects: tuple[StaticObject, ...]

    @property
    def candidate_chunk_count(self) -> int:
        return len(self.chunk_ids)

    @property
    def candidate_object_count(self) -> int:
        return len(self.objects)


@dataclass(frozen=True)
class EnemySpawn:
    id: str
    kind: str
    x: float
    z: float
    home_x: float
    home_z: float


@dataclass(frozen=True)
class SafeZone:
    id: str
    x: float
    z: float
    radius: float


@dataclass(frozen=True)
class CameraZone:
    id: str
    min_x: float
    min_z: float
    max_x: float
    max_z: float
    priority: int
    mode: str
    target: Vec3
    zoom: float
    yaw_deg: float | None
    pitch_deg: float | None
    enter_sec: float
    leave_sec: float
    exit_margin: float
    once: bool
    freeze_world: bool

    def contains(self, x: float, z: float) -> bool:
        return self.min_x <= x <= self.max_x and self.min_z <= z <= self.max_z

    def contains_with_margin(self, x: float, z: float) -> bool:
        return (
            self.min_x - self.exit_margin <= x <= self.max_x + self.exit_margin
            and self.min_z - self.exit_margin <= z <= self.max_z + self.exit_margin
        )


@dataclass(frozen=True)
class CameraCue:
    target: Vec3 | None = None
    target_object: str | None = None
    resolve_current_base: bool = False
    zoom: float | None = None
    yaw_deg: float | None = None
    pitch_deg: float | None = None
    blend_sec: float = 0.0
    hold_sec: float = 0.0


@dataclass(frozen=True)
class CameraSequence:
    id: str
    activation: str
    freeze_world: bool
    cues: tuple[CameraCue, ...]


class WorldData:
    def __init__(
        self,
        raw: dict[str, Any],
        chunk_size: float = 128.0,
        static_visual_max_height: float = 96.0,
        visual_detail_per_chunk: int = 1,
    ) -> None:
        self.raw = raw
        ground = raw["ground"]
        self.width = float(ground["width_cells"] * ground["cell_size"])
        self.depth = float(ground["depth_cells"] * ground["cell_size"])
        self.cell_size = float(ground["cell_size"])
        self.chunk_size = chunk_size
        self.chunk_cols = max(1, math.ceil(self.width / self.chunk_size))
        self.chunk_rows = max(1, math.ceil(self.depth / self.chunk_size))
        self.static_visual_max_height = static_visual_max_height
        self.visual_detail_per_chunk = max(0, visual_detail_per_chunk)
        self.spawn_x = float(raw["spawn"]["player"][0])
        self.spawn_z = float(raw["spawn"]["player"][2])
        self.objects = tuple(self._load_object(item) for item in raw["objects"])
        self.enemies = tuple(self._load_enemy(item) for item in raw["enemies"])
        self.safe_zones = tuple(
            SafeZone(
                id=str(item["id"]),
                x=float(item["center_xz"][0]),
                z=float(item["center_xz"][1]),
                radius=float(item["radius"]),
            )
            for item in raw["safe_zones"]
        )
        self.camera_zones = {
            zone.id: zone for zone in (self._load_camera_zone(item) for item in raw["camera_zones"])
        }
        self.camera_sequences = {
            sequence.id: sequence
            for sequence in (self._load_camera_sequence(item) for item in raw["camera_sequences"])
        }
        self.texts = raw["texts"]
        self._solid_index = self._build_solid_index()
        self._visual_index = self._build_visual_index()
        self._visual_chunk_heights = self._build_visual_chunk_heights()
        self.ground_details = self._build_ground_details()

    def _load_object(self, item: dict[str, Any]) -> StaticObject:
        position = item["position"]
        half_x, half_z = item.get("half_extents_xz", [0.0, 0.0])
        sprite_width, sprite_height = item.get("sprite_world_size", [0.0, 0.0])
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
            occludes_player=bool(item.get("occludes_player", False)),
            sprite_world_width=float(sprite_width),
            sprite_world_height=float(sprite_height),
            reaction_radius=float(item.get("reaction_radius", 0.0)),
        )

    def _load_enemy(self, item: dict[str, Any]) -> EnemySpawn:
        position = item["position"]
        home = item.get("home", position)
        return EnemySpawn(
            id=str(item["id"]),
            kind=str(item["kind"]),
            x=float(position[0]),
            z=float(position[2]),
            home_x=float(home[0]),
            home_z=float(home[2]),
        )

    def _load_camera_zone(self, item: dict[str, Any]) -> CameraZone:
        min_x, min_z, max_x, max_z = item["trigger_rect_xz"]
        target = item["target"]
        return CameraZone(
            id=str(item["id"]),
            min_x=float(min_x),
            min_z=float(min_z),
            max_x=float(max_x),
            max_z=float(max_z),
            priority=int(item["priority"]),
            mode=str(item["mode"]),
            target=Vec3(float(target[0]), float(target[1]), float(target[2])),
            zoom=float(item["zoom"]),
            yaw_deg=float(item["yaw_deg"]) if "yaw_deg" in item else None,
            pitch_deg=float(item["pitch_deg"]) if "pitch_deg" in item else None,
            enter_sec=float(item["enter_sec"]),
            leave_sec=float(item["leave_sec"]),
            exit_margin=float(item["exit_margin"]),
            once=bool(item.get("once", False)),
            freeze_world=bool(item.get("freeze_world", False)),
        )

    def _load_camera_sequence(self, item: dict[str, Any]) -> CameraSequence:
        return CameraSequence(
            id=str(item["id"]),
            activation=str(item["activation"]),
            freeze_world=bool(item.get("freeze_world", False)),
            cues=tuple(self._load_camera_cue(cue) for cue in item["cues"]),
        )

    def _load_camera_cue(self, item: dict[str, Any]) -> CameraCue:
        target: Vec3 | None = None
        resolve_current_base = False
        raw_target = item.get("target")
        if isinstance(raw_target, str):
            resolve_current_base = raw_target == "resolve_current_base"
        elif raw_target is not None:
            target = Vec3(float(raw_target[0]), float(raw_target[1]), float(raw_target[2]))

        return CameraCue(
            target=target,
            target_object=item.get("target_object"),
            resolve_current_base=resolve_current_base,
            zoom=float(item["zoom"]) if "zoom" in item else None,
            yaw_deg=float(item["yaw_deg"]) if "yaw_deg" in item else None,
            pitch_deg=float(item["pitch_deg"]) if "pitch_deg" in item else None,
            blend_sec=float(item.get("blend_sec", 0.0)),
            hold_sec=float(item.get("hold_sec", 0.0)),
        )

    def object_by_id(self, object_id: str) -> StaticObject | None:
        for obj in self.objects:
            if obj.id == object_id:
                return obj
        return None

    @property
    def solid_objects(self) -> tuple[StaticObject, ...]:
        return tuple(obj for obj in self.objects if obj.solid)

    def _chunk_span(
        self, min_x: float, min_z: float, max_x: float, max_z: float
    ) -> tuple[range, range]:
        min_cx = self._chunk_x(min_x)
        min_cz = self._chunk_z(min_z)
        max_cx = self._chunk_x(max_x)
        max_cz = self._chunk_z(max_z)
        return range(min_cx, max_cx + 1), range(min_cz, max_cz + 1)

    def _chunk_x(self, x: float) -> int:
        return int(clamp(math.floor(x / self.chunk_size), 0, self.chunk_cols - 1))

    def _chunk_z(self, z: float) -> int:
        return int(clamp(math.floor(z / self.chunk_size), 0, self.chunk_rows - 1))

    @property
    def chunk_ids(self) -> tuple[tuple[int, int], ...]:
        return tuple((cx, cz) for cz in range(self.chunk_rows) for cx in range(self.chunk_cols))

    def _build_solid_index(self) -> dict[tuple[int, int], list[StaticObject]]:
        index: dict[tuple[int, int], list[StaticObject]] = {}
        for obj in self.solid_objects:
            x_range, z_range = self._chunk_span(obj.min_x, obj.min_z, obj.max_x, obj.max_z)
            for cx in x_range:
                for cz in z_range:
                    index.setdefault((cx, cz), []).append(obj)
        return index

    def object_visual_bounds(self, obj: StaticObject) -> ObjectVisualBounds:
        visual_width = max(obj.sprite_world_width, obj.half_x * 2.0, 12.0)
        visual_depth = max(obj.half_z * 2.0, min(visual_width, 24.0))
        visual_height = max(obj.sprite_world_height, obj.height, 16.0)
        half_x = visual_width / 2.0
        half_z = visual_depth / 2.0
        return ObjectVisualBounds(
            min_x=obj.x - half_x,
            min_z=obj.z - half_z,
            max_x=obj.x + half_x,
            max_z=obj.z + half_z,
            height=min(max(visual_height, 1.0), self.static_visual_max_height),
        )

    def _build_visual_index(self) -> dict[tuple[int, int], list[StaticObject]]:
        index: dict[tuple[int, int], list[StaticObject]] = {}
        for obj in self.objects:
            bounds = self.object_visual_bounds(obj)
            x_range, z_range = self._chunk_span(
                bounds.min_x, bounds.min_z, bounds.max_x, bounds.max_z
            )
            for cx in x_range:
                for cz in z_range:
                    index.setdefault((cx, cz), []).append(obj)
        return index

    def _build_visual_chunk_heights(self) -> dict[tuple[int, int], float]:
        heights = {chunk_id: 8.0 for chunk_id in self.chunk_ids}
        for chunk_id, objects in self._visual_index.items():
            heights[chunk_id] = max(
                heights.get(chunk_id, 8.0),
                *(self.object_visual_bounds(obj).height for obj in objects),
            )
        return heights

    def _build_ground_details(self) -> tuple[GroundDetail, ...]:
        details: list[GroundDetail] = []
        for cx, cz in self.chunk_ids:
            for index in range(self.visual_detail_per_chunk):
                seed = stable_u32(cx, cz, index)
                x_offset = 16.0 + (seed & 0xFFFF) / 0xFFFF * (self.chunk_size - 32.0)
                z_offset = 16.0 + ((seed >> 16) & 0xFFFF) / 0xFFFF * (self.chunk_size - 32.0)
                details.append(
                    GroundDetail(
                        id=f"detail_{cx}_{cz}_{index}",
                        chunk_id=(cx, cz),
                        x=min(self.width - 1.0, cx * self.chunk_size + x_offset),
                        z=min(self.depth - 1.0, cz * self.chunk_size + z_offset),
                        phase=seed % 4,
                        color=11 if seed & 1 else 3,
                    )
                )
        return tuple(details)

    def ground_details_for_chunks(
        self, chunk_ids: tuple[tuple[int, int], ...]
    ) -> tuple[GroundDetail, ...]:
        active = set(chunk_ids)
        return tuple(detail for detail in self.ground_details if detail.chunk_id in active)

    def query_visible_static_objects(
        self, camera: CameraState, screen_margin_px: float
    ) -> StaticVisibilityQuery:
        chunk_ids: list[tuple[int, int]] = []
        candidate_ids: set[str] = set()
        for chunk_id in self.chunk_ids:
            if not self.chunk_may_be_visible(chunk_id, camera, screen_margin_px):
                continue
            chunk_ids.append(chunk_id)
            for obj in self._visual_index.get(chunk_id, ()):
                candidate_ids.add(obj.id)
        return StaticVisibilityQuery(
            chunk_ids=tuple(chunk_ids),
            objects=tuple(obj for obj in self.objects if obj.id in candidate_ids),
        )

    def chunk_may_be_visible(
        self, chunk_id: tuple[int, int], camera: CameraState, margin_px: float
    ) -> bool:
        cx, cz = chunk_id
        min_x = cx * self.chunk_size
        min_z = cz * self.chunk_size
        max_x = min(self.width, min_x + self.chunk_size)
        max_z = min(self.depth, min_z + self.chunk_size)
        height = self._visual_chunk_heights.get(chunk_id, 8.0)
        rect = project_world_aabb(camera, min_x, min_z, max_x, max_z, height)
        if rect is None:
            return False
        min_sx, min_sy, max_sx, max_sy = rect
        return rects_overlap(
            min_sx,
            min_sy,
            max_sx,
            max_sy,
            -margin_px,
            -margin_px,
            camera.viewport_width + margin_px,
            camera.viewport_height + margin_px,
        )

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

    def point_in_safe_zone(self, x: float, z: float) -> bool:
        return any(math.hypot(x - zone.x, z - zone.z) <= zone.radius for zone in self.safe_zones)

    def collides_enemy_circle(self, x: float, z: float, radius: float) -> bool:
        if x - radius < 0.0 or x + radius > self.width:
            return True
        if z - radius < 0.0 or z + radius > self.depth:
            return True
        for zone in self.safe_zones:
            if math.hypot(x - zone.x, z - zone.z) < zone.radius + radius:
                return True
        for obj in self.query_solids(x - radius, z - radius, x + radius, z + radius):
            closest_x = clamp(x, obj.min_x, obj.max_x)
            closest_z = clamp(z, obj.min_z, obj.max_z)
            if (x - closest_x) ** 2 + (z - closest_z) ** 2 < radius * radius:
                return True
        return False

    def move_enemy_circle_sliding(
        self,
        x: float,
        z: float,
        delta_x: float,
        delta_z: float,
        radius: float,
        max_step: float = 4.0,
    ) -> tuple[float, float]:
        steps = max(1, math.ceil(max(abs(delta_x), abs(delta_z)) / max_step))
        step_x = delta_x / steps
        step_z = delta_z / steps
        current_x = x
        current_z = z
        for _ in range(steps):
            next_x = clamp(current_x + step_x, radius, self.width - radius)
            if not self.collides_enemy_circle(next_x, current_z, radius):
                current_x = next_x
            next_z = clamp(current_z + step_z, radius, self.depth - radius)
            if not self.collides_enemy_circle(current_x, next_z, radius):
                current_z = next_z
        return current_x, current_z


def load_world_data(chunk_size: float = 128.0) -> WorldData:
    config = load_data_json("game_config.json")
    raw = load_data_json("prototype_world.json")
    culling = config["culling"]
    return WorldData(
        raw,
        chunk_size=float(culling["chunk_size"]),
        static_visual_max_height=float(culling["static_visual_max_height"]),
        visual_detail_per_chunk=int(culling["visual_detail_per_chunk"]),
    )


def project_world_aabb(
    camera: CameraState,
    min_x: float,
    min_z: float,
    max_x: float,
    max_z: float,
    height: float,
) -> tuple[float, float, float, float] | None:
    points = []
    for x in (min_x, max_x):
        for y in (0.0, height):
            for z in (min_z, max_z):
                point = camera.project(Vec3(x, y, z))
                if point is not None:
                    points.append(point)
    if not points:
        return None
    return (
        min(point.x for point in points),
        min(point.y for point in points),
        max(point.x for point in points),
        max(point.y for point in points),
    )


def rects_overlap(
    a_min_x: float,
    a_min_y: float,
    a_max_x: float,
    a_max_y: float,
    b_min_x: float,
    b_min_y: float,
    b_max_x: float,
    b_max_y: float,
) -> bool:
    return a_min_x < b_max_x and a_max_x > b_min_x and a_min_y < b_max_y and a_max_y > b_min_y


def stable_u32(a: int, b: int, c: int = 0) -> int:
    value = (a * 0x9E3779B1) ^ (b * 0x85EBCA77) ^ (c * 0xC2B2AE3D) ^ 0x27D4EB2F
    value &= 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return value


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
