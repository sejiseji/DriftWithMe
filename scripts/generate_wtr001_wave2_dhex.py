from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "src/drift_with_me/assets/water_study"
RUNTIME_ROOT = ASSET_ROOT / "runtime_lite_phase_delta"
CHUNK_ROOT = ASSET_ROOT / "chunks_256/hex_rows"
DELTA_ROOT = RUNTIME_ROOT / "delta_chunks"

WIDTH = 1024
HEIGHT = 512
CHUNK_SIZE = 256
CHUNK_IDS = ("c00", "c10", "c20", "c30", "c01", "c11", "c21", "c31")
PHASES = 8

WAVE2_GENERATED_LAYERS = {
    "water_mid_plane_c": {
        "amplitude_x": 0.9,
        "amplitude_y": 0.7,
        "wavelength_x": 310.0,
        "wavelength_y": 250.0,
        "secondary": 0.32,
    },
    "water_surface_plane_c": {
        "amplitude_x": 1.2,
        "amplitude_y": 0.95,
        "wavelength_x": 230.0,
        "wavelength_y": 190.0,
        "secondary": 0.42,
    },
}

WAVE1_REUSED_LAYERS = (
    "water_surface_caustics_plane_c",
    "water_upper_lightnet_plane_c",
)


def read_chunk_rows(layer_id: str, chunk_id: str) -> list[str]:
    path = CHUNK_ROOT / f"{layer_id}_{chunk_id}.hex.txt"
    rows = path.read_text(encoding="utf-8").splitlines()
    if len(rows) != CHUNK_SIZE or any(len(row) != CHUNK_SIZE for row in rows):
        raise ValueError(f"{path}: expected {CHUNK_SIZE}x{CHUNK_SIZE}")
    return rows


def load_plane(layer_id: str) -> list[str]:
    rows = [["0"] * WIDTH for _ in range(HEIGHT)]
    for chunk_id in CHUNK_IDS:
        chunk_x = int(chunk_id[1]) * CHUNK_SIZE
        chunk_y = int(chunk_id[2]) * CHUNK_SIZE
        chunk_rows = read_chunk_rows(layer_id, chunk_id)
        for y, row in enumerate(chunk_rows):
            rows[chunk_y + y][chunk_x : chunk_x + CHUNK_SIZE] = row
    return ["".join(row) for row in rows]


def deform_plane(base_rows: list[str], phase_index: int, config: dict[str, float]) -> list[str]:
    if phase_index == 0:
        return list(base_rows)
    theta = math.tau * phase_index / PHASES
    amp_x = config["amplitude_x"]
    amp_y = config["amplitude_y"]
    wavelength_x = config["wavelength_x"]
    wavelength_y = config["wavelength_y"]
    secondary = config["secondary"]
    out: list[str] = []
    for y in range(HEIGHT):
        row_chars: list[str] = []
        y_wave = math.tau * y / wavelength_y
        for x in range(WIDTH):
            x_wave = math.tau * x / wavelength_x
            dx_float = amp_x * (
                math.sin(theta + y_wave)
                + secondary * math.sin(theta * 1.7 + x_wave * 0.55 + y_wave * 0.28)
            )
            dy_float = amp_y * (
                math.cos(theta * 0.82 + x_wave)
                + secondary * math.sin(theta * 1.35 + y_wave * 0.62 - x_wave * 0.24)
            )
            dx = int(round(dx_float))
            dy = int(round(dy_float))
            row_chars.append(base_rows[(y + dy) % HEIGHT][(x + dx) % WIDTH])
        out.append("".join(row_chars))
    return out


def chunk_from_plane(rows: list[str], chunk_id: str) -> list[str]:
    chunk_x = int(chunk_id[1]) * CHUNK_SIZE
    chunk_y = int(chunk_id[2]) * CHUNK_SIZE
    return [row[chunk_x : chunk_x + CHUNK_SIZE] for row in rows[chunk_y : chunk_y + CHUNK_SIZE]]


def dhex_patch(from_rows: list[str], to_rows: list[str]) -> tuple[str, int, int]:
    from_flat = "".join(from_rows)
    to_flat = "".join(to_rows)
    lines: list[str] = []
    changed_pixels = 0
    run_count = 0
    index = 0
    total = len(from_flat)
    while index < total:
        if from_flat[index] == to_flat[index]:
            index += 1
            continue
        start = index
        data: list[str] = []
        while index < total and from_flat[index] != to_flat[index]:
            data.append(to_flat[index])
            index += 1
        lines.append(f"{start:04X}:{''.join(data)}")
        changed_pixels += len(data)
        run_count += 1
    text = "\n".join(lines)
    if text:
        text += "\n"
    return text, changed_pixels, run_count


