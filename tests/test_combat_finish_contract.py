"""Public counter flow keeps charging, escape and final enemy results separate."""

import pytest

from drift_with_me.july_combat import configure_july_enemies
from drift_with_me.model import InputIntent
from test_combat_resources import make_model


@pytest.mark.parametrize(
    "july,energy,water,outcome",
    [
        (False, 0.0, 100.0, "capture"),
        (False, 60.0, 0.0, "deflect"),
        (False, 60.0, 100.0, "defeat"),
        (True, 0.0, 100.0, "defeat"),
        (True, 60.0, 100.0, "defeat"),
        (True, 60.0, 0.0, "deflect"),
    ],
)
def test_repeated_counter_inputs_and_restore_do_not_recharge_or_invent_defeat(
    july, energy, water, outcome
):
    model, camera = make_model()
    if july:
        configure_july_enemies(model)
    enemy = next(e for e in model.enemies if e.kind == "abnormal")
    model.config["combat_v1"]["enabled"] = True
    events = []
    model.start_contact_combat(enemy, events)
    session = model.combat_session
    session.phase = "PERFECT_BUBBLE_WINDOW"
    model._july_combat_camera = camera
    model.energy, model.water = energy, water
    bubble_cost = model.combat_bubble_water_cost()
    zap_cost = model.combat_zap_energy_cost()

    model.try_combat_counter_bubble(session, events)
    model.try_combat_counter_bubble(session, events)
    selected_energy, selected_water = model.energy, model.water
    for _ in range(30):
        model.combat_counter_action_mode()
    assert (model.energy, model.water) == (selected_energy, selected_water)
    model.try_combat_counter_zap(session, events)
    model.try_combat_counter_zap(session, events)
    for _ in range(1800):
        # Held/repeated requests through the actual phase machine remain harmless.
        events.extend(model.step(InputIntent(action_pressed=True), camera, 1 / 60))
        if model.combat_session is None:
            break
    assert model.combat_session is None
    assert session.outcome == outcome
    assert enemy.state == {"capture": "CAPTURED", "deflect": "REST", "defeat": "DEFEATED"}[outcome]
    assert model.water == pytest.approx(water - bubble_cost if water else water)
    assert model.energy == pytest.approx(
        energy - zap_cost if outcome == "defeat" and not july else energy
    )
    assert sum(e.kind == "bubble_fired" for e in events) == int(water > 0)
    assert sum(e.kind == "discharge_succeeded" for e in events) == int(
        outcome == "defeat" and not july
    )
    restored = [e for e in events if e.kind == "combat_restored"]
    assert len(restored) == 1 and restored[0].payload["combat_outcome"] == outcome
