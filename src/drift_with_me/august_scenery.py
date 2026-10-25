"""Saved August phase selects deterministic, cosmetic-only weather and recovery."""

import math
from functools import lru_cache

from drift_with_me.math3d import Vec3

# Ground-space routes, including the actual July garden and eastern water tap.
ROUTES = (
    ((160, -32), (160, 160)),
    ((160, 160), (216, 320), (216, 540), (196, 668)),
    ((160, 160), (244, 300), (244, 416), (432, 416), (640, 300), (816, 232)),
    ((816, 232), (880, 400), (952, 640), (952, 780), (904, 824), (868, 848)),
)
TREE_RING = tuple(
    (124 + 78 * math.cos(i * math.tau / 32), 682 + 85 * math.sin(i * math.tau / 32))
    for i in range(33)
)
MAX_RAIN = 120
MAX_SPLASHES = 16


def environment(app):
    if app.august_active() and app.work_week.number == 4:
        return False, True
    if not app.august_active() or app.work_week.number != 3:
        return False, False
    done = app.office.august_progress.phase == "done"
    return not done, done


@lru_cache(maxsize=1)
def planks():
    result = []
    for route in (*ROUTES, TREE_RING):
        for a, b in zip(route, route[1:], strict=False):
            dx, dz = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dz)
            ux, uz = dx / length, dz / length
            steps = max(1, math.ceil(length / 8))
            for i in range(steps):
                t = (i + 0.5) / steps
                x, z = a[0] + dx * t, a[1] + dz * t
                half = length / steps * 0.46
                corners = tuple(
                    Vec3(x + ux * s + uz * w, 0.2, z + uz * s - ux * w)
                    for s, w in ((-half, -10), (half, -10), (half, 10), (-half, 10))
                )
                result.append((x, z, corners, i % 3))
    return tuple(result)


def draw_boardwalk(renderer, model, camera):
    if not getattr(model, "august_recovered", False):
        return
    p = renderer.pyxel
    for x, z, corners, _tone in planks():
        center = camera.project(Vec3(x, 0, z))
        if center is None or not (
            -40 < center.x < camera.viewport_width + 40
            and -30 < center.y < camera.viewport_height + 30
        ):
            continue
        q = tuple(camera.project(v) for v in corners)
        if any(v is None for v in q):
            continue
        a, b, c, d = q
        color = 4
        p.tri(a.x, a.y, b.x, b.y, c.x, c.y, color)
        p.tri(a.x, a.y, c.x, c.y, d.x, d.y, color)
        p.line(a.x, a.y, d.x, d.y, 5)


@lru_cache(maxsize=1)
def flowers():
    from drift_with_me.flowerbed import FLOWER_IDS
    from drift_with_me.garden_props_preview import GardenProp
    from drift_with_me.july_construction import ConstructionLayout

    props = []
    for i, (x, z, corners, _) in enumerate(planks()[::8]):
        # Use the same upright production flower assets and depth sorting.
        a, d = corners[0], corners[3]
        dx, dz = d.x - a.x, d.z - a.z
        side = 1 if i % 2 else -1
        props.append(
            GardenProp(
                FLOWER_IDS[i % len(FLOWER_IDS)],
                x + dx * side,
                z + dz * side,
                f"august_bloom:{i}",
                world_scale=0.8,
            )
        )
    return ConstructionLayout(tuple(props), ())


def flower_commands(renderer, model, camera):
    if not getattr(model, "august_recovered", False):
        return []
    from drift_with_me.garden_props_preview import garden_preview_draw_commands

    return garden_preview_draw_commands(renderer, model, camera, flowers())


def rain_segments(camera, time):
    # A bounded world-space lattice, independent of the gameplay random stream.
    cx, cz = math.floor(camera.target.x / 64), math.floor(camera.target.z / 64)
    for i in range(MAX_RAIN):
        gx, gz = cx + i % 12 - 6, cz + i // 12 - 5
        seed = (gx * 73856093 ^ gz * 19349663) & 0xFFFF
        x, z = gx * 64 + seed % 57, gz * 64 + (seed // 57) % 57
        height = (seed % 100 - time * 110) % 100
        a = camera.project(Vec3(x + height * 0.24, height, z))
        b = camera.project(Vec3(x + (height + 6) * 0.24, height + 6, z))
        if a and b and 0 <= a.x < camera.viewport_width and 0 <= a.y < camera.viewport_height:
            yield a, b, seed, x, z


def draw_rain(renderer, model, camera, time):
    if not getattr(model, "august_rain", False):
        return
    p = renderer.pyxel
    p.dither(0.10)
    p.rect(0, 0, camera.viewport_width, camera.viewport_height, 1)
    p.dither(1)
    splashes = 0
    for a, b, seed, x, z in rain_segments(camera, time):
        p.line(round(a.x), round(a.y), round(b.x), round(b.y), 6 if seed % 4 else 13)
        age = (time * 2 + seed / 97) % 1
        if age < 0.18 and splashes < MAX_SPLASHES:
            ground = camera.project(Vec3(x, 0, z))
            if (
                ground
                and 0 <= ground.x < camera.viewport_width
                and 0 <= ground.y < camera.viewport_height
            ):
                p.pset(round(ground.x) - 1, round(ground.y), 6)
                p.pset(round(ground.x) + 1, round(ground.y) - 1, 13)
                splashes += 1
