"""Use authored directional loops, not reflection or the default north frame."""

from types import SimpleNamespace

import pytest

from drift_with_me.august_sightings import draw_notice_glyph, juvenile_frame
from drift_with_me.math3d import Vec3


@pytest.mark.parametrize(
    "dx,dy,name",
    [
        (0, -1, "N"),
        (1, -1, "NE"),
        (1, 0, "E"),
        (1, 1, "SE"),
        (0, 1, "S"),
        (-1, 1, "SW"),
        (-1, 0, "W"),
        (-1, -1, "NW"),
    ],
)
def test_slug_direction_follows_projected_motion(dx, dy, name):
    camera = SimpleNamespace(project=lambda v: SimpleNamespace(x=v.x, y=v.z))
    asset = SimpleNamespace(frame=lambda frame_id=None: frame_id)
    assert juvenile_frame(asset, "slug", camera, Vec3(0, 0, 0), Vec3(dx, 0, dy), 0) == name + "_00"


def test_slug_uses_the_existing_four_frame_six_fps_loop():
    camera = SimpleNamespace(project=lambda v: SimpleNamespace(x=v.x, y=v.z))
    asset = SimpleNamespace(frame=lambda frame_id=None: frame_id)
    assert [
        juvenile_frame(asset, "slug", camera, Vec3(0, 0, 0), Vec3(1, 0, 0), t)
        for t in (0, 0.17, 0.34, 0.51, 0.68)
    ] == ["E_00", "E_01", "E_02", "E_03", "E_00"]


def test_radial_urchin_retains_its_only_production_frame():
    asset = SimpleNamespace(frame=lambda frame_id=None: "idle" if frame_id is None else frame_id)
    assert juvenile_frame(asset, "urchin", None, None, None, 1) == "idle"


def test_notice_is_thick_red_with_white_and_dark_outlines():
    calls = []
    pixels = SimpleNamespace(rect=lambda *args: calls.append(args))
    draw_notice_glyph(pixels, 20, 30, 1)
    assert {call[-1] for call in calls} == {0, 7, 8}
    red = [c for c in calls if c[-1] == 8]
    assert max(x + w for x, y, w, h, c in red) - min(x for x, y, w, h, c in red) == 4
    assert min(x for x, y, w, h, c in calls) < min(x for x, y, w, h, c in red)
