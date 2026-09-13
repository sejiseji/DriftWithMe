from __future__ import annotations

import pytest

from drift_with_me.app import DriftWithMeApp
from drift_with_me.config import load_runtime_config
from drift_with_me.effects import EffectSystem
from drift_with_me.events import GameEvent
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.world import load_world_data


def make_hitstop_app(enabled: bool = True) -> DriftWithMeApp:
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config("medium")
    app.runtime.raw["effects"]["hitstop_enabled"] = enabled
    app.world = load_world_data()
    app.model = GameModel(app.runtime.raw, app.world)
    app.effects = EffectSystem(app.runtime.raw)
    app.accumulator = 0.5
    app.hitstop_remaining = 0.0
    app._processed_hitstop_event_ids = set()
    return app


def event(app: DriftWithMeApp, kind: str) -> GameEvent:
    return app.model.event_queue.emit(
        world_tick=app.model.world_tick,
        kind=kind,
        actor_id="test",
        target_id=None,
        world_position=(app.model.player.x, 0.0, app.model.player.z),
    )


def test_hitstop_default_off_ignores_combat_events() -> None:
    app = make_hitstop_app(enabled=False)

    app.request_hitstop_from_events([event(app, "discharge_succeeded")])

    assert app.hitstop_remaining == 0.0
    assert app.accumulator == 0.5
    assert app._processed_hitstop_event_ids == set()


def test_hitstop_uses_max_duration_cap_and_event_deduplication() -> None:
    app = make_hitstop_app(enabled=True)
    app.runtime.raw["effects"]["hitstop_hard_cap_ms"] = 40.0
    repel = event(app, "barrier_repelled")
    zap = event(app, "discharge_succeeded")

    app.request_hitstop_from_events([repel, zap])

    assert app.hitstop_remaining == pytest.approx(0.04)
    assert app.accumulator == 0.0

    app.hitstop_remaining = 0.01
    app.accumulator = 0.5
    app.request_hitstop_from_events([zap])

    assert app.hitstop_remaining == pytest.approx(0.01)
    assert app.accumulator == 0.5


def test_hitstop_freezes_model_clock_but_advances_fx() -> None:
    app = make_hitstop_app(enabled=True)
    app.hitstop_remaining = 0.05
    app.accumulator = 0.25
    app.model.player.barrier_active = True
    app.effects.spawn_burst(
        app.model.player.x,
        0.0,
        app.model.player.z,
        color=12,
        count=1,
        speed=0.0,
    )
    before_tick = app.model.world_tick

    consumed = app.update_hitstop(1.0 / 60.0, InputIntent(barrier=False))

    assert consumed
    assert app.model.world_tick == before_tick
    assert app.model.debug.fixed_steps_last_callback == 0
    assert app.accumulator == 0.0
    assert app.hitstop_remaining == pytest.approx(0.05 - 1.0 / 60.0)
    assert app.effects.particles[0].age == pytest.approx(1.0 / 60.0)
    assert not app.model.player.barrier_active
