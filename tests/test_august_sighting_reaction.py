"""Sighting reactions are transient presentation and leave the input model intact."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.august_sightings import (
    EXIT_COVERS,
    MAX_SIGHTING_ZOOM,
    JuvenileSighting,
    reaction_amount,
    sighting_camera,
    sighting_facing,
    sighting_opacity,
)
from drift_with_me.config import load_runtime_config
from drift_with_me.math3d import (
    AffineProjectionProfile,
    CameraState,
    Vec3,
    affine_camera_from_perspective,
)
from drift_with_me.render import Renderer
from drift_with_me.world import load_world_data


@pytest.mark.parametrize("site", sorted(EXIT_COVERS))
@pytest.mark.parametrize("affine", [False, True])
def test_push_returns_exactly_and_does_not_move_actors_or_input_camera(site, affine):
    config = load_runtime_config().raw
    world = load_world_data()
    cover = world.object_by_id(EXIT_COVERS[site])
    player = SimpleNamespace(x=cover.x - 60, z=cover.z - 50, last_move_x=1, last_move_z=0)
    buddy = SimpleNamespace(x=player.x - 16, y=26, z=player.z - 8)
    model = SimpleNamespace(player=player, buddy=buddy, world=world)
    camera = CameraState.from_config(config, Vec3(player.x, 0, player.z), 512, 236)
    if affine:
        camera = affine_camera_from_perspective(
            camera,
            AffineProjectionProfile.from_config(config),
            base_distance=config["camera"]["base_distance"],
        )
    before = deepcopy((vars(player), vars(buddy), camera))
    cue = JuvenileSighting(site, 0.15)
    result = sighting_camera(model, camera, cue)
    assert result.distance < camera.distance
    assert camera.distance / result.distance <= MAX_SIGHTING_ZOOM
    assert (result.yaw_deg, result.pitch_deg) == (camera.yaw_deg, camera.pitch_deg)
    assert (vars(player), vars(buddy), camera) == before
    assert sighting_camera(model, camera, None) is camera
    assert sighting_camera(model, camera, JuvenileSighting(site, 1.2)) is camera
    assert sighting_facing(model, result, cue) is not None
    model.august_sighting_view = cue
    renderer = Renderer.__new__(Renderer)
    assert renderer.player_sprite_direction_view(model, result) != "idle"
    assert (vars(player), vars(buddy), camera) == before


def test_reaction_has_short_attack_and_no_lingering_zoom():
    assert reaction_amount(0) == 0
    assert 0 < reaction_amount(0.05) < 1
    assert reaction_amount(0.1) == reaction_amount(0.26) == 1
    assert reaction_amount(0.8) < reaction_amount(0.5)
    assert reaction_amount(1.18) == reaction_amount(1.3) == 0


def test_foreground_fade_never_removes_exit_cover_and_restores_after_reaction():
    world = load_world_data()
    model = SimpleNamespace(
        world=world, player=SimpleNamespace(x=200, z=766), buddy=SimpleNamespace(x=184, y=26, z=758)
    )
    config = load_runtime_config().raw
    camera = CameraState.from_config(config, Vec3(200, 0, 766), 512, 236)
    renderer = SimpleNamespace(
        object_screen_bounds=lambda *_: SimpleNamespace(x=0, y=0, width=512, height=236)
    )
    cue = JuvenileSighting("northwest", 0.15)
    command = SimpleNamespace(stable_id=EXIT_COVERS["northwest"], depth=0)
    assert sighting_opacity(renderer, model, camera, command, cue) == 1
    command.stable_id = "wall_02"
    assert sighting_opacity(renderer, model, camera, command, cue) == pytest.approx(0.35)
    assert (
        sighting_opacity(renderer, model, camera, command, JuvenileSighting("northwest", 1.2)) == 1
    )
    assert sighting_opacity(renderer, model, camera, command, None) == 1


def test_two_notice_marks_avoid_the_whole_juvenile_corridor(monkeypatch):
    import drift_with_me.august_sightings as module

    path = (Vec3(180, 0, 80), Vec3(300, 0, 80))
    monkeypatch.setattr(module, "crossing_path", lambda *_: path)
    monkeypatch.setattr(
        module,
        "placement_for_upright_height_billboard",
        lambda _c, _d, a: SimpleNamespace(
            left=230 if a.x == 0 else 190,
            right=250 if a.x == 0 else 208,
            top=130 if a.x == 0 else 100,
            bottom=148 if a.x == 0 else 116,
        ),
    )
    calls = []
    monkeypatch.setattr(
        module,
        "draw_notice_glyph",
        lambda _p, x, y, scale: calls.append((x, y, scale)),
    )
    model = SimpleNamespace(
        august_sighting_view=JuvenileSighting("southeast", 0.15),
        player=SimpleNamespace(x=0, z=0),
        buddy=SimpleNamespace(x=30, y=26, z=0),
    )
    camera = SimpleNamespace(
        viewport_width=512, viewport_height=236, project=lambda v: SimpleNamespace(x=v.x, y=v.z)
    )
    asset = SimpleNamespace(definition=object())
    renderer = SimpleNamespace(
        pyxel=object(),
        player_sprite_asset=lambda *_: asset,
        buddy_sprite_asset=lambda *_: asset,
        player_visual_y_offset=lambda *_: 0,
    )
    module.draw_notice(renderer, model, camera, 0)
    marks = calls
    assert len(marks) == 2
    assert all(not (168 <= x <= 312 and 66 <= y <= 84) for x, y, *_ in marks)
    calls.clear()
    model.august_sighting_view = None
    module.draw_notice(renderer, model, camera, 0)
    assert not calls


def test_close_framing_can_reach_the_requested_double_size_cap(monkeypatch):
    import drift_with_me.august_sightings as module

    world = load_world_data()
    cover = world.object_by_id(EXIT_COVERS["southeast"])
    model = SimpleNamespace(
        world=world,
        player=SimpleNamespace(x=cover.x - 4, z=cover.z - 4),
        buddy=SimpleNamespace(x=cover.x - 8, y=10, z=cover.z - 4),
    )
    camera = CameraState.from_config(load_runtime_config().raw, Vec3(cover.x, 0, cover.z), 512, 236)
    monkeypatch.setattr(
        module,
        "crossing_path",
        lambda *_: (Vec3(cover.x - 10, 0, cover.z), Vec3(cover.x, 0, cover.z + 5)),
    )
    result = sighting_camera(model, camera, JuvenileSighting("southeast", 0.15))
    assert camera.distance / result.distance == pytest.approx(2.44)
