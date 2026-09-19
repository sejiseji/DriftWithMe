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
from drift_with_me.model import GameModel, InteractionState
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
NORMAL_URCHIN_SOURCE_HASH = "06fec2bbf7eeac8b6e8b9fab9e4ebc4584c2a364c2ba03d3e34ee41878b0dfa4"
NORMAL_URCHIN_RECT = (64, 160, 64, 64)
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
ENVIRONMENT_WAVE1_SOURCE_HASHES = {
    "water_station_active": "0cd8570bfe0fd3d6dd1b96ab409c36a28f3bddaf6c42d2e1ef4521a87a94c0f1",
    "water_station_stopped": "f5a8ae8eed5e4b5ec7d9f22b4abc76fe59860482efba1a91c775c5f48d3b0309",
    "solar_station_idle": "f5a7fc5bb95ae14b0f3b7923327b8180a9430f240c37ebb15cd40e89d29dd7f1",
    "solar_station_active": "748b9391dc51f2423ccdcd5424824391aeec83583e9ddcc3b46067b8f5492c3f",
    "tree_leafy_a": "a868d992db8472f81045ada9a39cb6893ad88d2d320aa226264868e3a5d8ffe4",
    "tree_thin_b": "68de99d52511238f5ecbad7314e1cdeaa591dbf56916b17a86d0d00866a88e80",
    "reactive_grass_tall": "4b8d853400e617c486a88468f5203906d3f1f5ef6972c132b7614c3fbdf5c8f7",
    "reactive_grass_low": "5706308cefaf67b84c5ee62d0a742b17d5f60f28113e0272ae7fb8318f10c092",
    "ground_pebbles": "4bbbaed6dbc1a8219523d1bcd734171989693d2205428804302a90f7a5af47be",
    "ground_fallen_leaves": "9ee3c9b0ca1baf6a67a043e7650c7eab720b1b666ca886251b3452a21bc8c4aa",
    "ground_crack_grass": "fef48effd241c5d71ff9f7606dda45112e70ccdcd7a0ad1d519e3acc21fefa69",
    "ground_rubble": "bd1d1394dc20ff381e380ea7b373a4056c0d4cb988abc9809614bcad59b35423",
    "concrete_clean_a": "e2b5cfa4caafd4a1d5f3050d5033a5547c5e8251befba4a2467f1edee39c8640",
    "concrete_cracked_a": "442d6e57264e39e5f3ac2718db6fb2ec8ae804748cf39b4922c967063b93658e",
    "concrete_spalled_a": "bdfc8389a72a6e9cf8ba3ec68874e5e322204155c4dc9a93e7bfa21aec96ff31",
    "concrete_joint_grass_a": "a759a7227455db825b88adfaf08399941dbd1bb6c1515d516b2174a6916a0514",
    "decal_stain_a": "01afbe6d0e3b35d3ce16cf6d26531dbb679072cb667f27004821be99a3669f66",
    "decal_crack_grass_a": "10c2354747798a9237d874b9d085134d4327a1d6912d089afa55ca074ddbcdc7",
    "decal_rubble_a": "2a2208d7ab8319fcde96af649212d55db8dfb05652b82b15a1ddfe1f1ce56329",
    "decal_broken_edge_a": "95ae5cf54fc533ce45a78d9c089c55da88b19d60b5708992c05e03346732368a",
    "grass_tall_a": "6d0a65997436af94a5b16727f167e81eb26e249887083e9819cad312bb65c243",
    "grass_low_a": "c117cebf842445c61510bfbf3192997cea3449f2e16e701bad96e64099939964",
    "pebbles_a": "aef2501b657821f6324812832795d68e136f2295230226e4e8388c135cca3966",
    "fallen_leaves_a": "f1b36b299cbd6bf2f1dbcb45e514d5603ba5f50e3c177594e1d0bb09dd0684cd",
    "crack_sprout_a": "31afbd889e88698f704b94d06542c1196eb2be6ccdaa8543ae4bbc057afea7b7",
    "rubble_small_a": "ba84a6adb25c1272dc677101cbc3e941f629403bd9c9d4ffd980e5ff8e6a590e",
    "grass_patch_low_a": "a15dc2ea6edb1a5306b358136ff37cb463158ed6ce764af7beae7b114202a07e",
    "grass_patch_low_b": "854dfd407874d091f6c5eab0757d058f3da8999a24fed7f9c27b2ccb078b5218",
    "grass_patch_tall_a": "2acf33ebd448bf4757960169e4583df102fb580a4acafec83457a3b7328f482a",
    "grass_patch_tall_b": "d5e0c7fc7e59a647472e050dae934904af2ffc7eb19c6e66a10ddcc04d826037",
    "grass_edge_a": "ab61e3da8b6005d4a11eb5c1a446a6e7b279aea8422138895d38f11b51fbd977",
    "grass_scatter_a": "8eaca3d8803852bea6446d34211cb05cfa2921fbb5ea76d99fc211156ffe99a8",
    "giant_tree_root_massive_a": "0a11dc36dec13a26a11d1c07150032e2925b5e0aa1a328a1c0649e0d06b9e052",
    "giant_tree_root_spire_b": "c5033a26b48d675229657950fdd0c50206db739a3e0e4e36e2572dee790ebe59",
    "giant_tree_root_hollow_c": "05db0fbc47deae7b8f24203301e6e4615549d3c637403c03b2724fd1aace8bb3",
    "giant_tree_root_arch_d": "ace5740816d1b0e0cca9b6180713e6fc94ead47028bb13016c00e30687203954",
    "giant_tree_root_tall_b": "b4106c344c6c3269e86667d7488120f14bbf9eb2fd6c2bb4b3f9470928808a5c",
    "giant_tree_stump_ruin_a": "5431102e3105b370050c5ad7a8ee9fedd917a83be13e16a11652badec9eb3aca",
    "giant_tree_root_arch_a": "dd0ccbb80369e9bbe15d734004f9c67d0aa234a382fff1fa15d9d077744107b1",
    "giant_tree_02x_a": "873edfbcc1b37ef7e638d57e332fbc1901e6b34ea4db93c1f7808a75df2b783d",
    "giant_tree_02x_b": "0416f9512913932031523391660a2466642037ac28c811f8b9e6890b84cde9d6",
    "giant_tree_02x_c": "468c2d8da16069f85eb7d652e94f9a90536413be5d1603b88ca0dbe6288bb830",
    "giant_tree_02x_d": "7065feea96acf079fb9f979a3c17337b622e76a9f5b5f30be12cd8822f64ab79",
    "water_surface_glint_horizontal": (
        "0447e5a059faee3fb1a107ba380b7daf13f290197b1f75173a1a0839b007dd8c"
    ),
}
TALL_GRASS_REACTIVE_POSE_HASHES = {
    "idle_00": "3e4c7c8d338024e5acb5af09d519dc8a8697feea0c807f9c76489feddbe5be46",
    "bend_left_1": "2528e2d8645f2225e46c64819530c75821d3132101fd7f354568d8703921340c",
    "bend_left_2": "fb334e1eaf82a9e0b4694dccaf12f8a44416e97c37232a371ac30f3fc8efee0e",
    "recover_left": "606625f04d48519eb0d69bd76d4669316e8f02c989e69f967ee7cd41d74a8c20",
    "bend_right_1": "9584d3c0f7c240d6f7bd90f87e5b2a591ce1c87023e6c2b6d11a9101cee4bd12",
    "bend_right_2": "5bdfb43ce90760a026fde5ba8c1bafe27d08f68f4d60df39bc8fb1f84ce9ce24",
    "recover_right": "a98030ae11e9c285bc35ca8cc83883607978b75cd42771df3bded293f471536c",
}
TALL_GRASS_REACTIVE_SOURCE_HASH = "a7d38ecaa752a6c27d309143ecc2f468d65fa458c4ecc7e2b348838694e3d029"
ENVIRONMENT_WAVE1_RUNTIME_HASHES = {
    **ENVIRONMENT_WAVE1_SOURCE_HASHES,
    "grass_tall_a": TALL_GRASS_REACTIVE_POSE_HASHES["idle_00"],
}
ENVIRONMENT_VISIBLE_COLORS_WITH_COLKEY_8 = {
    "water_station_active": {
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "9",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
    },
    "water_station_stopped": {
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "9",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
    },
    "solar_station_idle": {
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "9",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
    },
    "solar_station_active": {
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "9",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
    },
    "tree_leafy_a": {"0", "1", "2", "3", "4", "5", "7", "9", "A", "B", "C", "D", "E", "F"},
    "tree_thin_b": {"0", "1", "2", "3", "4", "5", "9", "A", "B", "C", "D", "E", "F"},
    "concrete_clean_a": {"1", "5", "7", "D", "F"},
    "concrete_cracked_a": {"0", "1", "5", "7", "D", "F"},
    "concrete_spalled_a": {"1", "5", "7", "D", "F"},
    "concrete_joint_grass_a": {"0", "1", "4", "5", "7", "D", "F"},
    "decal_stain_a": {"1", "4"},
    "decal_crack_grass_a": {"0", "1", "4", "5", "9", "D", "F"},
    "decal_rubble_a": {"0", "1", "4", "5", "7", "9", "D", "F"},
    "decal_broken_edge_a": {"0", "1", "4", "5", "D", "F"},
    "grass_tall_a": {"0", "1", "2", "3", "4", "5", "9", "A", "B", "D", "E", "F"},
    "grass_low_a": {"0", "1", "2", "3", "4", "5", "9", "A", "B", "D", "E", "F"},
    "pebbles_a": {"0", "1", "2", "4", "5", "7", "9", "D", "E", "F"},
    "fallen_leaves_a": {"0", "1", "2", "4", "5", "9", "A", "C", "D", "E", "F"},
    "crack_sprout_a": {"0", "1", "2", "3", "4", "5", "9", "A", "D", "E", "F"},
    "rubble_small_a": {"0", "1", "2", "4", "5", "7", "9", "A", "D", "E", "F"},
    "grass_patch_low_a": {"0", "1", "3", "A", "B"},
    "grass_patch_low_b": {"0", "1", "3", "5", "A", "B", "D"},
    "grass_patch_tall_a": {"0", "1", "3", "5", "A", "B"},
    "grass_patch_tall_b": {"0", "1", "3", "5", "A", "B", "F"},
    "grass_edge_a": {"0", "1", "3", "4", "5", "A", "B"},
    "grass_scatter_a": {"0", "1", "3", "A", "B"},
    "giant_tree_root_massive_a": {
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "9",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
    },
    "giant_tree_root_spire_b": {
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "9",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
    },
    "giant_tree_root_hollow_c": {
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "9",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
    },
    "giant_tree_root_arch_d": {
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "9",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
    },
    "giant_tree_root_tall_b": {
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
    },
    "giant_tree_stump_ruin_a": {
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
    },
    "giant_tree_root_arch_a": {"0", "1", "2", "3", "4", "5", "6", "7", "A", "B", "C", "D", "F"},
    "giant_tree_02x_a": {"0", "1", "2", "3", "4", "5", "6", "7", "9", "A", "B", "C", "D", "E", "F"},
    "giant_tree_02x_b": {"0", "1", "2", "3", "4", "5", "6", "7", "9", "A", "B", "C", "D", "E", "F"},
    "giant_tree_02x_c": {"0", "1", "2", "3", "4", "5", "6", "7", "9", "A", "B", "C", "D", "E", "F"},
    "giant_tree_02x_d": {"0", "1", "2", "3", "4", "5", "6", "7", "9", "A", "B", "C", "D", "E", "F"},
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

    assert len(rows) == 64
    assert {len(row) for row in rows} == {64}
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


@pytest.mark.parametrize("asset_id", tuple(ENVIRONMENT_WAVE1_SOURCE_HASHES))
def test_environment_wave1_source_hex_preserves_received_pixels(asset_id: str) -> None:
    rows = tuple(
        (ROOT / f"src/drift_with_me/assets/{asset_id}.hex")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )

    if asset_id == "water_surface_glint_horizontal":
        expected_height = 243
        expected_width = 357
    elif asset_id.startswith(("water_", "solar_", "tree_")):
        expected_height = 128
        expected_width = 96
    elif asset_id.startswith("giant_tree_02x_"):
        expected_height = 256
        expected_width = 256
    elif asset_id.startswith("giant_tree_"):
        expected_height = 128
        expected_width = 128
    else:
        expected_height = 64
        expected_width = 64
    assert len(rows) == expected_height
    assert {len(row) for row in rows} == {expected_width}
    assert pixel_hash(rows) == ENVIRONMENT_WAVE1_SOURCE_HASHES[asset_id]
    if asset_id in ENVIRONMENT_VISIBLE_COLORS_WITH_COLKEY_8:
        assert set("".join(rows)) - {"8"} == ENVIRONMENT_VISIBLE_COLORS_WITH_COLKEY_8[asset_id]


@pytest.mark.parametrize("pose_id", tuple(TALL_GRASS_REACTIVE_POSE_HASHES))
def test_tall_grass_reactive_pose_hex_preserves_received_pixels(pose_id: str) -> None:
    rows = tuple(
        (ROOT / f"src/drift_with_me/assets/grass_tall_a_reactive_{pose_id}.hex")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )

    assert len(rows) == 64
    assert {len(row) for row in rows} == {64}
    assert pixel_hash(rows) == TALL_GRASS_REACTIVE_POSE_HASHES[pose_id]
    assert set("".join(rows)) <= set("0123456789ABCDEF")


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


def test_static_manifest_rejects_multiple_hex_frames(tmp_path: Path) -> None:
    import pyxel

    asset = valid_asset()
    asset["frames"].append(
        {"id": "bend_right_1", "path": "bend_right_1.hex", "source_hash": pixel_hash(ROWS)}
    )
    (tmp_path / "jack.hex").write_text("\n".join(ROWS) + "\n", encoding="utf-8")
    (tmp_path / "bend_right_1.hex").write_text("\n".join(ROWS) + "\n", encoding="utf-8")
    manifest_path = tmp_path / "sprites.json"
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "assets": [asset]}, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(HexAssetError, match="static assets must have exactly one frame"):
        load_sprite_manifest_path(pyxel, manifest_path)


