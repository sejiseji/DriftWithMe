from __future__ import annotations

import argparse
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "src" / "drift_with_me" / "assets"
SIZE = 16
DIR8 = (
    (1.0, 0.0),
    (math.sqrt(0.5), math.sqrt(0.5)),
    (0.0, 1.0),
    (-math.sqrt(0.5), math.sqrt(0.5)),
    (-1.0, 0.0),
    (-math.sqrt(0.5), -math.sqrt(0.5)),
    (0.0, -1.0),
    (math.sqrt(0.5), -math.sqrt(0.5)),
)


def blank() -> list[list[int]]:
    return [[0 for _ in range(SIZE)] for _ in range(SIZE)]


def set_pixel(canvas: list[list[int]], x: int, y: int, color: int) -> None:
    if 0 <= x < SIZE and 0 <= y < SIZE:
        canvas[y][x] = color


def draw_line(canvas: list[list[int]], x0: int, y0: int, x1: int, y1: int, color: int) -> None:
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        set_pixel(canvas, x0, y0, color)
        if x0 == x1 and y0 == y1:
            return
        doubled = error * 2
        if doubled >= dy:
            error += dy
            x0 += sx
        if doubled <= dx:
            error += dx
            y0 += sy


def link_pixels(direction_index: int) -> tuple[str, ...]:
    canvas = blank()
    direction_x, direction_y = DIR8[direction_index]
    normal_x, normal_y = -direction_y, direction_x
    length = 7.0
    samples: list[tuple[int, int]] = []
    for step in range(9):
        amount = step / 8.0
        irregular = math.sin(amount * math.pi) * 0.30
        x = round(8 + direction_x * length * amount + normal_x * irregular)
        y = round(8 + direction_y * length * amount + normal_y * irregular)
        if not samples or samples[-1] != (x, y):
            samples.append((x, y))

    for x, y in samples:
        set_pixel(canvas, x, y, 1)
        set_pixel(canvas, x + 1, y, 1)
        set_pixel(canvas, x - 1, y, 1)
        set_pixel(canvas, x, y + 1, 1)
        set_pixel(canvas, x, y - 1, 1)
    for index, (x, y) in enumerate(samples):
        set_pixel(canvas, x, y, 8)
        if 0 < index < len(samples) - 1:
            shadow_x = round(x + normal_x)
            shadow_y = round(y + normal_y)
            set_pixel(canvas, shadow_x, shadow_y, 2)
        if index in {2, 6}:
            highlight_x = round(x - normal_x)
            highlight_y = round(y - normal_y)
            set_pixel(canvas, highlight_x, highlight_y, 14)

    joint_x, joint_y = samples[0]
    set_pixel(canvas, joint_x, joint_y, 14)
    tip_x, tip_y = samples[-1]
    set_pixel(canvas, tip_x, tip_y, 15)
    return tuple("".join(format(pixel, "X") for pixel in row) for row in canvas)


def claw_pixels(direction_index: int) -> tuple[str, ...]:
    canvas = blank()
    direction_x, direction_y = DIR8[direction_index]
    directions = (
        DIR8[(direction_index - 1) % 8],
        (direction_x, direction_y),
        DIR8[(direction_index + 1) % 8],
    )
    center_x = 8
    center_y = 8

    for y in range(center_y - 2, center_y + 3):
        for x in range(center_x - 2, center_x + 3):
            distance = abs(x - center_x) + abs(y - center_y)
            if distance <= 2:
                set_pixel(canvas, x, y, 1)
    for y in range(center_y - 1, center_y + 2):
        for x in range(center_x - 1, center_x + 2):
            if abs(x - center_x) + abs(y - center_y) <= 1:
                set_pixel(canvas, x, y, 8)
    set_pixel(canvas, center_x - round(direction_y), center_y + round(direction_x), 2)
    set_pixel(canvas, center_x, center_y, 14)

    for finger_index, (finger_x, finger_y) in enumerate(directions):
        start_x = round(center_x + direction_x * 1.5)
        start_y = round(center_y + direction_y * 1.5)
        reach = 4.5 if finger_index == 1 else 4.0
        end_x = round(center_x + finger_x * reach + direction_x * 1.0)
        end_y = round(center_y + finger_y * reach + direction_y * 1.0)
        draw_line(canvas, start_x, start_y, end_x, end_y, 1)
        inner_x = round(center_x + finger_x * (reach - 1.0) + direction_x)
        inner_y = round(center_y + finger_y * (reach - 1.0) + direction_y)
        draw_line(canvas, start_x, start_y, inner_x, inner_y, 14)
        set_pixel(canvas, end_x, end_y, 15)
    return tuple("".join(format(pixel, "X") for pixel in row) for row in canvas)


def expected_assets() -> dict[Path, str]:
    generated: dict[Path, str] = {}
    for direction_index in range(8):
        parts = {
            "link": link_pixels(direction_index),
            "claw": claw_pixels(direction_index),
        }
        for part, rows in parts.items():
            path = ASSET_DIR / f"abnormal_urchin_{part}_dir{direction_index}_00.hex"
            generated[path] = "\n".join(rows) + "\n"
    return generated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    stale: list[Path] = []
    for path, expected in expected_assets().items():
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                stale.append(path)
            continue
        path.write_text(expected, encoding="utf-8")

    if stale:
        for path in stale:
            print(f"stale: {path.relative_to(ROOT)}")
        return 1
    if args.check:
        print("abnormal urchin arm parts: PASS")
    else:
        print("abnormal urchin arm parts: generated 16 HEX frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
