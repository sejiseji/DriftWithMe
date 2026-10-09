from types import SimpleNamespace

import pytest

import drift_with_me.water_study_assets as assets
from drift_with_me.app import AppScreen
from test_wtr001_water_study import make_water_app


@pytest.fixture(autouse=True)
def reset_cache():
    assets.clear_water_study_cache_for_tests()
    yield
    assets.clear_water_study_cache_for_tests()


class CountingImage:
    calls = 0

    def __init__(self, width, height):
        self.width, self.height = width, height

    def set(self, x, y, rows):
        type(self).calls += 1


def test_complete_cache_publishes_once_after_exactly_960_chunks():
    CountingImage.calls = 0
    pyxel = SimpleNamespace(Image=CountingImage)
    loader = assets.water_study_cache_loader(pyxel)
    assert assets.water_study_cache_loader(pyxel) is loader
    for _ in range(961):
        assert loader.advance(0) is None
    assert CountingImage.calls == 960
    assert id(pyxel) not in assets._WATER_STUDY_CACHE_BY_PYXEL_ID
    assert loader.preview_cache is not None
    assert not loader.preview_cache.ready
    assert loader.preview_cache.resident_pixel_count == 2621440
    app = make_water_app()
    app.water_study_asset_cache = loader.preview_cache
    for layer, sequence in loader.preview_cache.frame_sequences.items():
        assert app.water_study_plane_for_frame(layer, 0) is sequence.planes[0]
    cache = loader.advance(0)
    assert cache.ready
    assert cache.resident_pixel_count == 62914560
    for layer, sequence in cache.frame_sequences.items():
        assert sequence.planes[0] is loader.preview_cache.frame_sequences[layer].planes[0]
    assert assets.preload_water_study_cache(pyxel) is cache
    assert loader.advance(0) is cache
    assert CountingImage.calls == 960


def test_sync_preload_finishes_existing_partial_job_without_duplicate_chunks():
    CountingImage.calls = 0
    pyxel = SimpleNamespace(Image=CountingImage)
    loader = assets.water_study_cache_loader(pyxel)
    loader.advance(0)
    cache = assets.preload_water_study_cache(pyxel)
    assert cache is loader.cache
    assert CountingImage.calls == 960


def test_early_entry_close_reentry_and_repeated_entry_preserve_one_job():
    app = make_water_app()
    app.pyxel.Image = CountingImage
    app.water_study_asset_cache = None
    world_tick = app.model.world_tick
    assert app.enter_water_study()
    loader = app.water_study_loader
    assert app.screen is AppScreen.WATER_STUDY
    assert not app.enter_water_study()
    assert app.water_study_loader is loader
    app.mouse_pressed_in = lambda _: True
    app.update_water_study_screen(1 / 60)
    assert app.screen is AppScreen.PLAY
    assert loader.work_sec == 0
    assert app.enter_water_study()
    assert app.water_study_loader is loader
    app.mouse_pressed_in = lambda _: False
    original_advance = loader.advance
    loader.advance = lambda _budget=0.002: original_advance(0)
    app.update_water_study_screen(1 / 60)
    assert app.water_study_asset_cache is None
    assert app.water_study_clock == 0
    assert app.model.world_tick == world_tick
    assert app.exit_water_study()
    assert app.enter_water_study()
    assert app.water_study_loader is loader


def test_background_prepare_finishes_then_entry_reuses_cache():
    app = make_water_app()
    app.pyxel.Image = CountingImage
    app.water_study_asset_cache = None
    for _ in range(2000):
        app.prepare_water_study_assets()
        if app.water_study_asset_cache is not None and app.water_study_asset_cache.ready:
            break
    cache = app.water_study_asset_cache
    assert cache.ready
    assert app.enter_water_study()
    assert app.water_study_asset_cache is cache
    assert app.exit_water_study()
    assert app.enter_water_study()
    assert app.water_study_asset_cache is cache


def test_load_failure_does_not_publish_or_retry_and_close_still_works(monkeypatch):
    app = make_water_app()
    app.water_study_asset_cache = None

    def failed_iterator(*args, **kwargs):
        yield None
        raise ValueError("broken source")

    monkeypatch.setattr(
        assets, "_iter_approved_look04_plus_sparkle_frame_sequences", failed_iterator
    )
    assert app.enter_water_study()
    app.mouse_pressed_in = lambda _: False
    app.update_water_study_screen(1 / 60)
    loader = app.water_study_loader
    assert isinstance(loader.error, ValueError)
    assert loader.advance() is None
    assert id(app.pyxel) not in assets._WATER_STUDY_CACHE_BY_PYXEL_ID
    app.mouse_pressed_in = lambda _: True
    app.update_water_study_screen(1 / 60)
    assert app.screen is AppScreen.PLAY


@pytest.mark.parametrize("fps,expected_budget", [(30, 0.014), (60, 0.8 / 60), (120, 0.8 / 120)])
def test_foreground_budget_is_bounded_and_close_stays_first(monkeypatch, fps, expected_budget):
    from dataclasses import replace

    import drift_with_me.app as app_module

    app = make_water_app()
    app.runtime = replace(
        app.runtime,
        raw={
            **app.runtime.raw,
            "display": {**app.runtime.raw["display"], "target_render_fps": fps},
        },
    )
    app.screen = AppScreen.WATER_STUDY
    app.water_study_asset_cache = None
    budgets = []

    def advance(budget=0.002):
        budgets.append(budget)
        return None

    loader = SimpleNamespace(advance=advance, preview_cache=None)
    app.water_study_loader = loader
    app.mouse_pressed_in = lambda _: False
    app.update_water_study_screen(1 / fps)
    assert budgets == [expected_budget]
    assert app.water_study_clock == 0
    app.mouse_pressed_in = lambda _: True
    app.update_water_study_screen(1 / fps)
    assert budgets == [expected_budget]
    monkeypatch.setattr(app_module, "water_study_cache_loader", lambda _: loader)
    app.prepare_water_study_assets()
    assert budgets == [expected_budget, 0.002]


def test_complete_sequence_begins_at_frame_zero_after_preparation():
    from test_wtr001_water_study import make_fake_water_cache

    app = make_water_app()
    app.screen = AppScreen.WATER_STUDY
    app.water_study_asset_cache = None
    cache = make_fake_water_cache()
    app.water_study_loader = SimpleNamespace(advance=lambda _: cache, preview_cache=None)
    app.mouse_pressed_in = lambda _: False
    app.update_water_study_screen(0.5)
    assert app.water_study_asset_cache is cache
    assert app.water_study_clock == 0
    app.update_water_study_screen(1 / 60)
    assert app.water_study_clock == pytest.approx(1 / 60)
