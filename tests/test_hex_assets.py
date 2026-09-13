from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from drift_with_me.camera import camera_ground_axes
from drift_with_me.config import load_runtime_config
from drift_with_me.hex_assets import (
    HexAssetError,
    draw_scaled_sprite,
    load_runtime_sprite_library,
    load_sprite_manifest_path,
    parse_hex_rows,
    placement_for_upright_height_billboard,
    source_hash_for_pixels,
)
from drift_with_me.math3d import CameraState, Vec3, screen_to_world_direction
from drift_with_me.model import GameModel
from drift_with_me.render import Renderer
from drift_with_me.world import load_world_data

ROOT = Path(__file__).resolve().parents[1]
ROWS = ("012", "345", "678", "9AB", "CDE")
JACK_SOURCE_HASH = "9e63b51c48c928394fc992bda83c1c851588f69ba4dae7be7e340054d885cd7d"
JACK_FRONT_SOURCE_HASH = "5cf48ead95a750c893f45e925bbe33d8deb5e778945e33e78fd74e4fc003cf6f"
JACK_BACK_SOURCE_HASH = "19848ca6c4c3e4df4670ae62824943a054aed4fe56a3a57320aa605a3f67d7b6"
JACK_DIRECTION_HASHES = {
    "front": JACK_FRONT_SOURCE_HASH,
    "front_left": JACK_SOURCE_HASH,
    "front_right": "173a29c11bf5952a27e37a3a501a8ac5f941c9de0eb7e424238b30fca39784ab",
    "left": "ddeb02e3d1ff05281c9fb0ebfadf94c31ca7c66ff55ba5ac273ae68be160d419",
    "back_left": "48d752c3ea5e5c4669306669cb7159953d637615e09d22edd58a9f30f171b5a0",
    "back": JACK_BACK_SOURCE_HASH,
    "back_right": "c3f00558ffc3b6cf579e96cfd730e406501859602d26a3fb5b785f9b6c19d72a",
    "right": "00792669416356148de3d10ec2320cf6013e94f71328aac9670319b02934dfd8",
}
JACK_DIRECTION_RECTS = {
    "front_left": (0, 0, 32, 32),
    "front_right": (32, 0, 32, 32),
    "front": (0, 32, 32, 32),
    "left": (0, 64, 32, 32),
    "back_left": (32, 64, 32, 32),
    "right": (0, 96, 32, 32),
    "back_right": (32, 96, 32, 32),
    "back": (0, 128, 32, 32),
}
NORMAL_URCHIN_SOURCE_HASH = "a9e16f5b554a53f4492849cf05f937e3657a2b0aed64bd46f13357148f850d03"
NORMAL_URCHIN_RECT = (64, 160, 32, 32)
ABNORMAL_URCHIN_SOURCE_HASHES = {
    "body": "0b2a6e1715d99944fcf38e57300a70c750be3f40d5317cc4362e20371caf8b4b",
    "composite": "9def2c00c1daaf9642812966229d1f2d6afbc04269cad3e1bdd246fbb76e0f4b",
    "hand_screen_left": "11c55440e8b97445525bcbf86b5bc8116fd1bb770b55e8a7d9a6010f20ba9708",
    "hand_screen_right": "540500b38cc374fe8005849c3b9e3cd594751cc31685a0ffb79db75caa7c5136",
    "hands": "823ec08a050a63ce68f08217dc7005d622e0d91ca04f0f86a8dd1a299ee98b7c",
}
ABNORMAL_URCHIN_RECT = (0, 160, 64, 64)
FUSE_DIRECTION_HASHES = {
    "front": "a9c9661505e49fbf9d42a4e2f066c2a668b68677d844eb8eaa8000620460189c",
    "front_right": "669450adbdc57c659942a737164f6727866ef22ac129e647f621482442d850f8",
    "right": "e4d70c506274fec641c01111add437712777f7e7c6f67101dcbd3c15ffbab5e8",
    "back_right": "4ade96bae2660569dea2826941e5853f100ab218aaf00ef1dd85b1d39d93ef57",
    "back": "f36e148c68b10c0f99cdeb0732f90e53d0d074af8f953cd5501d09ca06c19058",
    "back_left": "18fba52bce98e9a0277f0a0e0d6ed6ba6a886dad4397ae8f50f43b73ce4ec926",
    "left": "f7d1a7b3f13c1a57e5505b7706cb03a82721a0197f6b7db1fdb8b56e74838d95",
    "front_left": "3d4f0deba3774002fa4b205c89ce56569e4721eaabd73b7e3bf8ef9a7c10cf13",
}
FUSE_DIRECTION_RECTS = {
    "front_right": (128, 0, 48, 40),
    "front_left": (176, 0, 48, 40),
    "front": (128, 40, 48, 40),
    "right": (176, 40, 48, 40),
    "back_right": (128, 80, 48, 40),
    "back": (176, 80, 48, 40),
    "back_left": (128, 120, 48, 40),
    "left": (176, 120, 48, 40),
}


