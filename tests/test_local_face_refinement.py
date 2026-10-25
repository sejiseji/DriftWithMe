import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "src/drift_with_me/assets"
ASSETS = {a["id"]: a for a in json.loads((ROOT / "jack_sprite.json").read_text())["source_assets"]}


def pixels(path):
    source = ROOT / path
    if not source.exists():
        source = Path(__file__).parent / "fixtures/npc_face_baselines" / path
    return [int(c, 16) for c in "".join(source.read_text().split())]


@pytest.mark.parametrize("mood", ["normal", "smile", "worried", "surprised", "thinking"])
def test_yumesaki_eye_edit_preserves_clothes_expression_mouth_and_alpha(mood):
    asset = ASSETS["refined_yumesaki_counter_" + mood]
    frame = asset["frames"][0]
    new = pixels(frame["path"])
    old = pixels(frame["path"].replace("_facefix.hex", ".hex"))
    assert new != old
    for i, (a, b) in enumerate(zip(old, new, strict=True)):
        x, y = i % 232, i // 232
        if not (77 <= x < 145 and 63 <= y < 101):
            assert a == b
        assert (a == 8) == (b == 8)


@pytest.mark.parametrize(
    "pose,span", [("normal", (31, 32)), ("look_left", (29, 30)), ("look_right", (34, 35))]
)
def test_miyano_all_map_poses_have_contiguous_white_teeth_and_fixed_body(pose, span):
    a = ASSETS["aug_npc_miyano"]
    f = next(f for f in a["frames"] if f["id"] == pose)
    new = pixels(f["path"])
    old = pixels(f["path"].replace("_facefix.hex", ".hex"))
    for i, (v, w) in enumerate(zip(old, new, strict=True)):
        if i // 64 == 12 and span[0] <= i % 64 <= span[1]:
            assert w == 7
        else:
            assert v == w
    assert a["anchor_px"] == [32, 64] and a["world_size"] == [32, 32]


def test_miyano_large_teeth_change_is_white_only_and_fuji_is_not_edited():
    f = ASSETS["w4_miyano_dialogue_identity_normal"]["frames"][0]
    old = pixels(f["path"].replace("_facefix.hex", ".hex"))
    new = pixels(f["path"])
    changed = [i for i, (a, b) in enumerate(zip(old, new, strict=True)) if a != b]
    assert changed and all(
        new[i] == 7 and 80 <= i % 200 < 103 and 62 <= i // 200 < 68 for i in changed
    )
    for key in [
        "fuji_matte",
        "fuji_map_knees",
        "w4_fuji_dialogue_identity_normal",
        "refined_fuji_counter_normal",
        "aug_npc_fuji",
    ]:
        assert all("_facefix" not in f["path"] for f in ASSETS[key]["frames"])
