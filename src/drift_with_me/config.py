from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

APP_TITLE = "DriftWithMe"
DEFAULT_PROFILE = "medium"


@dataclass(frozen=True)
class DisplayProfile:
    name: str
    width: int
    height: int


@dataclass(frozen=True)
class RuntimeConfig:
    raw: dict[str, Any]
    profile: DisplayProfile

    @property
    def fixed_hz(self) -> int:
        return int(self.raw["simulation"]["fixed_hz"])

    @property
    def fixed_dt(self) -> float:
        return 1.0 / self.fixed_hz

    @property
    def target_fps(self) -> int:
        return int(self.raw["display"]["target_render_fps"])

    @property
    def desktop_scale(self) -> int:
        return int(self.raw["display"]["desktop_scale"])

    @property
    def screen_width(self) -> int:
        return self.profile.width

    @property
    def screen_height(self) -> int:
        return self.profile.height


def load_data_json(name: str) -> dict[str, Any]:
    path = resources.files("drift_with_me.data").joinpath(name)
    return json.loads(path.read_text(encoding="utf-8"))


def load_runtime_config(profile_name: str | None = None) -> RuntimeConfig:
    raw = load_data_json("game_config.json")
    selected = profile_name or raw["display"]["default_profile"]
    profiles = raw["display"]["profiles"]
    if selected not in profiles:
        known = ", ".join(sorted(profiles))
        raise ValueError(f"unknown display profile {selected!r}; expected one of {known}")
    width, height = profiles[selected]
    return RuntimeConfig(raw=raw, profile=DisplayProfile(selected, int(width), int(height)))