def test_reactive_pose_set_manifest_loads_multiple_hex_frames(tmp_path: Path) -> None:
    import pyxel

    left_rows = ("EEE", "CDE", "678", "345", "012")
    asset = valid_asset("grass_pose_test", "idle.hex")
    asset["animation"] = "reactive_pose_set"
    asset["frames"] = [
        {"id": "idle_00", "path": "idle.hex", "source_hash": pixel_hash(ROWS)},
        {
            "id": "bend_left_1",
            "path": "bend_left_1.hex",
            "source_hash": pixel_hash(left_rows),
        },
    ]
    asset["source_hash"] = source_hash_for_pixels(
        bytes([int(char, 16) for row in ROWS for char in row])
        + bytes([int(char, 16) for row in left_rows for char in row])
    )
    (tmp_path / "idle.hex").write_text("\n".join(ROWS) + "\n", encoding="utf-8")
    (tmp_path / "bend_left_1.hex").write_text("\n".join(left_rows) + "\n", encoding="utf-8")
    manifest_path = tmp_path / "sprites.json"
    manifest_path.write_text(
        json.dumps({"schema_version": 1, "assets": [asset]}, indent=2) + "\n",
        encoding="utf-8",
    )

    loaded = load_sprite_manifest_path(pyxel, manifest_path).get("grass_pose_test")

    assert loaded is not None
    assert loaded.definition.animation == "reactive_pose_set"
    assert set(loaded.frames) == {"idle_00", "bend_left_1"}
    assert loaded.frame("bend_left_1").source_hash == pixel_hash(left_rows)


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
from drift_with_me.math3d import (
    AffineProjectionProfile,
    CameraState,
    Vec3,
    affine_camera_from_perspective,
)
from drift_with_me.model import GameModel, InteractionState
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
urchin = library.get("normal_urchin_idle_64")
assert urchin is not None
urchin_frame = urchin.frame()
assert (urchin_frame.u, urchin_frame.v, urchin_frame.width, urchin_frame.height) == urchin_rect
assert urchin_frame.source_hash == {NORMAL_URCHIN_SOURCE_HASH!r}
assert urchin.definition.colkey == 3
assert urchin.definition.anchor_px == (32.0, 60.0)
assert urchin.definition.world_size == (20.0, 20.0)
assert runtime.raw["assets"]["normal_urchin_idle_asset"] == "normal_urchin_idle_64"
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
environment_hashes = {ENVIRONMENT_WAVE1_RUNTIME_HASHES!r}
tall_grass_pose_hashes = {TALL_GRASS_REACTIVE_POSE_HASHES!r}
tall_grass_source_hash = {TALL_GRASS_REACTIVE_SOURCE_HASH!r}
low_grass_expected_colors = {ENVIRONMENT_VISIBLE_COLORS_WITH_COLKEY_8["grass_low_a"]!r}
environment_asset_ids = {{
    "water_station_active": "water_station_active_96",
    "water_station_stopped": "water_station_stopped_96",
    "solar_station_idle": "solar_station_idle_96",
    "solar_station_active": "solar_station_active_96",
    "tree_leafy_a": "tree_leafy_a_96",
    "tree_thin_b": "tree_thin_b_96",
    "reactive_grass_tall": "reactive_grass_tall_64",
    "reactive_grass_low": "reactive_grass_low_64",
    "ground_pebbles": "ground_pebbles_64",
    "ground_fallen_leaves": "ground_fallen_leaves_64",
    "ground_crack_grass": "ground_crack_grass_64",
    "ground_rubble": "ground_rubble_64",
    "concrete_clean_a": "concrete_clean_a_64",
    "concrete_cracked_a": "concrete_cracked_a_64",
    "concrete_spalled_a": "concrete_spalled_a_64",
    "concrete_joint_grass_a": "concrete_joint_grass_a_64",
    "decal_stain_a": "decal_stain_a_64",
    "decal_crack_grass_a": "decal_crack_grass_a_64",
    "decal_rubble_a": "decal_rubble_a_64",
    "decal_broken_edge_a": "decal_broken_edge_a_64",
    "grass_tall_a": "grass_tall_a_64",
    "grass_low_a": "grass_low_a_64",
    "pebbles_a": "pebbles_a_64",
    "fallen_leaves_a": "fallen_leaves_a_64",
    "crack_sprout_a": "crack_sprout_a_64",
    "rubble_small_a": "rubble_small_a_64",
    "grass_patch_low_a": "grass_patch_low_a_64",
    "grass_patch_low_b": "grass_patch_low_b_64",
    "grass_patch_tall_a": "grass_patch_tall_a_64",
    "grass_patch_tall_b": "grass_patch_tall_b_64",
    "grass_edge_a": "grass_edge_a_64",
    "grass_scatter_a": "grass_scatter_a_64",
    "giant_tree_root_massive_a": "giant_tree_root_massive_a_128",
    "giant_tree_root_spire_b": "giant_tree_root_spire_b_128",
    "giant_tree_root_hollow_c": "giant_tree_root_hollow_c_128",
    "giant_tree_root_arch_d": "giant_tree_root_arch_d_128",
    "giant_tree_root_tall_b": "giant_tree_root_tall_b_128",
    "giant_tree_stump_ruin_a": "giant_tree_stump_ruin_a_128",
    "giant_tree_root_arch_a": "giant_tree_root_arch_a_128",
    "giant_tree_02x_a": "giant_tree_02x_a_256",
    "giant_tree_02x_b": "giant_tree_02x_b_256",
    "giant_tree_02x_c": "giant_tree_02x_c_256",
    "giant_tree_02x_d": "giant_tree_02x_d_256",
    "water_surface_glint_horizontal": "water_surface_glint_horizontal_357",
}}
environment_world_sizes = {{
    "water_station_active": (36.0, 48.0),
    "water_station_stopped": (36.0, 48.0),
    "solar_station_idle": (36.0, 48.0),
    "solar_station_active": (36.0, 48.0),
    "tree_leafy_a": (48.0, 64.0),
    "tree_thin_b": (48.0, 64.0),
    "reactive_grass_tall": (24.0, 24.0),
    "reactive_grass_low": (28.0, 28.0),
    "ground_pebbles": (32.0, 32.0),
    "ground_fallen_leaves": (32.0, 32.0),
    "ground_crack_grass": (32.0, 32.0),
    "ground_rubble": (40.0, 32.0),
    "concrete_clean_a": (32.0, 32.0),
    "concrete_cracked_a": (32.0, 32.0),
    "concrete_spalled_a": (32.0, 32.0),
    "concrete_joint_grass_a": (32.0, 32.0),
    "decal_stain_a": (32.0, 32.0),
    "decal_crack_grass_a": (32.0, 32.0),
    "decal_rubble_a": (32.0, 32.0),
    "decal_broken_edge_a": (32.0, 32.0),
    "grass_tall_a": (28.0, 28.0),
    "grass_low_a": (28.0, 18.0),
    "pebbles_a": (22.0, 14.0),
    "fallen_leaves_a": (26.0, 16.0),
    "crack_sprout_a": (28.0, 18.0),
    "rubble_small_a": (32.0, 20.0),
    "grass_patch_low_a": (42.0, 20.0),
    "grass_patch_low_b": (42.0, 20.0),
    "grass_patch_tall_a": (46.0, 46.0),
    "grass_patch_tall_b": (52.0, 52.0),
    "grass_edge_a": (48.0, 28.0),
    "grass_scatter_a": (44.0, 24.0),
    "giant_tree_root_massive_a": (120.0, 120.0),
    "giant_tree_root_spire_b": (118.0, 118.0),
    "giant_tree_root_hollow_c": (118.0, 118.0),
    "giant_tree_root_arch_d": (120.0, 120.0),
    "giant_tree_root_tall_b": (128.0, 128.0),
    "giant_tree_stump_ruin_a": (102.0, 102.0),
    "giant_tree_root_arch_a": (110.0, 110.0),
    "giant_tree_02x_a": (192.0, 192.0),
    "giant_tree_02x_b": (192.0, 192.0),
    "giant_tree_02x_c": (192.0, 192.0),
    "giant_tree_02x_d": (192.0, 192.0),
    "water_surface_glint_horizontal": (256.0, 174.3),
}}
environment_colkeys = {{
    "water_station_active": 8,
    "water_station_stopped": 8,
    "solar_station_idle": 8,
    "solar_station_active": 8,
    "tree_leafy_a": 8,
    "tree_thin_b": 8,
    "concrete_clean_a": 8,
    "concrete_cracked_a": 8,
    "concrete_spalled_a": 8,
    "concrete_joint_grass_a": 8,
    "decal_stain_a": 8,
    "decal_crack_grass_a": 8,
    "decal_rubble_a": 8,
    "decal_broken_edge_a": 8,
    "grass_tall_a": 8,
    "grass_low_a": 8,
    "pebbles_a": 8,
    "fallen_leaves_a": 8,
    "crack_sprout_a": 8,
    "rubble_small_a": 8,
    "grass_patch_low_a": 8,
    "grass_patch_low_b": 8,
    "grass_patch_tall_a": 8,
    "grass_patch_tall_b": 8,
    "grass_edge_a": 8,
    "grass_scatter_a": 8,
    "giant_tree_root_massive_a": 8,
    "giant_tree_root_spire_b": 8,
    "giant_tree_root_hollow_c": 8,
    "giant_tree_root_arch_d": 8,
    "giant_tree_root_tall_b": 8,
    "giant_tree_stump_ruin_a": 8,
    "giant_tree_root_arch_a": 8,
    "giant_tree_02x_a": 8,
    "giant_tree_02x_b": 8,
    "giant_tree_02x_c": 8,
    "giant_tree_02x_d": 8,
    "water_surface_glint_horizontal": 8,
}}
environment_anchors = {{
    "water_station_active": (48.0, 127.0),
    "water_station_stopped": (48.0, 127.0),
    "solar_station_idle": (48.0, 127.0),
    "solar_station_active": (48.0, 127.0),
    "tree_leafy_a": (48.0, 127.0),
    "tree_thin_b": (48.0, 127.0),
    "concrete_clean_a": (32.0, 32.0),
    "concrete_cracked_a": (32.0, 32.0),
    "concrete_spalled_a": (32.0, 32.0),
    "concrete_joint_grass_a": (32.0, 32.0),
    "decal_stain_a": (32.0, 32.0),
    "decal_crack_grass_a": (32.0, 32.0),
    "decal_rubble_a": (32.0, 32.0),
    "decal_broken_edge_a": (32.0, 32.0),
    "grass_tall_a": (32.0, 63.0),
    "grass_low_a": (32.0, 63.0),
    "pebbles_a": (32.0, 63.0),
    "fallen_leaves_a": (32.0, 63.0),
    "crack_sprout_a": (32.0, 63.0),
    "rubble_small_a": (32.0, 63.0),
    "grass_patch_low_a": (32.0, 63.0),
    "grass_patch_low_b": (32.0, 63.0),
    "grass_patch_tall_a": (32.0, 63.0),
    "grass_patch_tall_b": (32.0, 63.0),
    "grass_edge_a": (32.0, 63.0),
    "grass_scatter_a": (32.0, 63.0),
    "giant_tree_root_massive_a": (64.0, 127.0),
    "giant_tree_root_spire_b": (64.0, 127.0),
    "giant_tree_root_hollow_c": (64.0, 127.0),
    "giant_tree_root_arch_d": (64.0, 127.0),
    "giant_tree_root_tall_b": (64.0, 127.0),
    "giant_tree_stump_ruin_a": (64.0, 127.0),
    "giant_tree_root_arch_a": (64.0, 127.0),
    "giant_tree_02x_a": (128.0, 255.0),
    "giant_tree_02x_b": (128.0, 255.0),
    "giant_tree_02x_c": (128.0, 255.0),
    "giant_tree_02x_d": (128.0, 255.0),
    "water_surface_glint_horizontal": (178.5, 121.5),
}}
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
for source_id, expected_hash in environment_hashes.items():
    env_asset = library.get(environment_asset_ids[source_id])
    assert env_asset is not None, source_id
    env_frame = env_asset.frame()
    assert env_frame.source is not None
    assert env_frame.source_hash == expected_hash
    if source_id == "grass_tall_a":
        assert env_asset.definition.animation == "reactive_pose_set"
        assert env_asset.definition.source_hash == tall_grass_source_hash
        assert tuple(env_asset.frames) == tuple(tall_grass_pose_hashes)
        for pose_id, expected_pose_hash in tall_grass_pose_hashes.items():
            assert env_asset.frame(pose_id).source_hash == expected_pose_hash
    assert env_asset.definition.world_size == environment_world_sizes[source_id]
    if source_id in environment_colkeys:
        assert env_asset.definition.colkey == environment_colkeys[source_id]
        assert env_asset.definition.anchor_px == environment_anchors[source_id]
    if source_id.startswith(("ground_", "concrete_", "decal_")) or source_id in {{
        "grass_low_a",
        "pebbles_a",
        "fallen_leaves_a",
        "crack_sprout_a",
        "rubble_small_a",
        "grass_patch_low_a",
        "grass_patch_low_b",
        "grass_edge_a",
        "grass_scatter_a",
        "water_surface_glint_horizontal",
    }}:
        assert env_asset.definition.projection_mode == "ground_decal_source_v1"
    else:
        assert env_asset.definition.projection_mode == "upright_height_billboard_v1"
