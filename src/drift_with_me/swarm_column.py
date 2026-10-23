"""Approved native water-column clip and one-shot, presentation-only attack turn."""

from pathlib import Path

from drift_with_me.hex_assets import load_sprite_manifest_path

WINDUP = 0.12
TURN = 0.48
COLUMN_DURATION = 1.88


def column_frame(elapsed):
    t = max(0.0, elapsed)
    if t < 0.4:
        return min(3, int(t / 0.1 + 1e-9))
    if t < 1.48:
        phase = (t - 0.4) % 0.27
        return 4 + sum(phase >= edge for edge in (0.07, 0.13, 0.20))
    if t < COLUMN_DURATION:
        return 8 + min(3, int((t - 1.48) / 0.1 + 1e-9))
    return None


def attack_view(phase, elapsed, actor, views):
    if phase != ("electric" if actor == "buddy" else "spear"):
        return None
    # Hold front briefly to brace, then traverse exactly eight production views.
    if elapsed < WINDUP:
        return "front"
    if elapsed >= WINDUP + TURN:
        return None
    start = views.index("front")
    return views[(start + int((elapsed - WINDUP) / TURN * len(views))) % len(views)]


def load_column_assets(pyxel):
    return load_sprite_manifest_path(
        pyxel, Path(__file__).parent / "assets/swarm_column/sprites.json"
    )
