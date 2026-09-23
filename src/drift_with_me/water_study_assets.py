from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

from drift_with_me.hex_assets import parse_hex_rows

WATER_STUDY_LAYER_IDS: tuple[str, ...] = (
    "water_deep_plane_a",
    "water_mid_plane_a",
    "water_surface_plane_a",
    "water_surface_caustics_plane_a",
    "water_upper_lightnet_plane_a",
    "water_highlights_plane_a",
)


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
        chunks: list[WaterStudyChunk] = []
        for chunk in layer["chunks"]:
            chunk_id = str(chunk["id"])
            origin_x, origin_y = (int(value) for value in chunk["logical_origin"])
            width, height = (int(value) for value in chunk["size"])
            if width != chunk_width or height != chunk_height:
                raise ValueError(
                    f"{chunk_id}: expected {chunk_width}x{chunk_height}, got {width}x{height}"
                )
            rows = parse_hex_rows(
                root.joinpath("chunks_256/hex_rows", f"{chunk_id}.hex.txt").read_text(
                    encoding="utf-8"
                ),
                width,
                height,
                chunk_id,
            )
            image = pyxel_module.Image(width, height)
            for y, row in enumerate(rows):
                for x, color in enumerate(row):
                    image.pset(x, y, int(color, 16))
            chunks.append(WaterStudyChunk(image, origin_x, origin_y, width, height))
        chunks.sort(key=lambda loaded: (loaded.origin_y, loaded.origin_x))
        planes[layer_id] = WaterStudyPlane(
            layer_id=layer_id,
            logical_width=logical_width,
            logical_height=logical_height,
            chunk_width=chunk_width,
            chunk_height=chunk_height,
            colkey=layer.get("colkey"),
            chunks=tuple(chunks),
        )

    missing = [layer_id for layer_id in WATER_STUDY_LAYER_IDS if layer_id not in planes]
    if missing:
        raise ValueError(f"missing water study layers: {', '.join(missing)}")
    return planes
