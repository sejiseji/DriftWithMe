from __future__ import annotations

import hashlib
import json
from importlib import resources

from drift_with_me.hex_assets import parse_hex_rows
from drift_with_me.water_study_assets import (
    WATER_STUDY_LAYER_IDS,
    WATER_STUDY_PHASE_LAYER_IDS,
    WATER_STUDY_PHASE_STEP_FRAMES,
    apply_dhex_patch_to_rows,
    load_water_study_phase_planes,
    load_water_study_planes,
    parse_dhex_patch,
)


class FakeImage:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.pset_count = 0
        self.pixels = [[0 for _ in range(width)] for _ in range(height)]

    def pset(self, x: int, y: int, color: int) -> None:
        self.pset_count += 1
        self.pixels[y][x] = color

    def hex_rows(self) -> tuple[str, ...]:
        return tuple("".join(f"{color:X}" for color in row) for row in self.pixels)


class FakePyxel:
    Image = FakeImage


def test_wtr001_bundled_water_layer_assets_match_contract() -> None:
    planes = load_water_study_planes(FakePyxel)

    assert tuple(planes) == WATER_STUDY_LAYER_IDS
    for layer_id, plane in planes.items():
        assert plane.layer_id == layer_id
        assert (plane.logical_width, plane.logical_height) == (1024, 512)
        assert (plane.chunk_width, plane.chunk_height) == (256, 256)
        assert len(plane.chunks) == 8
        assert [chunk.origin_x for chunk in plane.chunks[:4]] == [0, 256, 512, 768]
        assert [chunk.origin_y for chunk in plane.chunks[:4]] == [0, 0, 0, 0]
        assert [chunk.origin_x for chunk in plane.chunks[4:]] == [0, 256, 512, 768]
        assert [chunk.origin_y for chunk in plane.chunks[4:]] == [256, 256, 256, 256]
        assert all(chunk.image.pset_count == 256 * 256 for chunk in plane.chunks)

    assert planes["water_deep_plane_c"].colkey is None
    for layer_id in WATER_STUDY_LAYER_IDS[1:]:
        assert planes[layer_id].colkey == 8


def test_wtr001_water_layers_do_not_use_forbidden_green_indices() -> None:
    root = resources.files("drift_with_me").joinpath("assets/water_study")
    manifest = json.loads(
        root.joinpath("water_study_source_manifest.json").read_text(encoding="utf-8")
    )

    assert tuple(layer["id"] for layer in manifest["layers"]) == WATER_STUDY_LAYER_IDS
    for layer in manifest["layers"]:
        assert "3" not in layer["allowed_palette_indices"]
        assert "B" not in layer["allowed_palette_indices"]
        for chunk in layer["chunks"]:
            chunk_id = str(chunk["id"])
            text = root.joinpath("chunks_256/hex_rows", f"{chunk_id}.hex.txt").read_text(
                encoding="utf-8"
            )
            assert "3" not in text
            assert "B" not in text


def test_wtr001_phase_delta_wave1_assets_match_contract() -> None:
    phase_sets = load_water_study_phase_planes(FakePyxel)

    assert tuple(phase_sets) == WATER_STUDY_PHASE_LAYER_IDS
    assert WATER_STUDY_PHASE_STEP_FRAMES == {
        "water_surface_caustics_plane_c": 8,
        "water_upper_lightnet_plane_c": 10,
    }
    for layer_id, phases in phase_sets.items():
        assert len(phases) == 8
        for index, phase in enumerate(phases):
            assert phase.layer_id == f"{layer_id}_p{index:02d}"
            assert (phase.logical_width, phase.logical_height) == (1024, 512)
            assert (phase.chunk_width, phase.chunk_height) == (256, 256)
            assert phase.colkey == 8
            assert len(phase.chunks) == 8
            assert [chunk.origin_x for chunk in phase.chunks[:4]] == [0, 256, 512, 768]
            assert [chunk.origin_y for chunk in phase.chunks[:4]] == [0, 0, 0, 0]
            assert [chunk.origin_x for chunk in phase.chunks[4:]] == [0, 256, 512, 768]
            assert [chunk.origin_y for chunk in phase.chunks[4:]] == [256, 256, 256, 256]
            assert all(chunk.image.pset_count == 256 * 256 for chunk in phase.chunks)


