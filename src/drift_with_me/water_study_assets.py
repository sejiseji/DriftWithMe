from __future__ import annotations

import json
import time
from collections.abc import Callable
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

WATER_STUDY_STATIC_LAYER_IDS: tuple[str, ...] = (
    "water_deep_plane_c",
    "water_highlights_plane_c",
)

WTR002_SURFACE_CAUSTICS_RUNTIME_LAYER_ID = "water_surface_caustics_plane_c"
WTR002_SURFACE_CAUSTICS_ASSET_ID = "water_surface_caustics_plane_d"
WTR002_SURFACE_CAUSTICS_FRAME_COUNT = 20
WTR_LOOK03_HIGHLIGHTS_RUNTIME_LAYER_ID = "water_highlights_plane_c"
WTR_LOOK03_HIGHLIGHTS_ASSET_ID = "water_highlights_plane_d"
WTR_LOOK03_HIGHLIGHTS_FRAME_COUNT = 24
APPROVED_WATER_PRODUCTION_PROFILE = "approved_look03"
APPROVED_WATER_PRODUCTION_FPS = 12
APPROVED_WATER_PRODUCTION_HOLD_FRAMES = 5
APPROVED_WATER_PRODUCTION_LAYER_IDS: tuple[str, ...] = (
    "water_deep_plane_d",
    "water_mid_plane_d",
    "water_surface_plane_d",
    "water_surface_caustics_plane_d",
    "water_highlights_plane_d",
)
APPROVED_WATER_PRODUCTION_FRAME_COUNT = 24

_WATER_STUDY_CACHE_BY_PYXEL_ID: dict[int, WaterStudyAssetCache] = {}


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


@dataclass(frozen=True)
class WaterStudyFrameSequence:
    layer_id: str
    planes: tuple[WaterStudyPlane, ...]
    hold_frames: tuple[int, ...]

    @property
    def total_hold_frames(self) -> int:
        return sum(self.hold_frames)

    def plane_for_time(self, elapsed_sec: float, fps: int) -> WaterStudyPlane | None:
        if not self.planes:
            return None
        total = self.total_hold_frames
        if total <= 0:
            return self.planes[0]
        elapsed_frames = int(max(0.0, elapsed_sec) * float(fps))
        position = elapsed_frames % total
        cursor = 0
        for index, hold_frames in enumerate(self.hold_frames):
            cursor += hold_frames
            if position < cursor:
                return self.planes[index]
        return self.planes[-1]


