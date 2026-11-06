"""Presentation presets, not demographic claims about the characters."""

from __future__ import annotations

import unicodedata
from functools import lru_cache

from drift_with_me.config import load_data_json
from drift_with_me.office import supervisor_speaker_name

# Six short native Pyxel sounds. Slots 0-15 belong to SE, 32+ to BGM.
VOICE_SHAPES = {
    "male_child": ("g3a3", "tt", "21", "nf", 2),
    "male_adult": ("c3d3", "pp", "21", "nf", 2),
    "male_elder": ("g2f2", "pp", "21", "vf", 3),
    "female_child": ("e4g4", "tt", "21", "nf", 2),
    "female_adult": ("a3b3", "tt", "21", "nf", 2),
    "female_elder": ("e3d3", "tt", "21", "vf", 3),
}
VOICE_SLOTS = {key: 16 + index for index, key in enumerate(VOICE_SHAPES)}
VOICE_GAIN = 0.5  # Half the approved preview amplitude; preserve each native sound shape.
VOICE_INTERVAL_SEC = 1 / 15  # Four frames at 60 Hz; two at 30 Hz.


@lru_cache(maxsize=1)
def voice_metadata() -> dict:
    return load_data_json("dialogue_voices.json")


def voice_for_speaker(speaker: str) -> str | None:
    metadata = voice_metadata()
    speaker = supervisor_speaker_name(speaker)
    speaker = metadata["aliases"].get(speaker, speaker)
    if speaker in metadata.get("silent_speakers", ()):
        return None
    selection = metadata["speakers"].get(speaker, metadata["default"])
    preset = selection["preset"]
    return preset if preset in VOICE_SHAPES else "male_adult"


def audible_character(char: str) -> bool:
    # Includes Japanese punctuation, brackets, combining/control marks and emoji.
    return unicodedata.category(char)[0] in {"L", "N"}


def revealed_voice(page, start: int, end: int) -> str | None:
    """Pick only the latest naturally revealed letter; never enqueue characters."""
    offset = sum(len(line.text) for line in page)
    for line in reversed(page):
        offset -= len(line.text)
        lo, hi = max(0, start - offset), min(len(line.text), end - offset)
        if hi > lo and any(audible_character(c) for c in line.text[lo:hi]):
            return getattr(line, "voice_preset", None) or voice_for_speaker(line.speaker)
    return None
