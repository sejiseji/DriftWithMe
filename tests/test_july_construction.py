"""Projected placement, thin collision boundaries, week lifecycle and access routes."""

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.july_construction import FENCE_EDGES, PREFIX, STOCK
from drift_with_me.july_week1 import install_july_world
from drift_with_me.math3d import AffineProjectionProfile
from test_july_story import july_app


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_all_stock_is_screen_left_of_fuji_in_the_actual_affine_projection(profile):
    projection = AffineProjectionProfile.from_config(load_runtime_config(profile).raw)
    for _, x, z in STOCK:
        screen_dx = projection.basis_x.x * (x - 288) + projection.basis_z.x * (z - 384)
        assert screen_dx < -40


def test_fence_matches_edges_and_leaves_plot_and_gate_walkable():
    app = july_app()
    world, model = app.world, app.model
    assert not world.collides_player(180, 380, model.player_half_x, model.player_half_z)
    assert not world.collides_player(220, 384, model.player_half_x, model.player_half_z)
    for a, b in FENCE_EDGES:
        x, z = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        assert world.collides_player(x, z, model.player_half_x, model.player_half_z)
    for _, x, z in STOCK:
        assert world.collides_player(x, z + 2, model.player_half_x, model.player_half_z)


def test_stock_and_fence_do_not_block_supply_npc_survey_or_return_routes():
    app = july_app()
    app.model.player.x, app.model.player.z = 288, 384
    for ident in ("tap_start", "solar_start", "tap_east", "solar_east", "jul_w1_water"):
        target = app.world.object_by_id(ident)
        assert target is not None
        assert app.model.find_auto_move_path(target.x, target.z) is not None, ident
        assert not app.world.collides_player(target.x, target.z, 10, 10), ident
    for x, z in ((520, 480), (580, 480), (620, 488), (236, 384), (180, 380)):
        assert app.model.find_auto_move_path(x, z) is not None, (x, z)


def test_reinstall_and_june_cleanup_remove_only_july_objects():
    app = july_app()
    original = [o.id for o in app.world.objects]
    install_july_world(app)
    assert [o.id for o in app.world.objects] == original
    assert app.model.july_construction is not None
    install_july_world(app, enabled=False)
    assert app.model.july_construction is None
    assert not any(o.id.startswith(PREFIX) for o in app.world.objects)
    assert app.world.object_by_id("tap_start") is not None


def test_new_layout_reappears_after_save_resume_without_changing_the_schema():
    from drift_with_me.save_state import decode, encode, snapshot

    app = july_app()
    ids = {o.id for o in app.world.objects if o.id.startswith(PREFIX)}
    saved = snapshot(app)
    _, offices, *_ = decode(encode(saved))
    app.office = offices[app.work_week]
    install_july_world(app, combat=True)
    assert {o.id for o in app.world.objects if o.id.startswith(PREFIX)} == ids
    assert snapshot(app) == saved
    assert len(app.model.july_construction.props) > 8
