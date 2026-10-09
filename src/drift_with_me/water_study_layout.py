from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=128)
def water_study_visible_chunks(
    screen_width: int,
    screen_height: int,
    logical_width: int,
    logical_height: int,
    start_x: int,
    start_y: int,
    geometry: tuple[tuple[int, int, int, int], ...],
    cull_rect: tuple[int, int, int, int] | None,
) -> tuple[tuple[int, int, int], ...]:
    """Reuse tile placement only; callers still draw each frame's current images."""
    visible = []
    for plane_y in range(start_y, screen_height + logical_height, logical_height):
        for plane_x in range(start_x, screen_width + logical_width, logical_width):
            for index, (origin_x, origin_y, width, height) in enumerate(geometry):
                x, y = plane_x + origin_x, plane_y + origin_y
                if x >= screen_width or y >= screen_height or x + width <= 0 or y + height <= 0:
                    continue
                if cull_rect is not None:
                    cull_x, cull_y, cull_width, cull_height = cull_rect
                    if (
                        x >= cull_x + cull_width
                        or y >= cull_y + cull_height
                        or x + width <= cull_x
                        or y + height <= cull_y
                    ):
                        continue
                visible.append((x, y, index))
    return tuple(visible)
