"""Juveniles end at real ground positions behind authored cover, not a layer override."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from drift_with_me.august_sightings import EXIT_COVERS, crossing_path
from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import (
    AffineProjectionProfile,
    CameraState,
    Vec3,
    affine_camera_from_perspective,
)
from drift_with_me.world import load_world_data


@pytest.mark.parametrize("site", sorted(EXIT_COVERS))
@pytest.mark.parametrize("affine", [False, True])
@pytest.mark.parametrize("zoom", [0.8, 1.0, 1.2])
def test_exit_is_behind_cover_and_stays_fixed_while_camera_settles(site, affine, zoom):
    config = load_runtime_config().raw
    model = SimpleNamespace(world=load_world_data())
    cover = model.world.object_by_id(EXIT_COVERS[site])
    camera = CameraState.from_config(config, Vec3(cover.x - 60, 0, cover.z - 50), 512, 236)
    camera = replace(camera, distance=camera.distance / zoom)
    if affine:
        camera = affine_camera_from_perspective(
            camera,
            AffineProjectionProfile.from_config(config),
            base_distance=config["camera"]["base_distance"],
        )
    before = tuple(model.world.objects)
    start, end = crossing_path(model, camera, site)
    assert start.y == end.y == 0
    assert camera.project(end).depth > camera.project(Vec3(cover.x, 0, cover.z)).depth
    assert camera.project(start).x < camera.project(end).x
    moved = replace(camera, target=Vec3(camera.target.x + 25, 0, camera.target.z - 18))
    assert crossing_path(model, moved, site) == (start, end)
    assert tuple(model.world.objects) == before


def test_missing_cover_is_not_silently_replaced_by_a_fake_depth():
    model = SimpleNamespace(world=SimpleNamespace(object_by_id=lambda _: None))
    with pytest.raises(RuntimeError, match="authored juvenile exit cover"):
        crossing_path(model, None, "southeast")