assert runtime.raw["assets"]["water_station_working_asset"] == "water_station_active_96"
assert runtime.raw["assets"]["reactive_grass_tall_asset"] == "grass_tall_a_64"
assert runtime.raw["assets"]["reactive_grass_low_asset"] == "grass_low_a_upright_64"
assert runtime.raw["assets"]["ground_rubble_asset"] == "rubble_small_a_64"
assert runtime.raw["assets"]["concrete_clean_a_asset"] == "concrete_clean_a_64"
assert runtime.raw["assets"]["decal_crack_grass_a_asset"] == "decal_crack_grass_a_64"
assert runtime.raw["assets"]["grass_patch_low_a_asset"] == "grass_patch_low_a_64"
assert runtime.raw["assets"]["grass_patch_tall_a_asset"] == "grass_patch_tall_a_64"
assert runtime.raw["assets"]["giant_tree_root_arch_a_asset"] == "giant_tree_root_arch_a_128"
assert runtime.raw["assets"]["giant_tree_02x_c_asset"] == "giant_tree_02x_c_256"
assert runtime.raw["assets"]["water_surface_glint_horizontal_asset"] == (
    "water_surface_glint_horizontal_357"
)
assert runtime.raw["assets"]["giant_tree_root_spire_b_asset"] == "giant_tree_root_spire_b_128"
assert runtime.raw["assets"]["giant_tree_root_hollow_c_asset"] == "giant_tree_root_hollow_c_128"
assert runtime.raw["assets"]["giant_tree_root_arch_d_asset"] == "giant_tree_root_arch_d_128"
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
tap = model.world.object_by_id("tap_start")
stopped_tap = model.world.object_by_id("tap_stopped")
solar = model.world.object_by_id("solar_start")
tree = model.world.object_by_id("tree_02")
grass = model.world.object_by_id("grass_01")
low_grass = model.world.object_by_id("grass_02")
grassland_tall = model.world.object_by_id("grassland_tall_a_01")
giant_root = model.world.object_by_id("rock_02")
stump_root = model.world.object_by_id("rock_01")
west_root = model.world.object_by_id("wall_02")
east_tree = model.world.object_by_id("wall_03")
assert tap is not None and stopped_tap is not None and solar is not None
assert tree is not None and grass is not None and low_grass is not None
assert grassland_tall is not None and giant_root is not None
assert stump_root is not None
assert west_root is not None and east_tree is not None
assert renderer.object_sprite_asset(model, tap).definition.asset_id == "water_station_active_96"
assert (
    renderer.object_sprite_asset(model, stopped_tap).definition.asset_id
    == "water_station_stopped_96"
)
assert renderer.object_sprite_asset(model, solar).definition.asset_id == "solar_station_idle_96"
model.interaction = InteractionState(
    kind="energy_refill",
    object_id="solar_start",
    title="ENERGY CHARGE",
    lines=(),
    duration_sec=1.0,
)
assert renderer.object_sprite_asset(model, solar).definition.asset_id == "solar_station_active_96"
model.interaction = None
assert renderer.object_sprite_asset(model, tree).definition.asset_id == "tree_thin_b_96"
assert renderer.object_sprite_asset(model, grass).definition.asset_id == "grass_tall_a_64"
low_grass_asset = renderer.object_sprite_asset(model, low_grass)
assert (
    low_grass_asset.definition.asset_id
    == "grass_low_a_upright_64"
)
assert (
    low_grass_asset.definition.projection_mode
    == "upright_height_billboard_v1"
)
low_grass_frame = low_grass_asset.frame()
assert low_grass_frame.source_hash == environment_hashes["grass_low_a"]
assert low_grass_frame.source is not None
assert set("".join(low_grass_frame.source.rows)) - {{"8"}} == low_grass_expected_colors
assert renderer.object_sprite_asset(model, grassland_tall).definition.asset_id == (
    "grass_patch_tall_a_64"
)
assert renderer.object_sprite_asset(model, grassland_tall).definition.projection_mode == (
    "upright_height_billboard_v1"
)
assert renderer.object_sprite_asset(model, giant_root).definition.asset_id == (
    "giant_tree_root_massive_a_128"
)
assert renderer.object_sprite_asset(model, stump_root).definition.asset_id == (
    "giant_tree_root_hollow_c_128"
)
assert renderer.object_sprite_asset(model, west_root).definition.asset_id == (
    "giant_tree_root_arch_d_128"
)
assert renderer.object_sprite_asset(model, east_tree).definition.asset_id == (
    "giant_tree_root_spire_b_128"
)
assert len(model.world.ground_details) == 0
assert len(model.world.ground_surfaces) == 1
assert model.world.ground_surfaces[0].layers == ("water_surface_glint_horizontal",)
assert renderer.ground_surface_sprite_asset(model, "concrete_clean_a").definition.asset_id == (
    "concrete_clean_a_64"
)
assert renderer.ground_surface_sprite_asset(
    model, "water_surface_glint_horizontal"
).definition.asset_id == "water_surface_glint_horizontal_357"
assert len(model.world.baked_ground_patches) == 14
legacy_patch = model.world.baked_ground_patches[0]
assert legacy_patch.id == "spawn_affine_ground_patch"
assert legacy_patch.group == "spawn_192_legacy_compare"
assert not legacy_patch.enabled
affine_patches = [
    patch for patch in model.world.baked_ground_patches if patch.group == "affine_static_128"
]
assert len(affine_patches) == 4
assert all(not patch.enabled and patch.projection_kind == "affine" for patch in affine_patches)
assert all(patch.width == 128.0 for patch in affine_patches)
patch_probe_x = affine_patches[0].x
patch_probe_z = affine_patches[0].z
small_patches = [
    patch for patch in model.world.baked_ground_patches if patch.group == "spawn_64_bucket16"
]
assert len(small_patches) == 9
assert not any(patch.enabled for patch in [legacy_patch, *small_patches])
active_patches = renderer.draw_baked_ground_patches(model, camera)
assert active_patches == ()
assert not renderer.point_in_active_baked_ground_patch(patch_probe_x, patch_probe_z)
visible_pixels = 0
for y in range(runtime.screen_height):
    for x in range(runtime.screen_width):
        visible_pixels += pyxel.pget(x, y) != 3