@dataclass(frozen=True)
class WaterStudyAssetCache:
    static_layers: dict[str, WaterStudyPlane]
    phase_layers: dict[str, tuple[WaterStudyPlane, ...]]
    frame_sequences: dict[str, WaterStudyFrameSequence]
    ready: bool
    preload_total_sec: float
    static_preload_sec: float
    phase_preload_sec: float
    sequence_preload_sec: float
    layer_preload_sec: dict[str, float]
    resident_pixel_count: int

    def plane_for_frame(
        self, layer_id: str, elapsed_sec: float, fps: int
    ) -> WaterStudyPlane | None:
        sequence = self.frame_sequences.get(layer_id)
        if sequence is not None:
            return sequence.plane_for_time(elapsed_sec, fps)
        phases = self.phase_layers.get(layer_id)
        if not phases:
            return self.static_layers.get(layer_id)
        step_frames = WATER_STUDY_PHASE_STEP_FRAMES[layer_id]
        initial_phase = WATER_STUDY_PHASE_INITIAL_INDICES[layer_id]
        elapsed_frames = int(max(0.0, elapsed_sec) * float(fps))
        phase_index = (initial_phase + elapsed_frames // step_frames) % len(phases)
        return phases[phase_index]


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
        if len(offset_text) not in {4, 5} or any(char not in HEX_DIGITS for char in offset_text):
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


def load_water_study_planes(
    pyxel_module: Any,
    *,
    layer_ids: tuple[str, ...] = WATER_STUDY_LAYER_IDS,
    layer_timing_callback: Callable[[str, float], None] | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> dict[str, WaterStudyPlane]:
    root = resources.files("drift_with_me").joinpath("assets/water_study")
    manifest = json.loads(
        root.joinpath("water_study_source_manifest.json").read_text(encoding="utf-8")
    )
    chunk_width, chunk_height = (int(value) for value in manifest["physical_chunk_size"])
    planes: dict[str, WaterStudyPlane] = {}

    for layer in manifest["layers"]:
        layer_id = str(layer["id"])
        if layer_id not in layer_ids:
            continue
        layer_started_at = timer()
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
        if layer_timing_callback is not None:
            layer_timing_callback(layer_id, timer() - layer_started_at)

    missing = [layer_id for layer_id in layer_ids if layer_id not in planes]
    if missing:
        raise ValueError(f"missing water study layers: {', '.join(missing)}")
    return planes


def load_water_study_phase_planes(
    pyxel_module: Any,
    *,
    layer_timing_callback: Callable[[str, float], None] | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> dict[str, tuple[WaterStudyPlane, ...]]:
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
        layer_started_at = timer()
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
        if layer_timing_callback is not None:
            layer_timing_callback(layer_id, timer() - layer_started_at)

    missing = [layer_id for layer_id in WATER_STUDY_PHASE_LAYER_IDS if layer_id not in phase_sets]
    if missing:
        raise ValueError(f"missing water study phase layers: {', '.join(missing)}")
    return phase_sets


def _load_water_study_frame_sequence(
    pyxel_module: Any,
    *,
    asset_dir: str,
    expected_asset_id: str,
    expected_runtime_layer_id: str,
    expected_frame_count: int,
    timing_label: str,
    layer_timing_callback: Callable[[str, float], None] | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> tuple[str, WaterStudyFrameSequence]:
    root = resources.files("drift_with_me").joinpath(f"assets/water_study/{asset_dir}")
    manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))
    asset_id = str(manifest["asset_id"])
    runtime_layer_id = str(manifest["runtime_layer_id"])
    if asset_id != expected_asset_id:
        raise ValueError(f"unexpected {timing_label} asset id: {asset_id}")
    if runtime_layer_id != expected_runtime_layer_id:
        raise ValueError(f"unexpected {timing_label} runtime layer id: {runtime_layer_id}")

    chunk_width, chunk_height = (int(value) for value in manifest["chunk_size"])
    logical_width, logical_height = (int(value) for value in manifest["logical_size"])
    if (chunk_width, chunk_height) != (256, 256):
        raise ValueError(f"{timing_label} expects 256x256 chunks, got {chunk_width}x{chunk_height}")
    frame_count = int(manifest["frame_count"])
    if frame_count != expected_frame_count:
        raise ValueError(
            f"{timing_label} expected {expected_frame_count} frames, got {frame_count}"
        )
    hold_frames = tuple(int(value) for value in manifest["hold_frames"])
    if len(hold_frames) != frame_count or any(value <= 0 for value in hold_frames):
        raise ValueError(f"{timing_label} hold_frames must match frame_count")

    started_at = timer()
    planes: list[WaterStudyPlane] = []
    for frame in manifest["frames"]:
        frame_id = str(frame["id"])
        chunk_rows: dict[str, tuple[str, ...]] = {}
        for chunk in frame["chunks"]:
            chunk_suffix = str(chunk["chunk"])
            chunk_rows[chunk_suffix] = parse_hex_rows(
                root.joinpath(str(chunk["file"])).read_text(encoding="ascii"),
                chunk_width,
                chunk_height,
                f"{asset_id}_{frame_id}_{chunk_suffix}",
            )
        planes.append(
            _plane_from_chunk_rows(
                pyxel_module,
                layer_id=f"{asset_id}_{frame_id}",
                logical_width=logical_width,
                logical_height=logical_height,
                chunk_width=chunk_width,
                chunk_height=chunk_height,
                colkey=int(manifest["colkey"]),
                chunk_rows=chunk_rows,
            )
        )
    if len(planes) != frame_count:
        raise ValueError(f"{timing_label} expected {frame_count} frame planes, got {len(planes)}")
    if layer_timing_callback is not None:
        layer_timing_callback(asset_id, timer() - started_at)
    return (
        runtime_layer_id,
        WaterStudyFrameSequence(
            layer_id=runtime_layer_id,
            planes=tuple(planes),
            hold_frames=hold_frames,
        ),
    )


def load_wtr002_water_study_frame_sequences(
    pyxel_module: Any,
    *,
    layer_timing_callback: Callable[[str, float], None] | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> dict[str, WaterStudyFrameSequence]:
    runtime_layer_id, sequence = _load_water_study_frame_sequence(
        pyxel_module,
        asset_dir="wtr002_surface_caustics",
        expected_asset_id=WTR002_SURFACE_CAUSTICS_ASSET_ID,
        expected_runtime_layer_id=WTR002_SURFACE_CAUSTICS_RUNTIME_LAYER_ID,
        expected_frame_count=WTR002_SURFACE_CAUSTICS_FRAME_COUNT,
        timing_label="WTR002 surface caustics",
        layer_timing_callback=layer_timing_callback,
        timer=timer,
    )
    return {
        runtime_layer_id: sequence,
    }


def load_wtr_look03_water_study_frame_sequences(
    pyxel_module: Any,
    *,
    layer_timing_callback: Callable[[str, float], None] | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> dict[str, WaterStudyFrameSequence]:
    runtime_layer_id, sequence = _load_water_study_frame_sequence(
        pyxel_module,
        asset_dir="wtr_look03_highlights",
        expected_asset_id=WTR_LOOK03_HIGHLIGHTS_ASSET_ID,
        expected_runtime_layer_id=WTR_LOOK03_HIGHLIGHTS_RUNTIME_LAYER_ID,
        expected_frame_count=WTR_LOOK03_HIGHLIGHTS_FRAME_COUNT,
        timing_label="WTR_LOOK03 highlights",
        layer_timing_callback=layer_timing_callback,
        timer=timer,
    )
    return {
        runtime_layer_id: sequence,
    }


def load_approved_water_production_frame_sequences(
    pyxel_module: Any,
    *,
    layer_timing_callback: Callable[[str, float], None] | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> dict[str, WaterStudyFrameSequence]:
    root = resources.files("drift_with_me").joinpath("assets/water_study/approved_production")
    production_manifest = json.loads(
        root.joinpath("production_manifest.json").read_text(encoding="utf-8")
    )
    runtime_manifest = json.loads(
        root.joinpath("runtime_lite/runtime_lite_manifest.json").read_text(encoding="utf-8")
    )
    if str(runtime_manifest["encoding"]) != "DHEX1":
        raise ValueError("approved water production runtime-lite must use DHEX1")
    if str(runtime_manifest["profile"]) != APPROVED_WATER_PRODUCTION_PROFILE:
        raise ValueError(
            f"approved water production runtime-lite must use {APPROVED_WATER_PRODUCTION_PROFILE}"
        )
    chunk_width, chunk_height = (int(value) for value in production_manifest["chunk_size"])
    logical_width, logical_height = (int(value) for value in production_manifest["logical_size"])
    chunk_grid_x, chunk_grid_y = (int(value) for value in production_manifest["chunk_grid"])
    if (chunk_width, chunk_height) != (256, 256):
        raise ValueError(
            f"approved water production expects 256x256 chunks, got {chunk_width}x{chunk_height}"
        )
    layer_colkeys: dict[str, int | None] = {}
    for layer in production_manifest["layers"]:
        layer_id = str(layer["id"])
        if layer_id not in APPROVED_WATER_PRODUCTION_LAYER_IDS:
            continue
        colkey_value = layer.get("colkey")
        layer_colkeys[layer_id] = None if colkey_value is None else int(colkey_value)
    missing_manifest_layers = [
        layer_id
        for layer_id in APPROVED_WATER_PRODUCTION_LAYER_IDS
        if layer_id not in layer_colkeys
    ]
    if missing_manifest_layers:
        raise ValueError(
            "missing approved water production manifest layers: "
            + ", ".join(missing_manifest_layers)
        )

    sequences: dict[str, WaterStudyFrameSequence] = {}
    runtime_layers = runtime_manifest["layers"]
    for layer in runtime_layers:
        layer_id = str(layer["id"])
        if layer_id not in APPROVED_WATER_PRODUCTION_LAYER_IDS:
            raise ValueError(f"unexpected approved water production runtime layer: {layer_id}")
        layer_started_at = timer()
        source_frame_indices = tuple(int(index) for index in layer["source_frame_indices"])
        if len(source_frame_indices) != APPROVED_WATER_PRODUCTION_FRAME_COUNT:
            raise ValueError(
                f"{layer_id}: expected {APPROVED_WATER_PRODUCTION_FRAME_COUNT} "
                f"profile frames, got {len(source_frame_indices)}"
            )
        base_frame_index = source_frame_indices[0]
        base_rows: dict[str, tuple[str, ...]] = {}
        for chunk_x in range(chunk_grid_x):
            for chunk_y in range(chunk_grid_y):
                chunk_suffix = f"c{chunk_x}{chunk_y}"
                base_rows[chunk_suffix] = parse_hex_rows(
                    root.joinpath(
                        "chunks_256/hex",
                        f"{layer_id}_f{base_frame_index:03d}_{chunk_suffix}.hex.txt",
                    ).read_text(encoding="ascii"),
                    chunk_width,
                    chunk_height,
                    f"{layer_id}_f{base_frame_index:03d}_{chunk_suffix}",
                )
        current_rows = dict(base_rows)
        planes: list[WaterStudyPlane] = [
            _plane_from_chunk_rows(
                pyxel_module,
                layer_id=f"{layer_id}_t00",
                logical_width=logical_width,
                logical_height=logical_height,
                chunk_width=chunk_width,
                chunk_height=chunk_height,
                colkey=layer_colkeys[layer_id],
                chunk_rows=current_rows,
            )
        ]
        for transition in layer["transitions"]:
            from_tick = int(transition["from_tick"])
            to_tick = int(transition["to_tick"])
            target_rows = dict(current_rows) if to_tick == 0 else current_rows
            for chunk in transition["chunks"]:
                chunk_suffix = str(chunk["chunk"])
                patch_file = str(chunk["file"])
                patch_label = f"{layer_id}:t{from_tick:02d}->t{to_tick:02d}:{chunk_suffix}"
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
            if to_tick == 0:
                if target_rows != base_rows:
                    raise ValueError(f"{layer_id}: approved DHEX loopback does not reconstruct t00")
                continue
            planes.append(
                _plane_from_chunk_rows(
                    pyxel_module,
                    layer_id=f"{layer_id}_t{to_tick:02d}",
                    logical_width=logical_width,
                    logical_height=logical_height,
                    chunk_width=chunk_width,
                    chunk_height=chunk_height,
                    colkey=layer_colkeys[layer_id],
                    chunk_rows=current_rows,
                )
            )
        if len(planes) != len(source_frame_indices):
            raise ValueError(
                f"{layer_id}: expected {len(source_frame_indices)} planes, got {len(planes)}"
            )
        sequences[layer_id] = WaterStudyFrameSequence(
            layer_id=layer_id,
            planes=tuple(planes),
            hold_frames=(APPROVED_WATER_PRODUCTION_HOLD_FRAMES,) * len(planes),
        )
        if layer_timing_callback is not None:
            layer_timing_callback(layer_id, timer() - layer_started_at)
    missing_runtime_layers = [
        layer_id for layer_id in APPROVED_WATER_PRODUCTION_LAYER_IDS if layer_id not in sequences
    ]
    if missing_runtime_layers:
        raise ValueError(
            "missing approved water production runtime layers: " + ", ".join(missing_runtime_layers)
        )
    return {layer_id: sequences[layer_id] for layer_id in APPROVED_WATER_PRODUCTION_LAYER_IDS}


def load_water_study_frame_sequences(
    pyxel_module: Any,
    *,
    layer_timing_callback: Callable[[str, float], None] | None = None,
    timer: Callable[[], float] = time.perf_counter,
) -> dict[str, WaterStudyFrameSequence]:
    return load_approved_water_production_frame_sequences(
        pyxel_module,
        layer_timing_callback=layer_timing_callback,
        timer=timer,
    )


def _resident_pixel_count(cache: WaterStudyAssetCache) -> int:
    total = 0
    for plane in cache.static_layers.values():
        total += sum(chunk.width * chunk.height for chunk in plane.chunks)
    for phases in cache.phase_layers.values():
        for plane in phases:
            total += sum(chunk.width * chunk.height for chunk in plane.chunks)
    for sequence in cache.frame_sequences.values():
        for plane in sequence.planes:
            total += sum(chunk.width * chunk.height for chunk in plane.chunks)
    return total


def preload_water_study_cache(
    pyxel_module: Any,
    *,
    force: bool = False,
    timer: Callable[[], float] = time.perf_counter,
) -> WaterStudyAssetCache:
    cache_key = id(pyxel_module)
    if not force and cache_key in _WATER_STUDY_CACHE_BY_PYXEL_ID:
        return _WATER_STUDY_CACHE_BY_PYXEL_ID[cache_key]

    layer_timings: dict[str, float] = {}
    preload_started_at = timer()
    static_started_at = timer()
    static_layers: dict[str, WaterStudyPlane] = {}
    static_preload_sec = timer() - static_started_at
    phase_started_at = timer()
    phase_layers: dict[str, tuple[WaterStudyPlane, ...]] = {}
    phase_preload_sec = timer() - phase_started_at
    sequence_started_at = timer()
    frame_sequences = load_water_study_frame_sequences(
        pyxel_module,
        layer_timing_callback=layer_timings.__setitem__,
        timer=timer,
    )
    sequence_preload_sec = timer() - sequence_started_at
    cache = WaterStudyAssetCache(
        static_layers=static_layers,
        phase_layers=phase_layers,
        frame_sequences=frame_sequences,
        ready=True,
        preload_total_sec=timer() - preload_started_at,
        static_preload_sec=static_preload_sec,
        phase_preload_sec=phase_preload_sec,
        sequence_preload_sec=sequence_preload_sec,
        layer_preload_sec=layer_timings,
        resident_pixel_count=0,
    )
    cache = WaterStudyAssetCache(
        static_layers=cache.static_layers,
        phase_layers=cache.phase_layers,
        frame_sequences=cache.frame_sequences,
        ready=cache.ready,
        preload_total_sec=cache.preload_total_sec,
        static_preload_sec=cache.static_preload_sec,
        phase_preload_sec=cache.phase_preload_sec,
        sequence_preload_sec=cache.sequence_preload_sec,
        layer_preload_sec=cache.layer_preload_sec,
        resident_pixel_count=_resident_pixel_count(cache),
    )
    _WATER_STUDY_CACHE_BY_PYXEL_ID[cache_key] = cache
    return cache


def clear_water_study_cache_for_tests() -> None:
    _WATER_STUDY_CACHE_BY_PYXEL_ID.clear()
