"""Approved WTR production source metadata.

Artwork is already complete. Codex/runtime code should only load and play these assets.
"""

from dataclasses import dataclass

WIDTH = 1024
HEIGHT = 512
CHUNK_W = 256
CHUNK_H = 256
COLKEY = 8
FPS = 12


@dataclass(frozen=True)
class AnimatedWaterSource:
    id: str
    role: str
    frame_count: int
    transparent: bool
    colkey: int | None


SOURCES = (
    AnimatedWaterSource("water_deep_plane_d", "deep", 48, False, None),
    AnimatedWaterSource("water_mid_plane_d", "mid", 48, True, COLKEY),
    AnimatedWaterSource("water_surface_plane_d", "surface", 48, True, COLKEY),
    AnimatedWaterSource("water_surface_caustics_plane_d", "surface_caustics", 48, True, COLKEY),
    AnimatedWaterSource("water_highlights_plane_d", "highlights", 24, True, COLKEY),
)

APPROVED_LOOK03_WATER_FRAME_MAP = tuple(range(0, 48, 2))
APPROVED_LOOK03_HIGHLIGHTS_FRAME_MAP = tuple(range(24))

FULL_LOOK02_WATER_FRAME_MAP = tuple(range(48))
FULL_LOOK02_HIGHLIGHTS_FRAME_MAP = tuple(i % 24 for i in range(48))

UPPER_LIGHTNET_ENABLED = False
