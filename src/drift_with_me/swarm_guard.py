"""Screen-space vigilance, confined to swarm presentation; world actors never move."""

import math

# Right/left holds, three quick lower directions between them. One cycle 1.08s.
DURATIONS = (0.30, 0.08, 0.08, 0.08, 0.30, 0.08, 0.08, 0.08)
VIEWS = (
    "right",
    "front_right",
    "front",
    "front_left",
    "left",
    "front_left",
    "front",
    "front_right",
)
OFFSETS = ((-22, 0), (-22, 0), (0, -18), (22, 0), (22, 0), (22, 0), (0, -18), (-22, 0))
BUDDY_VIEWS = (
    "front_left",
    "front_left",
    "front",
    "front_right",
    "front_right",
    "front_right",
    "front",
    "front_left",
)
CYCLE = sum(DURATIONS)


def guard_sample(elapsed):
    t = max(0.0, elapsed) % CYCLE
    for i, duration in enumerate(DURATIONS):
        if t < duration:
            u = t / duration
            u = u * u * (3 - 2 * u)
            previous, target = OFFSETS[(i - 1) % 8], OFFSETS[i]
            offset = tuple(a + (b - a) * u for a, b in zip(previous, target, strict=True))
            return VIEWS[i], BUDDY_VIEWS[i], offset
        t -= duration
    return VIEWS[0], BUDDY_VIEWS[0], OFFSETS[0]


def follow(current, target, dt):
    amount = 1 - math.exp(-max(0, dt) / 0.055)
    return tuple(a + (b - a) * amount for a, b in zip(current, target, strict=True))
