from __future__ import annotations

import math
from dataclasses import replace

import pytest

from drift_with_me.config import load_runtime_config
from drift_with_me.hex_assets import (
    LoadedSpriteAsset,
    LoadedSpriteFrame,
    SpriteDefinition,
    SpriteFrameDefinition,
)
from drift_with_me.math3d import (
    AffineProjectionProfile,
    CameraState,
    Vec3,
    affine_camera_from_perspective,
    screen_to_ground_affine,
)
from drift_with_me.model import GameModel
from drift_with_me.render import (
    ATMOSPHERE_BUDDY_STRENGTH,
    ATMOSPHERE_DITHER_FOG_COLOR,
    ATMOSPHERE_ENEMY_STRENGTH,
    ATMOSPHERE_EQUIPMENT_STRENGTH,
    ATMOSPHERE_FAR_DITHER_CELLS,
    ATMOSPHERE_FAR_PALETTE,
    ATMOSPHERE_MID_DITHER_CELLS,
    ATMOSPHERE_NATURE_PROP_STRENGTH,
    ATMOSPHERE_PLAYER_STRENGTH,
    ATMOSPHERE_SHADOW_FAR_CELLS,
    ATMOSPHERE_SHADOW_IMPORTANT_MIN_CELLS,
    ATMOSPHERE_SHADOW_MID_CELLS,
    ATMOSPHERE_SHADOW_NEAR_CELLS,
    ATMOSPHERE_SOLID_STRENGTH,
    ATMOSPHERE_WEAK_PALETTE,
    Renderer,
)
from drift_with_me.world import load_world_data


class FakeImage:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._pixels = [[0 for _x in range(width)] for _y in range(height)]

    def pget(self, x: int, y: int) -> int:
        return self._pixels[y][x]

    def pset(self, x: int, y: int, color: int) -> None:
        self._pixels[y][x] = color


class FakePyxel:
    def __init__(self) -> None:
        self.images: list[FakeImage] = []

    def Image(self, width: int, height: int) -> FakeImage:
        return FakeImage(width, height)


class RecordingPyxel(FakePyxel):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple] = []

    def tri(self, *args) -> None:
        self.calls.append(("tri", *args))

    def line(self, *args) -> None:
        self.calls.append(("line", *args))

    def pset(self, *args) -> None:
        self.calls.append(("pset", *args))


def make_affine_camera():
    runtime = load_runtime_config()
    world = load_world_data()
    target = Vec3(world.spawn_x, 0.0, world.spawn_z)
    perspective = CameraState.from_config(
        runtime.raw,
        target,
        runtime.screen_width,
        runtime.screen_height,
    )
    profile = AffineProjectionProfile.from_config(runtime.raw)
    affine = affine_camera_from_perspective(
        perspective,
        profile,
        base_distance=float(runtime.raw["camera"]["base_distance"]),
    )
    return runtime, world, perspective, profile, affine


def test_affine_profile_matches_current_follow_projection_measurement() -> None:
    _runtime, world, perspective, profile, _affine = make_affine_camera()
    step = 32.0
    origin = Vec3(world.spawn_x, 0.0, world.spawn_z)
    p0 = perspective.project(origin)
    px = perspective.project(Vec3(origin.x + step, origin.y, origin.z))
    py = perspective.project(Vec3(origin.x, origin.y + step, origin.z))
    pz = perspective.project(Vec3(origin.x, origin.y, origin.z + step))
    assert p0 is not None and px is not None and py is not None and pz is not None

    assert profile.basis_x.x == pytest.approx((px.x - p0.x) / step)
    assert profile.basis_x.y == pytest.approx((px.y - p0.y) / step)
    assert profile.basis_y.x == pytest.approx((py.x - p0.x) / step)
    assert profile.basis_y.y == pytest.approx((py.y - p0.y) / step)
    assert profile.basis_z.x == pytest.approx((pz.x - p0.x) / step)
    assert profile.basis_z.y == pytest.approx((pz.y - p0.y) / step)


