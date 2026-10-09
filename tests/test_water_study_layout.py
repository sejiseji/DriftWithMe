from dataclasses import replace

import pytest

from drift_with_me.app import AppScreen, PointerSnapshot
from drift_with_me.config import load_runtime_config
from drift_with_me.water_study_assets import WaterStudyChunk, WaterStudyPlane
from drift_with_me.water_study_layout import water_study_visible_chunks
from test_wtr001_water_study import FakeDrawPyxel, make_water_app


@pytest.mark.parametrize(
    "profile,indices", [("low", [0, 1]), ("medium", [0, 1]), ("high", [0, 1, 2, 4, 5, 6])]
)
def test_phase_images_redraw_without_repeating_layout_and_clip_does_not_leak(profile, indices):
    app = make_water_app()
    app.runtime = load_runtime_config(profile)
    app.pyxel = FakeDrawPyxel()
    chunks = tuple(
        WaterStudyChunk(object(), x * 256, y * 256, 256, 256) for y in range(2) for x in range(4)
    )
    first = WaterStudyPlane("water_surface_plane_e", 1024, 512, 256, 256, 8, chunks)
    second = replace(first, chunks=tuple(replace(c, image=object()) for c in chunks), colkey=None)
    app.water_study_plane_for_frame = lambda layer, t: first if t == 0 else second
    water_study_visible_chunks.cache_clear()
    assert app.draw_water_study_plane(first.layer_id, 0) == len(indices)
    initial = water_study_visible_chunks.cache_info()
    app.pyxel.blt_calls.clear()
    assert app.draw_water_study_plane(first.layer_id, 1) == len(indices)
    assert [args[2] for args, _ in app.pyxel.blt_calls] == [second.chunks[i].image for i in indices]
    assert water_study_visible_chunks.cache_info().misses == initial.misses
    assert water_study_visible_chunks.cache_info().hits == initial.hits + 1
    app.pyxel.blt_calls.clear()
    assert app.draw_water_study_plane(first.layer_id, 1, (100, 90, 32, 8)) == 1
    assert app.pyxel.blt_calls[0][0][2] is second.chunks[0].image
    assert app.draw_water_study_plane(first.layer_id, 1) == len(indices)


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({}, ((0, 0, 0),)),
        ({"screen_width": 512}, ((0, 0, 0), (256, 0, 0))),
        ({"screen_height": 300}, ((0, 0, 0), (0, 256, 0))),
        ({"start_x": -1}, ((-1, 0, 0), (255, 0, 0))),
        ({"cull_rect": (256, 0, 8, 8)}, ()),
        ({"cull_rect": (-10, -10, 20, 20)}, ((0, 0, 0),)),
        ({"geometry": ((256, 0, 256, 256),)}, ((0, 0, 0),)),
        ({"geometry": ((0, 0, 128, 256),)}, ((0, 0, 0),)),
        ({"geometry": ((0, 0, 256, 256), (1, 1, 10, 10))}, ((0, 0, 0), (1, 1, 1))),
        ({"logical_width": 128, "start_x": -128}, ((-128, 0, 0), (0, 0, 0), (128, 0, 0))),
    ],
)
def test_layout_keys_refresh_for_viewport_motion_geometry_and_clipping(changes, expected):
    params = dict(
        screen_width=256,
        screen_height=256,
        logical_width=256,
        logical_height=256,
        start_x=-256,
        start_y=-256,
        geometry=((0, 0, 256, 256),),
        cull_rect=None,
    )
    params.update(changes)
    assert water_study_visible_chunks(**params) == expected


def test_moving_mask_layout_cache_is_bounded():
    water_study_visible_chunks.cache_clear()
    for x in range(200):
        water_study_visible_chunks(
            512, 236, 1024, 512, -1024, -512, ((0, 0, 256, 256),), (x, 10, 32, 8)
        )
    assert water_study_visible_chunks.cache_info().currsize == 128


def test_reentry_profile_resize_and_close_keep_world_but_use_current_frame():
    app = make_water_app()
    app.pyxel = FakeDrawPyxel()
    chunks = tuple(
        WaterStudyChunk(object(), x * 256, y * 256, 256, 256) for y in range(2) for x in range(4)
    )
    current = WaterStudyPlane("water_surface_plane_e", 1024, 512, 256, 256, 8, chunks)
    app.water_study_plane_for_frame = lambda *_: current
    before = (
        app.model.player.x,
        app.model.player.z,
        app.model.water,
        app.model.energy,
        app.camera_controller.current,
        app.model.world_tick,
    )
    for profile, count in (("low", 2), ("high", 6), ("medium", 2)):
        app.runtime = load_runtime_config(profile)
        assert app.enter_water_study()
        assert app.water_study_clock == 0
        app.water_study_profile_index += 1
        app.update_water_study_screen(1 / 60)
        current = replace(current, chunks=tuple(replace(c, image=object()) for c in chunks))
        app.pyxel.blt_calls.clear()
        assert app.draw_water_study_plane(current.layer_id, app.water_study_clock) == count
        assert app.pyxel.blt_calls[0][0][2] is current.chunks[0].image
        close = app.water_study_close_rect()
        app.pointer_snapshot = PointerSnapshot(True, True, close.x + 2, close.y + 2)
        app.update_water_study_screen(1 / 60)
        assert app.screen == AppScreen.PLAY
        app.pointer_snapshot = PointerSnapshot(False, False, 0, 0)
    assert (
        app.model.player.x,
        app.model.player.z,
        app.model.water,
        app.model.energy,
        app.camera_controller.current,
        app.model.world_tick,
    ) == before
