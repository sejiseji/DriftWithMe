"""Deterministic scenery only: the saved work week selects the park layout."""

import math
from copy import deepcopy
from dataclasses import dataclass

from drift_with_me.garden_props_preview import GardenProp, garden_preview_draw_commands
from drift_with_me.july_construction import ConstructionLayout
from drift_with_me.math3d import Vec3
from drift_with_me.week_cycle import WorkWeek
from drift_with_me.world import WorldData, load_world_data

PREFIX = "ne_park_"
PLOT = (800, 840, 904, 912)
BED = (832, 860, 872, 888)
PAVING = ((880, 840, 904, 916), (832, 840, 880, 856), (804, 892, 880, 916), (804, 884, 828, 892))
BENCH = (816, 900)
EDGES = (
    ((800, 840), (904, 840)),
    ((904, 840), (904, 848)),
    ((904, 904), (904, 912)),
    ((904, 912), (800, 912)),
    ((800, 912), (800, 840)),
)
PREVIEW_WEEKS = tuple(WorkWeek(7, n) for n in range(1, 5)) + (WorkWeek(8, 1),)


def park_stage(week):
    return 0 if week.month < 7 else min(week.number, 4) if week.month == 7 else 5


@dataclass(frozen=True)
class ParkLayout:
    stage: int
    props: ConstructionLayout


def contains(rect, x, z):
    return rect[0] <= x <= rect[2] and rect[1] <= z <= rect[3]


def park_ground_covers(layout, x, z, padding=0):
    if layout is None:
        return False
    rects = (PLOT, *PAVING) if layout.stage >= 3 else (PLOT,)
    return any(
        contains((a - padding, b - padding, c + padding, d + padding), x, z) for a, b, c, d in rects
    )


def install_park_world(app, week=None):
    """Never reset actors, resources, authored progress or enemy state."""
    if not hasattr(app, "world"):
        return
    week = week or getattr(app, "work_week", WorkWeek())
    stage = park_stage(week)
    raw = deepcopy(app.world.raw)
    # Restore only the one managed tree from authored data, including its exact collider.
    tree = next(o for o in load_world_data().raw["objects"] if o["id"] == "tree_33")
    raw["objects"] = [
        o for o in raw["objects"] if not o["id"].startswith(PREFIX) and o["id"] != "tree_33"
    ]
    raw["objects"].append(tree)
    props, links = [], []

    def collider(name, x, z, hx, hz, height=4):
        raw["objects"].append(
            dict(
                id=PREFIX + name,
                kind="construction_collision",
                position=[x, 0, z],
                half_extents_xz=[hx, hz],
                solid=True,
                height=height,
            )
        )

    if stage:
        raw["objects"] = [o for o in raw["objects"] if o["id"] != "tree_33"]
        collider("stump", 820, 876, 6, 6, 6)
        if stage <= 2:
            for i, (a, b) in enumerate(EDGES):
                # Stage one shows layout stakes; the continuous string belongs to week two.
                if stage == 2:
                    collider(
                        f"edge{i}",
                        (a[0] + b[0]) / 2,
                        (a[1] + b[1]) / 2,
                        max(abs(a[0] - b[0]) / 2, 0.7),
                        max(abs(a[1] - b[1]) / 2, 0.7),
                    )
                    count = max(1, int(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 / 6) + 1)
                    for j in range(count):
                        links.append(
                            tuple(
                                Vec3(a[0] + (b[0] - a[0]) * t, 4, a[1] + (b[1] - a[1]) * t)
                                for t in (j / count, (j + 1) / count)
                            )
                        )
            for i, (x, z) in enumerate(sorted({p for e in EDGES for p in e})):
                props.append(GardenProp("jlp1_stake_short", x, z, PREFIX + f"post{i}"))
                collider(f"post{i}", x, z, 1.2, 1.2)
            props.append(GardenProp("jlp1_material_soil", 840, 892, PREFIX + "soil"))
            collider("soil", 840, 894, 7, 5)
        if stage >= 4:
            collider("bench", *BENCH, 6, 15, 19)
            # Decorative planting, independent of the five-plot player arrangement.
            for i, ident in enumerate(("jun_w4_north", "jun_w4_east", "jun_w4_south")):
                for row in range(2 if stage == 4 else 3):
                    props.append(
                        GardenProp(
                            ident,
                            840 + i * 12,
                            866 + row * 10,
                            PREFIX + f"flower{i}_{row}",
                            world_scale=1.0,
                        )
                    )
    layout = ParkLayout(stage, ConstructionLayout(tuple(props), tuple(links))) if stage else None
    world = WorldData(
        raw,
        app.world.chunk_size,
        app.world.static_visual_max_height,
        app.world.visual_detail_per_chunk,
    )
    world.east_site_access_ready = app.world.east_site_access_ready
    app.world = app.model.world = world
    app.model.northeast_park = layout
    # Existing paths reference the previous spatial index; actors themselves remain untouched.
    app.model.cancel_auto_move()
    if hasattr(app, "pending_auto_move_goal"):
        app.pending_auto_move_goal = None


