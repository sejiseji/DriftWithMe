from __future__ import annotations

import json
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