def test_affine_ground_basis_is_invertible() -> None:
    _runtime, _world, _perspective, profile, _affine = make_affine_camera()

    assert math.isfinite(profile.ground_determinant)
    assert abs(profile.ground_determinant) > 1e-6


def test_affine_world_to_screen_to_ground_round_trip() -> None:
    _runtime, _world, _perspective, _profile, affine = make_affine_camera()
    max_error = 0.0

    for point in (
        Vec3(160.0, 0.0, 160.0),
        Vec3(220.0, 0.0, 240.0),
        Vec3(96.0, 0.0, 288.0),
        Vec3(320.0, 0.0, 128.0),
    ):
        projected = affine.project(point)
        assert projected is not None
        picked = screen_to_ground_affine(affine, projected.x, projected.y)
        assert picked is not None
        max_error = max(max_error, abs(picked.x - point.x), abs(picked.y - point.z))

    assert max_error <= 1e-9


def test_affine_screen_to_ground_to_screen_round_trip() -> None:
    _runtime, _world, _perspective, _profile, affine = make_affine_camera()
    max_error = 0.0

    for screen_x, screen_y in (
        (256.0, 136.88),
        (300.0, 120.0),
        (180.0, 180.0),
        (420.0, 92.0),
    ):
        picked = screen_to_ground_affine(affine, screen_x, screen_y)
        assert picked is not None
        projected = affine.project(Vec3(picked.x, 0.0, picked.y))
        assert projected is not None
        max_error = max(max_error, abs(projected.x - screen_x), abs(projected.y - screen_y))

    assert max_error <= 1e-9


def test_affine_xz_screen_vectors_are_position_invariant() -> None:
    _runtime, _world, _perspective, _profile, affine = make_affine_camera()
    base = Vec3(96.0, 0.0, 128.0)
    comparison = Vec3(352.0, 0.0, 416.0)

    base_root = affine.project(base)
    base_x = affine.project(Vec3(base.x + 32.0, base.y, base.z))
    base_z = affine.project(Vec3(base.x, base.y, base.z + 32.0))
    comparison_root = affine.project(comparison)
    comparison_x = affine.project(Vec3(comparison.x + 32.0, comparison.y, comparison.z))
    comparison_z = affine.project(Vec3(comparison.x, comparison.y, comparison.z + 32.0))
    assert (
        base_root is not None
        and base_x is not None
        and base_z is not None
        and comparison_root is not None
        and comparison_x is not None
        and comparison_z is not None
    )

    assert comparison_x.x - comparison_root.x == pytest.approx(base_x.x - base_root.x)
    assert comparison_x.y - comparison_root.y == pytest.approx(base_x.y - base_root.y)
    assert comparison_z.x - comparison_root.x == pytest.approx(base_z.x - base_root.x)
    assert comparison_z.y - comparison_root.y == pytest.approx(base_z.y - base_root.y)