def build_generated_layer(layer_id: str, config: dict[str, float]) -> dict:
    base_rows = load_plane(layer_id)
    phases = [deform_plane(base_rows, phase_index, config) for phase_index in range(PHASES)]
    layer_dir = DELTA_ROOT / layer_id
    layer_dir.mkdir(parents=True, exist_ok=True)
    transitions: list[dict] = []
    for phase_index in range(PHASES):
        from_phase = f"p{phase_index:02d}"
        to_phase = f"p{(phase_index + 1) % PHASES:02d}"
        from_rows = phases[phase_index]
        to_rows = phases[(phase_index + 1) % PHASES]
        transition_chunks: list[dict] = []
        transition_changed = 0
        transition_runs = 0
        transition_patch_bytes = 0
        for chunk_id in CHUNK_IDS:
            text, changed_pixels, run_count = dhex_patch(
                chunk_from_plane(from_rows, chunk_id), chunk_from_plane(to_rows, chunk_id)
            )
            rel_path = (
                Path("delta_chunks") / layer_id / f"{from_phase}_to_{to_phase}_{chunk_id}.dhex"
            )
            path = RUNTIME_ROOT / rel_path
            path.write_text(text, encoding="ascii")
            patch_bytes = len(text.encode("ascii"))
            transition_changed += changed_pixels
            transition_runs += run_count
            transition_patch_bytes += patch_bytes
            transition_chunks.append(
                {
                    "chunk": chunk_id,
                    "file": rel_path.as_posix(),
                    "changed_pixels": changed_pixels,
                    "run_count": run_count,
                    "sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
                }
            )
        transitions.append(
            {
                "from": from_phase,
                "to": to_phase,
                "chunks": transition_chunks,
                "changed_pixels": transition_changed,
                "run_count": transition_runs,
                "patch_bytes": transition_patch_bytes,
                "changed_ratio": round(transition_changed / (WIDTH * HEIGHT), 6),
            }
        )
    return {"id": layer_id, "transitions": transitions}


def transition_stats(layer: dict) -> dict:
    transitions = []
    changed_pixels = 0
    run_count = 0
    patch_bytes = 0
    for transition in layer["transitions"]:
        changed_pixels += int(transition["changed_pixels"])
        run_count += int(transition["run_count"])
        patch_bytes += int(transition["patch_bytes"])
        transitions.append(
            {
                "from": transition["from"],
                "to": transition["to"],
                "changed_pixels": transition["changed_pixels"],
                "run_count": transition["run_count"],
                "patch_bytes": transition["patch_bytes"],
                "changed_ratio": transition["changed_ratio"],
            }
        )
    return {
        "changed_pixels": changed_pixels,
        "run_count": run_count,
        "patch_bytes": patch_bytes,
        "transitions": transitions,
    }


def main() -> None:
    manifest_path = RUNTIME_ROOT / "runtime_lite_manifest.json"
    old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing_layers = {layer["id"]: layer for layer in old_manifest["layers"]}
    generated_layers = [
        build_generated_layer(layer_id, config)
        for layer_id, config in WAVE2_GENERATED_LAYERS.items()
    ]
    layers = [
        *generated_layers,
        *(existing_layers[layer_id] for layer_id in WAVE1_REUSED_LAYERS),
    ]
    manifest = {
        "version": "0.2.0",
        "base_asset_pack": old_manifest["base_asset_pack"],
        "phase_asset_source": "WTR001_Wave2_MultiLayer_Phase_Pack_v0.1",
        "encoding": old_manifest["encoding"],
        "logical_plane_size": old_manifest["logical_plane_size"],
        "chunk_size": old_manifest["chunk_size"],
        "chunk_grid": old_manifest["chunk_grid"],
        "phase_count": old_manifest["phase_count"],
        "runtime_phase_schedule": {
            "water_mid_plane_c": {"step_frames": 13, "initial_phase": "p00"},
            "water_surface_plane_c": {"step_frames": 9, "initial_phase": "p02"},
            "water_surface_caustics_plane_c": {"step_frames": 7, "initial_phase": "p05"},
            "water_upper_lightnet_plane_c": {"step_frames": 5, "initial_phase": "p01"},
        },
        "wave2_generation": WAVE2_GENERATED_LAYERS,
        "layers": layers,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    full_phase_logical_hex_bytes = len(layers) * PHASES * (WIDTH * HEIGHT + HEIGHT)
    full_phase_chunk_hex_bytes = (
        len(layers) * PHASES * len(CHUNK_IDS) * (CHUNK_SIZE * CHUNK_SIZE + CHUNK_SIZE)
    )
    delta_patch_bytes = sum(
        int(transition["patch_bytes"]) for layer in layers for transition in layer["transitions"]
    )
    stats = {
        "full_phase_logical_hex_bytes": full_phase_logical_hex_bytes,
        "full_phase_chunk_hex_bytes": full_phase_chunk_hex_bytes,
        "delta_patch_bytes": delta_patch_bytes,
        "layers": {layer["id"]: transition_stats(layer) for layer in layers},
        "delta_vs_full_chunk_ratio": delta_patch_bytes / full_phase_chunk_hex_bytes,
        "delta_vs_full_logical_ratio": delta_patch_bytes / full_phase_logical_hex_bytes,
        "savings_vs_full_chunk_pct": round(
            100.0 * (1.0 - delta_patch_bytes / full_phase_chunk_hex_bytes), 2
        ),
        "savings_vs_full_logical_pct": round(
            100.0 * (1.0 - delta_patch_bytes / full_phase_logical_hex_bytes), 2
        ),
        "raw_memory_estimates_bytes": {
            "cache_all_32_phase_planes_palette_indices": len(layers) * PHASES * WIDTH * HEIGHT,
            "extra_7_phases_per_layer_if_p00_aliases_base": len(layers)
            * (PHASES - 1)
            * WIDTH
            * HEIGHT,
        },
    }
    (RUNTIME_ROOT / "runtime_lite_stats.json").write_text(
        json.dumps(stats, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "generated Wave2 runtime-lite DHEX",
        f"layers={len(layers)}",
        f"patch_bytes={delta_patch_bytes}",
        f"savings={stats['savings_vs_full_chunk_pct']}%",
    )


if __name__ == "__main__":
    main()
