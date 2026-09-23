from __future__ import annotations

from drift_with_me.water_study_assets import WATER_STUDY_LAYER_IDS, load_water_study_planes


class FakeImage:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.pset_count = 0

    def pset(self, _x: int, _y: int, _color: int) -> None:
        self.pset_count += 1


class FakePyxel:
    Image = FakeImage


def test_wtr001_bundled_water_layer_assets_match_contract() -> None:
    planes = load_water_study_planes(FakePyxel)

    assert tuple(planes) == WATER_STUDY_LAYER_IDS
    for layer_id, plane in planes.items():
        assert plane.layer_id == layer_id
        assert (plane.logical_width, plane.logical_height) == (1024, 512)
        assert (plane.chunk_width, plane.chunk_height) == (256, 256)
        assert len(plane.chunks) == 8
        assert [chunk.origin_x for chunk in plane.chunks[:4]] == [0, 256, 512, 768]
        assert [chunk.origin_y for chunk in plane.chunks[:4]] == [0, 0, 0, 0]
        assert [chunk.origin_x for chunk in plane.chunks[4:]] == [0, 256, 512, 768]
        assert [chunk.origin_y for chunk in plane.chunks[4:]] == [256, 256, 256, 256]
        assert all(chunk.image.pset_count == 256 * 256 for chunk in plane.chunks)

    assert planes["water_deep_plane_b"].colkey is None
    for layer_id in WATER_STUDY_LAYER_IDS[1:]:
        assert planes[layer_id].colkey == 8
