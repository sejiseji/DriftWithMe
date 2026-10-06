from __future__ import annotations

import hashlib
from pathlib import Path

import pyxel

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "src/drift_with_me/assets"
RESOURCE_PATH = ASSET_DIR / "jack_sprite.pyxres"

BLINK_FRAMES = {
    "front_left": {
        "source": "jack_front_left_00.hex",
        "target": "jack_front_left_blink_00.hex",
        "position": (64, 0),
        "fills": ((5, 18, 7, 22), (18, 18, 21, 22)),
        "lines": ((6, 20, 7, 20), (19, 20, 20, 20)),
    },
    "front_right": {
        "source": "jack_front_right_00.hex",
        "target": "jack_front_right_blink_00.hex",
        "position": (96, 0),
        "fills": ((10, 18, 13, 22), (24, 18, 26, 22)),
        "lines": ((11, 20, 12, 20), (24, 20, 25, 20)),
    },
    "front": {
        "source": "jack_front_00.hex",
        "target": "jack_front_blink_00.hex",
        "position": (64, 32),
        "fills": ((8, 18, 11, 22), (20, 18, 23, 22)),
        "lines": ((9, 20, 10, 20), (21, 20, 22, 20)),
    },
    "left": {
        "source": "jack_left_00.hex",
        "target": "jack_left_blink_00.hex",
        "position": (64, 64),
        "fills": ((7, 18, 10, 22),),
        "lines": ((8, 20, 9, 20),),
    },
    "right": {
        "source": "jack_right_00.hex",
        "target": "jack_right_blink_00.hex",
        "position": (96, 64),
        "fills": ((21, 18, 24, 22),),
        "lines": ((22, 20, 23, 20),),
    },
}


def read_rows(path: Path) -> list[list[str]]:
    rows = [list(row) for row in path.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 32 or any(len(row) != 32 for row in rows):
        raise ValueError(f"{path}: expected 32x32 HEX source")
    return rows


def apply_blink(rows: list[list[str]], definition: dict) -> None:
    for x0, y0, x1, y1 in definition["fills"]:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                rows[y][x] = "E"
    for x0, y0, x1, y1 in definition["lines"]:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                rows[y][x] = "1"


def frame_hash(rows: list[str]) -> str:
    pixels = bytes(int(char, 16) for row in rows for char in row)
    return hashlib.sha256(pixels).hexdigest()


def main() -> None:
    rendered: dict[str, tuple[list[str], tuple[int, int]]] = {}
    for name, definition in BLINK_FRAMES.items():
        rows = read_rows(ASSET_DIR / definition["source"])
        apply_blink(rows, definition)
        text_rows = ["".join(row) for row in rows]
        (ASSET_DIR / definition["target"]).write_text("\n".join(text_rows) + "\n", encoding="utf-8")
        rendered[name] = (text_rows, definition["position"])

    pyxel.init(1, 1, title="Bake Jack blink sprites", headless=True)
    pyxel.load(str(RESOURCE_PATH))
    for rows, (u, v) in rendered.values():
        pyxel.images[0].set(u, v, rows)
    pyxel.save(
        str(RESOURCE_PATH),
        exclude_tilemaps=True,
        exclude_sounds=True,
        exclude_musics=True,
    )

    for name, (rows, position) in rendered.items():
        print(f"{name}: position={position} source_hash={frame_hash(rows)}")


if __name__ == "__main__":
    main()
