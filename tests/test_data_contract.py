from __future__ import annotations

import json
import math
from pathlib import Path

from drift_with_me.audio import SOUND_SHAPES
from drift_with_me.config import load_data_json

ROOT = Path(__file__).resolve().parents[1]


def test_bundled_json_matches_prototype_spec_data() -> None:
    for name in ("game_config.json", "prototype_world.json", "audio_events.json"):
        docs_data = json.loads(
            (ROOT / "docs" / "prototype_spec" / "data" / name).read_text(encoding="utf-8")
        )
        assert load_data_json(name) == docs_data


def test_audio_event_sound_keys_are_registered() -> None:
    audio = load_data_json("audio_events.json")

    assert all(item["sound_key"] in SOUND_SHAPES for item in audio["events"])


def test_env003_forest_composition_has_density_landmark_and_lanes() -> None:
    config = load_data_json("game_config.json")
    world = load_data_json("prototype_world.json")
    objects = world["objects"]
    by_id = {obj["id"]: obj for obj in objects}

    forest_trees = [
        obj
        for obj in objects
        if obj["kind"] == "sprite_prop" and obj.get("visual") in {"tree_leafy_a", "tree_thin_b"}
    ]
    forest_core = [obj for obj in forest_trees if obj["position"][2] >= 760.0]
    forest_edge = [obj for obj in forest_trees if 560.0 <= obj["position"][2] < 760.0]
    assert len(forest_core) >= 36
    assert len(forest_edge) >= 8

    giant = by_id["rock_02"]
    gx, _, gz = giant["position"]
    assert giant["visual"] == "giant_tree_root_massive_a"
    assert giant["half_extents_xz"][0] >= 50.0
    assert giant["half_extents_xz"][1] >= 20.0

    nearby_tree_roots = [
        obj
        for obj in forest_trees
        if math.hypot(obj["position"][0] - gx, obj["position"][2] - gz) < 92.0
    ]
    assert nearby_tree_roots == []

    landmark_grass = [
        obj
        for obj in objects
        if "grass" in obj.get("visual", "")
        and math.hypot(obj["position"][0] - gx, obj["position"][2] - gz) <= 180.0
    ]
    assert len(landmark_grass) >= 4

    solids = [obj for obj in objects if obj.get("solid")]
    half_x = float(config["player"]["collider_half_x"])
    half_z = float(config["player"]["collider_half_z"])

    def collides_waypoint(x: float, z: float) -> bool:
        for obj in solids:
            ox, _, oz = obj["position"]
            obj_half_x, obj_half_z = obj["half_extents_xz"]
            if abs(x - ox) < half_x + obj_half_x and abs(z - oz) < half_z + obj_half_z:
                return True
        return False

    approach_lane = [
        (160.0, 160.0),
        (224.0, 352.0),
        (316.0, 448.0),
        (420.0, 544.0),
        (568.0, 616.0),
        (688.0, 650.0),
        (620.0, 760.0),
        (520.0, 840.0),
    ]
    giant_loop = [
        (612.0, 544.0),
        (764.0, 584.0),
        (688.0, 620.0),
    ]
    assert not any(collides_waypoint(x, z) for x, z in approach_lane + giant_loop)
