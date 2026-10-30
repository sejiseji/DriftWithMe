"""ED sprites use one nearest-neighbour scale; project anchors, never source pixels."""

from __future__ import annotations

from dataclasses import replace

from drift_with_me.hex_assets import SpritePlacement
from drift_with_me.math3d import ProjectedPoint


def dot_scale(scale: float) -> float:
    """Integer enlargement or reciprocal-integer reduction keeps square pixel steps."""
    return float(max(1, int(scale))) if scale >= 1 else 1 / max(1, round(1 / max(0.125, scale)))


def place_sprite(definition, point, scale):
    scale = dot_scale(scale)
    w, h = definition.hex_width, definition.hex_height
    ax, ay = definition.anchor_px
    x, y = round(point.x), round(point.y)
    return SpritePlacement(
        anchor_x=x,
        anchor_y=y,
        depth=point.depth,
        scale=scale,
        flip_x=False,
        blt_x=x - w / 2 - scale * (ax - w / 2),
        blt_y=y - h / 2 - scale * (ay - h / 2),
        left=x - ax * scale,
        top=y - ay * scale,
        right=x + (w - ax) * scale,
        bottom=y + (h - ay) * scale,
    )


def snap_placement(definition, placement):
    point = ProjectedPoint(placement.anchor_x, placement.anchor_y, placement.depth)
    result = place_sprite(definition, point, placement.scale)
    if placement.flip_x:
        ax, ay = definition.anchor_px
        mirrored = replace(definition, anchor_px=(definition.hex_width - ax, ay))
        result = replace(place_sprite(mirrored, point, placement.scale), flip_x=True)
    return result
