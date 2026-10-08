"""Small ground-level shapes using the game's existing palette and grass."""

from __future__ import annotations

from drift_with_me.math3d import Vec3


def polygon(renderer, camera, points, color):
    projected = [camera.project(Vec3(x, 0, z)) for x, z in points]
    if any(p is None for p in projected):
        return
    a = projected[0]
    for b, c in zip(projected[1:-1], projected[2:], strict=True):
        renderer.pyxel.tri(a.x, a.y, b.x, b.y, c.x, c.y, color)


def draw_east_site_ground(renderer, model, camera):
    site = model.world.raw.get("east_site")
    if not site:
        return
    pyxel = renderer.pyxel
    # Short connection to the existing shallow patch, not a movement barrier.
    pyxel.dither(0.4)
    try:
        polygon(
            renderer,
            camera,
            [(900, 231), (924, 225), (950, 233), (952, 263), (932, 281), (902, 272)],
            5,
        )
    finally:
        pyxel.dither(1)
    for a, b in (((904, 234), (946, 235)), ((907, 271), (934, 278))):
        p, q = camera.project(Vec3(a[0], 0, a[1])), camera.project(Vec3(b[0], 0, b[1]))
        if p and q:
            pyxel.line(p.x, p.y, q.x, q.y, 5)
    # The stable water remains traversable. Only the collapsed landing is closed.
    if not model.world.east_site_access_ready:
        bank = renderer.sprite_assets.get("collapsed_bank_64x136")
        if bank is not None:
            renderer.draw_ground_source_asset(bank, camera, 960, 184)
    # Permanent canopy shade, distinct from the moving cloud pass that follows.
    pyxel.dither(0.24)
    try:
        polygon(
            renderer,
            camera,
            [
                (856, 30),
                (872, 22),
                (898, 27),
                (912, 42),
                (904, 58),
                (880, 66),
                (856, 57),
                (848, 42),
            ],
            0,
        )
    finally:
        pyxel.dither(1)
    # Lid rim and closed plate: no hatch-opening or underground map in this step.
    x, z = 928, 144
    rim = [
        (x - 12, z - 6),
        (x - 7, z - 10),
        (x + 9, z - 10),
        (x + 14, z - 3),
        (x + 11, z + 9),
        (x - 9, z + 10),
        (x - 14, z + 2),
    ]
    polygon(renderer, camera, rim, 0)
    polygon(
        renderer,
        camera,
        [
            (x - 9, z - 5),
            (x - 6, z - 8),
            (x + 7, z - 8),
            (x + 11, z - 2),
            (x + 8, z + 7),
            (x - 7, z + 8),
            (x - 11, z + 1),
        ],
        5,
    )
    polygon(renderer, camera, [(x - 5, z - 5), (x + 6, z - 5), (x + 9, z + 3), (x - 7, z + 5)], 1)
    grass = renderer.configured_sprite_asset(model, "grass_patch_low_a_asset")
    if grass is not None:
        renderer.draw_ground_source_asset(grass, camera, 948, 154)
    # Keep the small handle legible above the fringe of grass.
    p = camera.project(Vec3(x + 1, 2, z - 1))
    if p:
        scale = camera.viewport_width / 512 * getattr(camera, "zoom", 1.0)
        w, h = max(3, round(5 * scale)), max(2, round(3 * scale))
        pyxel.rectb(p.x - w / 2, p.y - h, w, h, 6)
