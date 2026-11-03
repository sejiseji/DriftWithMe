from types import SimpleNamespace

from drift_with_me.hex_assets import SpritePlacement
from drift_with_me.pixel_stability import (
    MAX_SOURCES,
    MAX_TEXTURES,
    StableNearest,
    allowed,
)


def place(x=10.4, y=20.7, scale=0.75):
    return SpritePlacement(x, y, 100, scale, False, x - 4, y - 6, x - 3, y - 6, x + 3, y)


def test_axis_retains_only_a_small_spatial_dead_band():
    r = StableNearest()
    a = r.axis(("actor", "x"), 1, 0, 10, 0)
    b = r.axis(("actor", "x"), 1.01, 0, 10, 0)
    assert a == b
    c = r.axis(("actor", "x"), 1.2, 0, 10, 0)
    assert c != a
    for j, v in enumerate(c):
        assert v - 0.18 / 1.2 <= (j + 0.5) / 1.2 < v + 1 + 0.18 / 1.2


def test_instance_histories_are_order_independent():
    a = StableNearest()
    b = StableNearest()
    expected = b.axis(("one", "x"), 0.9, -10, 10, 4)
    a.axis(("other", "x"), 0.8, -10, 10, 4)
    assert a.axis(("one", "x"), 0.9, -10, 10, 4) == expected


class FakeImage:
    def __init__(self, w, h, color=3):
        self.w = w
        self.h = h
        self.color = color
        self.rows = []

    def pget(self, x, y):
        return self.color

    def set(self, x, y, rows):
        self.rows = rows


def test_source_identity_preserves_atmospheric_color_variants_and_integer_banks():
    r = StableNearest()
    draws = []
    bank = FakeImage(4, 4, 7)
    pyxel = SimpleNamespace(
        Image=FakeImage, blt=lambda *args, **kw: draws.append(args[2]), image=lambda i: bank
    )
    definition = SimpleNamespace(anchor_px=(2, 4), world_size=(4, 4), colkey=0)
    source = FakeImage(4, 4, 3)
    frame = SimpleNamespace(width=4, height=4, u=0, v=0, image=source, source_hash="same-source")
    assert r.draw(pyxel, frame, definition, place(scale=1))
    frame.image = FakeImage(4, 4, 8)
    assert r.draw(pyxel, frame, definition, place(scale=1))
    assert any("8" in row for row in draws[-1].rows)
    frame.image = 0
    assert r.draw(pyxel, frame, definition, place(scale=1))
    assert any("7" in row for row in draws[-1].rows)
    assert len(r.textures) <= MAX_TEXTURES and len(r.sources) <= MAX_SOURCES
    r.reset()
    assert not r.maps and not r.textures and not r.sources


def test_exclusions_do_not_depend_on_stale_renderer_context():
    r = SimpleNamespace(pixel_stability_context=True, camera_is_affine=lambda c: True)
    m = SimpleNamespace(world_paused=False, combat_session=None)
    assert allowed(r, m, None)
    for k in ["combat_session", "swarm_presentation", "august_sighting_view"]:
        setattr(m, k, object())
        assert not allowed(r, m, None)
        setattr(m, k, None)
    m.world_paused = True
    assert not allowed(r, m, None)
    r.pixel_stability_context = False
    m.world_paused = False
    assert not allowed(r, m, None)


def test_native_palette_plane_matches_pixel_reads_with_uv_and_flip():
    class NativeImage(FakeImage):
        width = 8
        height = 8

        def data_ptr(self):
            return bytes((x + 2 * y) % 16 for y in range(8) for x in range(8))

        def pget(self, x, y):
            raise AssertionError("native plane should not read every pixel")

    class ReadImage(FakeImage):
        def pget(self, x, y):
            return (x + 2 * y) % 16

    definition = SimpleNamespace(anchor_px=(2, 4), world_size=(4, 4), colkey=0)
    results = []
    for source in [NativeImage(8, 8), ReadImage(8, 8)]:
        draws = []
        px = SimpleNamespace(
            Image=FakeImage, blt=lambda *a, draws=draws, **kw: draws.append(a[2].rows)
        )
        r = StableNearest()
        frame = SimpleNamespace(width=4, height=4, u=2, v=1, image=source, source_hash="uv")
        for scale in [0.75, 0.78, 0.9, 1.3, 0.6]:
            from dataclasses import replace

            assert r.draw(px, frame, definition, replace(place(scale=scale), flip_x=True))
        results.append(draws)
    assert results[0] == results[1]


def test_source_cache_is_bounded_by_pixels_and_reset_releases_it(monkeypatch):
    from drift_with_me import pixel_stability

    monkeypatch.setattr(pixel_stability, "MAX_SOURCE_PIXELS", 32)
    r = StableNearest()
    px = SimpleNamespace(Image=FakeImage, blt=lambda *a, **kw: None)
    definition = SimpleNamespace(anchor_px=(2, 4), world_size=(4, 4), colkey=0)
    for i in range(150):
        frame = SimpleNamespace(
            width=4, height=4, u=0, v=0, image=FakeImage(4, 4, i % 16), source_hash=str(i)
        )
        assert r.draw(px, frame, definition, place(scale=0.75 + i / 200), instance=str(i))
        assert r.source_pixels <= 32
        assert len(r.sources) <= 2 and len(r.textures) <= MAX_TEXTURES and len(r.maps) <= 128
    r.reset()
    assert r.source_pixels == 0 and not r.sources and not r.textures and not r.maps


def test_offscreen_skips_raster_build_but_preserves_axis_history_and_reentry():
    from dataclasses import replace

    r = StableNearest()
    reference = StableNearest()
    draws = []
    px = SimpleNamespace(
        width=512,
        height=236,
        Image=FakeImage,
        blt=lambda *a, **kw: draws.append(a[2].rows),
    )
    reference_px = SimpleNamespace(Image=FakeImage, blt=lambda *a, **kw: None)
    definition = SimpleNamespace(anchor_px=(2, 4), world_size=(4, 4), colkey=0)
    frame = SimpleNamespace(width=4, height=4, u=0, v=0, image=FakeImage(4, 4), source_hash="s")
    for scale in [0.75, 0.76, 0.77, 0.85]:
        assert r.draw(px, frame, definition, replace(place(scale=scale), anchor_x=-100))
        assert reference.draw(reference_px, frame, definition, place(scale=scale))
        assert r.maps == reference.maps
    assert not r.sources and not r.textures and r.builds == 0 and r.culled_draws == 4
    assert r.draw(px, frame, definition, place(scale=0.86))
    assert reference.draw(reference_px, frame, definition, place(scale=0.86))
    assert r.maps == reference.maps
    assert draws[-1] == next(reversed(reference.textures.values()))[0].rows
    before = r.culled_draws
    assert r.draw(px, frame, definition, replace(place(scale=1), anchor_x=-1))
    assert r.culled_draws == before  # A negative anchor with visible pixels is retained.
