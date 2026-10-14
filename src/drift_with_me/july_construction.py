"""July-only work plot and stockyard; approved props share visual/collision roots."""

from dataclasses import dataclass
from math import ceil, hypot

from drift_with_me.garden_props_preview import GardenProp
from drift_with_me.math3d import Vec3

PREFIX = "jul_build_"
# The east opening faces Fuji. No full-rectangle collider occupies the plot.
FENCE_EDGES = (
    ((140, 352), (220, 352)),
    ((220, 352), (220, 364)),
    ((220, 400), (220, 412)),
    ((220, 412), (140, 412)),
    ((140, 412), (140, 352)),
)
STOCK = (
    ("jlp1_material_soil", 212, 430),
    ("jlp1_material_gravel", 236, 430),
    ("jlp1_material_curbs", 260, 430),
    ("jlp1_tray_white", 200, 454),
    ("jlp1_tray_yellow", 224, 454),
    ("jlp1_tray_redorange", 248, 454),
    ("jlp1_tray_purple", 212, 478),
    ("jlp1_tray_bluebell", 236, 478),
)


@dataclass(frozen=True)
class ConstructionLayout:
    props: tuple[GardenProp, ...]
    links: tuple[tuple[Vec3, Vec3], ...]
    parts: bool = False
    id_prefix: str = PREFIX


def build_layout():
    props, colliders, links = [], [], []

    def collider(ident, x, z, hx, hz):
        colliders.append(
            {
                "id": PREFIX + ident,
                "kind": "construction_collision",
                "position": [x, 0, z],
                "half_extents_xz": [hx, hz],
                "solid": True,
                "height": 4,
            }
        )

    roots = set()
    for i, (first, second) in enumerate(FENCE_EDGES):
        roots.update((first, second))
        dx, dz = second[0] - first[0], second[1] - first[1]
        collider(
            f"edge_{i}",
            (first[0] + second[0]) / 2,
            (first[1] + second[1]) / 2,
            max(abs(dx) / 2, 0.7),
            max(abs(dz) / 2, 0.7),
        )
        count = max(1, ceil(hypot(dx, dz) / 6))
        for j in range(count):
            links.append(
                tuple(
                    Vec3(first[0] + dx * t, 4, first[1] + dz * t)
                    for t in (j / count, (j + 1) / count)
                )
            )
        for j in range(1, max(1, ceil(hypot(dx, dz) / 28))):
            t = j / ceil(hypot(dx, dz) / 28)
            roots.add((first[0] + dx * t, first[1] + dz * t))
    for i, (x, z) in enumerate(sorted(roots)):
        tall = (x, z) in ((220, 364), (220, 400))
        props.append(
            GardenProp(
                "jlp1_stake_tall" if tall else "jlp1_stake_short", x, z, PREFIX + f"stake_{i}"
            )
        )
        collider(f"stake_{i}", x, z, 1.2, 1.2)
    for i, (asset, x, z) in enumerate(STOCK):
        props.append(GardenProp(asset, x, z, PREFIX + f"stock_{i}"))
        # Ground footprint of the approved preprojected pile/tray, not its full sprite height.
        collider(f"stock_{i}", x, z + 2, 7, 5)
    return ConstructionLayout(tuple(props), tuple(links)), colliders