class RecordingPyxel:
    def __init__(self) -> None:
        self.blt_calls = []

    def blt(self, *args, **kwargs) -> None:
        self.blt_calls.append((args, kwargs))


def pixel_hash(rows: tuple[str, ...]) -> str:
    pixels = bytes(int(char, 16) for row in rows for char in row)
    return hashlib.sha256(pixels).hexdigest()


@pytest.mark.parametrize("direction", tuple(JACK_DIRECTION_HASHES))
def test_jack_source_hex_preserves_received_pixels(direction: str) -> None:
    rows = tuple(
        (ROOT / f"src/drift_with_me/assets/jack_{direction}_00.hex")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )

    assert len(rows) == 32
    assert {len(row) for row in rows} == {32}
    assert pixel_hash(rows) == JACK_DIRECTION_HASHES[direction]


def test_normal_urchin_source_hex_preserves_received_pixels() -> None:
    rows = tuple(
        (ROOT / "src/drift_with_me/assets/normal_urchin_idle_00.hex")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )

    assert len(rows) == 32
    assert {len(row) for row in rows} == {32}
    assert pixel_hash(rows) == NORMAL_URCHIN_SOURCE_HASH


@pytest.mark.parametrize("part", tuple(ABNORMAL_URCHIN_SOURCE_HASHES))
def test_abnormal_urchin_source_hex_preserves_received_pixels(part: str) -> None:
    rows = tuple(
        (ROOT / f"src/drift_with_me/assets/abnormal_urchin_{part}_00.hex")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )

    assert len(rows) == 64
    assert {len(row) for row in rows} == {64}
    assert pixel_hash(rows) == ABNORMAL_URCHIN_SOURCE_HASHES[part]


@pytest.mark.parametrize("direction", tuple(FUSE_DIRECTION_HASHES))
def test_fuse_source_hex_preserves_received_pixels(direction: str) -> None:
    rows = tuple(
        (ROOT / f"src/drift_with_me/assets/fuse_{direction}_neutral.hex")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )

    assert len(rows) == 40
    assert {len(row) for row in rows} == {48}
    assert pixel_hash(rows) == FUSE_DIRECTION_HASHES[direction]


def valid_asset(asset_id: str = "jack_test", frame_path: str = "jack.hex") -> dict:
    frame_hash = pixel_hash(ROWS)
    return {
        "schema_version": 1,
        "id": asset_id,
        "palette_id": "pyxel_default_16",
        "hex_width": 3,
        "hex_height": 5,
        "colkey": 0,
        "anchor_px": [1.5, 5],
        "world_size": [6.0, 10.0],
        "projection_mode": "upright_height_billboard_v1",
        "flip_policy": "none",
        "frames": [{"id": "idle", "path": frame_path, "source_hash": frame_hash}],
        "animation": "static",
        "source_hash": frame_hash,
    }


