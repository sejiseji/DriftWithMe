"""Optional, stateless ground wind for a bounded affine grassland prototype."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from drift_with_me.math3d import AffineCameraState, Vec3

if TYPE_CHECKING:
    from drift_with_me.model import GameModel
    from drift_with_me.render import Renderer

# Additional shades only; the original sixteen palette entries remain untouched.
SHADES = (0x147F85, 0x178D93, 0x2DA09F, 0x3CAAA2)


def wind_value(x: float, z: float, seconds: float, speed: float = 26.0) -> float:
    """Advected, curved patches; no per-tile animation state or camera phase."""
    drift = x - seconds * speed
    return (
        0.56
        * math.sin(drift / 76.0 + 0.45 * math.sin(z / 97.0))
        * math.cos(z / 88.0 + 0.35 * math.sin(drift / 127.0))
        + 0.34 * math.sin(drift / 139.0 + z / 163.0) * math.cos(z / 113.0 - drift / 191.0)
        + 0.10 * math.sin(drift / 53.0 - 0.3 * math.cos(z / 71.0)) * math.cos(z / 73.0)
    )


def overlaps(a: tuple, b: tuple) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def draw_grass_wind(
    renderer: Renderer,
    model: GameModel,
    camera: AffineCameraState,
    seconds: float,
    area: dict | None = None,
) -> tuple[int, int]:
    config = model.config.get("grass_wind", {})
    grass = model.config.get("grassland_micro", {})
    if (
        not config.get("enabled", False)
        or not grass.get("enabled", False)
        or not isinstance(camera, AffineCameraState)
        or model.combat_session is not None
    ):
        return 0, 0
    visible = renderer.grassland_micro_visible_world_rect(camera, margin_px=2.0)
    if visible is None:
        return 0, 0
    raw = config.get("rect_xz", ())
    if len(raw) != 4:
        return 0, 0
    region = tuple(float(value) for value in raw)
    step = max(8.0, float(config.get("cell_world", 16.0)))
    strength = max(0.0, min(1.0, float(config.get("strength", 0.65))))
    if strength <= 0.0:
        return 0, 0
    palette = list(renderer.pyxel.colors)
    # Never reinterpret palette slots owned by another layer/theme.
    if len(palette) == 16:
        renderer.pyxel.colors.extend(SHADES)
    elif palette[16:20] != list(SHADES):
        return 0, 0
    colors = (16, 17, 3, 18, 19)
    water = [(a.min_x, a.min_z, a.max_x, a.max_z) for a in model.world.shallow_water_areas]
    patches = [
        (p.x - p.width / 2, p.z - p.depth / 2, p.x + p.width / 2, p.z + p.depth / 2)
        for p in renderer._active_baked_ground_patches
    ]
    origin = camera.project(Vec3(camera.target.x, 0.0, camera.target.z))
    if origin is None:
        return 0, 0
    scale = camera.effective_scale
    bx, by = camera.profile.basis_x.x * scale, camera.profile.basis_x.y * scale
    bz, bw = camera.profile.basis_z.x * scale, camera.profile.basis_z.y * scale
    hx, hy = step * (abs(bx) + abs(bz)) / 2, step * (abs(by) + abs(bw)) / 2
    tested = drawn = 0
    areas = (area,) if area is not None else grass.get("areas", ())
    for area in areas:
        bounds = renderer.grassland_micro_world_rect(model.world, area)
        if bounds is None:
            continue
        fade = renderer.grassland_transition_world(area, grass)
        x0 = max(region[0], visible[0], bounds[0] + fade)
        z0 = max(region[1], visible[1], bounds[1] + fade)
        x1 = min(region[2], visible[2], bounds[2] - fade)
        z1 = min(region[3], visible[3], bounds[3] - fade)
        if x0 >= x1 or z0 >= z1:
            continue
        for iz in range(math.floor(z0 / step), math.ceil(z1 / step)):
            row = []
            for ix in range(math.floor(x0 / step), math.ceil(x1 / step)):
                rect = (
                    max(x0, ix * step),
                    max(z0, iz * step),
                    min(x1, (ix + 1) * step),
                    min(z1, (iz + 1) * step),
                )
                tested += 1
                if any(overlaps(rect, excluded) for excluded in (*water, *patches)):
                    continue
                # Affine ground projection is linear; no four projections per cell.
                cx, cz = (ix + 0.5) * step, (iz + 0.5) * step
                sx = origin.x + (cx - camera.target.x) * bx + (cz - camera.target.z) * bz
                sy = origin.y + (cx - camera.target.x) * by + (cz - camera.target.z) * bw
                if sx + hx < -2 or sx - hx > camera.viewport_width + 2:
                    continue
                if sy + hy < -2 or sy - hy > camera.viewport_height + 2:
                    continue
                # Sample fixed cell centers even for viewport-clipped edge cells.
                x, z = (ix + 0.5) * step, (iz + 0.5) * step
                edge = min(x - region[0], region[2] - x, z - region[1], region[3] - z)
                feather = max(0.0, min(1.0, edge / 48.0))
                value = wind_value(x, z, seconds, float(config.get("speed_world_per_sec", 26.0)))
                level = max(0, min(4, round(2.0 + value * strength * feather * 2.0)))
                if level != 2:
                    row.append((rect, level))
            # Coalesce equal shade cells; no full-map cache or offscreen state.
            merged = []
            for rect, level in row:
                if merged and merged[-1][1] == level and merged[-1][0][2] == rect[0]:
                    previous, _ = merged[-1]
                    merged[-1] = ((previous[0], rect[1], rect[2], rect[3]), level)
                else:
                    merged.append((rect, level))
            for rect, level in merged:
                renderer.draw_ground_rect(camera, rect, colors[level])
                drawn += 1
    return tested, drawn
