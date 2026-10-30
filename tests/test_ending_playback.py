"""Synthetic saves and palettes only; no user storage or graphical session."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.collectibles import BY_ID, owned_collectibles
from drift_with_me.collectibles import BY_ID as ITEMS
from drift_with_me.ending_playback import (
    EndingPlayback,
    apply_palette,
    restore_palette,
    runtime_data,
    runtime_image,
)
from drift_with_me.save_state import snapshot
from test_collectibles import week_app


def final_app(complete=False):
    app, storage = week_app(ITEMS["crayon_drawing"])
    app.office.august_progress.phase = "done"
    app.screen = AppScreen.OFFICE
    app.key_pressed = lambda *_: True
    app.mouse_pressed_in = lambda *_: True
    app.travel_input_held = lambda: True
    app.east_site_progress.collectibles = set(BY_ID) if complete else {"herb_fine", "stone_marble"}
    return app, storage


@pytest.mark.parametrize("complete", [False, True])
def test_credits_fade_room_freeze_save_and_replay(complete):
    app, storage = final_app(complete)
    before = snapshot(app)
    persistent = deepcopy(storage.items)
    assert app.begin_ending()
    first = app.ending_playback
    assert app.screen == AppScreen.CREDITS and not app.begin_ending()
    assert app.ending_playback is first and first.elapsed == 0
    assert first.owned == frozenset(owned_collectibles(app))
    for dt in (94, 3.8, 4, 4.5, 3.7):
        app.update_ending(dt)
        assert app.screen == AppScreen.CREDITS
        assert snapshot(app) == before and storage.items == persistent
    assert first.elapsed == 110
    app.update_ending(0.6)
    assert 0 < first.room_mix < 1 and app.screen == AppScreen.CREDITS
    assert not app.begin_ending()
    app.update_ending(0.71)
    assert app.screen == AppScreen.COLLECTION_ROOM and app.ending_playback is None
    for _ in range(3):
        app.update_collection_room()  # Held input across fade cannot close/restart.
        assert app.screen == AppScreen.COLLECTION_ROOM
    app.travel_input_held = lambda: False
    app.update_collection_room()
    app.key_pressed = lambda *_: False
    app.mouse_pressed_in = lambda *_: False
    for _ in range(300):
        app.update_collection_room()
    assert app.screen == AppScreen.COLLECTION_ROOM
    app.key_pressed = lambda *_: True
    app.update_collection_room()
    assert app.screen == AppScreen.OFFICE
    assert app.begin_ending() and app.ending_playback.elapsed == 0
    assert snapshot(app) == before and storage.items == persistent


def test_entry_gated_by_final_report_and_input_never_advances_clock():
    app, _ = final_app()
    app.office.august_progress.phase = "report"
    assert not app.begin_ending()
    s = EndingPlayback(frozenset())
    for dt in (0, -2, float("inf"), float("nan")):
        s.advance(dt)
    assert s.elapsed == 0 and not s.complete
    s.advance(111.3)
    assert s.complete and s.room_mix == 1


class Colors:
    def __init__(self, colors):
        self.values = list(colors)

    def to_list(self):
        return list(self.values)

    def from_list(self, colors):
        self.values = list(colors)


def test_palette_interpolation_and_exact_restore():
    base = [0, 0x2B335F, 0xEEEEEE]
    app = SimpleNamespace(pyxel=SimpleNamespace(colors=Colors(base), pal=lambda *a: None))
    apply_palette(app, base, 1)
    assert app.pyxel.colors.values[:3] == [0xFFFFFF] * 3
    assert app.pyxel.colors.values[255] == base[1]
    restore_palette(app)
    assert app.pyxel.colors.values == base and app.ending_original_colors is None


def test_runtime_data_has_full_approved_duration_and_no_missing_assets():
    import hashlib

    from drift_with_me.ending_playback import ROOT

    data = runtime_data()
    assert data["duration"] == 110 and data["fps"] == 24 and len(data["frames"]) == 2640
    assert len(data["palette"]) < 255
    for asset in data["assets"]:
        raw = (ROOT / "assets/credits_runtime" / asset["name"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == asset["sha256"]
        rows = raw.decode().splitlines()
        w, h = asset["size"]
        assert len(rows) == h and all(len(row) == w for row in rows)
        assert all(int(x, 16) < 16 for row in rows for x in row)
    assert not data["frames"][-1]


def test_runtime_draws_both_phases_without_pillow_and_restores_after_room(monkeypatch):
    import sys

    from drift_with_me.ending_playback import draw

    app, _ = final_app(True)
    calls = []

    class FakeImage:
        def __init__(self, w, h):
            self.size = w, h

        def set(self, x, y, rows):
            assert len(rows) == self.size[1]

    fake = SimpleNamespace(
        width=512,
        height=236,
        colors=Colors([0, 0x2B335F] + [0] * 14),
        Image=FakeImage,
        blt=lambda *a, **kw: calls.append(a),
        clip=lambda *a: None,
        rect=lambda *a: None,
        cls=lambda *a: None,
        pal=lambda *a: None,
        text=lambda *a: None,
    )
    app.pyxel = fake
    monkeypatch.setitem(sys.modules, "pyxel", fake)
    from drift_with_me.collection_room import image_for

    image_for.cache_clear()
    runtime_image.cache_clear()
    assert app.begin_ending()
    draw(app)
    app.update_ending(99.5)
    draw(app)
    assert calls
    app.update_ending(10.9)
    draw(app)
    assert app.screen == AppScreen.CREDITS
    app.update_ending(1)
    assert app.screen == AppScreen.COLLECTION_ROOM
    assert fake.colors.values == [0, 0x2B335F] + [0] * 14
    image_for.cache_clear()
    runtime_image.cache_clear()


def test_playback_has_no_write_path_in_normal_session_or_flowerbed_store():
    app, _ = final_app(True)
    app.week_debug_active = False

    def forbidden(*args, **kwargs):
        pytest.fail("ending attempted a save or flowerbed write")

    app.progress_store.write = forbidden
    app.normal_progress_store.write = forbidden
    app.flowerbed_layout_store.write = forbidden
    before = snapshot(app)
    assert app.begin_ending()
    app.update_ending(112)
    assert app.screen == AppScreen.COLLECTION_ROOM and snapshot(app) == before


def test_final_report_button_enters_credits_then_releases_into_room():
    app, _ = final_app(True)
    app.field_transition = app.week_transition = None
    app.key_pressed = lambda *keys: "KEY_RETURN" in keys
    app.mouse_pressed_in = lambda *_: False
    assert app.update_august(0) and app.screen == AppScreen.CREDITS
    app.update_ending(111.4)
    assert app.screen == AppScreen.COLLECTION_ROOM
