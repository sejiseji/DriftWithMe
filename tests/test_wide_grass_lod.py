"""Experimental LOD preserves existing clump positions and gameplay state."""

from copy import deepcopy
from dataclasses import replace

from drift_with_me.model import GameModel
from drift_with_me.render import Renderer
from test_affine_projection import RecordingPyxel, make_affine_camera


def test_lod_keeps_subset_of_authored_clumps_and_close_view_is_identical():
    runtime, world, _perspective, _profile, affine = make_affine_camera()
    model = GameModel(runtime.raw, world)
    before = deepcopy(model.player)
    renderer = Renderer(RecordingPyxel())
    clumps = []
    renderer.draw_micro_grass_blade = lambda *args: clumps.append(args)
    for area in runtime.raw["grassland_micro"]["areas"]:
        area["max_visible_clumps"] = 100000

    def draw(zoom, enabled):
        clumps.clear()
        renderer.wide_grass_lod = enabled
        renderer.draw_grassland_micro_layer(model, replace(affine, zoom=zoom))
        return list(clumps)

    full = draw(0.65, False)
    sparse = draw(0.65, True)
    assert full and sparse
    assert len(sparse) < len(full) / 2
    assert set(sparse) <= set(full)
    assert draw(1.3, True) == draw(1.3, False)
    assert draw(0.65, True) == sparse
    assert model.player == before


def test_wide_lod_has_hysteresis_at_the_normal_field_zoom():
    runtime, world, _perspective, _profile, affine = make_affine_camera()
    model = GameModel(runtime.raw, world)
    renderer = Renderer(RecordingPyxel())
    renderer.wide_grass_lod = True
    for zoom, active in [(1.0, True), (1.24, True), (1.31, False), (1.24, False), (1.19, True)]:
        renderer.draw_grassland_micro_layer(model, replace(affine, zoom=zoom))
        assert renderer._wide_grass_lod_active is active


def test_lod_preserves_the_existing_shoreline_wind_cohort(monkeypatch):
    from drift_with_me import wind_life
    from drift_with_me.grass_sway import sample_gust
    from drift_with_me.math3d import Vec3

    runtime, world, _perspective, _profile, affine = make_affine_camera()
    model = GameModel(runtime.raw, world)
    renderer = Renderer(RecordingPyxel())
    renderer._wind_life_active = True
    renderer._wind_life_blocked = ()
    renderer._active_baked_ground_patches = ()
    renderer._grass_wind_model = model
    renderer._grass_wind_counts = (0, 0)
    renderer.wind_life_shore_drawn = 0
    renderer._grass_wind_time = 1.0
    renderer._grass_sway_config = runtime.raw["grass_sway"]
    renderer._grass_sway_gust = sample_gust(1.0)
    for area in runtime.raw["grassland_micro"]["areas"]:
        area["max_visible_clumps"] = 100000
    camera = replace(affine, target=Vec3(400, 0, 330), zoom=0.7)
    selected = []
    monkeypatch.setattr(
        wind_life, "shore_angle", lambda x, z, *args: selected.append((x, z)) or 0.0
    )
    renderer.wide_grass_lod = False
    renderer.draw_grassland_micro_layer(model, camera)
    full = set(selected)
    selected.clear()
    renderer.wide_grass_lod = True
    renderer.draw_grassland_micro_layer(model, camera)
    assert full and set(selected) == full
