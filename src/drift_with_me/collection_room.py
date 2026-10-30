"""Small indexed room ending. Images are cached; no save writes or video decoder."""

from __future__ import annotations

import json
from functools import cache, lru_cache
from pathlib import Path

from drift_with_me.curtain_motion import curtain_strips

ROOT = Path(__file__).parent


@lru_cache(maxsize=1)
def room_config():
    return json.loads((ROOT / "data/collection_room.json").read_text())


def visible_layers(owned, frame=0):
    c = room_config()
    owned = set(owned)
    sequence = c["curtain_sequence"]
    pose = sequence[(frame % c["period_frames"]) * len(sequence) // c["period_frames"]]
    result = []
    for layer in sorted(c["layers"], key=lambda x: x["z"]):
        name = layer["name"]
        if name.startswith("curtain_") and name != f"curtain_{pose}":
            continue
        required = set(layer.get("requires", ()))
        if layer["optional"] and not (
            required <= owned if layer.get("all_items") else required & owned
        ):
            continue
        result.append(layer)
    return result


def layer_position(layer, frame):
    x, y = layer["xy"]
    if layer["name"].startswith("sleep_"):
        y += int(frame % 144 >= 72)
    return x, y


@cache
def image_for(name, width, height):
    import pyxel

    image = pyxel.Image(width, height)
    rows = (ROOT / "assets/collection_room" / f"{name}.hex").read_text().splitlines()
    image.set(0, 0, rows)
    return image


def draw_room(app, owned):
    import pyxel

    c = room_config()
    width, height = c["canvas"]
    scale = min(pyxel.width / width, pyxel.height / height)
    left = (pyxel.width - width * scale) / 2
    top = (pyxel.height - height * scale) / 2
    frame = int(getattr(app, "presentation_time", 0) * c["fps"])
    pyxel.cls(1)
    pyxel.clip(round(left + 46 * scale), round(top), round(420 * scale), round(236 * scale))
    for layer in visible_layers(owned, frame):
        w, h = layer["size"]
        x, y = layer_position(layer, frame)
        x += c["viewport_offset"][0]
        y += c["viewport_offset"][1]
        # Pyxel scales about the sprite centre, so compensate the origin.
        dx = left + x * scale + (w * scale - w) / 2
        dy = top + y * scale + (h * scale - h) / 2
        if layer["name"].startswith("curtain_"):
            for source, row, height in curtain_strips(frame, c):
                strip_y = top + (y + row) * scale + (height * scale - height) / 2
                pyxel.blt(
                    dx,
                    strip_y,
                    image_for(source, w, h),
                    0,
                    row,
                    w,
                    height,
                    layer["colkey"],
                    scale=scale,
                )
        else:
            pyxel.blt(
                dx, dy, image_for(layer["name"], w, h), 0, 0, w, h, layer["colkey"], scale=scale
            )
    pyxel.text(left + 432 * scale, top + 220 * scale, "End", 7)
    pyxel.clip()
