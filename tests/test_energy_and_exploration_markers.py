from types import SimpleNamespace

import pytest

from drift_with_me.app import DriftWithMeApp
from drift_with_me.render import Renderer
from drift_with_me.save_state import decode, encode, snapshot
from test_july_story import july_app


@pytest.mark.parametrize("energy", [0, 8, 40, 60, 80, 100])
def test_v2_resources_resume_exact_quantity_under_new_cap(energy):
    app = july_app()
    app.model.water, app.model.energy = 37, energy
    resources = decode(encode(snapshot(app)))[4]
    assert resources == {"water": 37, "energy": energy}
    assert app.model.energy_max == app.model.water_max == 100


def test_new_start_refill_and_upper_save_bound():
    app = july_app()
    m = app.model
    assert m.energy == m.energy_max == 100
    m.water, m.energy = 37, 40
    target = app.world.object_by_id("solar_start")
    m.start_interaction([], "energy_refill", target, "CHARGE", (), 1.2)
    m.complete_interaction()
    assert (m.water, m.energy) == (37, 100)
    record = snapshot(app)
    record["resources"]["energy"] = 101
    with pytest.raises(ValueError):
        decode(encode(record))


@pytest.mark.parametrize(
    "method", ["draw_auto_move_goal", "draw_interaction_marker", "draw_action_marker"]
)
def test_exploration_marker_methods_hide_during_combat_and_resume(method):
    calls = []
    renderer = Renderer(
        SimpleNamespace(line=lambda *a: calls.append(a), circb=lambda *a: calls.append(a))
    )
    renderer.draw_world_circle = lambda *a: calls.append(a)
    target = SimpleNamespace(x=100, z=100, height=16, state="IDLE")
    model = SimpleNamespace(
        combat_session=None,
        auto_move_goal=(100, 100),
        interaction_candidate=lambda c: target,
        danger_blocks_interaction=lambda: False,
        captured_enemy=lambda c: None,
        bubble_target=lambda c: target,
    )
    camera = SimpleNamespace(project=lambda point: SimpleNamespace(x=40, y=40))
    args = (model, camera, 0) if method == "draw_auto_move_goal" else (model, camera)
    getattr(renderer, method)(*args)
    assert calls
    calls.clear()
    model.combat_session = object()
    getattr(renderer, method)(*args)
    assert not calls
    model.combat_session = None
    getattr(renderer, method)(*args)
    assert calls


@pytest.mark.parametrize(
    "combat,restoring,visible", [(False, False, True), (True, False, False), (False, True, False)]
)
def test_app_hides_exploration_markers_until_camera_restore_finishes(
    monkeypatch, combat, restoring, visible
):
    import drift_with_me.app as module

    app = DriftWithMeApp.__new__(DriftWithMeApp)
    seen = []
    app.renderer = SimpleNamespace(draw_scene=lambda *args, **kwargs: seen.append(kwargs))
    app.model = SimpleNamespace(combat_session=object() if combat else None, interaction=None)
    app.combat_camera_restore = object() if restoring else None
    app.camera = lambda: None
    app.scene_camera = lambda camera: camera
    app.presentation_time, app.debug_enabled, app.effects = 0, False, None
    monkeypatch.setattr(module, "draw_week3_key", lambda *args: None)
    for name in (
        "draw_july_markers",
        "draw_hud",
        "draw_map_objectives",
        "draw_combat_chance_cues",
        "draw_july_story",
    ):
        setattr(app, name, lambda: None)
    app.draw_play()
    assert seen[0]["exploration_markers"] == visible
