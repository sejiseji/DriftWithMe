from __future__ import annotations

from drift_with_me.input import Rect
from drift_with_me.ui_skin import load_ui_skin_library, scale_hex_rows


class FakeImage:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.rows: tuple[str, ...] = ()

    def set(self, x: int, y: int, rows: list[str]) -> None:
        assert x == 0
        assert y == 0
        self.rows = tuple(rows)


class FakePyxel:
    def __init__(self) -> None:
        self.blt_calls = []

    def Image(self, width: int, height: int) -> FakeImage:
        return FakeImage(width, height)

    def blt(self, *args, **kwargs) -> None:
        self.blt_calls.append((args, kwargs))


def test_sf_ui_skin_manifest_loads_approved_assets() -> None:
    pyxel = FakePyxel()

    library = load_ui_skin_library(pyxel)

    assert library.enabled
    assert library.errors == ()
    assert "sf_frame_resource" in library.assets
    assert "sf_button_primary" in library.assets
    resource = library.assets["sf_frame_resource"]
    assert (resource.width, resource.height) == (129, 42)
    assert resource.colkey == 8
    assert resource.image.rows == resource.rows


def test_sf_ui_skin_draws_scaled_to_existing_hud_rects() -> None:
    pyxel = FakePyxel()
    library = load_ui_skin_library(pyxel)

    assert library.draw(pyxel, "sf_frame_resource", Rect(8, 8, 132, 40))

    args, kwargs = pyxel.blt_calls[-1]
    expected_image = library.scaled_image(pyxel, library.assets["sf_frame_resource"], 132, 40)
    assert args[:7] == (8, 8, expected_image, 0, 0, 132, 40)
    assert kwargs == {"colkey": 8}


def test_scale_hex_rows_preserves_outer_edges() -> None:
    rows = ("0123", "4567", "89AB", "CDEF")

    scaled = scale_hex_rows(rows, 2, 2)

    assert scaled == ("03", "CF")
