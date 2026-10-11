import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.east_site_render import draw_hatch_grass, hatch_grass_placement
from drift_with_me.hex_assets import parse_sprite_definition
from drift_with_me.math3d import AffineCameraState, AffineProjectionProfile, CameraState, Vec3


@pytest.mark.parametrize("projection", ["perspective", "affine"])
@pytest.mark.parametrize("zoom", [0.75, 1.0, 1.5, 2.0])
def test_hatch_grass_keeps_source_aspect_root_anchor_and_original_definition(zoom, projection):
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "src/drift_with_me/assets/jack_sprite.json").read_text())
    raw = next(a for a in manifest["source_assets"] if a["id"] == "grass_patch_low_a_64")
    definition = parse_sprite_definition(raw, "grass_patch_low_a_64")
    asset = SimpleNamespace(definition=definition)
    runtime = load_runtime_config()
    camera = CameraState.from_config(runtime.raw, Vec3(948, 0, 154), 512, 236, zoom=zoom)
    if projection == "affine":
        camera = AffineCameraState(
            Vec3(948, 0, 154),
            AffineProjectionProfile.from_config(runtime.raw),
            zoom,
            0.5,
            0.58,
            512,
            236,
        )
    placement = hatch_grass_placement(asset, camera)
    assert placement is not None
    assert (placement.right - placement.left) / (placement.bottom - placement.top) == pytest.approx(
        definition.hex_width / definition.hex_height
    )
    root_point = camera.project(Vec3(948, 0, 154))
    assert placement.left + definition.anchor_px[0] * placement.scale == pytest.approx(root_point.x)
    assert placement.top + definition.anchor_px[1] * placement.scale == pytest.approx(root_point.y)
    assert definition.world_size == (42.0, 20.0)
    assert definition.projection_mode == "ground_decal_source_v1"
    calls = []
    renderer = SimpleNamespace(draw_atmospheric_scaled_sprite=lambda *args: calls.append(args))
    draw_hatch_grass(renderer, asset, camera, 948, 154)
    assert calls == [(asset, placement)]
