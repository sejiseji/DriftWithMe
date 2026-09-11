# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from drift_with_me.config import load_data_json, load_runtime_config
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel
from drift_with_me.render import Renderer
from drift_with_me.world import WorldData


class DummyPyxel:
    pass


def build_world(extra_details: int) -> WorldData:
    config = load_data_json("game_config.json")
    raw = load_data_json("prototype_world.json")
    culling = config["culling"]
    base_per_chunk = int(culling["visual_detail_per_chunk"])
    ground = raw["ground"]
    width = float(ground["width_cells"] * ground["cell_size"])
    depth = float(ground["depth_cells"] * ground["cell_size"])
    chunk_size = float(culling["chunk_size"])
    chunk_count = math.ceil(width / chunk_size) * math.ceil(depth / chunk_size)
    extra_per_chunk = (extra_details + chunk_count - 1) // chunk_count
    return WorldData(
        raw,
        chunk_size=chunk_size,
        static_visual_max_height=float(culling["static_visual_max_height"]),
        visual_detail_per_chunk=base_per_chunk + extra_per_chunk,
    )


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percent))))
    return ordered[index]


def measure(extra_details: int, iterations: int) -> dict:
    runtime = load_runtime_config()
    world = build_world(extra_details)
    model = GameModel(runtime.raw, world)
    camera = CameraState.from_config(
        runtime.raw,
        Vec3(model.player.x, 0.0, model.player.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    renderer = Renderer(DummyPyxel())

    samples_ms: list[float] = []
    warmup = min(60, max(1, iterations // 10))
    for index in range(iterations + warmup):
        start = time.perf_counter()
        renderer.world_commands(model, camera, presentation_time=index / 60.0)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if index >= warmup:
            samples_ms.append(elapsed_ms)

    stats = renderer.last_stats
    return {
        "extra_details": extra_details,
        "ground_details": len(world.ground_details),
        "iterations": iterations,
        "median_ms": round(statistics.median(samples_ms), 4),
        "p95_ms": round(percentile(samples_ms, 0.95), 4),
        "candidate_chunks": stats.candidate_chunks,
        "candidate_static_objects": stats.candidate_static_objects,
        "visible_static_objects": stats.visible_static_objects,
        "visible_ground_details": stats.visible_ground_details,
        "draw_commands": stats.draw_commands,
        "active_enemies": stats.active_enemies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure culling candidate generation.")
    parser.add_argument("--iterations", type=int, default=600)
    parser.add_argument("--extra-details", type=int, nargs="*", default=[0, 128, 512])
    args = parser.parse_args()

    results = [measure(extra, args.iterations) for extra in args.extra_details]
    print(json.dumps({"results": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
