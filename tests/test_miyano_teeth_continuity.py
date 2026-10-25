import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
ASSETS = ROOT / "src/drift_with_me/assets"
DEFS = {a["id"]: a for a in json.loads((ASSETS / "jack_sprite.json").read_text())["source_assets"]}


@pytest.mark.parametrize(
    "ident,box",
    [
        ("w4_miyano_dialogue_identity_normal", (80, 60, 104, 72)),
        ("refined_miyano_counter_normal", (90, 82, 128, 99)),
        ("miyano_map_knees", (37, 23, 49, 32)),
    ],
)
def test_only_tooth_pixels_change_to_white_without_touching_face_or_transparency(ident, box):
    a = DEFS[ident]
    new = [int(c, 16) for c in "".join((ASSETS / a["frames"][0]["path"]).read_text().split())]
    old = [
        int(c, 16)
        for c in "".join(
            (ROOT / "tests/fixtures/miyano_teeth_pre_continuity" / f"{ident}.hex")
            .read_text()
            .split()
        )
    ]
    width = a["hex_width"]
    changes = [i for i, (v, w) in enumerate(zip(old, new, strict=True)) if v != w]
    assert changes and all(
        new[i] == 7 and box[0] <= i % width < box[2] and box[1] <= i // width < box[3]
        for i in changes
    )
    assert all((v == a["colkey"]) == (w == a["colkey"]) for v, w in zip(old, new, strict=True))
    for y in range(box[1], box[3]):
        xs = [x for x in range(box[0], box[2]) if new[y * width + x] == 7]
        if xs:
            assert xs == list(range(min(xs), max(xs) + 1))
