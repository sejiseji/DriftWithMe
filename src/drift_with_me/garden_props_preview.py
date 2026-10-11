"""Approved modular gardening props, staged only in the no-save week preview."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from drift_with_me.hex_assets import draw_scaled_sprite, placement_for_upright_height_billboard
from drift_with_me.math3d import Vec3, screen_to_ground_affine

SPECIES = ("white", "yellow", "redorange", "purple", "bluebell")
MATERIALS = ("soil", "gravel", "curbs")
ASSET_IDS = (
    "jlp1_stake_short",
    "jlp1_stake_tall",
    "jlp1_string_projected_layer",
    "jlp1_stakes_string_assembly",
    "jlp1_string_ground_source",
    *(f"jlp1_material_{name}" for name in MATERIALS),
    *(asset for name in SPECIES for asset in (f"jlp1_seedling_{name}", f"jlp1_tray_{name}")),
)


@dataclass(frozen=True)
class GardenProp:
    asset_id: str
    x: float
    z: float
    instance_id: str


@dataclass
class GardenPropsPreview:
    origin: tuple[float, float]
    materials: tuple[tuple[float, float], ...]
    trays: tuple[tuple[float, float], ...]
    layout: int = 0
    amount: int = 0
    parts: bool = False
    overlap: int = 0
    previous_time: float = 0.0
    actor_start: tuple[float, float] = (400.0, 600.0)
    props: tuple[GardenProp, ...] = field(default=(), init=False)
    links: tuple[tuple[Vec3, Vec3], ...] = field(default=(), init=False)

    @classmethod
    def for_camera(cls, camera, previous_time=0.0):
        def at(x, y):
            point = screen_to_ground_affine(
                camera, x * camera.viewport_width / 512, y * camera.viewport_height / 236
            )
            if point is None:
                raise ValueError("garden preview requires a valid affine camera")
            return point.x, point.y

        state = cls(
            origin=at(435, 122),
            materials=tuple(at(x, y) for x, y in ((150, 188), (183, 184), (216, 180))),
            trays=tuple(
                at(x, y) for x, y in ((327, 172), (354, 168), (381, 164), (339, 192), (366, 188))
            ),
            previous_time=previous_time,
        )
        state.rebuild()
        return state

    def rebuild(self):
        # World-space posts and elevated links can be freely rearranged. The
        # preprojected assembly and top-down source are alternate assets, not
        # additional transforms on these links.
        x, z = self.origin
        vertices = (
            ((-15, -8), (15, -8), (15, 8), (-15, 8))
            if self.layout == 0
            else ((-15, -8), (15, -8), (15, 0), (0, 0), (0, 12), (-15, 12))
        )
        roots = [(x + dx, z + dz) for dx, dz in vertices]
        if self.layout == 0:
            roots = [
                roots[0],
                ((roots[0][0] + roots[1][0]) / 2, roots[0][1]),
                *roots[1:3],
                ((roots[2][0] + roots[3][0]) / 2, roots[2][1]),
                roots[3],
            ]
        props = [
            GardenProp("jlp1_stake_short", px, pz, f"garden:stake:{i}")
            for i, (px, pz) in enumerate(roots)
        ]
        links = []
        for first, second in zip(roots, roots[1:] + roots[:1], strict=True):
            # Short depth-sorted segments let an actor cross either side of a
            # fence. Only the ground endpoints are projected, at knot height.
            length = math.hypot(second[0] - first[0], second[1] - first[1])
            count = max(1, math.ceil(length / 6))
            for i in range(count):
                a, b = i / count, (i + 1) / count
                links.append(
                    (
                        Vec3(
                            first[0] + (second[0] - first[0]) * a,
                            4,
                            first[1] + (second[1] - first[1]) * a,
                        ),
                        Vec3(
                            first[0] + (second[0] - first[0]) * b,
                            4,
                            first[1] + (second[1] - first[1]) * b,
                        ),
                    )
                )
        props.extend(
            GardenProp(f"jlp1_material_{name}", px, pz, f"garden:material:{name}")
            for i, (name, (px, pz)) in enumerate(zip(MATERIALS, self.materials, strict=True))
            if i >= self.amount
        )
        props.extend(
            GardenProp(f"jlp1_tray_{name}", px, pz, f"garden:tray:{name}")
            for name, (px, pz) in zip(SPECIES, self.trays, strict=True)
        )
        self.props, self.links = tuple(props), tuple(links)

    def elapsed(self, now):
        value = min(0.05, max(0.0, now - self.previous_time))
        self.previous_time = now
        return value


def bounds_visible(bounds, camera, margin=4):
    left, top, right, bottom = bounds
    return (
        right >= -margin
        and bottom >= -margin
        and left <= camera.viewport_width + margin
        and top <= camera.viewport_height + margin
    )


def garden_preview_draw_commands(renderer, model, camera):
    state = getattr(model, "garden_props_preview", None)
    if state is None or state.parts:
        return []
    from drift_with_me.render import DrawCommand

    commands = []
    for prop in state.props:
        asset = renderer.sprite_assets.get(prop.asset_id)
        if asset is None:
            continue
        placement = placement_for_upright_height_billboard(
            camera, asset.definition, Vec3(prop.x, 0, prop.z)
        )
        if placement is None or not bounds_visible(
            (placement.left, placement.top, placement.right, placement.bottom), camera
        ):
            continue
        commands.append(
            DrawCommand(
                depth=placement.depth,
                layer_bias=0,
                stable_id=prop.instance_id,
                draw=lambda asset=asset, placement=placement: draw_scaled_sprite(
                    renderer.pyxel, asset.frame(), asset.definition, placement
                ),
                atmosphere_strength=0.0,
            )
        )
    for i, (first, second) in enumerate(state.links):
        a, b = camera.project(first), camera.project(second)
        if (
            a is None
            or b is None
            or not bounds_visible(
                (min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y)), camera
            )
        ):
            continue
        midpoint = camera.project(Vec3((first.x + second.x) / 2, 0, (first.z + second.z) / 2))
        if midpoint is None:
            continue
        commands.append(
            DrawCommand(
                depth=midpoint.depth,
                layer_bias=1,
                stable_id=f"garden:string:{i:03d}",
                draw=lambda a=a, b=b: renderer.pyxel.line(
                    round(a.x), round(a.y), round(b.x), round(b.y), 15
                ),
                atmosphere_strength=0.0,
            )
        )
    return commands
