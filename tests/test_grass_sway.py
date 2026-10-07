from types import SimpleNamespace

import pytest

from drift_with_me.grass_sway import (
    GUST_PERIOD_SECONDS,
    bend_angle,
    gust_tables,
    lift_weak_gain,
    rotate_tip,
    sample_gust,
)
from drift_with_me.render import Renderer


@pytest.mark.parametrize("shape", range(4))
def test_sway_keeps_roots_colors_and_stroke_count(shape):
    records = []
    renderer = Renderer(
        SimpleNamespace(
            line=lambda *args: records.append(("line", args)),
            pset=lambda *args: records.append(("pset", args)),
        )
    )
    renderer.draw_micro_grass_blade(20, 30, 6, 11, 3, 1, shape)
    before = list(records)
    records.clear()
    renderer.draw_micro_grass_blade(20, 30, 6, 11, 3, 1, shape, 0.6)
    assert len(records) == len(before)
    assert records != before
    for (kind, old), (new_kind, new) in zip(before, records, strict=True):
        assert kind == new_kind and old[-1] == new[-1]
        if kind == "line":
            assert old[:2] == new[:2]


def test_gust_returns_to_rest_and_reentry_uses_common_time():
    config = {
        "enabled": True,
        "rect_xz": [288, 336, 736, 704],
        "strength": 0.7,
        "gust_enabled": False,
    }
    values = [bend_angle(450, 500, i / 30, 0.5, config) for i in range(240)]
    assert min(values) == 0 and max(values) > 0.4
    expected = bend_angle(450, 500, 9, 0.5, config)
    assert bend_angle(900, 500, 9, 0.5, config) == 0
    assert bend_angle(450, 500, 9, 0.5, config) == expected
    assert rotate_tip(20, 30, 21, 24, 0) == (21, 24)
    config["enabled"] = False
    assert bend_angle(450, 500, 9, 0.5, config) == 0


def test_seeded_tables_are_reproducible_and_cache_is_bounded():
    gust_tables.cache_clear()
    expected = gust_tables(17)
    assert gust_tables(17) is expected
    assert gust_tables(18) != expected
    for seed in range(12):
        gust_tables(seed)
    assert gust_tables.cache_info().currsize == 4
    assert gust_tables(17) == expected
    assert all(len(table) == 256 for table in expected)


def test_lookup_is_smooth_at_loop_and_sample_boundaries():
    epsilon = 1e-4
    for t in (0.0, 0.5, 4.0, GUST_PERIOD_SECONDS):
        left = sample_gust(t - epsilon)
        center = sample_gust(t)
        right = sample_gust(t + epsilon)
        for a, b, c in zip(left, center, right, strict=True):
            assert abs(c - a) < 1e-4
            assert abs((b - a) / epsilon - (c - b) / epsilon) < 1e-3
    assert sample_gust(0) == sample_gust(GUST_PERIOD_SECONDS)


def test_shared_time_handles_skipped_frames_and_breaks_short_repeat():
    cfg = {"enabled": True, "rect_xz": [288, 336, 736, 704], "strength": 0.7}
    final = bend_angle(450, 500, 15.0, 0.5, cfg)
    for t in (0.0, 1 / 60, 0.3, 9.0):
        bend_angle(450, 500, t, 0.5, cfg)
    assert bend_angle(450, 500, 15.0, 0.5, cfg) == final
    assert bend_angle(900, 500, 14.0, 0.5, cfg) == 0
    assert bend_angle(450, 500, 15.0, 0.5, cfg) == final
    old_period = 210 / 38
    values = [bend_angle(450, 500, i / 30, 0.5, cfg) for i in range(300)]
    next_values = [bend_angle(450, 500, i / 30 + old_period, 0.5, cfg) for i in range(300)]
    assert max(abs(a - b) for a, b in zip(values, next_values, strict=True)) > 0.05
    gains = [sample_gust(i / 30)[0] for i in range(1920)]
    assert max(gains) - min(gains) > 0.35
    assert max(abs(a - b) for a, b in zip(gains, gains[1:], strict=False)) < 0.02


def test_weak_gain_lift_keeps_strong_maximum_and_smooth_join():
    assert lift_weak_gain(0.55) == pytest.approx(0.65)
    assert lift_weak_gain(0.60) > 0.60
    for gain in (0.85, 0.90, 1.0, 1.15):
        assert lift_weak_gain(gain) == gain
    gains = [sample_gust(i / 30)[0] for i in range(3840)]
    from drift_with_me.grass_sway import _periodic_sample

    table = gust_tables(20261007)[0]
    old = [_periodic_sample(table, (i / 30 % 128) * 256 / 128) for i in range(3840)]
    assert max(gains) == max(old)
    assert min(gains) > min(old) + 0.09
    epsilon = 1e-5
    left, center, right = (lift_weak_gain(0.85 + offset) for offset in (-epsilon, 0, epsilon))
    assert (center - left) / epsilon == pytest.approx((right - center) / epsilon, abs=1e-3)
