"""Bounded native-pixel water jets: stepped volume, diagonal streams and spray.

No RNG or persistent particle pool. At most 40 body rows, 21 three-pixel stream
clusters and eight analytical droplets per jet, all within the spear phase.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MAX_ROWS = 40
MAX_STREAMS = 21
STREAM_PIXELS = 3
MAX_SPRAY = 8
SPRAY_LIFETIME_MAX = 0.28
WATER_COLORS = (1, 6, 12, 7)


@dataclass(frozen=True)
class Droplet:
    x: int
    y: int
    color: int
    age: float
    lifetime: float


def spray_samples(cx, base_y, half_width, height, elapsed, seed=0):
    scale = max(0.5, min(1.7, height / 48))
    particles = []
    for i in range(MAX_SPRAY):
        birth = 0.05 + i * 0.035
        lifetime = 0.26 + (i % 3) * 0.01
        age = elapsed - birth
        if not 0 <= age <= lifetime:
            continue
        side = -1 if (i + seed + i // 4) % 2 else 1
        source_height = 1.0 if i % 4 == 0 else 0.58 + (i % 4) * 0.10
        x0 = cx + side * half_width * (1 - source_height) * 0.8
        y0 = base_y - height * source_height
        vx = side * (8 + 3 * (i % 3)) * scale
        vy = -(48 + 4 * (i % 3)) * scale
        x = x0 + vx * age
        y = y0 + vy * age + 150 * scale * age * age
        color = 7 if i % 3 == 0 and age < lifetime * 0.55 else 12 if age < lifetime * 0.8 else 6
        particles.append(Droplet(round(x), round(y), color, age, lifetime))
    return tuple(particles)


def surface_samples(cx, base_y, half_width, height, elapsed, seed=0):
    # Three broken, coherently travelling diagonal lanes; not random sparkle.
    tick = math.floor(elapsed * 12) / 12
    clusters = []
    for lane in range(3):
        for segment in range(7):
            u = (segment / 7 + tick * 0.7 + seed * 0.027) % 1
            across = ((lane / 3 + u * 0.7 + tick * 0.3) % 1) * 2 - 1
            width = max(1, half_width * (1 - u) - 1)
            x = round(cx + across * width)
            y = round(base_y - u * height)
            color = 7 if (segment + lane) % 4 == 0 else 6 if across < 0.25 else 12
            clusters.append((x, y, color))
    return tuple(clusters)


def draw_water_spear(pyxel, left, right, top, foot, elapsed, seed=0):
    cx, base_y = round(foot.x), round(foot.y)
    half_width = max(2, min(20, round(abs(right.x - left.x) / 2)))
    height = max(2, min(MAX_ROWS * 2, round(abs(base_y - top.y) / 2) * 2))
    rows = min(MAX_ROWS, math.ceil(height / 2))
    # Quantized scanlines make a stepped 1-2px silhouette and coherent shadow.
    for row in range(rows):
        y = base_y - row * 2
        width = max(1, round(half_width * (1 - row * 2 / height)))
        pyxel.rect(cx - width, y - 1, width * 2 + 1, 2, 1)
        if width > 1:
            pyxel.rect(cx - width + 1, y - 1, width * 2 - 1, 2, 12)
            shadow_x = cx + max(0, width // 4)
            pyxel.rect(shadow_x, y - 1, max(1, cx + width - shadow_x), 2, 6)
    streams = surface_samples(cx, base_y, half_width, height, elapsed, seed)
    for x, y, color in streams:
        pyxel.pset(x, y, color)
        pyxel.pset(x + 1, y - 1, color)
        pyxel.pset(x + 1, y - 2, color)
    spray = spray_samples(cx, base_y, half_width, height, elapsed, seed)
    for dot in spray:
        pyxel.pset(dot.x, dot.y, dot.color)
        pyxel.pset(dot.x, dot.y + 1, 6 if dot.color == 12 else 12)
    return {"rows": rows, "stream_clusters": len(streams), "spray_particles": len(spray)}
