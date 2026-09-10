#!/usr/bin/env python3
"""Validate the delivered P0 specification data; does not execute the game.

Run from any directory:
    python3 tools/validate_spec_data.py
    python3 tools/validate_spec_data.py --self-test
Requires Python 3.11+, standard library only.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from collections import deque
from pathlib import Path
from typing import Any


class ValidationError(ValueError):
    """The specification data violates a required invariant."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def finite_tree(value: Any, path: str) -> None:
    if isinstance(value, float):
        require(math.isfinite(value), f"{path}: non-finite number")
    elif isinstance(value, dict):
        for key, item in value.items():
            finite_tree(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            finite_tree(item, f"{path}[{index}]")


def vector3(value: Any, path: str) -> list[float]:
    require(isinstance(value, list) and len(value) == 3, f"{path}: expected 3-vector")
    require(
        all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in value
        ),
        f"{path}: expected finite coordinates",
    )
    return value


def overlaps_box(x: float, z: float, hx: float, hz: float, obj: dict[str, Any]) -> bool:
    px, _, pz = obj["position"]
    ox, oz = obj["half_extents_xz"]
    # Tangency is permitted, penetration is not.
    return abs(x - px) < hx + ox - 1e-9 and abs(z - pz) < hz + oz - 1e-9


def validate(
    config: dict[str, Any], world: dict[str, Any], audio: dict[str, Any]
) -> dict[str, Any]:
    for name, document in [("config", config), ("world", world), ("audio", audio)]:
        finite_tree(document, name)
        require(document.get("schema_version") == 1, f"{name}: unsupported schema_version")
    require(config["spec_version"] == world["spec_version"] == "0.1.0", "spec_version mismatch")
    g = world["ground"]
    require(g["width_cells"] == g["depth_cells"] == 32, "P0 map must have 32x32 cells")
    require(g["cell_size"] == 32, "P0 cell_size must be 32")
    width = g["width_cells"] * g["cell_size"]
    depth = g["depth_cells"] * g["cell_size"]
    require(g["bounds_xz"] == [0, 0, width, depth], "ground bounds mismatch")
    require(g["height"] == 0 and g["origin"] == [0, 0, 0], "P0 ground must be flat at Y=0")
    require(
        g["default_walkable"] is True and not g["cell_overrides"], "P0 must start as open ground"
    )
    require(config["display"]["profiles"]["medium"] == [512, 236], "medium resolution mismatch")
    require(
        config["display"]["default_profile"] in config["display"]["profiles"],
        "unknown display profile",
    )
    for name, size in config["display"]["profiles"].items():
        require(
            len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size),
            f"bad resolution {name}",
        )
        require(size[0] > size[1], f"{name} must be landscape")
    require(config["simulation"]["fixed_hz"] == 60, "P0 fixed_hz mismatch")
    require(config["simulation"]["day_phase"] == "day", "P0 must start in daytime")
    require(
        config["simulation"]["realtime_day_night"] is False, "real-time day/night is out of scope"
    )
    require(config["simulation"]["max_steps_per_callback"] > 0, "max_steps must be positive")
    for name in (
        "water_max",
        "water_start",
        "barrier_water_per_sec",
        "bubble_water_cost",
        "energy_max",
        "energy_start",
        "discharge_energy_cost",
        "refill_duration_sec",
        "solar_charge_duration_sec",
    ):
        require(config["resources"][name] >= 0, f"resources.{name} must be nonnegative")
    r = config["resources"]
    require(
        0 < r["water_max"] and 0 <= r["water_start"] <= r["water_max"], "water capacity mismatch"
    )
    require(
        0 < r["energy_max"] and 0 <= r["energy_start"] <= r["energy_max"],
        "energy capacity mismatch",
    )
    require(r["bubble_water_cost"] <= r["water_max"], "bubble cannot be funded")
    require(r["discharge_energy_cost"] <= r["energy_max"], "discharge cannot be funded")
    c = config["camera"]
    require(0 < c["near"] < c["far"], "near/far invalid")
    require(0 < c["zoom_min"] <= 1 <= c["zoom_max"], "zoom range invalid")
    require(0 < c["pitch_deg"] < 90 and 0 < c["horizontal_fov_deg"] < 180, "camera angle invalid")
    require(
        config["culling"]["active_enter_radius"] < config["culling"]["active_exit_radius"],
        "activity hysteresis invalid",
    )
    require(
        config["bubble"]["max_projectiles"] == config["bubble"]["max_captured_targets"] == 1,
        "P0 bubble caps mismatch",
    )
    require(
        config["enemy"]["normal"]["move_speed"] < config["player"]["move_speed"],
        "normal enemy must be slow",
    )
    require(
        config["enemy"]["abnormal"]["dash_speed"] > config["player"]["move_speed"],
        "abnormal dash must be faster",
    )
    objects = world["objects"]
    enemies = world["enemies"]
    all_entities = objects + enemies
    ids = [o["id"] for o in all_entities]
    require(len(ids) == len(set(ids)), "duplicate entity id")
    kinds = {
        "water_station",
        "solar_station",
        "inspectable",
        "ambient_maintenance",
        "obstacle",
        "sprite_prop",
        "reactive_prop",
    }
    for obj in objects:
        require(obj["kind"] in kinds, f"unknown object kind {obj['kind']}")
    for obj in all_entities:
        x, y, z = vector3(obj["position"], obj["id"])
        require(
            0 <= x <= width and 0 <= z <= depth and y == 0, f"{obj['id']}: invalid root position"
        )
        if obj.get("text_key") is not None:
            require(obj["text_key"] in world["texts"], f"{obj['id']}: missing text_key")
    solids = [o for o in objects if o.get("solid")]
    for obj in solids:
        require(
            "half_extents_xz" in obj and len(obj["half_extents_xz"]) == 2,
            f"{obj['id']}: missing extent",
        )
        hx, hz = obj["half_extents_xz"]
        require(hx > 0 and hz > 0, f"{obj['id']}: nonpositive extent")
        x, _, z = obj["position"]
        require(hx <= x <= width - hx and hz <= z <= depth - hz, f"{obj['id']}: solid outside map")
        require(
            0 < obj["height"] <= config["culling"]["static_visual_max_height"],
            f"{obj['id']}: culling height insufficient",
        )
    px, _, pz = vector3(world["spawn"]["player"], "player spawn")
    phx, phz = config["player"]["collider_half_x"], config["player"]["collider_half_z"]
    require(phx <= px <= width - phx and phz <= pz <= depth - phz, "spawn outside map")
    require(not any(overlaps_box(px, pz, phx, phz, o) for o in solids), "spawn intersects obstacle")
    for enemy in enemies:
        require(enemy["kind"] in config["enemy"], f"{enemy['id']}: unknown enemy kind")
        require(enemy["home"] == enemy["position"], f"{enemy['id']}: initial home mismatch")
        x, _, z = enemy["position"]
        radius = config["enemy"][enemy["kind"]]["radius"]
        require(
            not any(overlaps_box(x, z, radius, radius, o) for o in solids),
            f"{enemy['id']}: intersects solid",
        )
        for safe in world["safe_zones"]:
            sx, sz = safe["center_xz"]
            require(
                math.hypot(x - sx, z - sz) >= safe["radius"] + radius,
                f"{enemy['id']}: inside safe zone",
            )
    for zone in world["camera_zones"]:
        x0, z0, x1, z1 = zone["trigger_rect_xz"]
        require(
            0 <= x0 < x1 <= width and 0 <= z0 < z1 <= depth, f"{zone['id']}: bad camera rectangle"
        )
        require(c["zoom_min"] <= zone["zoom"] <= c["zoom_max"], f"{zone['id']}: zoom out of bounds")
        vector3(zone["target"], zone["id"] + ".target")
    for sequence in world["camera_sequences"]:
        for cue in sequence["cues"]:
            if "target_object" in cue:
                require(cue["target_object"] in ids, f"{sequence['id']}: missing cue target")
            require(cue["blend_sec"] >= 0 and cue["hold_sec"] >= 0, "negative cue duration")
    expected_events = {
        "bubble_fired",
        "enemy_captured",
        "barrier_repelled",
        "discharge_succeeded",
        "action_denied",
    }
    actual_events = [e["event"] for e in audio["events"]]
    require(
        set(actual_events) == expected_events and len(actual_events) == 5,
        "audio event list mismatch",
    )
    for event in audio["events"]:
        require(
            0 <= event["channel"] < config["audio"]["max_simultaneous_channels"],
            "audio channel mismatch",
        )
        require(
            event["priority"] == config["audio"]["event_priority"][event["event"]],
            "audio priority mismatch",
        )
    require(config["audio"]["bgm_enabled"] is False, "P0 BGM must be disabled")
    require(config["effects"]["onomatopoeia_enabled"] is False, "onomatopoeia is deferred")

    # Static-only 16-unit sampling. This is not an AI/escape-path simulation.
    step = 16.0
    nx, nz = int(width / step), int(depth / step)

    def sample(i: int, j: int) -> tuple[float, float]:
        return (i + 0.5) * step, (j + 0.5) * step

    passable = set()
    for i in range(nx):
        for j in range(nz):
            x, z = sample(i, j)
            if (
                phx <= x <= width - phx
                and phz <= z <= depth - phz
                and not any(overlaps_box(x, z, phx, phz, o) for o in solids)
            ):
                passable.add((i, j))
    start = min(passable, key=lambda ij: (sample(*ij)[0] - px) ** 2 + (sample(*ij)[1] - pz) ** 2)
    reached = {start}
    queue = deque([start])
    while queue:
        i, j = queue.popleft()
        for nxt in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)):
            if nxt in passable and nxt not in reached:
                reached.add(nxt)
                queue.append(nxt)
    interaction_range = config["interaction"]["range"]
    reachable_stations = []
    for obj in objects:
        if obj["kind"] not in {"water_station", "solar_station"}:
            continue
        x, _, z = obj["position"]
        require(
            any(
                math.hypot(sample(*ij)[0] - x, sample(*ij)[1] - z) <= interaction_range
                for ij in reached
            ),
            f"{obj['id']}: unreachable in static sample grid",
        )
        reachable_stations.append(obj["id"])
    return {
        "entity_count": len(all_entities),
        "solid_count": len(solids),
        "enemy_count": len(enemies),
        "passable_sample_cells": len(passable),
        "reachable_sample_cells": len(reached),
        "reachable_station_ids": reachable_stations,
        "audio_events": len(actual_events),
    }


