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

Ground assets were connected on 2026-09-14 from the extracted ground v0.2 pack:

- `concrete_clean_a`: source hash `e2b5cfa4caafd4a1d5f3050d5033a5547c5e8251befba4a2467f1edee39c8640`
- `concrete_cracked_a`: source hash `442d6e57264e39e5f3ac2718db6fb2ec8ae804748cf39b4922c967063b93658e`
- `concrete_spalled_a`: source hash `bdfc8389a72a6e9cf8ba3ec68874e5e322204155c4dc9a93e7bfa21aec96ff31`
- `concrete_joint_grass_a`: source hash `a759a7227455db825b88adfaf08399941dbd1bb6c1515d516b2174a6916a0514`
- `decal_stain_a`: source hash `01afbe6d0e3b35d3ce16cf6d26531dbb679072cb667f27004821be99a3669f66`
- `decal_crack_grass_a`: source hash `10c2354747798a9237d874b9d085134d4327a1d6912d089afa55ca074ddbcdc7`
- `decal_rubble_a`: source hash `2a2208d7ab8319fcde96af649212d55db8dfb05652b82b15a1ddfe1f1ce56329`
- `decal_broken_edge_a`: source hash `95ae5cf54fc533ce45a78d9c089c55da88b19d60b5708992c05e03346732368a`

The concrete base sources are opaque 64 x 64 ground materials and contain no color index `8`. The current runtime source-asset schema still stores `colkey: 8` for these base tiles because it requires an integer `colkey`; this has no visual effect while the source contains no `8` pixels. Decals use `8` as transparency, and color `0` remains visible black.

Tree assets were updated again on 2026-09-14 from the extracted tree v0.2 pack:

- `tree_leafy_a`: source hash `a868d992db8472f81045ada9a39cb6893ad88d2d320aa226264868e3a5d8ffe4`
- `tree_thin_b`: source hash `68de99d52511238f5ecbad7314e1cdeaa591dbf56916b17a86d0d00866a88e80`

Both extracted tree sources use `8` as the only transparent color. Color `0` is visible black and must not be treated as transparency. The billboard anchor is `(48, 127)`.

The ground v0.2 pack is connected only as three review surfaces near the start area:

- `concrete_clean_a`
- `concrete_clean_a` + `decal_crack_grass_a`
- `concrete_spalled_a` + `decal_stain_a` + `decal_rubble_a`

This is a first visual review path for the approved board extraction. Full-road tiling, pavement transitions, intersections, and automatic density placement remain deferred.

## Runtime Loading

The existing `assets/jack_sprite.pyxres` remains the source for baked character and enemy sprites.

Environment Wave1 assets are added to `assets/jack_sprite.json` as `source_assets`. At runtime:

1. Pyxel loads the existing `.pyxres` with tilemaps, sounds, and music excluded.
2. The HEX `source_assets` are parsed once at startup.
3. Each HEX source is copied into a cached `pyxel.Image`.
4. Drawing reuses those images each frame.

This avoids overwriting existing image banks and keeps the Wave1 source pixels as received.

## World Size And Projection

Transparent sprites use their asset-specific `colkey`. Most Wave1 transparent sprites use `0`; the extracted equipment v0.2, tree v0.2, and ground decal v0.2 assets use `8` so color `0` can remain visible black.

| Asset group | Projection | Runtime world size |
| --- | --- | --- |
| Water stations | `upright_height_billboard_v1` | 36 x 48 |
| Solar stations | `upright_height_billboard_v1` | 36 x 48 |
| Trees | `upright_height_billboard_v1` | 48 x 64 |
| Tall grass | `upright_height_billboard_v1` | 24 x 24 |
| Low grass | `upright_height_billboard_v1` | 28 x 28 |
| Ground pebbles/leaves/crack grass | `ground_decal_source_v1` | 32 x 32 |
| Ground rubble | `ground_decal_source_v1` | 40 x 32 |
| Ground v0.2 concrete/decal review surfaces | `ground_decal_source_v1` | 32 x 32 |

Water station source art is 96 x 128. The supplied recommendation was 32 x 48, but the runtime uses 36 x 48 to preserve the source aspect ratio under Pyxel's uniform `blt` scale.

Grass recommendations were non-square, but the current billboard path is also uniform scale. Tall grass uses 24 x 24 and low grass uses 28 x 28 as a first review size rather than anisotropically stretching the pixels.

Ground small objects and the v0.2 review surfaces use `ground_decal_source_v1`, which samples opaque HEX pixels and projects them onto the X/Z ground plane. This is intentionally separate from the vertical billboard path.

## Gameplay Boundaries

No collision, AI, input, camera, resource, or SE behavior was changed.

World data changes are limited to:

- `visual` identifiers for trees and grass.
- `sprite_world_size` for equipment and grass so visual culling matches the new sprites.
- `ground_surfaces` review entries for the three non-collision ground material comparisons.

## Deferred

- Full-map `ground_material_source` pavement tiling.
- Road, sidewalk, intersection, and transition placement rules.
- Pyxres baking for environment assets.
- iPhone visual/performance verification.
- Seam review for pavement tiles.
