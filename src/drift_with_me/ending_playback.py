"""Approved credits → white → persistent collection room. No progress writes."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ROOT = Path(__file__).parent
CREDITS_SECONDS = 110.0
ROOM_FADE_SECONDS = 1.3


@dataclass
class EndingPlayback:
    owned: frozenset[str]
    elapsed: float = 0.0

    def advance(self, elapsed):
        if math.isfinite(elapsed) and elapsed > 0:
            self.elapsed += elapsed

    @property
    def room_mix(self):
        if self.complete:
            return 1.0
        return max(0.0, min(1.0, (self.elapsed - CREDITS_SECONDS) / ROOM_FADE_SECONDS))

    @property
    def complete(self):
        return self.elapsed >= CREDITS_SECONDS + ROOM_FADE_SECONDS


@cache
def runtime_data():
    return json.loads((ROOT / "data/credits_runtime.json").read_text())


@cache
def runtime_image(index):
    import pyxel

    asset = runtime_data()["assets"][index]
    w, h = asset["size"]
    image = pyxel.Image(w, h)
    image.set(0, 0, (ROOT / "assets/credits_runtime" / asset["name"]).read_text().splitlines())
    return image


def restore_palette(app):
    colors = getattr(app, "ending_original_colors", None)
    if colors is not None:
        app.pyxel.colors.from_list(colors)
        app.pyxel.pal()
        app.ending_original_colors = None


def begin(app):
    from drift_with_me.app import AppScreen
    from drift_with_me.collectibles import owned_collectibles

    if (
        app.screen != AppScreen.OFFICE
        or app.work_week.month != 8
        or app.work_week.number != 4
        or app.office.august_progress.phase != "done"
    ):
        return False
    restore_palette(app)
    app.ending_playback = EndingPlayback(frozenset(owned_collectibles(app)))
    app.screen = AppScreen.CREDITS
    app.clear_world_input_latches()
    return True


def update(app, elapsed):
    from drift_with_me.app import AppScreen

    state = app.ending_playback
    state.advance(elapsed)
    app.clear_world_input_latches()
    if state.complete:
        restore_palette(app)
        app.screen = AppScreen.COLLECTION_ROOM
        app.collection_room_wait_release = True
        app.ending_playback = None


def apply_palette(app, colors, white):
    if getattr(app, "ending_original_colors", None) is None:
        app.ending_original_colors = list(app.pyxel.colors.to_list())
    base = app.ending_original_colors

    def mix(color):
        return sum(
            round(((color >> shift) & 255) * (1 - white) + 255 * white) << shift
            for shift in (16, 8, 0)
        )

    palette = [mix(color) for color in colors]
    palette += [0] * (256 - len(palette))
    palette[255] = base[1]
    app.pyxel.colors.from_list(palette)


def draw(app):
    from drift_with_me.collection_room import draw_room

    p = app.pyxel
    state = app.ending_playback
    outer_scale = min(p.width / 512, p.height / 236)
    left = (p.width - 512 * outer_scale) / 2
    top = (p.height - 236 * outer_scale) / 2
    vx, vy, vw, vh = left + 46 * outer_scale, top, 420 * outer_scale, 236 * outer_scale
    try:
        if state.elapsed >= CREDITS_SECONDS:
            if getattr(app, "ending_original_colors", None) is None:
                app.ending_original_colors = list(p.colors.to_list())
            apply_palette(app, app.ending_original_colors, 1 - state.room_mix)
            draw_room(app, state.owned)
            p.rect(0, 0, vx, p.height, 255)
            p.rect(vx + vw, 0, p.width - vx - vw, p.height, 255)
            return
        data = runtime_data()
        t = state.elapsed
        fade = max(0.0, min(1.0, (t - 106.3) / 1.0))
        fade = fade * fade * (3 - 2 * fade)
        apply_palette(app, data["palette"], fade)
        p.cls(255)
        p.clip(round(vx), round(vy), round(vw), round(vh))
        p.rect(vx, vy, vw, vh, 16)
        scale = min(vw / 512, vh / 288)
        ox, oy = vx + (vw - 512 * scale) / 2, vy + (vh - 288 * scale) / 2
        index = min(len(data["frames"]) - 1, int(t * data["fps"]))
        for asset_index, x, y in data["frames"][index]:
            asset = data["assets"][asset_index]
            w, h = asset["size"]
            if x + w <= 0 or x >= 512 or y + h <= 0 or y >= 288:
                continue
            for source, target in asset["remap"]:
                p.pal(source, target)
            dx = ox + x * scale + (w * scale - w) / 2
            dy = oy + y * scale + (h * scale - h) / 2
            p.blt(dx, dy, runtime_image(asset_index), 0, 0, w, h, asset["colkey"], scale=scale)
            if asset["remap"]:
                p.pal()
    except Exception:
        restore_palette(app)
        raise
    finally:
        p.clip()