assert visible_pixels > 0
renderer.draw_scene(model, camera, presentation_time=0.0, debug=False)
assert renderer.last_stats.visible_baked_ground_patches == 0
assert renderer.last_stats.visible_ground_details == 0
assert renderer.last_stats.baked_ground_cache_size == 0
profile = AffineProjectionProfile.from_config(runtime.raw)
affine = affine_camera_from_perspective(
    camera,
    profile,
    base_distance=float(runtime.raw["camera"]["base_distance"]),
)
renderer.max_baked_ground_builds_per_frame = 8
pyxel.cls(3)
active_patches = renderer.draw_baked_ground_patches(model, affine)
assert active_patches == ()
assert not renderer.point_in_active_baked_ground_patch(patch_probe_x, patch_probe_z)
assert renderer.last_stats.baked_ground_cache_size == 0
renderer.draw_scene(model, affine, presentation_time=0.0, debug=False)
assert renderer.last_stats.visible_baked_ground_patches == 0
assert renderer.last_stats.visible_ground_details == 0
assert renderer.last_stats.baked_ground_cache_size == 0
patch = affine_patches[0]
bucket = renderer.baked_ground_camera_bucket(patch, affine)
first_key = renderer.baked_ground_cache_key(patch, affine, *bucket)
shifted_camera = affine_camera_from_perspective(
    CameraState.from_config(
        runtime.raw,
        Vec3(model.player.x + 32.0, 0.0, model.player.z + 32.0),
        runtime.screen_width,
        runtime.screen_height,
    ),
    profile,
    base_distance=float(runtime.raw["camera"]["base_distance"]),
)
shifted_bucket = renderer.baked_ground_camera_bucket(patch, shifted_camera)
shifted_key = renderer.baked_ground_cache_key(patch, shifted_camera, *shifted_bucket)
assert bucket == (patch.x, patch.z)
assert shifted_bucket == (patch.x, patch.z)
assert first_key == shifted_key
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