def write_manifest(tmp_path: Path, asset: dict, rows: tuple[str, ...] = ROWS) -> Path:
    manifest_path = tmp_path / "sprites.json"
    frame_path = tmp_path / asset["frames"][0]["path"]
    frame_path.parent.mkdir(parents=True, exist_ok=True)
    frame_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "assets": [asset]}, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def write_manifest_assets(tmp_path: Path, assets: list[dict]) -> Path:
    manifest_path = tmp_path / "sprites.json"
    for asset in assets:
        frame_path = tmp_path / asset["frames"][0]["path"]
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        frame_path.write_text("\n".join(ROWS) + "\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "assets": assets}, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_parse_hex_rows_accepts_crlf_and_preserves_color_numbers() -> None:
    rows = parse_hex_rows("012\r\nABC\r\n", 3, 2, "test.hex")

    assert rows == ("012", "ABC")
    assert source_hash_for_pixels(bytes([0, 1, 2, 10, 11, 12])) == pixel_hash(rows)


def test_load_manifest_transfers_hex_into_pyxel_image(tmp_path: Path) -> None:
    import pyxel

    manifest_path = write_manifest(tmp_path, valid_asset())

    library = load_sprite_manifest_path(pyxel, manifest_path)
    asset = library.get("jack_test")
    assert asset is not None
    frame = asset.frame()

    assert frame.source is not None
    assert frame.source.source_hash == pixel_hash(ROWS)
    assert [[frame.image.pget(x, y) for x in range(3)] for y in range(5)] == [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
        [9, 10, 11],
        [12, 13, 14],
    ]


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("01a\nFFF\n", "invalid HEX"),
        ("012\n34\n", "expected 3 columns"),
        ("012\nABC\n\n", "expected 2 rows"),
        ("012\rABC\n", "lone CR"),
    ],
)
def test_parse_hex_rows_rejects_non_contract_input(text: str, match: str) -> None:
    with pytest.raises(HexAssetError, match=match):
        parse_hex_rows(text, 3, 2, "bad.hex")


def test_manifest_rejects_bad_aspect_ratio(tmp_path: Path) -> None:
    import pyxel

    asset = valid_asset()
    asset["world_size"] = [8.0, 10.0]
    manifest_path = write_manifest(tmp_path, asset)

    with pytest.raises(HexAssetError, match="aspect ratio"):
        load_sprite_manifest_path(pyxel, manifest_path)


def test_manifest_rejects_source_hash_mismatch(tmp_path: Path) -> None:
    import pyxel

    asset = valid_asset()
    asset["source_hash"] = "0" * 64
    manifest_path = write_manifest(tmp_path, asset)

    with pytest.raises(HexAssetError, match="source_hash mismatch"):
        load_sprite_manifest_path(pyxel, manifest_path)


def test_manifest_rejects_unsafe_frame_path(tmp_path: Path) -> None:
    import pyxel

    asset = valid_asset(frame_path="../jack.hex")
    manifest_path = tmp_path / "sprites.json"
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "assets": [asset]}, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(HexAssetError, match="expected normalized relative path"):
        load_sprite_manifest_path(pyxel, manifest_path)


def test_placement_keeps_sprite_anchor_on_projected_world_point(tmp_path: Path) -> None:
    import pyxel

    manifest_path = write_manifest(tmp_path, valid_asset())
    asset = load_sprite_manifest_path(pyxel, manifest_path).get("jack_test")
    assert asset is not None
    runtime = load_runtime_config()
    camera = CameraState.from_config(
        runtime.raw,
        Vec3(512.0, 0.0, 512.0),
        runtime.screen_width,
        runtime.screen_height,
    )
    anchor = Vec3(512.0, 1.5, 512.0)
    projected = camera.project(anchor)
    assert projected is not None

    placement = placement_for_upright_height_billboard(camera, asset.definition, anchor)
    assert placement is not None
    center_x = asset.definition.hex_width / 2.0
    center_y = asset.definition.hex_height / 2.0
    anchor_x, anchor_y = asset.definition.anchor_px

    assert placement.blt_x + center_x + placement.scale * (anchor_x - center_x) == pytest.approx(
        projected.x
    )
    assert placement.blt_y + center_y + placement.scale * (anchor_y - center_y) == pytest.approx(
        projected.y
    )
    assert placement.right - placement.left == pytest.approx(
        asset.definition.hex_width * placement.scale
    )
    assert placement.bottom - placement.top == pytest.approx(
        asset.definition.hex_height * placement.scale
    )