def test_grassland_micro_layer_uses_world_anchored_clumps_and_is_affine_only() -> None:
    runtime, world, perspective, _profile, affine = make_affine_camera()
    pyxel = RecordingPyxel()
    renderer = Renderer(pyxel)
    config = runtime.raw["grassland_micro"]
    model = GameModel(runtime.raw, world)

    assert config["enabled"] is True
    assert config["affine_only"] is True
    assert config["cell_world"] == pytest.approx(24.0)
    assert config["min_blades_per_cell"] == 1
    assert config["max_blades_per_cell"] == 5
    assert config["base_variation_enabled"] is False
    assert config["base_variation_color"] != 13
    assert config["transition_world"] == pytest.approx(32.0)
    assert config["transition_cell_world"] == pytest.approx(8.0)
    assert config["transition_pattern"] == "noise"
    assert config["transition_soft_color"] == 11
    assert config["micro_density_inner"] == pytest.approx(1.0)
    assert config["micro_density_edge"] == pytest.approx(0.2)
    assert config["areas"][0]["bounds_ref"] == "visual_ground"
    assert world.visual_ground_rect.min_x == pytest.approx(-256.0)
    assert world.visual_ground_rect.max_x == pytest.approx(1280.0)
    assert renderer.draw_grassland_micro_layer(model, perspective) == 0

    assert renderer.draw_grassland_micro_layer(model, affine) == 1
    assert any(call[0] == "tri" and call[-1] == config["base_color"] for call in pyxel.calls)
    base_lines = [call for call in pyxel.calls if call[0] == "line"]
    assert base_lines

    shifted = replace(
        affine,
        target=Vec3(affine.target.x, affine.target.y, affine.target.z + 32.0),
    )
    pyxel.calls.clear()
    assert renderer.draw_grassland_micro_layer(model, shifted) == 1
    shifted_lines = [call for call in pyxel.calls if call[0] == "line"]
    assert shifted_lines
    assert {(call[1], call[2]) for call in base_lines[:16]} != {
        (call[1], call[2]) for call in shifted_lines[:16]
    }

    overview = replace(
        affine,
        target=Vec3(768.0, 0.0, 768.0),
        zoom=0.7,
    )
    pyxel.calls.clear()
    assert renderer.draw_grassland_micro_layer(model, overview) == 1
    assert any(call[0] == "tri" and call[-1] == config["base_color"] for call in pyxel.calls)
    assert any(call[0] == "line" for call in pyxel.calls)


def test_grassland_boundary_transition_classification_and_density() -> None:
    renderer = Renderer(RecordingPyxel())
    rect = (0.0, 0.0, 128.0, 128.0)
    transition_world = 32.0

    assert renderer.grassland_transition_t(rect, 0.0, 64.0, transition_world) == pytest.approx(0.0)
    assert renderer.grassland_transition_t(rect, 16.0, 64.0, transition_world) == pytest.approx(0.5)
    assert renderer.grassland_transition_t(rect, 64.0, 64.0, transition_world) == pytest.approx(1.0)
    assert renderer.grassland_base_coverage(rect, 16.0, 64.0, transition_world) == pytest.approx(
        0.5
    )
    assert renderer.grassland_micro_density(
        rect,
        0.0,
        64.0,
        transition_world,
        density_inner=1.0,
        density_edge=0.2,
    ) == pytest.approx(0.2)
    assert renderer.grassland_micro_density(
        rect,
        16.0,
        64.0,
        transition_world,
        density_inner=1.0,
        density_edge=0.2,
    ) == pytest.approx(0.6)
    assert renderer.grassland_transition_soft_coverage(0.2) > 0.2
    assert renderer.grassland_transition_base_coverage(0.2) == pytest.approx(0.0)
    assert renderer.grassland_transition_base_coverage(0.8) > 0.5


def test_grassland_bayer_pattern_is_world_cell_deterministic() -> None:
    renderer = Renderer(RecordingPyxel())
    results = [
        renderer.grassland_bayer_pass(cell_x, cell_z, 0.5, phase=3)
        for cell_z in range(4)
        for cell_x in range(4)
    ]

    assert sum(results) == 8
    assert results == [
        renderer.grassland_bayer_pass(cell_x, cell_z, 0.5, phase=3)
        for cell_z in range(4)
        for cell_x in range(4)
    ]


def test_grassland_noise_pattern_is_world_cell_deterministic() -> None:
    renderer = Renderer(RecordingPyxel())
    first = [
        renderer.grassland_transition_pass(
            cell_x, cell_z, 0.5, 5, {}, {"transition_pattern": "noise"}
        )
        for cell_z in range(8)
        for cell_x in range(8)
    ]
    second = [
        renderer.grassland_transition_pass(
            cell_x, cell_z, 0.5, 5, {}, {"transition_pattern": "noise"}
        )
        for cell_z in range(8)
        for cell_x in range(8)
    ]

    assert first == second
    assert 16 <= sum(first) <= 48


