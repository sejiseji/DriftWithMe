"""Analytic root-fixed sway for existing grass strokes, with no animation state."""

from __future__ import annotations

import math
import random
from functools import lru_cache

GUST_PERIOD_SECONDS = 128.0
GUST_TABLE_SIZE = 256


@lru_cache(maxsize=4)
def gust_tables(seed: int) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Build two small periodic value-noise tables once per seed (four-seed cap)."""
    rng = random.Random(seed)
    channels = (
        [0.55 + 0.60 * rng.random() ** 1.4 for _ in range(32)],
        [rng.uniform(-0.55, 0.55) for _ in range(32)],
    )
    tables = []
    for knots in channels:
        samples = []
        for i in range(GUST_TABLE_SIZE):
            position = i * len(knots) / GUST_TABLE_SIZE
            index = int(position)
            u = position - index
            # Quintic blending has zero first/second derivatives at each knot.
            blend = u * u * u * (u * (u * 6.0 - 15.0) + 10.0)
            samples.append(knots[index] + (knots[(index + 1) % len(knots)] - knots[index]) * blend)
        tables.append(tuple(samples))
    return tables[0], tables[1]


def _periodic_sample(table: tuple[float, ...], position: float) -> float:
    index = math.floor(position)
    u = position - index
    a, b, c, d = (table[(index + offset) % len(table)] for offset in (-1, 0, 1, 2))
    # Catmull-Rom keeps the lookup continuous in value and slope, including wrap.
    return b + 0.5 * u * (c - a + u * (2 * a - 5 * b + 4 * c - d + u * (3 * (b - c) + d - a)))


def lift_weak_gain(gain: float) -> float:
    """Lift the .55 floor to .65; leave gains of .85 and above unchanged."""
    if gain >= 0.85:
        return gain
    u = max(0.0, min(1.0, (gain - 0.55) / 0.30))
    return gain + 0.10 * (1.0 - u * u * (3.0 - 2.0 * u))


def sample_gust(seconds: float, seed: int = 20261007) -> tuple[float, float]:
    """Continuous shared gain/phase; no advancing cursor or per-blade updates."""
    gain, phase = gust_tables(seed)
    position = (seconds % GUST_PERIOD_SECONDS) * GUST_TABLE_SIZE / GUST_PERIOD_SECONDS
    return lift_weak_gain(_periodic_sample(gain, position)), _periodic_sample(phase, position)


def bend_angle(
    x: float,
    z: float,
    seconds: float,
    variation: float,
    config: dict,
    gust: tuple[float, float] | None = None,
) -> float:
    if not config.get("enabled", False):
        return 0.0
    x0, z0, x1, z1 = config.get("rect_xz", (0, 0, 0, 0))
    if not (x0 < x < x1 and z0 < z < z1):
        return 0.0
    if gust is None:
        gust = (
            sample_gust(seconds, int(config.get("gust_seed", 20261007)))
            if config.get("gust_enabled", True)
            else (1.0, 0.0)
        )
    gain, phase_offset = gust
    edge = min(x - x0, x1 - x, z - z0, z1 - z)
    feather = min(1.0, edge / 32.0)
    speed = float(config.get("speed_world_per_sec", 38.0))
    # A moving curved front, with slight fixed per-blade delay/strength variation.
    across = z - x * 0.12
    phase = (x + z * 0.12 - seconds * speed) * math.tau / 210.0
    phase += phase_offset + 0.65 * math.sin(across / 69.0) + (variation - 0.5) * 0.42
    pulse = max(0.0, math.sin(phase)) ** 2
    strength = max(0.0, min(1.0, float(config.get("strength", 0.70))))
    return math.radians(48.0) * strength * gain * feather * pulse * (0.82 + variation * 0.18)


def rotate_tip(root_x: int, root_y: int, tip_x: int, tip_y: int, angle: float) -> tuple[int, int]:
    if angle == 0.0:
        return tip_x, tip_y
    x, y = tip_x - root_x, tip_y - root_y
    c, s = math.cos(angle), math.sin(angle)
    return root_x + round(x * c - y * s), root_y + round(x * s + y * c)