def test_flipped_placement_mirrors_anchor_and_draws_negative_width(tmp_path: Path) -> None:
    import pyxel

    raw_asset = valid_asset()
    raw_asset["anchor_px"] = [1.0, 5]
    manifest_path = write_manifest(tmp_path, raw_asset)
    asset = load_sprite_manifest_path(pyxel, manifest_path).get("jack_test")
    assert asset is not None
    runtime = load_runtime_config()
    camera = CameraState.from_config(
        runtime.raw,
        Vec3(512.0, 0.0, 512.0),
        runtime.screen_width,
        runtime.screen_height,
    )
    anchor = Vec3(512.0, 1.5, 512.0)
    projected = camera.project(anchor)
    assert projected is not None

    placement = placement_for_upright_height_billboard(
        camera, asset.definition, anchor, flip_x=True
    )
    assert placement is not None
    assert placement.flip_x
    mirrored_anchor_x = asset.definition.hex_width - 1.0
    assert placement.left == pytest.approx(projected.x - mirrored_anchor_x * placement.scale)

    fake_pyxel = RecordingPyxel()
    draw_scaled_sprite(fake_pyxel, asset.frame(), asset.definition, placement)

    args, _kwargs = fake_pyxel.blt_calls[0]
    assert args[5] == -3
    assert args[6] == 5


def test_runtime_sprite_library_reports_missing_manifest_without_crashing() -> None:
    import pyxel

    runtime = load_runtime_config()
    raw = copy.deepcopy(runtime.raw)
    raw["assets"]["sprite_rendering_enabled"] = True
    raw["assets"]["manifest"] = "assets/missing.json"

    library = load_runtime_sprite_library(pyxel, raw)

    assert library.enabled
    assert library.assets == {}
    assert library.errors