def self_test(config: dict[str, Any], world: dict[str, Any], audio: dict[str, Any]) -> int:
    mutations = [
        ("negative resource", lambda c, w, a: c["resources"].__setitem__("bubble_water_cost", -1)),
        ("duplicate ID", lambda c, w, a: w["objects"].append(copy.deepcopy(w["objects"][0]))),
        (
            "missing target",
            lambda c, w, a: w["camera_sequences"][0]["cues"][0].__setitem__(
                "target_object", "missing"
            ),
        ),
        ("near/far", lambda c, w, a: c["camera"].__setitem__("near", c["camera"]["far"])),
        ("non-finite", lambda c, w, a: c["player"].__setitem__("move_speed", float("nan"))),
        (
            "unsafe enemy spawn",
            lambda c, w, a: (
                w["enemies"][0].__setitem__("position", [160, 0, 160]),
                w["enemies"][0].__setitem__("home", [160, 0, 160]),
            ),
        ),
        ("missing audio", lambda c, w, a: a["events"].pop()),
    ]
    for name, mutate in mutations:
        c, w, a = copy.deepcopy((config, world, audio))
        mutate(c, w, a)
        try:
            validate(c, w, a)
        except ValidationError:
            continue
        raise ValidationError(f"self-test failed: {name} was not rejected")
    return len(mutations)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        docs = [
            json.loads((args.root / "data" / name).read_text(encoding="utf-8"))
            for name in ("game_config.json", "prototype_world.json", "audio_events.json")
        ]
        report = validate(*docs)
        if args.self_test:
            report["rejected_invalid_mutations"] = self_test(*docs)
        print(
            json.dumps(
                {"status": "PASS", "scope": "specification_data_only", **report},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValidationError,
        KeyError,
        TypeError,
        IndexError,
    ) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