def test_wtr001_phase_delta_wave1_keeps_p00_equal_to_base_chunks() -> None:
    root = resources.files("drift_with_me").joinpath("assets/water_study")
    phase_sets = load_water_study_phase_planes(FakePyxel)

    for layer_id in WATER_STUDY_PHASE_LAYER_IDS:
        phase = phase_sets[layer_id][0]
        chunks = {
            f"c{chunk.origin_x // 256}{chunk.origin_y // 256}": chunk for chunk in phase.chunks
        }
        for chunk_suffix in ("c00", "c10", "c20", "c30", "c01", "c11", "c21", "c31"):
            base = root.joinpath("chunks_256/hex_rows", f"{layer_id}_{chunk_suffix}.hex.txt")
            base_rows = parse_hex_rows(
                base.read_text(encoding="utf-8"),
                256,
                256,
                f"{layer_id}_{chunk_suffix}",
            )
            assert chunks[chunk_suffix].image.hex_rows() == base_rows


def test_wtr001_runtime_lite_phase_delta_manifest_and_patches_match_contract() -> None:
    root = resources.files("drift_with_me").joinpath("assets/water_study/runtime_lite_phase_delta")
    manifest = json.loads(root.joinpath("runtime_lite_manifest.json").read_text(encoding="utf-8"))

    assert tuple(layer["id"] for layer in manifest["layers"]) == WATER_STUDY_PHASE_LAYER_IDS
    assert manifest["encoding"].startswith("DHEX1")
    assert manifest["phase_count"] == 8
    assert manifest["chunk_size"] == [256, 256]
    assert manifest["logical_plane_size"] == [1024, 512]
    for layer in manifest["layers"]:
        assert len(layer["transitions"]) == 8
        for transition in layer["transitions"]:
            assert len(transition["chunks"]) == 8
            assert transition["changed_pixels"] == sum(
                int(chunk["changed_pixels"]) for chunk in transition["chunks"]
            )
            assert transition["run_count"] == sum(
                int(chunk["run_count"]) for chunk in transition["chunks"]
            )
            for chunk in transition["chunks"]:
                path = root.joinpath(str(chunk["file"]))
                text = path.read_text(encoding="ascii")
                assert hashlib.sha256(text.encode("ascii")).hexdigest() == chunk["sha256"]
                runs = parse_dhex_patch(text, str(chunk["file"]))
                assert len(runs) == int(chunk["run_count"])
                assert sum(len(data) for _, data in runs) == int(chunk["changed_pixels"])
                for _, data in runs:
                    assert "3" not in data
                    assert "B" not in data


def test_wtr001_runtime_lite_phase_delta_loopback_reconstructs_p00() -> None:
    root = resources.files("drift_with_me").joinpath("assets/water_study")
    runtime_root = root.joinpath("runtime_lite_phase_delta")
    manifest = json.loads(
        runtime_root.joinpath("runtime_lite_manifest.json").read_text(encoding="utf-8")
    )

    for layer in manifest["layers"]:
        layer_id = str(layer["id"])
        base_rows = {
            chunk: parse_hex_rows(
                root.joinpath("chunks_256/hex_rows", f"{layer_id}_{chunk}.hex.txt").read_text(
                    encoding="utf-8"
                ),
                256,
                256,
                f"{layer_id}_{chunk}",
            )
            for chunk in ("c00", "c10", "c20", "c30", "c01", "c11", "c21", "c31")
        }
        current_rows = dict(base_rows)
        for transition in layer["transitions"]:
            for chunk in transition["chunks"]:
                chunk_id = str(chunk["chunk"])
                text = runtime_root.joinpath(str(chunk["file"])).read_text(encoding="ascii")
                current_rows[chunk_id] = apply_dhex_patch_to_rows(
                    current_rows[chunk_id],
                    parse_dhex_patch(text, str(chunk["file"])),
                    str(chunk["file"]),
                )
            if transition["to"] == "p00":
                assert current_rows == base_rows
