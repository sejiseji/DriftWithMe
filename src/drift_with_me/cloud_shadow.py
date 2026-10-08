"""Sparse, world-anchored cloud shade on the completed ground layer only."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

from drift_with_me.grass_wind import SHADES
from drift_with_me.math3d import AffineCameraState, Vec3, screen_to_ground_affine

if TYPE_CHECKING:
    from drift_with_me.model import GameModel

LEVELS = 10
PALETTE_START = 32
# Unequal rounded lobes; no moving stripe, brightness wave or temporal noise.
LOBES = ((-45.0, -20.0, 110.0, 105.0), (40.0, 0.0, 125.0, 95.0), (0.0, 65.0, 85.0, 85.0))
TRAVEL_MARGIN = 240.0


def cloud_center(seconds: float, config: dict, bounds) -> tuple[float, float] | None:
    """A long clear interval between finite passes, independent of the camera."""
    period = float(config.get("period_sec", 420.0))
    lead = float(config.get("clear_lead_sec", 70.0))
    travel = float(config.get("travel_sec", 144.0))
    if not all(math.isfinite(v) for v in (seconds, period, lead, travel)):
        return None
    if seconds < 0 or period <= 0 or not 0 <= lead < lead + travel <= period:
        return None
    cycle = math.floor(seconds / period)
    phase = seconds % period - lead
    if not 0 <= phase < travel:
        return None
    tracks = config.get("track_z_world", (500.0, 760.0, 260.0))
    if not tracks:
        return None
    z = float(tracks[cycle % len(tracks)])
    if not math.isfinite(z):
        return None
    x0, x1 = bounds.min_x - TRAVEL_MARGIN, bounds.max_x + TRAVEL_MARGIN
    return x0 + (x1 - x0) * phase / travel, z


def shade_rgb(rgb: int, amount: float) -> int:
    # Multiplication preserves terrain hue and detail; never adds light bands.
    channels = [round(((rgb >> shift) & 255) * (1.0 - amount)) for shift in (16, 8, 0)]
    return channels[0] << 16 | channels[1] << 8 | channels[2]


def projected_runs(camera: AffineCameraState) -> tuple[tuple[tuple[int, int, int], ...], ...]:
    """Precompute disjoint horizontal spans of a blended soft silhouette once per scale."""
    scale = camera.effective_scale
    bx, by = camera.profile.basis_x.x * scale, camera.profile.basis_x.y * scale
    bz, bw = camera.profile.basis_z.x * scale, camera.profile.basis_z.y * scale
    det = bx * bw - bz * by
    if abs(det) < 1e-9:
        return tuple(() for _ in range(LEVELS))
    bounds = []
    for x, z, rx, rz in LOBES:
        cx, cy = x * bx + z * bz, x * by + z * bw
        ex, ey = math.hypot(rx * bx, rz * bz), math.hypot(rx * by, rz * bw)
        bounds.append((cx - ex, cy - ey, cx + ex, cy + ey))
    min_x = math.floor(min(b[0] for b in bounds))
    max_x = math.ceil(max(b[2] for b in bounds))
    min_y = math.floor(min(b[1] for b in bounds))
    max_y = math.ceil(max(b[3] for b in bounds))
    spans = [[] for _ in range(LEVELS)]
    for y in range(min_y, max_y + 1):
        previous = 0
        start = min_x
        wx = (bw * min_x - bz * y) / det
        wz = (-by * min_x + bx * y) / det
        for x in range(min_x, max_x + 2):
            density = 0.0
            if x <= max_x:
                for cx, cz, rx, rz in LOBES:
                    radial = 1 - ((wx - cx) / rx) ** 2 - ((wz - cz) / rz) ** 2
                    if radial > 0:
                        density += radial * radial * 0.7
            level = min(LEVELS, round(density * LEVELS))
            if level != previous:
                if previous:
                    spans[previous - 1].append((y, start, x - start))
                start = x
                previous = level
            wx += bw / det
            wz -= by / det
    return tuple(tuple(group) for group in spans)


def ground_row_bounds(camera: AffineCameraState, bounds) -> tuple[tuple[int, int], ...]:
    # Inverse affine clipping avoids discarding an entire polygon when a remote
    # corner is behind the near plane. Only actual ground pixels are shaded.
    rows = []
    for y in range(camera.viewport_height):
        p = screen_to_ground_affine(camera, 0, y)
        q = screen_to_ground_affine(camera, 1, y)
        if p is None or q is None:
            rows.append((0, 0))
            continue
        left, right = 0.0, float(camera.viewport_width - 1)
        fx, fz = camera.profile.fixed_forward.x, camera.profile.fixed_forward.z
        depth = (
            camera.profile.reference_depth
            + (p.x - camera.target.x) * fx
            + (p.y - camera.target.z) * fz
        )
        constraints = (
            (p.x, q.x - p.x, bounds.min_x, bounds.max_x),
            (p.y, q.y - p.y, bounds.min_z, bounds.max_z),
            (depth, (q.x - p.x) * fx + (q.y - p.y) * fz, camera.near, camera.far),
        )
        for origin, slope, lo, hi in constraints:
            if abs(slope) < 1e-9:
                if not lo <= origin <= hi:
                    right = -1
                continue
            a, b = (lo - origin) / slope, (hi - origin) / slope
            left, right = max(left, min(a, b)), min(right, max(a, b))
        rows.append((math.ceil(left), math.floor(right) + 1) if left <= right else (0, 0))
    return tuple(rows)


class CloudShadowLayer:
    def __init__(self) -> None:
        self._mask_key = None
        self._runs = ()
        self._clip_key = None
        self._rows = ()
        self._palette_key = None
        self._image = None
        self.mask_builds = 0
        self.last_stats = {"spans": 0, "pixels": 0, "active": False}

    def draw(self, pyxel, model: GameModel, camera) -> None:
        self.last_stats = {"spans": 0, "pixels": 0, "active": False}
        config = model.config.get("cloud_shadow", {})
        if (
            not config.get("enabled", False)
            or model.config.get("simulation", {}).get("day_phase") != "day"
            or not isinstance(camera, AffineCameraState)
            or model.combat_session is not None
            or not hasattr(pyxel, "screen")
            or not hasattr(pyxel, "Image")
        ):
            return
        strength = max(0.0, min(0.25, float(config.get("strength", 0.18))))
        if not strength:
            return
        mask_key = camera.profile
        if mask_key != self._mask_key:
            # One reference-scale mask, also while a focus/zoom interpolates.
            # Scaling cached spans avoids rebuilding the silhouette every frame.
            reference = replace(
                camera, zoom=1.0 / camera.profile.viewport_scale(camera.viewport_width)
            )
            self._runs = projected_runs(reference)
            self._mask_key = mask_key
            self.mask_builds += 1
        # World ticks stop during pause/dialogue/combat. No draw-driven clock.
        seconds = model.world_tick / float(model.config["simulation"]["fixed_hz"])
        center = cloud_center(seconds, config, model.world.visual_ground_rect)
        if center is None:
            return
        point = camera.project(Vec3(center[0], 0.0, center[1]))
        if point is None:
            return
        ox, oy = round(point.x), round(point.y)
        bounds = model.world.visual_ground_rect
        clip_key = (camera, bounds)
        if clip_key != self._clip_key:
            self._rows = ground_row_bounds(camera, bounds)
            self._clip_key = clip_key
        groups = []
        scale = camera.effective_scale
        for group in self._runs:
            visible = []
            for dy, dx, width in group:
                top, bottom = oy + round(dy * scale), oy + round((dy + 1) * scale)
                left, right = ox + round(dx * scale), ox + round((dx + width) * scale)
                for y in range(max(0, top), min(camera.viewport_height, bottom)):
                    a, b = self._rows[y]
                    x0, x1 = max(a, left), min(b, right)
                    if x0 < x1:
                        visible.append((x0, y, x1 - x0))
            groups.append(visible)
        if not any(groups):
            return
        palette = tuple(pyxel.colors[:16])
        if len(pyxel.colors) == 16:
            # Preserve the four reserved grass-wind colors if that old optional
            # experiment is enabled later; it remains disabled by default.
            pyxel.colors.extend(SHADES)
        base = (*palette, *tuple(pyxel.colors[16:20]))
        palette_key = (base, strength)
        if palette_key != self._palette_key:
            colors = list(pyxel.colors)
            colors.extend([0] * max(0, PALETTE_START + LEVELS * len(base) - len(colors)))
            for level in range(1, LEVELS + 1):
                for source, rgb in enumerate(base):
                    colors[PALETTE_START + (level - 1) * len(base) + source] = shade_rgb(
                        rgb, strength * level / LEVELS
                    )
            pyxel.colors[:] = colors
            self._palette_key = palette_key
        size = (camera.viewport_width, camera.viewport_height)
        if self._image is None or (self._image.width, self._image.height) != size:
            self._image = pyxel.Image(*size)
        self._image.blt(0, 0, pyxel.screen, 0, 0, *size)
        try:
            for level, group in enumerate(groups):
                if not group:
                    continue
                for source in range(len(base)):
                    pyxel.pal(source, PALETTE_START + level * len(base) + source)
                for x, y, width in group:
                    pyxel.blt(x, y, self._image, x, y, width, 1)
        finally:
            pyxel.pal()
        self.last_stats = {
            "spans": sum(len(group) for group in groups),
            "pixels": sum(width for group in groups for _, _, width in group),
            "active": True,
        }