def test_runtime_pyxres_manifest_loads_jack_and_preserves_nonimage_banks() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    code = f"""
import json

import pyxel

from drift_with_me.config import load_runtime_config
from drift_with_me.hex_assets import load_runtime_sprite_library
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel
from drift_with_me.render import Renderer
from drift_with_me.world import load_world_data


def sound_snapshot():
    sound = pyxel.sounds[0]
    return (
        tuple(sound.notes),
        tuple(sound.tones),
        tuple(sound.volumes),
        tuple(sound.effects),
        sound.speed,
    )


def music_snapshot():
    return tuple(tuple(seq) for seq in pyxel.musics[0].seqs)


runtime = load_runtime_config()
pyxel.init(
    runtime.screen_width,
    runtime.screen_height,
    title="DriftWithMe pyxres test",
    headless=True,
)
pyxel.sounds[0].set("c3e3g3", "t", "3", "n", 10)
pyxel.musics[0].set([0], [], [], [])
pyxel.tilemaps[0].pset(0, 0, (1, 2))
before_sound = sound_snapshot()
before_music = music_snapshot()
before_tile = pyxel.tilemaps[0].pget(0, 0)
before_palette = tuple(pyxel.colors)

library = load_runtime_sprite_library(pyxel, runtime.raw)
assert library.enabled
assert library.errors == (), library.errors
asset = library.get("jack_idle_32")
assert asset is not None
frame = asset.frame()
assert frame.image == 0
assert (frame.u, frame.v, frame.width, frame.height) == (0, 0, 32, 32)
assert frame.source_hash == {JACK_SOURCE_HASH!r}
assert asset.definition.anchor_px == (16.0, 32.0)
assert asset.definition.world_size == (16.0, 16.0)
assert pyxel.images[0].pget(16, 32 - 1) != 0
front = library.get("jack_front_32")
assert front is not None
front_frame = front.frame()
assert (front_frame.u, front_frame.v, front_frame.width, front_frame.height) == (0, 32, 32, 32)
assert front_frame.source_hash == {JACK_FRONT_SOURCE_HASH!r}
back = library.get("jack_back_32")
assert back is not None
back_frame = back.frame()
assert (back_frame.u, back_frame.v, back_frame.width, back_frame.height) == (0, 128, 32, 32)
assert back_frame.source_hash == {JACK_BACK_SOURCE_HASH!r}
jack_assets = {JACK_DIRECTION_HASHES!r}
jack_rects = {JACK_DIRECTION_RECTS!r}
urchin_rect = {NORMAL_URCHIN_RECT!r}
abnormal_urchin_rect = {ABNORMAL_URCHIN_RECT!r}
for direction, expected_hash in jack_assets.items():
    jack = library.get(f"jack_{{direction}}_32")
    assert jack is not None, direction
    frame = jack.frame()
    assert (frame.u, frame.v, frame.width, frame.height) == jack_rects[direction]
    assert frame.source_hash == expected_hash
    assert jack.definition.colkey == 0
    assert jack.definition.anchor_px == (16.0, 32.0)
    assert jack.definition.world_size == (16.0, 16.0)
for direction in jack_assets:
    assert runtime.raw["assets"][f"player_{{direction}}_asset"] == f"jack_{{direction}}_32"
urchin = library.get("normal_urchin_idle_32")
assert urchin is not None
urchin_frame = urchin.frame()
assert (urchin_frame.u, urchin_frame.v, urchin_frame.width, urchin_frame.height) == urchin_rect
assert urchin_frame.source_hash == {NORMAL_URCHIN_SOURCE_HASH!r}
assert urchin.definition.colkey == 0
assert urchin.definition.anchor_px == (16.0, 32.0)
assert urchin.definition.world_size == (20.0, 20.0)
assert runtime.raw["assets"]["normal_urchin_idle_asset"] == "normal_urchin_idle_32"
abnormal = library.get("abnormal_urchin_inward_hands_64")
assert abnormal is not None
abnormal_frame = abnormal.frame()
assert (
    abnormal_frame.u,
    abnormal_frame.v,
    abnormal_frame.width,
    abnormal_frame.height,
) == abnormal_urchin_rect
assert abnormal_frame.source_hash == {ABNORMAL_URCHIN_SOURCE_HASHES["composite"]!r}
assert abnormal.definition.colkey == 0
assert abnormal.definition.anchor_px == (32.0, 62.0)
assert abnormal.definition.world_size == (20.0, 20.0)
assert runtime.raw["assets"]["abnormal_urchin_idle_asset"] == "abnormal_urchin_inward_hands_64"
fuse_assets = {FUSE_DIRECTION_HASHES!r}
fuse_rects = {FUSE_DIRECTION_RECTS!r}
fuse_frame = None
for direction, expected_hash in fuse_assets.items():
    fuse = library.get(f"fuse_{{direction}}_neutral_48")
    assert fuse is not None, direction
    frame = fuse.frame()
    assert (frame.u, frame.v, frame.width, frame.height) == fuse_rects[direction]
    assert frame.source_hash == expected_hash
    assert fuse.definition.colkey == 2
    assert fuse.definition.anchor_px == (24.0, 30.0)
    assert all(
        abs(actual - expected) < 1e-9
        for actual, expected in zip(
            fuse.definition.world_size,
            (25.2, 21.0),
            strict=True,
        )
    )
    if direction == "front_right":
        fuse_frame = frame
assert fuse_frame is not None
assert runtime.raw["assets"]["buddy_idle_asset"] == "fuse_front_right_neutral_48"
for direction in fuse_assets:
    assert runtime.raw["assets"][f"buddy_{{direction}}_asset"] == f"fuse_{{direction}}_neutral_48"
assert sound_snapshot() == before_sound
assert music_snapshot() == before_music
assert pyxel.tilemaps[0].pget(0, 0) == before_tile
assert tuple(pyxel.colors) == before_palette

model = GameModel(runtime.raw, load_world_data())
camera = CameraState.from_config(
    runtime.raw,
    Vec3(model.player.x, 0.0, model.player.z),
    runtime.screen_width,
    runtime.screen_height,
)
renderer = Renderer(pyxel, library)
pyxel.cls(3)
assert renderer.draw_player_sprite(model, camera, presentation_time=0.0)
placement = renderer.player_sprite_placement(model, camera, presentation_time=0.0)
assert placement is not None
left, top, width, height = placement.rect
visible_pixels = 0
for y in range(max(0, top), min(runtime.screen_height, top + height)):
    for x in range(max(0, left), min(runtime.screen_width, left + width)):
        visible_pixels += pyxel.pget(x, y) != 3
assert visible_pixels > 0
pyxel.cls(3)
enemy = next(enemy for enemy in model.enemies if enemy.kind == "normal")
assert renderer.normal_enemy_sprite_asset(model) is not None
assert renderer.normal_enemy_sprite_placement(model, enemy, camera) is not None
renderer.draw_enemy(model, enemy, camera)
placement = renderer.normal_enemy_sprite_placement(model, enemy, camera)
assert placement is not None
left, top, width, height = placement.rect
visible_pixels = 0
for y in range(max(0, top), min(runtime.screen_height, top + height)):
    for x in range(max(0, left), min(runtime.screen_width, left + width)):
        visible_pixels += pyxel.pget(x, y) != 3
assert visible_pixels > 0
pyxel.cls(3)
enemy = next(enemy for enemy in model.enemies if enemy.kind == "abnormal")
enemy.x = model.player.x + 40.0
enemy.z = model.player.z + 24.0
assert renderer.abnormal_enemy_sprite_asset(model) is not None
assert renderer.abnormal_enemy_sprite_placement(model, enemy, camera) is not None
renderer.draw_enemy(model, enemy, camera)
placement = renderer.abnormal_enemy_sprite_placement(model, enemy, camera)
assert placement is not None
left, top, width, height = placement.rect
visible_pixels = 0
for y in range(max(0, top), min(runtime.screen_height, top + height)):
    for x in range(max(0, left), min(runtime.screen_width, left + width)):
        visible_pixels += pyxel.pget(x, y) != 3
assert visible_pixels > 0
pyxel.cls(3)
assert renderer.draw_buddy_sprite(model, camera, bob=0.0)
placement = renderer.buddy_sprite_placement(model, camera, bob=0.0)
assert placement is not None
left, top, width, height = placement.rect
visible_pixels = 0
for y in range(max(0, top), min(runtime.screen_height, top + height)):
    for x in range(max(0, left), min(runtime.screen_width, left + width)):
        visible_pixels += pyxel.pget(x, y) != 3
assert visible_pixels > 0
print(
    json.dumps(
        {{
            "asset": asset.definition.asset_id,
            "hash": frame.source_hash,
            "fuse": fuse_frame.source_hash,
        }}
    )
)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_renderer_flips_player_sprite_for_screen_right_movement(tmp_path: Path) -> None:
    import pyxel

    manifest_path = write_manifest(tmp_path, valid_asset())
    library = load_sprite_manifest_path(pyxel, manifest_path)
    runtime = load_runtime_config()
    raw = copy.deepcopy(runtime.raw)
    raw["assets"]["sprite_rendering_enabled"] = True
    raw["assets"]["player_idle_asset"] = "jack_test"
    model = GameModel(raw, load_world_data())
    camera = CameraState.from_config(
        raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    screen_right, _ground_forward = camera_ground_axes(camera)
    renderer = Renderer(RecordingPyxel(), library)

    model.player.last_move_x = screen_right.x
    model.player.last_move_z = screen_right.y
    assert renderer.player_sprite_flip_x(model, camera)

    model.player.last_move_x = -screen_right.x
    model.player.last_move_z = -screen_right.y
    assert not renderer.player_sprite_flip_x(model, camera)


def test_renderer_selects_player_front_and_back_assets_for_screen_vertical_movement(
    tmp_path: Path,
) -> None:
    import pyxel

    assets = [
        valid_asset("jack_idle_32", "idle.hex"),
        valid_asset("jack_front_32", "front.hex"),
        valid_asset("jack_back_32", "back.hex"),
    ]
    manifest_path = write_manifest_assets(tmp_path, assets)
    library = load_sprite_manifest_path(pyxel, manifest_path)
    runtime = load_runtime_config()
    raw = copy.deepcopy(runtime.raw)
    raw["assets"]["sprite_rendering_enabled"] = True
    raw["assets"]["player_idle_asset"] = "jack_idle_32"
    raw["assets"]["player_front_asset"] = "jack_front_32"
    raw["assets"]["player_back_asset"] = "jack_back_32"
    model = GameModel(raw, load_world_data())
    camera = CameraState.from_config(
        raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    renderer = Renderer(RecordingPyxel(), library)
    model.player.moved_distance = 1.0

    screen_down = screen_to_world_direction(camera, model.player.x, model.player.z, 0.0, 1.0)
    model.player.last_move_x = screen_down.x
    model.player.last_move_z = screen_down.y
    asset = renderer.player_sprite_asset(model, camera)
    assert asset is not None
    assert asset.definition.asset_id == "jack_front_32"

    screen_up = screen_to_world_direction(camera, model.player.x, model.player.z, 0.0, -1.0)
    model.player.last_move_x = screen_up.x
    model.player.last_move_z = screen_up.y
    asset = renderer.player_sprite_asset(model, camera)
    assert asset is not None
    assert asset.definition.asset_id == "jack_back_32"

    screen_right, _ground_forward = camera_ground_axes(camera)
    model.player.last_move_x = screen_right.x
    model.player.last_move_z = screen_right.y
    asset = renderer.player_sprite_asset(model, camera)
    assert asset is not None
    assert asset.definition.asset_id == "jack_idle_32"


def test_renderer_selects_player_direction_assets_for_screen_movement(tmp_path: Path) -> None:
    import pyxel

    assets = [
        valid_asset(f"jack_{direction}_32", f"{direction}.hex")
        for direction in JACK_DIRECTION_HASHES
    ]
    manifest_path = write_manifest_assets(tmp_path, assets)
    library = load_sprite_manifest_path(pyxel, manifest_path)
    runtime = load_runtime_config()
    raw = copy.deepcopy(runtime.raw)
    raw["assets"]["sprite_rendering_enabled"] = True
    raw["assets"]["player_idle_asset"] = "jack_front_left_32"
    for direction in JACK_DIRECTION_HASHES:
        raw["assets"][f"player_{direction}_asset"] = f"jack_{direction}_32"
    model = GameModel(raw, load_world_data())
    camera = CameraState.from_config(
        raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    renderer = Renderer(RecordingPyxel(), library)
    model.player.moved_distance = 1.0

    cases = (
        ("right", 1.0, 0.0),
        ("front_right", 1.0, 1.0),
        ("front", 0.0, 1.0),
        ("front_left", -1.0, 1.0),
        ("left", -1.0, 0.0),
        ("back_left", -1.0, -1.0),
        ("back", 0.0, -1.0),
        ("back_right", 1.0, -1.0),
    )
    for expected, screen_x, screen_y in cases:
        direction = screen_to_world_direction(
            camera, model.player.x, model.player.z, screen_x, screen_y
        )
        model.player.last_move_x = direction.x
        model.player.last_move_z = direction.y
        asset = renderer.player_sprite_asset(model, camera)
        assert asset is not None
        assert asset.definition.asset_id == f"jack_{expected}_32"


def test_renderer_selects_buddy_direction_assets_for_screen_movement(tmp_path: Path) -> None:
    import pyxel

    assets = [
        valid_asset(f"fuse_{direction}_neutral_48", f"{direction}.hex")
        for direction in FUSE_DIRECTION_HASHES
    ]
    manifest_path = write_manifest_assets(tmp_path, assets)
    library = load_sprite_manifest_path(pyxel, manifest_path)
    runtime = load_runtime_config()
    raw = copy.deepcopy(runtime.raw)
    raw["assets"]["sprite_rendering_enabled"] = True
    raw["assets"]["buddy_idle_asset"] = "fuse_front_right_neutral_48"
    for direction in FUSE_DIRECTION_HASHES:
        raw["assets"][f"buddy_{direction}_asset"] = f"fuse_{direction}_neutral_48"
    model = GameModel(raw, load_world_data())
    camera = CameraState.from_config(
        raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    renderer = Renderer(RecordingPyxel(), library)
    model.player.moved_distance = 1.0

    cases = (
        ("right", 1.0, 0.0),
        ("front_right", 1.0, 1.0),
        ("front", 0.0, 1.0),
        ("front_left", -1.0, 1.0),
        ("left", -1.0, 0.0),
        ("back_left", -1.0, -1.0),
        ("back", 0.0, -1.0),
        ("back_right", 1.0, -1.0),
    )
    for expected, screen_x, screen_y in cases:
        direction = screen_to_world_direction(
            camera, model.player.x, model.player.z, screen_x, screen_y
        )
        model.player.last_move_x = direction.x
        model.player.last_move_z = direction.y
        asset = renderer.buddy_sprite_asset(model, camera)
        assert asset is not None
        assert asset.definition.asset_id == f"fuse_{expected}_neutral_48"
