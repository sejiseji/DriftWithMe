from dataclasses import replace
from types import SimpleNamespace

import pytest

from drift_with_me.cloud_shadow import (
    CloudShadowLayer,
    cloud_center,
    ground_row_bounds,
    shade_rgb,
)
from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import (
    AffineCameraState,
    AffineProjectionProfile,
    CameraState,
    Vec3,
    screen_to_ground_affine,
)
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.world import load_world_data


class Image:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.copies = []

    def blt(self, *args):
        self.copies.append(args)


def setup():
    config = load_runtime_config().raw
    model = GameModel(config, load_world_data())
    camera = AffineCameraState(
        Vec3(520, 0, 520), AffineProjectionProfile.from_config(config), 1, 0.5, 0.55, 512, 236
    )
    model.world_tick = 145 * 60
    calls, mappings = [], []
    pyxel = SimpleNamespace(
        colors=[0x909090 + i for i in range(16)],
        screen=object(),
        Image=Image,
        blt=lambda *args: calls.append(args),
        pal=lambda *args: mappings.append(args),
    )
    return model, camera, pyxel, calls, mappings


def test_long_clear_intervals_and_passes_enter_and_exit_outside_ground():
    model, _, _, _, _ = setup()
    config = model.config["cloud_shadow"]
    bounds = model.world.visual_ground_rect
    assert cloud_center(0, config, bounds) is None
    assert cloud_center(69.99, config, bounds) is None
    assert cloud_center(70, config, bounds)[0] < bounds.min_x
    assert cloud_center(213.99, config, bounds)[0] > bounds.max_x
    assert cloud_center(214, config, bounds) is None
    assert cloud_center(419.99, config, bounds) is None
    assert cloud_center(490, config, bounds)[1] != cloud_center(70, config, bounds)[1]


@pytest.mark.parametrize("seconds", [-1, float("nan"), float("inf")])
def test_invalid_clock_does_not_draw(seconds):
    model, _, _, _, _ = setup()
    assert (
        cloud_center(seconds, model.config["cloud_shadow"], model.world.visual_ground_rect) is None
    )


def test_cached_shape_does_not_follow_camera_and_visible_blits_stay_inside_ground():
    model, camera, pyxel, calls, _ = setup()
    layer = CloudShadowLayer()
    layer.draw(pyxel, model, camera)
    assert 0 < layer.last_stats["pixels"] < camera.viewport_width * camera.viewport_height
    assert all(0 <= x < x + w <= 512 and 0 <= y < 236 for x, y, _, _, _, w, _ in calls)
    runs = layer._runs
    for y in range(-200, 201):
        spans = sorted((x, x + w) for group in runs for yy, x, w in group if yy == y)
        assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False))
    calls.clear()
    layer.draw(pyxel, model, replace(camera, target=Vec3(540, 0, 520)))
    assert layer.mask_builds == 1 and layer._runs is runs
    for zoom in (0.8, 0.9, 1.05, 1.2):
        layer.draw(pyxel, model, replace(camera, zoom=zoom))
        assert layer.mask_builds == 1 and layer._runs is runs
    calls.clear()
    layer.draw(pyxel, model, replace(camera, target=Vec3(-5000, 0, -5000)))
    assert not calls


def test_ground_clip_handles_near_plane_and_world_boundary():
    model, camera, _, _, _ = setup()
    bounds = model.world.visual_ground_rect
    for target in (Vec3(520, 0, 520), Vec3(-250, 0, -250), Vec3(1280, 0, 1280)):
        moved = replace(camera, target=target)
        rows = ground_row_bounds(moved, bounds)
        assert any(a < b for a, b in rows)
        for y, (a, b) in enumerate(rows):
            if a < b:
                for x in (a, b - 1):
                    p = screen_to_ground_affine(moved, x, y)
                    assert bounds.min_x - 1e-6 <= p.x <= bounds.max_x + 1e-6
                    assert bounds.min_z - 1e-6 <= p.y <= bounds.max_z + 1e-6


@pytest.mark.parametrize("gate", ["night", "disabled", "combat", "perspective"])
def test_out_of_scope_layers_do_not_touch_palette_or_buffer(gate):
    model, camera, pyxel, calls, mappings = setup()
    colors = list(pyxel.colors)
    if gate == "night":
        model.config["simulation"]["day_phase"] = "night"
    elif gate == "disabled":
        model.config["cloud_shadow"]["enabled"] = False
    elif gate == "combat":
        model.combat_session = object()
    else:
        camera = object()
    layer = CloudShadowLayer()
    layer.draw(pyxel, model, camera)
    assert not calls and not mappings and pyxel.colors == colors
    assert layer.mask_builds == 0


def test_palette_is_only_darker_and_restored_even_if_blit_fails():
    model, camera, pyxel, _, mappings = setup()
    original = tuple(pyxel.colors)
    layer = CloudShadowLayer()
    layer.draw(pyxel, model, camera)
    assert tuple(pyxel.colors[:16]) == original
    assert mappings[-1] == ()
    for rgb in original:
        shaded = shade_rgb(rgb, 0.14)
        assert all((shaded >> shift) & 255 <= (rgb >> shift) & 255 for shift in (0, 8, 16))

    def fail(*args):
        raise RuntimeError("diagnostic blit failure")

    pyxel.blt = fail
    with pytest.raises(RuntimeError):
        layer.draw(pyxel, model, camera)
    assert mappings[-1] == ()


def test_pause_and_reentry_keep_the_same_shadow_without_draw_driven_time():
    model, camera, pyxel, calls, _ = setup()
    layer = CloudShadowLayer()
    layer.draw(pyxel, model, camera)
    first = list(calls)
    tick = model.world_tick
    model.interaction = object()
    for _ in range(20):
        model.step(
            InputIntent(), CameraState.from_config(model.config, camera.target, 512, 236), 1 / 60
        )
    assert model.world_tick == tick
    calls.clear()
    layer.draw(pyxel, model, camera)
    assert calls == first
    model.interaction = None
    model.step(
        InputIntent(), CameraState.from_config(model.config, camera.target, 512, 236), 1 / 60
    )
    assert model.world_tick == tick + 1
