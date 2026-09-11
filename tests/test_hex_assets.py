from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.hex_assets import (
    HexAssetError,
    load_runtime_sprite_library,
    load_sprite_manifest_path,
    parse_hex_rows,
    placement_for_upright_height_billboard,
    source_hash_for_pixels,
)
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel
from drift_with_me.render import Renderer
from drift_with_me.world import load_world_data

ROWS = ("012", "345", "678", "9AB", "CDE")


class RecordingPyxel:
    def __init__(self) -> None:
        self.blt_calls = []

    def blt(self, *args, **kwargs) -> None:
        self.blt_calls.append((args, kwargs))


def pixel_hash(rows: tuple[str, ...]) -> str:
    pixels = bytes(int(char, 16) for row in rows for char in row)
    return hashlib.sha256(pixels).hexdigest()


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


def test_runtime_sprite_library_is_disabled_by_default() -> None:
    import pyxel

    runtime = load_runtime_config()

    library = load_runtime_sprite_library(pyxel, runtime.raw)

    assert not library.enabled
    assert library.assets == {}
    assert library.errors == ()


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


def test_renderer_can_draw_player_through_loaded_sprite(tmp_path: Path) -> None:
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
    fake_pyxel = RecordingPyxel()
    renderer = Renderer(fake_pyxel, library)

    assert renderer.draw_player_sprite(model, camera, presentation_time=0.0)

    args, kwargs = fake_pyxel.blt_calls[0]
    assert args[2] is library.get("jack_test").frame().image
    assert args[5:7] == (3, 5)
    assert kwargs["colkey"] == 0
    assert kwargs["scale"] > 0.0
