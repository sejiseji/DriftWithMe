"""WTR individual water sparkle animation assets v1.0.

Artwork is complete. Runtime should only select, animate and place these sprites.
Do not enlarge these assets above their canonical authored canvas.
"""

from dataclasses import dataclass

BANK_W = 256
BANK_H = 256
COLKEY = 8
FRAME_COUNT = 4


@dataclass(frozen=True)
class SparkleAnimDef:
    id: str
    bank_y: int
    frame_w: int
    frame_h: int
    frame_count: int
    ticks_per_frame: int
    loop: bool
    category: str


SPARKLE_ANIMS = (
    SparkleAnimDef("sparkle_cross_large", 0, 64, 64, 4, 2, False, "large"),
    SparkleAnimDef("sparkle_cross_medium", 64, 48, 48, 4, 2, False, "medium"),
    SparkleAnimDef("sparkle_cross_small", 112, 32, 32, 4, 2, False, "small"),
    SparkleAnimDef("sparkle_glint_horizontal_large", 144, 64, 32, 4, 2, False, "large_glint"),
    SparkleAnimDef("sparkle_glint_horizontal_medium", 176, 48, 24, 4, 2, False, "medium_glint"),
    SparkleAnimDef("sparkle_cluster_micro", 200, 64, 48, 4, 2, False, "micro_cluster"),
)


def source_rect(anim: SparkleAnimDef, frame_index: int):
    frame_index = max(0, min(anim.frame_count - 1, frame_index))
    return (frame_index * anim.frame_w, anim.bank_y, anim.frame_w, anim.frame_h)
