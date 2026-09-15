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

Nature and small ground-detail assets were updated on 2026-09-14 from the clean nature v0.3 pack. These are preferred over the earlier Wave1 small nature sources:

- `grass_tall_a`: source hash `6d0a65997436af94a5b16727f167e81eb26e249887083e9819cad312bb65c243`
- `grass_low_a`: source hash `c117cebf842445c61510bfbf3192997cea3449f2e16e701bad96e64099939964`
- `pebbles_a`: source hash `aef2501b657821f6324812832795d68e136f2295230226e4e8388c135cca3966`
- `fallen_leaves_a`: source hash `f1b36b299cbd6bf2f1dbcb45e514d5603ba5f50e3c177594e1d0bb09dd0684cd`
- `crack_sprout_a`: source hash `31afbd889e88698f704b94d06542c1196eb2be6ccdaa8543ae4bbc057afea7b7`
- `rubble_small_a`: source hash `ba84a6adb25c1272dc677101cbc3e941f629403bd9c9d4ffd980e5ff8e6a590e`

All clean nature v0.3 assets use `8` as the transparent color. Color `0` is visible black and must not be treated as transparency. Existing runtime keys now resolve to these v0.3 assets: `reactive_grass_tall` -> `grass_tall_a`, `ground_pebbles` -> `pebbles_a`, `ground_fallen_leaves` -> `fallen_leaves_a`, `ground_crack_grass` -> `crack_sprout_a`, and `ground_rubble` -> `rubble_small_a`. The `grass_low_a` asset remains available, but the current `reactive_grass_low` runtime key uses the older upright `reactive_grass_low_64` sprite so low grass does not appear as a floor-stuck decal during the current review.

Grassland direct v0.1 assets were connected on 2026-09-15. These six sprites are direct extractions from the approved source images, with no redraw, simplification, recolor, or palette replacement:

- `grass_patch_low_a`: source hash `a15dc2ea6edb1a5306b358136ff37cb463158ed6ce764af7beae7b114202a07e`
- `grass_patch_low_b`: source hash `854dfd407874d091f6c5eab0757d058f3da8999a24fed7f9c27b2ccb078b5218`
- `grass_patch_tall_a`: source hash `2acf33ebd448bf4757960169e4583df102fb580a4acafec83457a3b7328f482a`
- `grass_patch_tall_b`: source hash `d5e0c7fc7e59a647472e050dae934904af2ffc7eb19c6e66a10ddcc04d826037`
- `grass_edge_a`: source hash `ab61e3da8b6005d4a11eb5c1a446a6e7b279aea8422138895d38f11b51fbd977`
- `grass_scatter_a`: source hash `8eaca3d8803852bea6446d34211cb05cfa2921fbb5ea76d99fc211156ffe99a8`

All grassland direct v0.1 sprites use `8` as the transparent color. Color `0` is visible black and must not be treated as transparency. The low grass, edge, and scatter assets remain available in the manifest, but their authored `ground_details` placements were removed after the grassland prototype review because the large source sprites read as flattened floor decals under affine projection. The two tall grass assets remain `reactive_prop` upright billboards and use the existing AFF007-C bending path.

After the initial v0.3 connection, the random per-chunk ground-detail generation was disabled (`visual_detail_per_chunk: 0`) because each 64 x 64 ground-projected source is expensive to project per frame in Pyxel Web. The authored one-each review placements were later removed from `ground_details` for the current visual pass.

On 2026-09-14, fixed-camera baked ground patch probes were added around the player spawn. They are intentionally runtime-generated caches, not new `.pyxres` or tilemap resources yet. The renderer samples the existing ground material/decal HEX sources into pre-projected images for the normal FOLLOW camera and draws those images with `blt`. While a patch is active, the legacy per-pixel ground projections inside the same world area are skipped. This gives us a low-risk performance probe before committing to generated `.pyxres`/`bltm` assets.

The first `192 x 192` single patch proved very fast but visibly wrong: it reused one large projected ground image with screen-space translation only, so the internal perspective drifted and looked like a sliding board. That patch remains in data as `spawn_affine_ground_patch` with group `spawn_192_legacy_compare`, but it is disabled by default for comparison.

The follow-up `64 x 64` patch split reduced the visible perspective error, but zoom, camera bucket changes, and patch rebuild latency still made the ground texture read as a separate projected layer. As a result, all baked ground patches are now disabled by default and kept only as a comparison experiment in data:

- `spawn_affine_ground_patch`, group `spawn_192_legacy_compare`, disabled.
- 4 `128 x 128` patches in group `affine_static_128`, disabled.
- 9 `64 x 64` patches in group `spawn_64_bucket16`, disabled.
- Baked patch renderer code remains available for future experiments, but it is not the current visual baseline.

Native headless reference measurements from the disabled 64 patch experiment:

- 9 enabled patches, cache image sizes about `58 x 27` to `75 x 34`, drawn 2x.
- First build total for 9 patches: about `107 ms`, spread across 9 frames by default.
- Warm baked draw: about `0.15 ms/frame`.
- Legacy review ground sources plus authored details: about `14.59 ms/frame`.
- These are local headless measurements, not iPhone/Web runtime FPS guarantees.

The current visual baseline is a map-wide gray ground undercoat plus the grassland micro prototype where configured. The broad `ground_surfaces` pavement review entries are disabled, and the authored `ground_details` list is currently empty. Small pebbles, fallen leaves, crack sprout, and rubble assets remain available, but their world placements were removed after review because they read as dirty road damage in the current prototype.

