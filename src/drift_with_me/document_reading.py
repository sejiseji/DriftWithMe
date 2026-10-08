"""Small office-only paper and connected tentacle poses, using Jack's palette."""

from __future__ import annotations


def reading_pose_pixels(
    base: tuple[tuple[int, ...], ...], phase: int, *, nod: bool, blink: bool
) -> tuple[tuple[int, ...], ...]:
    if len(base) != 32 or any(len(row) != 32 for row in base):
        raise ValueError("reading pose requires the existing 32px front sprite")
    pixels = [[0] * 32 for _ in range(44)]
    for y, row in enumerate(base):
        target_y = y + int(nod and y < 26)
        pixels[target_y] = list(row)
    # Replace the two existing inner foreground arms below their shared roots.
    # Clear their original hanging tips instead of adding limbs over them.
    for y in range(27, 32):
        for x in range(8, 14 if y >= 28 else 13):
            pixels[y][x] = 0
        for x in range(19, 25 if y >= 28 else 24):
            pixels[y][x] = 0
    # A slight downward gaze. Existing closed eyes remain the approved blink.
    if not blink:
        iris = [(x, y) for y in range(18, 23) for x in range(5, 28) if base[y][x] == 5]
        for x, y in iris:
            target_y = y + int(nod)
            pixels[target_y][x] = 1
        for x, y in iris:
            target_y = y + int(nod) + 1
            pixels[target_y][x] = 5

    def rect(x, y, width, height, color):
        for py in range(y, y + height):
            for px in range(x, x + width):
                pixels[py][px] = color

    rect(4, 31, 24, 10, 1)
    rect(5, 32, 22, 8, 7)
    for y in (33, 35, 37):
        rect(10, y, 13, 1, 13)
    rect(25, 32, 2, 2, 13)

    def line_points(a, b):
        x, y = a
        bx, by = b
        dx, dy = abs(bx - x), -abs(by - y)
        sx, sy = 1 if x < bx else -1, 1 if y < by else -1
        error = dx + dy
        result = []
        while True:
            result.append((x, y))
            if (x, y) == (bx, by):
                return result
            twice = 2 * error
            if twice >= dy:
                error += dy
                x += sx
            if twice <= dx:
                error += dx
                y += sy

    def arm(vertices):
        points = []
        for a, b in zip(vertices, vertices[1:], strict=False):
            points.extend(line_points(a, b))
        for radius, color in ((2, 1), (1, 14)):
            for x, y in points:
                for oy in range(-radius, radius + 1):
                    for ox in range(-radius, radius + 1):
                        if ox * ox + oy * oy <= radius * radius:
                            pixels[y + oy][x + ox] = color
        for x, y in points[::3]:
            pixels[y][x] = 15

    # Continue the original roots at (10,26) and (21,26).
    # Keep the left tip pressed down and bend the right arm along printed rows.
    arm([(10, 26), (10, 29), (9, 33)])
    tip = ((19, 33), (22, 33), (19, 35), (21, 37))[phase % 4]
    arm([(21, 26), (21, 29), tip])
    # The round stroke caps lie inside the original skin at these two joins.
    # Remove only internal dark cap dots, retaining original silhouette edges.
    for y in range(24, 28):
        for x in (*range(8, 13), *range(19, 24)):
            if pixels[y][x] == 1 and base[y][x] in (9, 14, 15):
                pixels[y][x] = 14
    return tuple(tuple(row) for row in pixels)