def test_grassland_boundary_transition_skips_prefilled_interior_cells() -> None:
    runtime, world, _perspective, profile, _affine = make_affine_camera()
    pyxel = RecordingPyxel()
    renderer = Renderer(pyxel)
    camera = CameraState.from_config(
        runtime.raw,
        Vec3(512.0, 0.0, -160.0),
        runtime.screen_width,
        runtime.screen_height,
    )
    camera = affine_camera_from_perspective(
        camera,
        profile,
        base_distance=float(runtime.raw["camera"]["base_distance"]),
    )
    config = runtime.raw["grassland_micro"]
    area = config["areas"][0]
    area_rect = renderer.grassland_micro_world_rect(world, area)
    assert area_rect is not None
    draw_rect = renderer.grassland_micro_visible_draw_rect(camera, area_rect, area, config)
    assert draw_rect is not None

    renderer.draw_grassland_base_transition(camera, area_rect, draw_rect, area, config, 3)

    tri_calls = [call for call in pyxel.calls if call[0] == "tri"]
    assert 0 < len(tri_calls) < 2500
    assert len(renderer._grassland_transition_cell_cache) == 1
    cached_cells = next(iter(renderer._grassland_transition_cell_cache.values()))

    pyxel.calls.clear()
    renderer.draw_grassland_base_transition(camera, area_rect, draw_rect, area, config, 3)

    assert next(iter(renderer._grassland_transition_cell_cache.values())) is cached_cells


def test_visual_ground_bounds_extend_beyond_walkable_for_affine_ground_draw() -> None:
    _runtime, world, _perspective, _profile, affine = make_affine_camera()
    pyxel = RecordingPyxel()
    renderer = Renderer(pyxel)
    camera = replace(
        affine,
        target=Vec3(-64.0, 0.0, 160.0),
    )

    rect = renderer.visible_ground_draw_rect(world.visual_ground_rect, camera, margin_px=8.0)
    assert rect is not None
    assert rect.min_x < world.walkable_rect.min_x
    renderer.draw_ground(world, camera)

    assert any(call[0] == "tri" and call[-1] == 13 for call in pyxel.calls)


def test_visual_ground_draw_stops_outside_visual_bounds() -> None:
    _runtime, world, _perspective, _profile, affine = make_affine_camera()
    renderer = Renderer(RecordingPyxel())
    camera = replace(
        affine,
        target=Vec3(-2000.0, 0.0, -2000.0),
    )

    assert (
        renderer.visible_ground_draw_rect(world.visual_ground_rect, camera, margin_px=8.0) is None
    )


def test_affine_height_projects_straight_up_for_actor_roots() -> None:
    _runtime, _world, _perspective, profile, affine = make_affine_camera()
    root = affine.project(Vec3(160.0, 0.0, 160.0))
    raised = affine.project(Vec3(160.0, 26.0, 160.0))
    assert root is not None and raised is not None

    assert raised.x - root.x == pytest.approx(profile.basis_y.x * 26.0)
    assert raised.y - root.y == pytest.approx(profile.basis_y.y * 26.0)
    assert raised.x == pytest.approx(root.x)
    assert raised.y < root.y


def test_affine_buddy_y_separates_body_from_ground_shadow() -> None:
    runtime, world, _perspective, _profile, affine = make_affine_camera()
    model = GameModel(runtime.raw, world)

    shadow = affine.project(Vec3(model.buddy.x, 0.0, model.buddy.z))
    body = affine.project(Vec3(model.buddy.x, model.buddy.y, model.buddy.z))
    assert shadow is not None and body is not None
    assert body.x == pytest.approx(shadow.x)
    assert body.y < shadow.y


