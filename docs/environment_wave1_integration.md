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

Equipment assets were updated again on 2026-09-14 from the extracted equipment v0.2 pack:

- `water_station_active`: source hash `0cd8570bfe0fd3d6dd1b96ab409c36a28f3bddaf6c42d2e1ef4521a87a94c0f1`
- `water_station_stopped`: source hash `f5a8ae8eed5e4b5ec7d9f22b4abc76fe59860482efba1a91c775c5f48d3b0309`
- `solar_station_idle`: source hash `f5a7fc5bb95ae14b0f3b7923327b8180a9430f240c37ebb15cd40e89d29dd7f1`
- `solar_station_active`: source hash `748b9391dc51f2423ccdcd5424824391aeec83583e9ddcc3b46067b8f5492c3f`

The extracted equipment sources use `8` as the only transparent color. Color `0` is visible black and must not be treated as transparency. The billboard anchor is `(48, 127)`.

Tree assets were updated again on 2026-09-14 from the extracted tree v0.2 pack:

- `tree_leafy_a`: source hash `a868d992db8472f81045ada9a39cb6893ad88d2d320aa226264868e3a5d8ffe4`
- `tree_thin_b`: source hash `68de99d52511238f5ecbad7314e1cdeaa591dbf56916b17a86d0d00866a88e80`

Both extracted tree sources use `8` as the only transparent color. Color `0` is visible black and must not be treated as transparency. The billboard anchor is `(48, 127)`.

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

Transparent sprites use their asset-specific `colkey`. Most Wave1 transparent sprites use `0`; the extracted equipment v0.2 and tree v0.2 assets use `8` so color `0` can remain visible black.

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
