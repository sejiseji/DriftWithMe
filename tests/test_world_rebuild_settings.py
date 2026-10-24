"""World rebuilds must not revive disabled procedural ground decorations."""

import pytest

from drift_with_me.flowerbed import install_flowerbed_world
from drift_with_me.july_week2 import install_week2_world
from drift_with_me.july_week3 import install_week3_world
from drift_with_me.july_week4 import install_week4_world
from drift_with_me.world import WorldData
from test_flowerbed import garden_app


@pytest.mark.parametrize(
    "install",
    [install_flowerbed_world, install_week2_world, install_week3_world, install_week4_world],
)
@pytest.mark.parametrize("detail_count", [0, 2])
def test_rebuild_preserves_configured_culling_and_decoration_policy(install, detail_count):
    app, _ = garden_app()
    app.world = app.model.world = WorldData(app.world.raw, 96, 80, detail_count)
    before = app.world
    authored = tuple((o.id, o.kind, o.x, o.z) for o in before.objects if "grass" in o.kind)
    install(app)
    assert app.world is app.model.world
    assert app.world.chunk_size == 96
    assert app.world.static_visual_max_height == 80
    assert app.world.visual_detail_per_chunk == detail_count
    assert app.world.ground_details == before.ground_details
    assert (
        tuple((o.id, o.kind, o.x, o.z) for o in app.world.objects if "grass" in o.kind) == authored
    )


def test_full_install_chain_keeps_disabled_random_details_disabled():
    app, _ = garden_app()
    assert app.world.visual_detail_per_chunk == 0
    assert not app.world.ground_details
    for _ in range(2):
        install_flowerbed_world(app)
        assert app.world.visual_detail_per_chunk == 0
        assert not app.world.ground_details
