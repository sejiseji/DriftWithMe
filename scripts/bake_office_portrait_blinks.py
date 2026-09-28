from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "src/drift_with_me/assets"
COLKEY = "8"

BLINK_OVERLAYS = {
    "succubus_green": {
        "fills": ((27, 27, 31, 29, "F"), (38, 27, 42, 29, "F")),
        "lines": ((28, 28, 30, 28, "4"), (39, 28, 41, 28, "4")),
    },
    "tired_gray_oldman": {
        "fills": ((20, 26, 26, 29, "D"), (33, 26, 39, 29, "D")),
        "lines": ((21, 28, 25, 28, "1"), (34, 28, 38, 28, "1")),
    },
    "nervous_elf_woodsman": {
        "fills": ((20, 24, 27, 28, "F"), (32, 24, 39, 28, "F")),
        "lines": ((21, 27, 26, 27, "4"), (33, 27, 38, 27, "4")),
    },
    "smug_blond_hero": {
        "fills": ((27, 20, 34, 23, "F"), (38, 23, 44, 27, "F")),
        "lines": ((28, 22, 33, 22, "4"), (39, 25, 43, 25, "4")),
    },
}


def read_rows(path: Path) -> list[list[str]]:
    rows = [list(row) for row in path.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 64 or any(len(row) != 64 for row in rows):
        raise ValueError(f"{path}: expected 64x64 HEX source")
    return rows


def paint_rect(rows: list[list[str]], definition: tuple[int, int, int, int, str]) -> None:
    x0, y0, x1, y1, color = definition
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            rows[y][x] = color


def overlay_rows(source: list[list[str]], definition: dict) -> list[str]:
    closed = [row.copy() for row in source]
    for fill in definition["fills"]:
        paint_rect(closed, fill)
    for line in definition["lines"]:
        paint_rect(closed, line)
    return [
        "".join(
            changed if changed != original else COLKEY
            for original, changed in zip(a, b, strict=True)
        )
        for a, b in zip(source, closed, strict=True)
    ]


def source_hash(rows: list[str]) -> str:
    pixels = bytes(int(char, 16) for row in rows for char in row)
    return hashlib.sha256(pixels).hexdigest()


def main() -> None:
    for portrait_id, definition in BLINK_OVERLAYS.items():
        source = read_rows(ASSET_DIR / f"{portrait_id}_64.hex")
        rows = overlay_rows(source, definition)
        target = ASSET_DIR / f"{portrait_id}_blink_overlay_64.hex"
        target.write_text("\n".join(rows) + "\n", encoding="utf-8")
        print(f"{target.name}: source_hash={source_hash(rows)}")


if __name__ == "__main__":
    main()
