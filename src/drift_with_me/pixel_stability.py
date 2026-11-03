"""Bounded, anchor-relative sprite sampling for normal exploration rendering."""

from __future__ import annotations

import math
import operator
from collections import OrderedDict

MAX_TEXTURES = 32
MAX_SOURCES = 64
MAX_SOURCE_PIXELS = 1024 * 1024
HEX_COLORS = "0123456789abcdef"
HEX_TRANSLATION = bytes(ord(HEX_COLORS[i]) if i < 16 else 0 for i in range(256))
MAX_SIDE = 256
HYSTERESIS_PX = 0.18


def allowed(renderer, model, camera):
    return (
        getattr(renderer, "pixel_stability_context", False)
        and renderer.camera_is_affine(camera)
        and not model.world_paused
        and model.combat_session is None
        and getattr(model, "swarm_presentation", None) is None
        and getattr(model, "august_sighting_view", None) is None
    )


class StableNearest:
    """Anchor-relative nearest sampling with a small per-column/row dead band.

    Scale remains continuous. Each output cell retains its source index only
    within 0.18 logical pixels of its previous boundary. No global scale steps,
    blending, new palette entries or modifications to source/animation frames.
    This intentionally trades exact nearest sampling for bounded contour lag.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.maps = OrderedDict()
        self.textures = OrderedDict()
        self.sources = OrderedDict()
        self.source_pixels = 0
        self.source_reads = 0
        self.culled_draws = 0
        self.builds = 0
        self.fallbacks = 0

    def axis(self, key, scale, start, end, anchor):
        old_scale, old = self.maps.get(key, (scale, {}))
        if abs(scale - old_scale) > max(0.03, old_scale * 0.2):
            old = {}
        values = {}
        for j in range(start, end):
            u = anchor + (j + 0.5) / scale
            v = math.floor(u)
            previous = old.get(j)
            if (
                previous is not None
                and previous - HYSTERESIS_PX / scale <= u < previous + 1 + HYSTERESIS_PX / scale
            ):
                v = previous
            values[j] = v
        self.maps[key] = (scale, values)
        self.maps.move_to_end(key)
        while len(self.maps) > 128:
            self.maps.popitem(last=False)
        return tuple(values.values())

    def draw(self, pyxel, frame, definition, p, instance="isolated"):
        w, h = frame.width, frame.height
        ax, ay = definition.anchor_px
        if p.flip_x:
            ax = w - ax
        scale = p.scale
        left = math.floor(-ax * scale) - 1
        top = math.floor(-ay * scale) - 1
        right = math.ceil((w - ax) * scale) + 1
        bottom = math.ceil((h - ay) * scale) + 1
        width, height = right - left, bottom - top
        if not (
            0.05 < scale < 8
            and 0 < width <= MAX_SIDE
            and 0 < height <= MAX_SIDE
            and w * h <= MAX_SIDE * MAX_SIDE
            and definition.colkey <= 15
        ):
            self.fallbacks += 1
            return False
        geom = (instance, w, h, ax, ay, definition.world_size, p.flip_x)
        xs = self.axis((geom, "x"), scale, left, right, ax)
        ys = self.axis((geom, "y"), scale, top, bottom, ay)
        viewport_w = getattr(pyxel, "width", 0)
        viewport_h = getattr(pyxel, "height", 0)
        # Keep both axis histories, even while hidden. Only skip palette/texture
        # generation for a fully outside padded raster, with a 2px safety border.
        if (
            viewport_w > 0
            and viewport_h > 0
            and (
                p.anchor_x + right < -2
                or p.anchor_y + bottom < -2
                or p.anchor_x + left >= viewport_w + 2
                or p.anchor_y + top >= viewport_h + 2
            )
        ):
            self.culled_draws += 1
            return True
        source_image = (
            (pyxel.images[frame.image] if hasattr(pyxel, "images") else pyxel.image(frame.image))
            if isinstance(frame.image, int)
            else frame.image
        )
        if not hasattr(source_image, "pget"):
            self.fallbacks += 1
            return False
        sourcekey = (id(source_image), frame.source_hash, frame.u, frame.v, w, h, definition.colkey)
        cached_source = self.sources.get(sourcekey)
        source = cached_source[1] if cached_source is not None else None
        if source is None:
            if hasattr(source_image, "data_ptr"):
                # Copy the native palette plane once; preserve original UV addressing.
                raw = bytes(source_image.data_ptr())
                stride = source_image.width
                if not (0 <= frame.u <= stride - w and 0 <= frame.v <= source_image.height - h):
                    raw = None
            else:
                raw = None
            if raw is not None:
                pixels = tuple(
                    raw[(frame.v + y) * stride + frame.u : (frame.v + y) * stride + frame.u + w]
                    for y in range(h)
                )
            else:
                pixels = tuple(
                    bytes(source_image.pget(frame.u + x, frame.v + y) for x in range(w))
                    for y in range(h)
                )
            if any(max(row, default=0) > 15 for row in pixels):
                self.fallbacks += 1
                return False
            source = tuple(row.translate(HEX_TRANSLATION).decode("ascii") for row in pixels)
            self.sources[sourcekey] = (source_image, source)
            self.source_reads += 1
            self.source_pixels += w * h
            while len(self.sources) > MAX_SOURCES or self.source_pixels > MAX_SOURCE_PIXELS:
                old_key, _ = self.sources.popitem(last=False)
                self.source_pixels -= old_key[4] * old_key[5]
        self.sources.move_to_end(sourcekey)
        key = (sourcekey, xs, ys, p.flip_x)
        cached_image = self.textures.get(key)
        image = cached_image[0] if cached_image is not None else None
        if image is None:
            clear = HEX_COLORS[definition.colkey]
            indices = tuple((w - 1 - x if p.flip_x else x) if 0 <= x < w else w for x in xs)
            take = operator.itemgetter(*indices)
            clear_row = clear * width
            remapped = {}
            rows = []
            for y in ys:
                if not 0 <= y < h:
                    rows.append(clear_row)
                    continue
                if y not in remapped:
                    remapped[y] = "".join(take(source[y] + clear))
                rows.append(remapped[y])
            image = pyxel.Image(width, height)
            image.set(0, 0, rows)
            self.textures[key] = (image, source_image)
            self.builds += 1
            while len(self.textures) > MAX_TEXTURES:
                self.textures.popitem(last=False)
        self.textures.move_to_end(key)
        pyxel.blt(
            p.anchor_x + left,
            p.anchor_y + top,
            image,
            0,
            0,
            width,
            height,
            colkey=definition.colkey,
        )
        return True
