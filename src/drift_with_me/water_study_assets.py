from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

from drift_with_me.hex_assets import HEX_DIGITS, HexAssetError, parse_hex_rows

WATER_STUDY_LAYER_IDS: tuple[str, ...] = (
    "water_deep_plane_c",
    "water_mid_plane_c",
    "water_surface_plane_c",
    "water_surface_caustics_plane_c",
    "water_upper_lightnet_plane_c",
    "water_highlights_plane_c",
)

WATER_STUDY_PHASE_LAYER_IDS: tuple[str, ...] = (
    "water_mid_plane_c",
    "water_surface_plane_c",
    "water_surface_caustics_plane_c",
    "water_upper_lightnet_plane_c",
)

WATER_STUDY_PHASE_STEP_FRAMES: dict[str, int] = {
    "water_mid_plane_c": 13,
    "water_surface_plane_c": 9,
    "water_surface_caustics_plane_c": 7,
    "water_upper_lightnet_plane_c": 5,
}

WATER_STUDY_PHASE_INITIAL_INDICES: dict[str, int] = {
    "water_mid_plane_c": 0,
    "water_surface_plane_c": 2,
    "water_surface_caustics_plane_c": 5,
    "water_upper_lightnet_plane_c": 1,
}


@dataclass(frozen=True)
class WaterStudyChunk:
    image: Any
    origin_x: int
    origin_y: int
    width: int
    height: int


@dataclass(frozen=True)
class WaterStudyPlane:
    layer_id: str
    logical_width: int
    logical_height: int
    chunk_width: int
    chunk_height: int
    colkey: int | None
    chunks: tuple[WaterStudyChunk, ...]


def _image_from_rows(pyxel_module: Any, rows: tuple[str, ...], width: int, height: int) -> Any:
    image = pyxel_module.Image(width, height)
    for y, row in enumerate(rows):
        for x, color in enumerate(row):
            image.pset(x, y, int(color, 16))
    return image


def _plane_from_chunk_rows(
    pyxel_module: Any,
    *,
    layer_id: str,
    logical_width: int,
    logical_height: int,
    chunk_width: int,
    chunk_height: int,
    colkey: int | None,
    chunk_rows: dict[str, tuple[str, ...]],
) -> WaterStudyPlane:
    chunks: list[WaterStudyChunk] = []
    for chunk_id, rows in chunk_rows.items():
        chunk_x = int(chunk_id[1])
        chunk_y = int(chunk_id[2])
        chunks.append(
            WaterStudyChunk(
                _image_from_rows(pyxel_module, rows, chunk_width, chunk_height),
                chunk_x * chunk_width,
                chunk_y * chunk_height,
                chunk_width,
                chunk_height,
            )
        )
    chunks.sort(key=lambda loaded: (loaded.origin_y, loaded.origin_x))
    return WaterStudyPlane(
        layer_id=layer_id,
        logical_width=logical_width,
        logical_height=logical_height,
        chunk_width=chunk_width,
        chunk_height=chunk_height,
        colkey=colkey,
        chunks=tuple(chunks),
    )


def parse_dhex_patch(text: str, source_label: str) -> tuple[tuple[int, str], ...]:
    runs: list[tuple[int, str]] = []
    normalized = text.replace("\r\n", "\n")
    if "\r" in normalized:
        raise HexAssetError(f"{source_label}: lone CR line ending is not supported")
    for lineno, line in enumerate(normalized.splitlines(), start=1):
        if not line:
            continue
        if ":" not in line:
            raise HexAssetError(f"{source_label}:{lineno}: missing DHEX separator")
        offset_text, data = line.split(":", 1)
        if len(offset_text) != 4 or any(char not in HEX_DIGITS for char in offset_text):
            raise HexAssetError(f"{source_label}:{lineno}: invalid DHEX offset")
        start = int(offset_text, 16)
        if not data or any(char not in HEX_DIGITS for char in data):
            raise HexAssetError(f"{source_label}:{lineno}: invalid DHEX data")
        if start >= 256 * 256 or start + len(data) > 256 * 256:
            raise HexAssetError(f"{source_label}:{lineno}: DHEX run exceeds chunk")
        runs.append((start, data))
    return tuple(runs)


def apply_dhex_patch_to_rows(
    rows: tuple[str, ...],
    runs: tuple[tuple[int, str], ...],
    source_label: str,
    *,
    width: int = 256,
    height: int = 256,
) -> tuple[str, ...]:
    if len(rows) != height or any(len(row) != width for row in rows):
        raise HexAssetError(f"{source_label}: DHEX base chunk must be {width}x{height}")
    flat = list("".join(rows))
    for start, data in runs:
        flat[start : start + len(data)] = data
    return tuple("".join(flat[y * width : (y + 1) * width]) for y in range(height))


