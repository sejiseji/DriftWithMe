from __future__ import annotations

import pytest

from drift_with_me.swarm_battle import (
    ASSIST,
    CAPTURE_SHORT,
    ENERGY_SHORT,
    KINDS,
    MIXED_SHORT,
    PRESETS,
    RETREAT,
    STARTS,
    SwarmBattle,
)


def ready(b):
    while b.phase in {"entry", "ready"}:
        b.tick(b.settings.entry if b.phase == "entry" else b.settings.ready)


def hit(b):
    ready(b)
    b.tick(max(0, b.settings.sweep * b.settings.target - b.elapsed))
    b.input()


def finish_window(b):
    hit(b)
    assert b.phase == "bound"
    b.tick(b.settings.bound_hold)
    assert b.phase == "finish_wait"


def settle(b):
    for _ in range(1600):
        if b.phase in {"field", "victory"}:
            return
        b.tick(1 / 60)
    pytest.fail(f"did not settle: {b.phase}")


def retry(b):
    b.tick(b.settings.shock)
    assert b.phase == "assist" and b.message == ASSIST
    b.tick(b.settings.assist)
    ready(b)


def test_six_mixed_actors_share_progress():
    b = SwarmBattle()
    assert KINDS.count("urchin") == KINDS.count("slug") == 3
    assert [b.enemy_position(i) for i in range(6)] == list(STARTS)
    ready(b)
    b.tick(0.5)
    for i, (x, y) in enumerate(STARTS):
        assert b.enemy_position(i) == pytest.approx(
            (x + (320 - x) * b.progress * 0.78, y + (174 - y) * b.progress * 0.78)
        )


def test_success_waits_then_automatically_finishes_once_without_input():
    b = SwarmBattle()
    finish_window(b)
    assert (b.water, b.energy) == (88, 100)
    b.tick(b.settings.finish_wait)
    assert b.phase == "electric" and (b.water, b.energy) == (76, 80)
    for _ in range(20):
        b.input()
    b.tick(b.settings.electric)
    assert b.defeated == {i for i, kind in enumerate(KINDS) if kind == "urchin"}
    settle(b)
    assert b.phase == "victory" and len(b.defeated) == 6
    assert b.events[-5:] == ["electric", "circle", "converge", "spear", "victory"]
    assert (b.water, b.energy) == (76, 80)


def test_wait_button_is_not_a_timing_judgement_and_cannot_skip_cutin():
    b = SwarmBattle()
    finish_window(b)
    for _ in range(100):
        b.input()
    b.tick(b.settings.cutin / 2)
    assert b.phase == "finish_wait" and b.failures == 0 and b.assists == 1
    b.tick(b.settings.cutin / 2)
    assert b.phase == "electric" and (b.water, b.energy) == (76, 80)
    settle(b)
    assert b.phase == "victory" and b.failures == 0


def test_capture_failure_assist_success():
    b = SwarmBattle()
    ready(b)
    b.input()
    assert b.phase == "shake" and (b.water, b.energy) == (100, 100)
    retry(b)
    assert b.phase == "approach" and b.assists == 0
    assert [b.enemy_position(i) for i in range(6)] == list(STARTS)
    finish_window(b)
    settle(b)
    assert b.phase == "victory" and (b.water, b.energy) == (76, 80)


def test_second_capture_failure_retreat_and_rematch():
    b = SwarmBattle()
    ready(b)
    b.input()
    retry(b)
    b.input()
    b.tick(b.settings.shock)
    assert b.message == RETREAT
    settle(b)
    assert b.phase == "field" and b.position == (160, 160)
    assert (b.water, b.energy) == (100, 100)
    b.rematch()
    assert b.assists == 1 and not b.captured and b.phase == "entry"


@pytest.mark.parametrize(
    ("preset", "message", "remaining"),
    [
        ("capture-water", CAPTURE_SHORT, (0, 100)),
        ("finish-water", MIXED_SHORT, (0, 100)),
        ("energy", ENERGY_SHORT, (88, 0)),
        ("both", ENERGY_SHORT, (0, 0)),
    ],
)
def test_resource_denial_before_any_defeat(preset, message, remaining):
    b = SwarmBattle(*PRESETS[preset])
    hit(b)
    if preset != "capture-water":
        b.tick(b.settings.bound_hold)
        b.tick(b.settings.finish_wait)
    assert b.message == message and b.phase == "retreat_line"
    assert not b.defeated and (b.water, b.energy) == remaining
    settle(b)
    assert b.phase == "field" and (b.water, b.energy) == remaining


def test_capture_timeout_is_failure_but_finisher_wait_timeout_is_success():
    b = SwarmBattle()
    ready(b)
    b.tick(b.settings.sweep)
    assert b.phase == "shake"
    retry(b)
    finish_window(b)
    settle(b)
    assert b.phase == "victory"


def test_exact_resources():
    b = SwarmBattle(24, 20)
    finish_window(b)
    settle(b)
    assert b.phase == "victory" and (b.water, b.energy) == (0, 0)


def test_preview_font_covers_every_japanese_dialogue_and_label():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src/drift_with_me"
    text = (root / "swarm_battle.py").read_text() + (root / "swarm_view.py").read_text()
    font = (root / "assets/fonts/umplus_j12r_swarm.bdf").read_text()
    glyphs = {int(line.split()[1]) for line in font.splitlines() if line.startswith("ENCODING ")}
    assert {ord(c) for c in text if ord(c) >= 32} <= glyphs
