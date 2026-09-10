from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel
from drift_with_me.world import EnemySpawn, StaticObject, WorldData


@dataclass(frozen=True)
class DrawCommand:
    depth: float
    stable_id: str
    draw: Callable[[], None]


class Renderer:
    def __init__(self, pyxel_module) -> None:
        self.pyxel = pyxel_module

    def draw_scene(
        self, model: GameModel, camera: CameraState, presentation_time: float, debug: bool
    ) -> None:
        pyxel = self.pyxel
        pyxel.cls(1)
        self.draw_ground(model.world, camera)
        self.draw_safe_zones(model.world, camera)
        commands = self.world_commands(model, camera, presentation_time)
        for command in sorted(commands, key=lambda item: (-item.depth, item.stable_id)):
            command.draw()
        self.draw_barrier(model, camera)
        if debug:
            self.draw_debug_world(model, camera)

    def draw_ground(self, world: WorldData, camera: CameraState) -> None:
        pyxel = self.pyxel
        corners = [
            camera.project(Vec3(0.0, 0.0, 0.0)),
            camera.project(Vec3(world.width, 0.0, 0.0)),
            camera.project(Vec3(world.width, 0.0, world.depth)),
            camera.project(Vec3(0.0, 0.0, world.depth)),
        ]
        if all(point is not None for point in corners):
            p0, p1, p2, p3 = corners
            pyxel.tri(int(p0.x), int(p0.y), int(p1.x), int(p1.y), int(p2.x), int(p2.y), 3)
            pyxel.tri(int(p0.x), int(p0.y), int(p2.x), int(p2.y), int(p3.x), int(p3.y), 3)

        for line in range(0, int(world.width) + 1, 128):
            self.draw_world_line(camera, Vec3(line, 0.0, 0.0), Vec3(line, 0.0, world.depth), 11)
            self.draw_world_line(camera, Vec3(0.0, 0.0, line), Vec3(world.width, 0.0, line), 11)
        self.draw_world_line(camera, Vec3(0.0, 0.0, 0.0), Vec3(world.width, 0.0, 0.0), 7)
        self.draw_world_line(
            camera, Vec3(world.width, 0.0, 0.0), Vec3(world.width, 0.0, world.depth), 7
        )
        self.draw_world_line(
            camera, Vec3(world.width, 0.0, world.depth), Vec3(0.0, 0.0, world.depth), 7
        )
        self.draw_world_line(camera, Vec3(0.0, 0.0, world.depth), Vec3(0.0, 0.0, 0.0), 7)

    def draw_safe_zones(self, world: WorldData, camera: CameraState) -> None:
        for zone in world.safe_zones:
            self.draw_world_circle(camera, zone.x, zone.z, zone.radius, 12)

    def world_commands(
        self,
        model: GameModel,
        camera: CameraState,
        presentation_time: float,
    ) -> list[DrawCommand]:
        commands: list[DrawCommand] = []
        for obj in model.world.objects:
            anchor = camera.project(Vec3(obj.x, 0.0, obj.z))
            if anchor is None:
                continue
            commands.append(
                DrawCommand(
                    depth=anchor.depth,
                    stable_id=obj.id,
                    draw=lambda obj=obj: self.draw_object(obj, camera),
                )
            )
        for enemy in model.world.enemies:
            anchor = camera.project(Vec3(enemy.x, 0.0, enemy.z))
            if anchor is None:
                continue
            commands.append(
                DrawCommand(
                    depth=anchor.depth,
                    stable_id=enemy.id,
                    draw=lambda enemy=enemy: self.draw_enemy(enemy, camera),
                )
            )
        player_anchor = camera.project(Vec3(model.player.x, 0.0, model.player.z))
        if player_anchor is not None:
            commands.append(
                DrawCommand(
                    depth=player_anchor.depth,
                    stable_id="player",
                    draw=lambda: self.draw_player(model, camera, presentation_time),
                )
            )
        return commands

    def draw_object(self, obj: StaticObject, camera: CameraState) -> None:
        if obj.solid:
            height = obj.height if obj.height > 0 else 24.0
            color = 5 if obj.kind == "obstacle" else 4
            self.draw_box(camera, obj.x, obj.z, obj.half_x, obj.half_z, height, 0.0, color)
            return
        point = camera.project(Vec3(obj.x, 0.0, obj.z))
        if point is None:
            return
        pyxel = self.pyxel
        x = int(point.x)
        y = int(point.y)
        if obj.kind == "water_station":
            color = 12 if obj.supply == "working" else 13
            pyxel.rect(x - 4, y - 12, 8, 12, color)
            pyxel.line(x - 6, y - 10, x + 6, y - 10, 7)
        elif obj.kind == "solar_station":
            pyxel.tri(x, y - 14, x - 7, y - 2, x + 7, y - 2, 10)
        elif obj.inspectable:
            pyxel.rectb(x - 5, y - 13, 10, 12, 7)
            pyxel.pset(x, y - 7, 10)
        else:
            pyxel.pset(x, y, 7)

    def draw_enemy(self, enemy: EnemySpawn, camera: CameraState) -> None:
        point = camera.project(Vec3(enemy.x, 4.0, enemy.z))
        if point is None:
            return
        pyxel = self.pyxel
        radius = max(3, int(900 / max(point.depth, 1.0)))
        color = 8 if enemy.kind == "normal" else 2
        x = int(point.x)
        y = int(point.y)
        pyxel.circ(x, y, radius, color)
        for index in range(8):
            angle = index * math.tau / 8.0
            pyxel.line(
                x + int(math.cos(angle) * radius),
                y + int(math.sin(angle) * radius),
                x + int(math.cos(angle) * (radius + 3)),
                y + int(math.sin(angle) * (radius + 3)),
                7,
            )

    def draw_player(self, model: GameModel, camera: CameraState, presentation_time: float) -> None:
        hover = float(model.config["player"]["visual_hover_base"])
        hover += math.sin(
            presentation_time / float(model.config["player"]["visual_hover_period_sec"]) * math.tau
        )
        hover *= float(model.config["player"]["visual_hover_amplitude"]) / 2.0
        shadow = camera.project(Vec3(model.player.x, 0.0, model.player.z))
        if shadow is not None:
            radius = max(3, int(1200 / max(shadow.depth, 1.0)))
            self.pyxel.elli(
                int(shadow.x - radius),
                int(shadow.y - radius // 3),
                radius * 2,
                max(2, radius // 2),
                0,
            )
        half = model.player_cube_size / 2.0
        self.draw_box(
            camera, model.player.x, model.player.z, half, half, model.player_cube_size, hover, 11
        )

    def draw_barrier(self, model: GameModel, camera: CameraState) -> None:
        if not model.player.barrier_active:
            return
        radius = float(model.config["barrier"]["radius"])
        self.draw_world_circle(camera, model.player.x, model.player.z, radius, 12)

    def draw_box(
        self,
        camera: CameraState,
        x: float,
        z: float,
        half_x: float,
        half_z: float,
        height: float,
        y_offset: float,
        color: int,
    ) -> None:
        bottom = y_offset
        top = y_offset + height
        vertices = {
            "nwl": Vec3(x - half_x, bottom, z - half_z),
            "nel": Vec3(x + half_x, bottom, z - half_z),
            "sel": Vec3(x + half_x, bottom, z + half_z),
            "swl": Vec3(x - half_x, bottom, z + half_z),
            "nwh": Vec3(x - half_x, top, z - half_z),
            "neh": Vec3(x + half_x, top, z - half_z),
            "seh": Vec3(x + half_x, top, z + half_z),
            "swh": Vec3(x - half_x, top, z + half_z),
        }
        faces = [
            ("top", ("nwh", "neh", "seh", "swh"), min(color + 1, 15)),
            ("north", ("nwl", "nel", "neh", "nwh"), color),
            ("east", ("nel", "sel", "seh", "neh"), max(color - 1, 1)),
            ("south", ("sel", "swl", "swh", "seh"), color),
            ("west", ("swl", "nwl", "nwh", "swh"), max(color - 1, 1)),
        ]
        projected_faces = []
        for name, keys, face_color in faces:
            projected = [camera.project(vertices[key]) for key in keys]
            if any(point is None for point in projected):
                continue
            avg_depth = sum(point.depth for point in projected if point is not None) / len(
                projected
            )
            projected_faces.append((avg_depth, name, projected, face_color))
        for _depth, _name, points, face_color in sorted(projected_faces, key=lambda item: -item[0]):
            p0, p1, p2, p3 = points
            self.pyxel.tri(
                int(p0.x), int(p0.y), int(p1.x), int(p1.y), int(p2.x), int(p2.y), face_color
            )
            self.pyxel.tri(
                int(p0.x), int(p0.y), int(p2.x), int(p2.y), int(p3.x), int(p3.y), face_color
            )
            for start, end in ((p0, p1), (p1, p2), (p2, p3), (p3, p0)):
                self.pyxel.line(int(start.x), int(start.y), int(end.x), int(end.y), 0)

    def draw_world_circle(
        self, camera: CameraState, x: float, z: float, radius: float, color: int
    ) -> None:
        last = None
        for index in range(33):
            angle = index * math.tau / 32.0
            point = camera.project(
                Vec3(x + math.cos(angle) * radius, 0.0, z + math.sin(angle) * radius)
            )
            if point is not None and last is not None:
                self.pyxel.line(int(last.x), int(last.y), int(point.x), int(point.y), color)
            last = point

    def draw_world_line(self, camera: CameraState, start: Vec3, end: Vec3, color: int) -> None:
        a = camera.project(start)
        b = camera.project(end)
        if a is None or b is None:
            return
        self.pyxel.line(int(a.x), int(a.y), int(b.x), int(b.y), color)

    def draw_debug_world(self, model: GameModel, camera: CameraState) -> None:
        point = camera.project(Vec3(model.player.x, 0.0, model.player.z))
        if point is None:
            return
        self.pyxel.circb(int(point.x), int(point.y), 5, 7)