def load_water_study_planes(pyxel_module: Any) -> dict[str, WaterStudyPlane]:
    root = resources.files("drift_with_me").joinpath("assets/water_study")
    manifest = json.loads(
        root.joinpath("water_study_source_manifest.json").read_text(encoding="utf-8")
    )
    chunk_width, chunk_height = (int(value) for value in manifest["physical_chunk_size"])
    planes: dict[str, WaterStudyPlane] = {}

    for layer in manifest["layers"]:
        layer_id = str(layer["id"])
        if layer_id not in WATER_STUDY_LAYER_IDS:
            continue
        logical_width, logical_height = (int(value) for value in layer["logical_size"])
        chunk_rows: dict[str, tuple[str, ...]] = {}
        for chunk in layer["chunks"]:
            chunk_id = str(chunk["id"])
            width, height = (int(value) for value in chunk["size"])
            if width != chunk_width or height != chunk_height:
                raise ValueError(
                    f"{chunk_id}: expected {chunk_width}x{chunk_height}, got {width}x{height}"
                )
            chunk_rows[chunk_id.removeprefix(f"{layer_id}_")] = parse_hex_rows(
                root.joinpath("chunks_256/hex_rows", f"{chunk_id}.hex.txt").read_text(
                    encoding="utf-8"
                ),
                width,
                height,
                chunk_id,
            )
        planes[layer_id] = _plane_from_chunk_rows(
            pyxel_module,
            layer_id=layer_id,
            logical_width=logical_width,
            logical_height=logical_height,
            chunk_width=chunk_width,
            chunk_height=chunk_height,
            colkey=layer.get("colkey"),
            chunk_rows=chunk_rows,
        )

    missing = [layer_id for layer_id in WATER_STUDY_LAYER_IDS if layer_id not in planes]
    if missing:
        raise ValueError(f"missing water study layers: {', '.join(missing)}")
    return planes


def load_water_study_phase_planes(pyxel_module: Any) -> dict[str, tuple[WaterStudyPlane, ...]]:
    asset_root = resources.files("drift_with_me").joinpath("assets/water_study")
    root = asset_root.joinpath("runtime_lite_phase_delta")
    manifest = json.loads(root.joinpath("runtime_lite_manifest.json").read_text(encoding="utf-8"))
    chunk_width, chunk_height = (int(value) for value in manifest["chunk_size"])
    logical_width, logical_height = (int(value) for value in manifest["logical_plane_size"])
    colkey = 8
    if (chunk_width, chunk_height) != (256, 256):
        raise ValueError(
            f"runtime-lite DHEX expects 256x256 chunks, got {chunk_width}x{chunk_height}"
        )
    phase_sets: dict[str, tuple[WaterStudyPlane, ...]] = {}

    for layer in manifest["layers"]:
        layer_id = str(layer["id"])
        if layer_id not in WATER_STUDY_PHASE_LAYER_IDS:
            continue
        base_rows: dict[str, tuple[str, ...]] = {}
        for chunk_x in range(int(manifest["chunk_grid"][0])):
            for chunk_y in range(int(manifest["chunk_grid"][1])):
                chunk_suffix = f"c{chunk_x}{chunk_y}"
                base_rows[chunk_suffix] = parse_hex_rows(
                    asset_root.joinpath(
                        "chunks_256/hex_rows", f"{layer_id}_{chunk_suffix}.hex.txt"
                    ).read_text(encoding="utf-8"),
                    chunk_width,
                    chunk_height,
                    f"{layer_id}_{chunk_suffix}",
                )
        current_rows = dict(base_rows)
        phases: list[WaterStudyPlane] = []
        phases.append(
            _plane_from_chunk_rows(
                pyxel_module,
                layer_id=f"{layer_id}_p00",
                logical_width=logical_width,
                logical_height=logical_height,
                chunk_width=chunk_width,
                chunk_height=chunk_height,
                colkey=colkey,
                chunk_rows=current_rows,
            )
        )
        for transition in layer["transitions"]:
            from_phase = str(transition["from"])
            to_phase = str(transition["to"])
            if from_phase == "p07" and to_phase == "p00":
                loopback_rows = dict(current_rows)
                target_rows = loopback_rows
            else:
                target_rows = current_rows
            for chunk in transition["chunks"]:
                chunk_suffix = str(chunk["chunk"])
                patch_file = str(chunk["file"])
                patch_label = f"{layer_id}:{from_phase}->{to_phase}:{chunk_suffix}"
                runs = parse_dhex_patch(
                    root.joinpath(patch_file).read_text(encoding="ascii"), patch_label
                )
                target_rows[chunk_suffix] = apply_dhex_patch_to_rows(
                    target_rows[chunk_suffix],
                    runs,
                    patch_label,
                    width=chunk_width,
                    height=chunk_height,
                )
            if from_phase == "p07" and to_phase == "p00":
                if loopback_rows != base_rows:
                    raise ValueError(f"{layer_id}: DHEX loopback does not reconstruct p00")
                continue
            phases.append(
                _plane_from_chunk_rows(
                    pyxel_module,
                    layer_id=f"{layer_id}_{to_phase}",
                    logical_width=logical_width,
                    logical_height=logical_height,
                    chunk_width=chunk_width,
                    chunk_height=chunk_height,
                    colkey=colkey,
                    chunk_rows=current_rows,
                )
            )
        expected_phase_count = int(manifest["phase_count"])
        if len(phases) != expected_phase_count:
            raise ValueError(
                f"{layer_id}: expected {expected_phase_count} phases, got {len(phases)}"
            )
        phase_sets[layer_id] = tuple(phases)

    missing = [layer_id for layer_id in WATER_STUDY_PHASE_LAYER_IDS if layer_id not in phase_sets]
    if missing:
        raise ValueError(f"missing water study phase layers: {', '.join(missing)}")
    return phase_sets
