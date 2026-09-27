from __future__ import annotations

from drift_with_me.water_study_assets import (
    APPROVED_LOOK04_PLUS_SPARKLE_FRAME_COUNT,
    APPROVED_LOOK04_PLUS_SPARKLE_HOLD_FRAMES,
    WATER_STUDY_RUNTIME_LAYER_IDS,
    _image_from_rows,
    clear_water_study_cache_for_tests,
    preload_water_study_cache,
)


class FakeImage:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.pixel_count = 0
        self.set_calls: list[tuple[int, int, list[str]]] = []

    def set(self, x: int, y: int, rows: list[str]) -> None:
        self.set_calls.append((x, y, rows))
        self.pixel_count += sum(len(row) for row in rows)


class FakePyxel:
    Image = FakeImage


def test_water_study_image_uses_bulk_row_transfer_when_available() -> None:
    rows = ("0123", "4567")

    image = _image_from_rows(FakePyxel, rows, 4, 2)

    assert image.set_calls == [(0, 0, list(rows))]


def test_wtr001_active_preload_cache_contract_and_reuse() -> None:
    clear_water_study_cache_for_tests()

    cache = preload_water_study_cache(FakePyxel, force=True)

    assert cache.ready
    assert cache.static_layers == {}
    assert cache.phase_layers == {}
    assert tuple(cache.frame_sequences) == WATER_STUDY_RUNTIME_LAYER_IDS
    expected_origins = (
        (0, 0),
        (256, 0),
        (512, 0),
        (768, 0),
        (0, 256),
        (256, 256),
        (512, 256),
        (768, 256),
    )
    for layer_id in WATER_STUDY_RUNTIME_LAYER_IDS:
        sequence = cache.frame_sequences[layer_id]
        assert len(sequence.planes) == APPROVED_LOOK04_PLUS_SPARKLE_FRAME_COUNT
        assert sequence.hold_frames == (
            (APPROVED_LOOK04_PLUS_SPARKLE_HOLD_FRAMES,) * APPROVED_LOOK04_PLUS_SPARKLE_FRAME_COUNT
        )
        assert sequence.total_hold_frames == 120
        assert sequence.planes[0].layer_id == f"{layer_id}_t00"
        assert sequence.planes[-1].layer_id == f"{layer_id}_t23"
        for plane in sequence.planes:
            assert (plane.logical_width, plane.logical_height) == (1024, 512)
            assert (plane.chunk_width, plane.chunk_height) == (256, 256)
            assert tuple((chunk.origin_x, chunk.origin_y) for chunk in plane.chunks) == (
                expected_origins
            )
            assert all(chunk.image.pixel_count == 256 * 256 for chunk in plane.chunks)
        if layer_id == "water_deep_plane_e":
            assert sequence.planes[0].colkey is None
        else:
            assert sequence.planes[0].colkey == 8
        assert cache.plane_for_frame(layer_id, 0.0, 60) is sequence.planes[0]
        assert cache.plane_for_frame(layer_id, 5 / 60, 60) is sequence.planes[1]

    assert cache.preload_total_sec >= 0.0
    assert cache.static_preload_sec >= 0.0
    assert cache.phase_preload_sec >= 0.0
    assert cache.sequence_preload_sec >= 0.0
    for layer_id in WATER_STUDY_RUNTIME_LAYER_IDS:
        assert layer_id in cache.layer_preload_sec
        assert cache.layer_preload_sec[layer_id] >= 0.0
    assert cache.sparkle_fx_bank is None
    expected_pixels = len(WATER_STUDY_RUNTIME_LAYER_IDS) * APPROVED_LOOK04_PLUS_SPARKLE_FRAME_COUNT
    expected_pixels *= 1024 * 512
    assert cache.resident_pixel_count == expected_pixels
    assert preload_water_study_cache(FakePyxel) is cache