def test_renderer_spins_and_jumps_jack_during_water_refill(tmp_path: Path) -> None:
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
    model.interaction = InteractionState(
        kind="water_refill",
        object_id="tap_start",
        title="WATER REFILL",
        lines=(),
        duration_sec=1.0,
        elapsed_sec=0.5,
    )
    camera = CameraState.from_config(
        raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    renderer = Renderer(RecordingPyxel(), library)

    asset = renderer.player_sprite_asset(model, camera)
    assert asset is not None
    assert asset.definition.asset_id == "jack_left_32"
    assert renderer.player_visual_y_offset(model, 0.0) == pytest.approx(
        renderer.player_visual_hover(model, 0.0) + 12.0
    )


def test_renderer_spins_and_jumps_buddy_during_energy_refill(tmp_path: Path) -> None:
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
    model.interaction = InteractionState(
        kind="energy_refill",
        object_id="solar_start",
        title="ENERGY CHARGE",
        lines=(),
        duration_sec=1.0,
        elapsed_sec=0.25,
    )
    camera = CameraState.from_config(
        raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    renderer = Renderer(RecordingPyxel(), library)

    asset = renderer.buddy_sprite_asset(model, camera)
    assert asset is not None
    assert asset.definition.asset_id == "fuse_front_neutral_48"
    assert renderer.interaction_actor_jump(model, "energy_refill") == pytest.approx(
        12.0 * 2**0.5 / 2.0
    )
