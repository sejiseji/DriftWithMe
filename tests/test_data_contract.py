from __future__ import annotations

import json
from pathlib import Path

from drift_with_me import __version__
from drift_with_me.audio import AudioEngine
from drift_with_me.config import APP_TITLE, load_data_json, load_runtime_config
from drift_with_me.world import load_world_data

ROOT = Path(__file__).resolve().parents[1]


def test_project_metadata_is_present() -> None:
    assert __version__ == "0.1.0"
    assert APP_TITLE == "DriftWithMe"


def test_medium_profile_matches_spec_default() -> None:
    config = load_runtime_config()

    assert config.profile.name == "medium"
    assert config.screen_width == 512
    assert config.screen_height == 236
    assert config.fixed_hz == 60


def test_bundled_json_matches_prototype_spec_data() -> None:
    for name in ("game_config.json", "prototype_world.json", "audio_events.json"):
        docs_data = json.loads(
            (ROOT / "docs" / "prototype_spec" / "data" / name).read_text(encoding="utf-8")
        )
        assert load_data_json(name) == docs_data


def test_world_data_uses_square_map_and_expected_counts() -> None:
    world = load_world_data()

    assert world.width == 1024
    assert world.depth == 1024
    assert len(world.objects) == 18
    assert len(world.solid_objects) == 8
    assert len(world.enemies) == 3
    assert set(world.camera_zones) == {"overview_north"}
    assert set(world.camera_sequences) == {"pan_demo"}


def test_audio_event_set_is_the_required_five_events() -> None:
    audio = AudioEngine(load_runtime_config().raw)

    assert set(audio.preview_events) == {
        "bubble_fired",
        "enemy_captured",
        "barrier_repelled",
        "discharge_succeeded",
        "action_denied",
    }
