from __future__ import annotations

from drift_with_me import __version__, config


def test_project_metadata_is_present() -> None:
    assert __version__ == "0.1.0"
    assert config.WINDOW_TITLE == "DriftWithMe"


def test_screen_size_is_small_enough_for_pyxel_prototyping() -> None:
    assert config.SCREEN_WIDTH == 256
    assert config.SCREEN_HEIGHT == 192
