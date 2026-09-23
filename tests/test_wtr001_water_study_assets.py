from __future__ import annotations

import json
from importlib import resources

from drift_with_me.water_study_assets import (
    WATER_STUDY_LAYER_IDS,
    WATER_STUDY_PHASE_LAYER_IDS,
    WATER_STUDY_PHASE_STEP_FRAMES,
    load_water_study_phase_planes,
    load_water_study_planes,
)


class FakeImage:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.pset_count = 0

    def pset(self, _x: int, _y: int, _color: int) -> None:
        self.pset_count += 1


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
    phase_root = root.joinpath("phase_delta_wave1/chunks_256/hex_rows")

    for layer_id in WATER_STUDY_PHASE_LAYER_IDS:
        for chunk_suffix in ("c00", "c10", "c20", "c30", "c01", "c11", "c21", "c31"):
            base = root.joinpath("chunks_256/hex_rows", f"{layer_id}_{chunk_suffix}.hex.txt")
            phase = phase_root.joinpath(f"{layer_id}_p00_{chunk_suffix}.hex.txt")
            assert phase.read_text(encoding="utf-8") == base.read_text(encoding="utf-8")


def test_wtr001_phase_delta_wave1_does_not_use_forbidden_green_indices() -> None:
    root = resources.files("drift_with_me").joinpath("assets/water_study/phase_delta_wave1")
    manifest = json.loads(
        root.joinpath("phase_delta_wave1_manifest.json").read_text(encoding="utf-8")
    )

    assert tuple(layer["id"] for layer in manifest["layers"]) == WATER_STUDY_PHASE_LAYER_IDS
    assert manifest["palette_policy"]["forbidden_water_indices"] == ["3", "B"]
    for layer in manifest["layers"]:
        assert int(layer["phase_count"]) == 8
        for phase in layer["phases"]:
            for chunk in phase["chunks"]:
                chunk_id = str(chunk["id"])
                text = root.joinpath("chunks_256/hex_rows", f"{chunk_id}.hex.txt").read_text(
                    encoding="utf-8"
                )
                assert "3" not in text
                assert "B" not in text
