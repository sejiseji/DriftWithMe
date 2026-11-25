import math
from dataclasses import replace
from types import SimpleNamespace

from drift_with_me.math3d import Vec3
from drift_with_me.render import Renderer
from test_affine_projection import make_affine_camera


class GenericCamera:
    """Same camera math, but dispatches through the per-pixel reference path."""

    def __init__(self, camera):
        self.camera = camera

    def __getattr__(self, name):
        return getattr(self.camera, name)


def test_affine_decal_matches_draw_calls_through_pan_and_zoom_threshold():
    _, _, _, _, affine = make_affine_camera()
    drawn = []
    renderer = Renderer(SimpleNamespace(rect=lambda *args: drawn.append(args)))
    renderer._active_atmosphere_dither_cells = 8
    renderer._active_atmosphere_dither_fog_color = 5
    source = SimpleNamespace(
        width=8,
        height=6,
        frame_id="ground",
        rows=("12345670", "23456780", "34567890", "456789A0", "56789AB0", "6789ABC0"),
    )
    asset = SimpleNamespace(
        definition=SimpleNamespace(
            asset_id="decal",
            projection_mode="ground_decal_source_v1",
            anchor_px=(3, 2),
            world_size=(8.0, 6.0),
            colkey=0,
        ),
        frame=lambda: SimpleNamespace(source=source),
    )
    sample_counts = set()
    for screen_anchor in (affine.anchor_x, 0.0):
        for zoom in (0.73, 1.0, 1.0397, 1.041, 1.43):
            for pan in (-0.9, -0.5, 0.0, 0.25, 0.9):
                camera = replace(
                    affine,
                    target=Vec3(160.0 + pan, 0.17, 160.0 - pan),
                    zoom=zoom,
                    anchor_x=screen_anchor,
                    fx_offset_x=0.21,
                    fx_offset_y=-0.48,
                )
                assert renderer.draw_ground_source_asset(asset, camera, 160.0, 160.0)
                fast = list(drawn)
                drawn.clear()
                assert renderer.draw_ground_source_asset(asset, GenericCamera(camera), 160.0, 160.0)
                assert drawn == fast
                assert any(pixel[4] == 5 for pixel in drawn)
                sample_counts.add(len(drawn))
                drawn.clear()
    assert sample_counts == {12, 42}


def test_affine_decal_keeps_exact_depth_edges_and_skips_nonfinite_points():
    _, _, _, _, affine = make_affine_camera()
    pixels = ((0, 0, "3"), (1, 1, "4"), (2, 2, "5"), (3, 3, "6"))
    origin = (160.0, 160.0)
    step = (1.0, 1.0)
    affine = replace(affine, target=Vec3(160.0, 0.0, 160.0))
    edge = affine.project(Vec3(161.5, 0.0, 161.5))
    assert edge is not None
    depth = edge.depth
    clipped = []
    for near, far in (
        (0.0, 1800.0),
        (depth, depth),
        (0.0, math.nextafter(depth, -math.inf)),
        (math.nextafter(depth, math.inf), 1800.0),
    ):
        camera = replace(affine, near=near, far=far)
        expected = list(Renderer.project_ground_source_pixels(camera, pixels, *origin, *step, 1))
        got = list(Renderer.affine_ground_source_pixels(camera, pixels, 4, 4, *origin, *step, 1))
        assert got == expected
        clipped.append(len(got))
    assert clipped == [4, 1, 1, 2]
    camera = replace(affine, fx_offset_x=float("nan"))
    assert not list(Renderer.affine_ground_source_pixels(camera, pixels, 4, 4, *origin, *step, 1))
