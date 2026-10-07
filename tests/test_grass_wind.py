from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from drift_with_me.config import load_runtime_config
from drift_with_me.grass_wind import SHADES, draw_grass_wind, overlaps, wind_value
from drift_with_me.math3d import AffineCameraState, AffineProjectionProfile, CameraState, Vec3
from drift_with_me.model import GameModel
from drift_with_me.render import Renderer
from drift_with_me.world import load_world_data


def setup_wind():
    config = load_runtime_config().raw
    config["grass_wind"]["enabled"] = True
    model = GameModel(config, load_world_data())
    camera = AffineCameraState(
        Vec3(450, 0, 500), AffineProjectionProfile.from_config(config), 1, 0.5, 0.55, 512, 236
    )
    pyxel = SimpleNamespace(colors=list(range(16)))
    renderer = Renderer(pyxel)
    drawn = []
    renderer.draw_ground_rect = lambda camera, rect, color: drawn.append((rect, color))
    return model, camera, renderer, drawn


def test_offscreen_reentry_is_stateless_and_camera_independent():
    model, camera, renderer, drawn = setup_wind()
    first = draw_grass_wind(renderer, model, camera, 7.5)
    snapshot = list(drawn)
    drawn.clear()
    assert draw_grass_wind(renderer, model, replace(camera, target=Vec3(-5000, 0, -5000)), 7.5) == (
        0,
        0,
    )
    assert not drawn
    assert draw_grass_wind(renderer, model, camera, 7.5) == first
    assert drawn == snapshot
    assert wind_value(450, 500, 7.5) != wind_value(450, 500, 8.5)


def test_visible_only_palette_and_region_boundaries():
    model, camera, renderer, drawn = setup_wind()
    tested, patches = draw_grass_wind(renderer, model, camera, 2)
    assert 0 < patches < tested < 3000
    assert renderer.pyxel.colors[:16] == list(range(16))
    assert renderer.pyxel.colors[16:] == list(SHADES)
    for rect, color in drawn:
        assert 288 <= rect[0] < rect[2] <= 736
        assert 336 <= rect[1] < rect[3] <= 704
        assert color in {16, 17, 18, 19}
        assert not any(
            overlaps(rect, (a.min_x, a.min_z, a.max_x, a.max_z))
            for a in model.world.shallow_water_areas
        )


def test_toggle_perspective_and_combat_do_no_work():
    model, camera, renderer, drawn = setup_wind()
    model.config["grass_wind"]["enabled"] = False
    assert draw_grass_wind(renderer, model, camera, 1) == (0, 0)
    model.config["grass_wind"]["enabled"] = True
    perspective = CameraState.from_config(model.config, camera.target, 512, 236)
    assert draw_grass_wind(renderer, model, perspective, 1) == (0, 0)
    model.combat_session = SimpleNamespace()
    assert draw_grass_wind(renderer, model, camera, 1) == (0, 0)
    assert not drawn and len(renderer.pyxel.colors) == 16


def test_water_exclusion_and_foreign_palette_are_preserved():
    model, camera, renderer, drawn = setup_wind()
    model.config["grass_wind"]["rect_xz"] = [80, 80, 320, 330]
    camera = replace(camera, target=Vec3(220, 0, 210))
    draw_grass_wind(renderer, model, camera, 4)
    for rect, _ in drawn:
        assert not overlaps(rect, (96, 96, 288, 288))
    drawn.clear()
    renderer.pyxel.colors = list(range(24))
    assert draw_grass_wind(renderer, model, camera, 4) == (0, 0)
    assert not drawn