def test_affine_entity_roots_project_for_equipment_tree_enemy_and_world_patch() -> None:
    runtime, world, _perspective, _profile, affine = make_affine_camera()
    model = GameModel(runtime.raw, world)

    object_ids = ("tap_start", "solar_start", "tree_02", "grass_01")
    for object_id in object_ids:
        obj = model.world.object_by_id(object_id)
        assert obj is not None
        assert affine.project(Vec3(obj.x, 0.0, obj.z)) is not None

    normal_enemy = next(enemy for enemy in model.enemies if enemy.kind == "normal")
    abnormal_enemy = next(enemy for enemy in model.enemies if enemy.kind == "abnormal")
    assert affine.project(Vec3(normal_enemy.x, 0.0, normal_enemy.z)) is not None
    assert affine.project(Vec3(abnormal_enemy.x, 0.0, abnormal_enemy.z)) is not None

    assert model.world.ground_details == ()
    patch = next(
        item for item in model.world.baked_ground_patches if item.group == "affine_static_128"
    )
    assert affine.project(Vec3(patch.x, 0.0, patch.z)) is not None


def test_affine_fallback_screen_radii_do_not_depend_on_depth() -> None:
    _runtime, _world, _perspective, _profile, affine = make_affine_camera()
    renderer = Renderer(None)

    near = renderer.depth_scaled_radius(affine, 96.0, numerator=1200.0, minimum=3)
    far = renderer.depth_scaled_radius(affine, 900.0, numerator=1200.0, minimum=3)

    assert near == far == 3


def test_affine_solid_box_expands_to_depth_sorted_face_commands() -> None:
    _runtime, world, _perspective, _profile, affine = make_affine_camera()
    renderer = Renderer(None)
    wall = world.object_by_id("wall_01")
    assert wall is not None

    commands = renderer.solid_box_face_commands(wall, affine)
    stable_ids = {command.stable_id for command in commands}

    assert len(commands) == 5
    assert stable_ids == {
        "wall_01:top",
        "wall_01:north",
        "wall_01:east",
        "wall_01:south",
        "wall_01:west",
    }
    assert all(math.isfinite(command.depth) for command in commands)
    assert len({command.depth for command in commands}) > 1


def test_affine_world_commands_split_solid_boxes_but_perspective_keeps_single_box() -> None:
    runtime, world, _perspective, profile, _affine = make_affine_camera()
    model = GameModel(runtime.raw, world)
    renderer = Renderer(None)
    target = Vec3(320.0, 0.0, 320.0)
    perspective = CameraState.from_config(
        runtime.raw,
        target,
        runtime.screen_width,
        runtime.screen_height,
    )
    affine = affine_camera_from_perspective(
        perspective,
        profile,
        base_distance=float(runtime.raw["camera"]["base_distance"]),
    )

    perspective_ids = {
        command.stable_id for command in renderer.world_commands(model, perspective, 0.0)
    }
    affine_ids = {command.stable_id for command in renderer.world_commands(model, affine, 0.0)}

    assert "wall_01" in perspective_ids
    assert "wall_01:top" not in perspective_ids
    assert "wall_01" not in affine_ids
    assert {"wall_01:top", "wall_01:north", "wall_01:east"}.issubset(affine_ids)