def draw_park_ground(renderer, model, camera):
    layout = getattr(model, "northeast_park", None)
    if layout is None:
        return
    renderer.draw_ground_rect(camera, PLOT, 3 if layout.stage >= 4 else 4)
    if layout.stage == 1:
        for x in range(808, 897, 16):
            renderer.draw_ground_rect(camera, (x, 844, x + 4, 908), 9)
    if layout.stage >= 3:
        for rect in PAVING:
            renderer.draw_ground_rect(camera, rect, 13)
        # Sparse, low-contrast joints; no dense cracked-concrete texture.
        for z in (864, 888):
            renderer.draw_ground_rect(camera, (880, z, 904, z + 0.6), 5)
        renderer.draw_ground_rect(camera, (856, 840, 856.6, 856), 5)
    renderer.draw_ground_rect(camera, BED, 4 if layout.stage < 5 else 3)
    # W2 observation remains on earth; later paving does not erase saved observations.
    if layout.stage == 2:
        renderer.draw_world_line(camera, Vec3(890, 0.2, 888), Vec3(898, 0.2, 880), 5)


def park_draw_commands(renderer, model, camera):
    from drift_with_me.render import DrawCommand

    layout = getattr(model, "northeast_park", None)
    if layout is None:
        return []
    commands = garden_preview_draw_commands(renderer, model, camera, layout.props)

    def box(name, x, z, hx, hz, height, y, color):
        for depth, face, points, _shade in renderer.project_box_faces(
            camera, x, z, hx, hz, height, y, color
        ):
            commands.append(
                DrawCommand(
                    depth=depth,
                    layer_bias=0,
                    stable_id=PREFIX + name + face,
                    draw=lambda p=points, c=(9 if face == "top" else color): (
                        renderer.draw_projected_box_face(p, c)
                    ),
                )
            )

    # A low octagonal trunk with a pale cut face and growth ring, not a wooden crate.
    ring = [
        (820 + 6 * math.cos(i * math.tau / 8), 876 + 6 * math.sin(i * math.tau / 8))
        for i in range(8)
    ]
    for i, (a, b) in enumerate(zip(ring, ring[1:] + ring[:1], strict=True)):
        points = [
            camera.project(Vec3(x, y, z))
            for x, y, z in ((a[0], 0, a[1]), (b[0], 0, b[1]), (b[0], 5, b[1]), (a[0], 5, a[1]))
        ]
        if all(p is not None for p in points):
            commands.append(
                DrawCommand(
                    depth=sum(p.depth for p in points) / 4,
                    layer_bias=0,
                    stable_id=PREFIX + f"bark{i}",
                    draw=lambda p=points, c=4 if i % 2 else 9: renderer.draw_projected_box_face(
                        p, c
                    ),
                )
            )

    def cut_face():
        center = camera.project(Vec3(820, 5, 876))
        if center is None:
            return
        for a, b in zip(ring, ring[1:] + ring[:1], strict=True):
            pa, pb = (camera.project(Vec3(p[0], 5, p[1])) for p in (a, b))
            if pa is not None and pb is not None:
                renderer.pyxel.tri(
                    int(center.x), int(center.y), int(pa.x), int(pa.y), int(pb.x), int(pb.y), 15
                )
        for i in range(12):
            a, b = i * math.tau / 12, (i + 1) * math.tau / 12
            renderer.draw_world_line(
                camera,
                Vec3(820 + 3 * math.cos(a), 5.1, 876 + 3 * math.sin(a)),
                Vec3(820 + 3 * math.cos(b), 5.1, 876 + 3 * math.sin(b)),
                4,
            )

    anchor = camera.project(Vec3(820, 5, 876))
    if anchor is not None:
        commands.append(
            DrawCommand(
                depth=anchor.depth, layer_bias=1, stable_id=PREFIX + "cut_face", draw=cut_face
            )
        )
    if layout.stage >= 4:
        x, z = BENCH
        box("seat", x, z, 5, 14, 2, 8, 4)
        # Back is west of the seat, so the bench looks east toward the new flowerbed.
        box("back", x - 4, z, 1, 14, 8, 10, 4)
        for i, dz in enumerate((-10, 10)):
            box(f"leg{i}", x, z + dz, 3, 1.5, 8, 0, 5)
    return commands
