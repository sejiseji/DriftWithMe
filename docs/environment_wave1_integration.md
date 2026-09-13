# Environment Wave1 Integration

Date: 2026-09-14
Base HEAD before work: d78e6cd

## Scope

Integrated the following DriftWithMe Environment Wave1 v0.1 HEX source assets:

- `water_station_active`
- `water_station_stopped`
- `solar_station_idle`
- `solar_station_active`
- `tree_leafy_a`
- `tree_thin_b`
- `reactive_grass_tall`
- `reactive_grass_low`
- `ground_pebbles`
- `ground_fallen_leaves`
- `ground_crack_grass`
- `ground_rubble`

Tree assets were updated on 2026-09-14 from the tree fix v0.1 pack:

- `tree_leafy_a`: source hash `b2869ada09a121eaa379f0d79953a56b02690a8c3037b019386ff586c36f06c6`
- `tree_thin_b`: source hash `f2dfa10bd7188dbf06beceab48ccca8f8f6a0b91e5030500512f5ca570b65229`

Both fixed tree sources use visible colors `1`, `3`, `4`, `5`, `B`, and `D`; `0` remains the only transparent color.

The Wave1 `ground/` material and decal pack remains deferred. Those assets are ground material sources, not vertical billboards, and need a separate ground rendering review before connection.

## Runtime Loading

The existing `assets/jack_sprite.pyxres` remains the source for baked character and enemy sprites.

Environment Wave1 assets are added to `assets/jack_sprite.json` as `source_assets`. At runtime:

1. Pyxel loads the existing `.pyxres` with tilemaps, sounds, and music excluded.
2. The HEX `source_assets` are parsed once at startup.
3. Each HEX source is copied into a cached `pyxel.Image`.
4. Drawing reuses those images each frame.

This avoids overwriting existing image banks and keeps the Wave1 source pixels as received.

## World Size And Projection

All transparent sprites use `colkey` 0.

| Asset group | Projection | Runtime world size |
| --- | --- | --- |
| Water stations | `upright_height_billboard_v1` | 36 x 48 |
| Solar stations | `upright_height_billboard_v1` | 36 x 48 |
| Trees | `upright_height_billboard_v1` | 48 x 64 |
| Tall grass | `upright_height_billboard_v1` | 24 x 24 |
| Low grass | `upright_height_billboard_v1` | 28 x 28 |
| Ground pebbles/leaves/crack grass | `ground_decal_source_v1` | 32 x 32 |
| Ground rubble | `ground_decal_source_v1` | 40 x 32 |

Water station source art is 96 x 128. The supplied recommendation was 32 x 48, but the runtime uses 36 x 48 to preserve the source aspect ratio under Pyxel's uniform `blt` scale.

Grass recommendations were non-square, but the current billboard path is also uniform scale. Tall grass uses 24 x 24 and low grass uses 28 x 28 as a first review size rather than anisotropically stretching the pixels.

Ground small objects use `ground_decal_source_v1`, which samples opaque HEX pixels and projects them onto the X/Z ground plane. This is intentionally separate from the vertical billboard path.

## Gameplay Boundaries

No collision, AI, input, camera, resource, or SE behavior was changed.

World data changes are limited to:

- `visual` identifiers for trees and grass.
- `sprite_world_size` for equipment and grass so visual culling matches the new sprites.

## Deferred

- `ground_material_source` pavement tiles.
- Wave1 `ground/` decals.
- Pyxres baking for environment assets.
- iPhone visual/performance verification.
- Seam review for pavement tiles.
