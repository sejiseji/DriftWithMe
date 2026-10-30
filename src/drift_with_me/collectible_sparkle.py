"""Stateless, bounded collectible billboard: approved B vortex in game16 colours."""

from __future__ import annotations

import math

PARTICLE_COUNT = 18
DECAY = 1.10
OMEGA = 2.70
BLINK_HZ = 0.70
BURST_SECONDS = 3.0932796833977783
LOOP_SECONDS = 4.5
EXTENT = 36
# Exact approved11x15 faceted marker; dot means transparent.
MARKER = (
    ".....1.....",
    "....171....",
    "....77a....",
    "...177f1...",
    "..1777fa1..",
    ".17777ffa1.",
    ".17777ffa1.",
    "177777fffa1",
    ".17777ffa1.",
    ".1a777ffa1.",
    "..1777fa1..",
    "...177f1...",
    "....a7a....",
    "....1a1....",
    ".....1.....",
)
SEEDS = tuple(
    (
        23 + (index * 7) % 10,
        index * 2.399963229728653,
        index * 0.025,
        math.log((23 + (index * 7) % 10) / 1.7) / DECAY,
    )
    for index in range(PARTICLE_COUNT)
)


def phase_offset(ident: str) -> float:
    """Stable across processes; separate pickups do not blink together."""
    return sum((i + 1) * ord(c) for i, c in enumerate(ident)) % 450 / 100


def particles(seconds: float, ident: str = "") -> tuple[tuple[float, float, str, int], ...]:
    if not math.isfinite(seconds):
        return ()
    phase = (max(0.0, seconds) + phase_offset(ident)) % LOOP_SECONDS
    result = []
    for index, (radius, theta, delay, death) in enumerate(SEEDS):
        age = phase - delay
        if not 0 <= age < death:
            continue
        distance = radius * math.exp(-DECAY * age)
        angle = theta + OMEGA * age
        shape = (
            "point"
            if distance < 8 or age < 0.22 + 0.025 * (index % 4)
            else "cross"
            if age < 0.57 + 0.035 * (index % 5)
            else "diamond"
        )
        pulse = 0.5 + 0.5 * math.sin(math.tau * (BLINK_HZ * age + index * 0.309016994))
        # Birth is a subdued point, not a synchronous bright reappearance.
        color = 15 if age < 0.10 else 7 if pulse > 0.70 else 10 if pulse > 0.24 else 15
        result.append((distance * math.cos(angle), distance * math.sin(angle), shape, color))
    return tuple(result)


def pixels(
    x: int, y: int, seconds: float, ident: str, width: int, height: int
) -> tuple[tuple[int, int, int], ...]:
    """Particle billboard and central diamond, clipped without altering Pyxel clip state."""
    scale = width / 512
    result = []

    def put(dx: int, dy: int, color: int) -> None:
        px, py = round(x + dx * scale), round(y + dy * scale)
        if 0 <= px < width and 0 <= py < height:
            result.append((px, py, color))

    for dx, dy, shape, color in particles(seconds, ident):
        px, py = round(dx), round(dy)
        radius = 0 if shape == "point" else 1 if shape == "cross" else 2
        for sy in range(-radius, radius + 1):
            for sx in range(-radius, radius + 1):
                if abs(sx) + abs(sy) <= radius:
                    put(px + sx, py + sy, color)
        if shape == "diamond":
            put(px - 1, py, 7)
    # Last inside this billboard, still at the object's existing world depth.
    for row, line in enumerate(MARKER):
        for col, value in enumerate(line):
            if value != ".":
                put(col - 5, row - 7, int(value, 16))
    return tuple(result)


def draw(px: object, x: int, y: int, seconds: float, ident: str, width: int, height: int) -> None:
    for sx, sy, color in pixels(x, y, seconds, ident, width, height):
        px.pset(sx, sy, color)