def test_affine_solid_sprite_visual_binding_keeps_collision_box() -> None:
    runtime, world, _perspective, profile, _affine = make_affine_camera()
    model = GameModel(runtime.raw, world)
    renderer = Renderer(None)
    root = world.object_by_id("wall_02")
    assert root is not None
    assert root.solid
    assert root.visual == "giant_tree_root_arch_a"
    assert root.half_x == pytest.approx(48.0)
    assert root.half_z == pytest.approx(16.0)
    assert root.sprite_world_width == pytest.approx(110.0)
    assert root.sprite_world_height == pytest.approx(110.0)
    assert root.occludes_player
    assert not renderer.object_uses_box_geometry(root)

    perspective = CameraState.from_config(
        runtime.raw,
        Vec3(root.x, 0.0, root.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    affine = affine_camera_from_perspective(
        perspective,
        profile,
        base_distance=float(runtime.raw["camera"]["base_distance"]),
    )
    affine_ids = {command.stable_id for command in renderer.world_commands(model, affine, 0.0)}

    assert "wall_02" in affine_ids
    assert "wall_02:top" not in affine_ids
    assert "wall_02:north" not in affine_ids

    giant_tree = world.object_by_id("wall_03")
    assert giant_tree is not None
    assert giant_tree.solid
    assert giant_tree.visual == "giant_tree_02x_c"
    assert giant_tree.x == pytest.approx(640.0)
    assert giant_tree.half_x == pytest.approx(16.0)
    assert giant_tree.half_z == pytest.approx(48.0)
    assert giant_tree.sprite_world_width == pytest.approx(192.0)
    assert giant_tree.sprite_world_height == pytest.approx(192.0)
    assert not renderer.object_uses_box_geometry(giant_tree)

    perspective = CameraState.from_config(
        runtime.raw,
        Vec3(giant_tree.x, 0.0, giant_tree.z),
        runtime.screen_width,
        runtime.screen_height,
    )
    affine = affine_camera_from_perspective(
        perspective,
        profile,
        base_distance=float(runtime.raw["camera"]["base_distance"]),
    )
    affine_ids = {command.stable_id for command in renderer.world_commands(model, affine, 0.0)}

    assert "wall_03" in affine_ids
    assert "wall_03:top" not in affine_ids
    assert "wall_03:north" not in affine_ids


def test_affine_solid_box_occludes_player_with_projected_bounds() -> None:
    runtime, world, _perspective, _profile, affine = make_affine_camera()
    model = GameModel(runtime.raw, world)
    renderer = Renderer(None)

    model.player.x = 272.0
    model.player.z = 288.0
    assert not world.collides_player(
        model.player.x,
        model.player.z,
        model.player_half_x,
        model.player_half_z,
    )

    assert renderer.player_is_occluded(model, affine, 0.0)


def test_affine_atmosphere_palette_depth_preserves_gameplay_entities() -> None:
    runtime, _world, perspective, _profile, affine = make_affine_camera()
    renderer = Renderer(None)
    renderer._atmosphere_config = runtime.raw["atmosphere"]
    far_depth = affine.profile.reference_depth + 220.0

    assert renderer.atmosphere_palette_mappings(perspective, far_depth, 1.0) == ()
    assert renderer.atmosphere_palette_mappings(affine, far_depth, 0.1) == ()
    assert renderer.atmosphere_palette_mappings(affine, far_depth, 0.35) == ATMOSPHERE_WEAK_PALETTE
    assert renderer.atmosphere_palette_mappings(affine, far_depth, 1.0) == ATMOSPHERE_FAR_PALETTE
    far_targets = {target for _source, target in ATMOSPHERE_FAR_PALETTE}
    assert 1 not in far_targets
    assert 13 in far_targets
    assert ATMOSPHERE_DITHER_FOG_COLOR == 13
    assert ATMOSPHERE_FAR_DITHER_CELLS == 4


def test_affine_atmosphere_palette_has_near_mid_far_bands() -> None:
    runtime, _world, _perspective, _profile, affine = make_affine_camera()
    renderer = Renderer(None)
    renderer._atmosphere_config = runtime.raw["atmosphere"]
    reference = affine.profile.reference_depth

    assert renderer.atmosphere_palette_mappings(affine, reference + 32.0, 1.0) == ()
    assert renderer.atmosphere_palette_mappings(affine, reference + 96.0, 1.0)
    assert renderer.atmosphere_palette_mappings(affine, reference + 220.0, 1.0)
    assert renderer.atmosphere_palette_mappings(
        affine, reference + 96.0, 1.0
    ) != renderer.atmosphere_palette_mappings(affine, reference + 220.0, 1.0)


def test_affine_atmosphere_dither_interpolates_between_depth_bands() -> None:
    runtime, _world, perspective, _profile, affine = make_affine_camera()
    renderer = Renderer(None)
    renderer._atmosphere_config = runtime.raw["atmosphere"]
    reference = affine.profile.reference_depth
    near_offset = runtime.raw["atmosphere"]["near_depth_offset"]
    far_offset = runtime.raw["atmosphere"]["far_depth_offset"]
    midpoint = reference + (near_offset + far_offset) / 2.0

    assert renderer.atmosphere_dither_cells(perspective, reference + 220.0, 1.0) == 0
    assert renderer.atmosphere_dither_cells(affine, reference + 32.0, 1.0) == 0
    assert renderer.atmosphere_dither_cells(affine, midpoint, 1.0) == ATMOSPHERE_MID_DITHER_CELLS
    assert (
        renderer.atmosphere_dither_cells(affine, reference + 220.0, 1.0)
        == ATMOSPHERE_FAR_DITHER_CELLS
    )
    samples = [
        renderer.atmosphere_dither_cells(
            affine,
            reference + near_offset + (far_offset - near_offset) * index / 10.0,
            1.0,
        )
        for index in range(11)
    ]
    assert samples[0] == 0
    assert samples[-1] == ATMOSPHERE_FAR_DITHER_CELLS
    assert samples == sorted(samples)
    assert len(set(samples)) >= min(6, ATMOSPHERE_FAR_DITHER_CELLS + 1)
    assert renderer.atmosphere_dither_cells(affine, reference + 220.0, 0.7) == round(
        ATMOSPHERE_FAR_DITHER_CELLS * 0.7
    )
    assert renderer.atmosphere_dither_cells(affine, reference + 220.0, 0.35) == 0


def test_affine_atmosphere_shadow_attenuates_by_depth() -> None:
    runtime, _world, perspective, _profile, affine = make_affine_camera()
    renderer = Renderer(None)
    renderer._atmosphere_config = runtime.raw["atmosphere"]
    reference = affine.profile.reference_depth

    assert renderer.atmosphere_shadow_dither_cells(perspective, reference + 220.0) == 16
    assert (
        renderer.atmosphere_shadow_dither_cells(affine, reference + 32.0)
        == ATMOSPHERE_SHADOW_NEAR_CELLS
    )
    assert (
        renderer.atmosphere_shadow_dither_cells(affine, reference + 96.0)
        == ATMOSPHERE_SHADOW_MID_CELLS
    )
    assert (
        renderer.atmosphere_shadow_dither_cells(affine, reference + 220.0)
        == ATMOSPHERE_SHADOW_FAR_CELLS
    )
    assert (
        renderer.atmosphere_shadow_dither_cells(affine, reference + 220.0, important_actor=True)
        == ATMOSPHERE_SHADOW_IMPORTANT_MIN_CELLS
    )


def test_affine_atmosphere_tuning_keeps_gameplay_entities_readable() -> None:
    runtime, world, _perspective, _profile, affine = make_affine_camera()
    model = GameModel(runtime.raw, world)
    renderer = Renderer(None)
    renderer._atmosphere_config = runtime.raw["atmosphere"]

    tree = world.object_by_id("tree_01")
    station = world.object_by_id("tap_start")
    wall = world.object_by_id("wall_01")
    assert tree is not None and station is not None and wall is not None

    assert renderer.object_atmosphere_strength(tree) == ATMOSPHERE_NATURE_PROP_STRENGTH
    assert renderer.object_atmosphere_strength(station) == ATMOSPHERE_EQUIPMENT_STRENGTH
    assert renderer.object_atmosphere_strength(wall) == ATMOSPHERE_SOLID_STRENGTH

    commands = renderer.world_commands(model, affine, 0.0)
    strengths = {command.stable_id: command.atmosphere_strength for command in commands}
    enemy_id = next(enemy.id for enemy in model.enemies)

    assert strengths["player"] == ATMOSPHERE_PLAYER_STRENGTH
    assert strengths["buddy"] == ATMOSPHERE_BUDDY_STRENGTH
    assert strengths[enemy_id] == ATMOSPHERE_ENEMY_STRENGTH
    assert not any(key.startswith("ground_detail:") for key in strengths)
    assert strengths["player"] < strengths[enemy_id] < renderer.object_atmosphere_strength(tree)
    assert strengths["buddy"] < strengths[enemy_id]


def test_atmosphere_dither_frame_preserves_colkey_and_reuses_cache() -> None:
    source = FakeImage(8, 8)
    for y in range(8):
        for x in range(8):
            source.pset(x, y, 2)
    source.pset(0, 1, 8)
    frame = LoadedSpriteFrame(
        frame_id="idle_00",
        image=source,
        source=None,
        u=0,
        v=0,
        width=8,
        height=8,
        source_hash="source-hash",
    )
    definition = SpriteDefinition(
        asset_id="tree_test",
        palette_id="pyxel_default_16",
        hex_width=8,
        hex_height=8,
        colkey=8,
        anchor_px=(4.0, 8.0),
        world_size=(8.0, 8.0),
        projection_mode="upright_height_billboard_v1",
        flip_policy="none",
        animation="static",
        frames=(SpriteFrameDefinition(frame_id="idle_00"),),
        source_hash="source-hash",
    )
    asset = LoadedSpriteAsset(definition=definition, frames={"idle_00": frame})
    renderer = Renderer(FakePyxel())
    renderer._active_atmosphere_dither_cells = ATMOSPHERE_FAR_DITHER_CELLS
    renderer._active_atmosphere_dither_fog_color = ATMOSPHERE_DITHER_FOG_COLOR

    derived = renderer.atmospheric_sprite_frame(asset, frame)
    assert derived is renderer.atmospheric_sprite_frame(asset, frame)
    assert derived.image.pget(0, 1) == 8
    for start_x, start_y in ((0, 0), (4, 0), (0, 4), (4, 4)):
        quadrant = [
            derived.image.pget(x, y)
            for y in range(start_y, start_y + 4)
            for x in range(start_x, start_x + 4)
            if (x, y) != (0, 1)
        ]
        assert ATMOSPHERE_DITHER_FOG_COLOR in quadrant
        assert 2 in quadrant


def test_affine_camera_ignores_source_yaw_pitch_but_keeps_target_anchor_and_zoom() -> None:
    runtime, _world, _perspective, profile, _affine = make_affine_camera()
    base_distance = float(runtime.raw["camera"]["base_distance"])
    source = CameraState(
        target=Vec3(768.0, 0.0, 768.0),
        yaw_deg=35.0,
        pitch_deg=10.0,
        horizontal_fov_deg=float(runtime.raw["camera"]["horizontal_fov_deg"]),
        distance=base_distance / 0.7,
        near=float(runtime.raw["camera"]["near"]),
        far=float(runtime.raw["camera"]["far"]),
        anchor_x=0.42,
        anchor_y=0.61,
        viewport_width=runtime.screen_width,
        viewport_height=runtime.screen_height,
    )

    affine = affine_camera_from_perspective(source, profile, base_distance=base_distance)

    assert affine.target == source.target
    assert affine.anchor_x == pytest.approx(source.anchor_x)
    assert affine.anchor_y == pytest.approx(source.anchor_y)
    assert affine.zoom == pytest.approx(0.7)
    assert affine.yaw_deg == pytest.approx(float(runtime.raw["camera"]["yaw_deg"]))
    assert affine.pitch_deg == pytest.approx(float(runtime.raw["camera"]["pitch_deg"]))