On 2026-09-15, a fixed-affine grassland micro prototype was added. This is not a new grass source asset and does not alter the received HEX pixels. It draws configured grassland rectangles as a green base plus 5-6 logical-pixel grass marks. After review, the marks were changed from screen-tile phase repetition to deterministic world-cell clumps: each tiny blade root is fixed in world X/Z, projected once, and drawn upright in screen space. This prevents the texture from reading like a HUD overlay while still avoiding per-pixel ground projection. After the 2026-09-16 review, this layer remains enabled for grassland testing (`grassland_micro.enabled: true`), covers the current grassland area from `z=256` through the far map edge, and culls clump generation to the affine screen-visible world range. It should not be confused with the removed road-crack/rubble ground details.

The renderer clears gameplay frames with the same gray color used by `draw_ground()` (`13`). This prevents uncovered map edges or out-of-world screen areas from switching to the old dark indigo clear color when the camera crosses certain positions.

AFF007-B adds the first static/dynamic environment split. Reactive environment props remain static world objects for collision and rendering, but `WorldData` now indexes `reactive_prop` entries by chunk and `EffectSystem` queries only Jack's world-space neighborhood before promoting a prop into a short-lived active state. The active state stores trigger radius, visual radius, reaction strength, movement direction, and recovery progress for future grass/reed/water/hanging-object animation waves. This replaces the old full `world.objects` scan used by grass burst reactions without changing collision, pathing, camera, source sprites, or the current visible grass asset.

AFF007-C connects that active state to grass rendering. Tall upright grass is drawn from the received HEX source with row-wise screen displacement only while active, so the top bends in Jack's movement direction and then recovers. The current placed low grass also uses an upright billboard path to avoid floor-stuck grass silhouettes. The static sprite path remains unchanged when no active state exists, and the behavior still does not affect collision, pathing, camera, source pixels, or SE.

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

Transparent sprites use their asset-specific `colkey`. Most Wave1 transparent sprites use `0`; the extracted equipment v0.2, tree v0.2, clean nature v0.3, and ground decal v0.2 assets use `8` so color `0` can remain visible black.

| Asset group | Projection | Runtime world size |
| --- | --- | --- |
| Water stations | `upright_height_billboard_v1` | 36 x 48 |
| Solar stations | `upright_height_billboard_v1` | 36 x 48 |
| Trees | `upright_height_billboard_v1` | 48 x 64 |
| Tall grass v0.3 | `upright_height_billboard_v1` | 28 x 28 |
| Low grass v0.3 | available, not currently placed | 28 x 18 |
| Reactive low grass | `upright_height_billboard_v1` | 28 x 28 |
| Pebbles v0.3 | `ground_decal_source_v1` | 22 x 14 |
| Fallen leaves v0.3 | `ground_decal_source_v1` | 26 x 16 |
| Crack sprout v0.3 | `ground_decal_source_v1` | 28 x 18 |
| Small rubble v0.3 | `ground_decal_source_v1` | 32 x 20 |
| Grass patch low A/B v0.1 | `ground_decal_source_v1` | 42 x 20 |
| Grass edge v0.1 | `ground_decal_source_v1` | 48 x 28 |
| Grass scatter v0.1 | `ground_decal_source_v1` | 44 x 24 |
| Grass patch tall A v0.1 | `upright_height_billboard_v1` | 46 x 46 |
| Grass patch tall B v0.1 | `upright_height_billboard_v1` | 52 x 52 |
| Ground v0.2 concrete/decal review surfaces | `ground_decal_source_v1` | 32 x 32 |

Water station source art is 96 x 128. The supplied recommendation was 32 x 48, but the runtime uses 36 x 48 to preserve the source aspect ratio under Pyxel's uniform `blt` scale.

Tall grass remains an upright billboard. The current reactive low grass also uses an upright billboard to preserve the original sprite silhouette on screen. The clean low grass and small nature props remain ground-projected assets for later review, but they are not placed in the current prototype.

Ground small objects and the v0.2 review surfaces use `ground_decal_source_v1`, which samples opaque HEX pixels and projects them onto the X/Z ground plane. This is intentionally separate from the vertical billboard path.

The grassland pack recommends `32 x 46` and `28 x 52` for the two tall grass billboards. The current upright billboard loader and Pyxel `blt` path use uniform scaling and require the runtime world aspect ratio to match the 64 x 64 source canvas, so the first connection keeps the intended heights and uses square runtime sizes (`46 x 46`, `52 x 52`). Preserving narrower visual widths for these upright sprites requires a later non-uniform or row-sliced drawing path.

## Gameplay Boundaries

No collision, AI, input, camera, resource, or SE behavior was changed.

World data changes are limited to:

- `visual` identifiers for trees and grass.
- `sprite_world_size` for equipment and grass so visual culling matches the new sprites.
- `ground_surfaces` is empty; large pavement review sheets are no longer active by default.
- `ground_details` is empty for the current prototype; sparse pebbles, fallen leaves, crack sprout, and small rubble assets are retained but not placed.
- Grassland v0.1 low grass, edge, and scatter `ground_details` are currently not placed in the world because they are too large to read cleanly as ground-projected floor sprites.
- `grassland_micro.enabled` is `true` so the current grassland micro surface test remains visible.
- `objects` includes multiple upright grass `reactive_prop` entries for low grass and grassland tall grass. They are visual-only and do not change collision or pathing.
- `visual_detail_per_chunk` is `0`; random small-detail scatter is deferred until a cheaper tiling/sprite path is available.

## Deferred

- Full-map `ground_material_source` pavement tiling.
- Road, sidewalk, intersection, and transition placement rules.
- Pyxres baking for environment assets.
- iPhone visual/performance verification.
- Seam review for pavement tiles.
