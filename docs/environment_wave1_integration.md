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

All clean nature v0.3 assets use `8` as the transparent color. Color `0` is visible black and must not be treated as transparency. Existing runtime keys now resolve to these v0.3 assets: `reactive_grass_tall` -> `grass_tall_a`, `reactive_grass_low` -> the upright `grass_low_a_upright_64` metadata variant, `ground_pebbles` -> `pebbles_a`, `ground_fallen_leaves` -> `fallen_leaves_a`, `ground_crack_grass` -> `crack_sprout_a`, and `ground_rubble` -> `rubble_small_a`. `grass_low_a_upright_64` uses the same received `grass_low_a.hex` pixels as the ground-decal definition, but keeps low grass as an upright billboard so it does not appear as a floor-stuck decal during the current review.

Grassland direct v0.1 assets were connected on 2026-09-15. These six sprites are direct extractions from the approved source images, with no redraw, simplification, recolor, or palette replacement:

- `grass_patch_low_a`: source hash `a15dc2ea6edb1a5306b358136ff37cb463158ed6ce764af7beae7b114202a07e`
- `grass_patch_low_b`: source hash `854dfd407874d091f6c5eab0757d058f3da8999a24fed7f9c27b2ccb078b5218`
- `grass_patch_tall_a`: source hash `2acf33ebd448bf4757960169e4583df102fb580a4acafec83457a3b7328f482a`
- `grass_patch_tall_b`: source hash `d5e0c7fc7e59a647472e050dae934904af2ffc7eb19c6e66a10ddcc04d826037`
- `grass_edge_a`: source hash `ab61e3da8b6005d4a11eb5c1a446a6e7b279aea8422138895d38f11b51fbd977`
- `grass_scatter_a`: source hash `8eaca3d8803852bea6446d34211cb05cfa2921fbb5ea76d99fc211156ffe99a8`

All grassland direct v0.1 sprites use `8` as the transparent color. Color `0` is visible black and must not be treated as transparency. The low grass, edge, and scatter assets remain available in the manifest, but their authored `ground_details` placements were removed after the grassland prototype review because the large source sprites read as flattened floor decals under affine projection. The two tall grass assets remain `reactive_prop` upright billboards, but the runtime deformation path is disabled by default because the row-sliced bend pass introduced visible grid artifacts on these authored sprites.

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

On 2026-09-15, a fixed-affine grassland micro prototype was added. This is not a new grass source asset and does not alter the received HEX pixels. It draws configured grassland rectangles as a green base plus 5-6 logical-pixel grass marks. After review, the marks were changed from screen-tile phase repetition to deterministic world-cell clumps: each tiny blade root is fixed in world X/Z, projected once, and drawn upright in screen space. This prevents the texture from reading like a HUD overlay while still avoiding per-pixel ground projection. After the 2026-09-16 review, this layer remains enabled for grassland testing (`grassland_micro.enabled: true`), covers the current map review area including the north and south sides, and extends to `-256..1280` as a visual undercoat so camera framing at the map edge does not expose the gray clear color. It still culls clump generation to the affine screen-visible world range. The micro blades now use deterministic hash variation per world cell rather than a four-pattern repeat. The temporary large low-frequency green variation patches were disabled after they read as mechanical rectangular mask changes. The grassland micro layer should not be confused with the removed road-crack/rubble ground details.

The renderer clears gameplay frames with the same gray color used by `draw_ground()` (`13`). This prevents uncovered map edges or out-of-world screen areas from switching to the old dark indigo clear color when the camera crosses certain positions.

On 2026-09-16, BND001 split the former single `world.width/depth` responsibility into explicit world bounds. `walkable_rect_xz` is the gameplay movement and pathing area, `camera_target_rect_xz` clamps FOLLOW/lookahead targets, `visual_ground_rect_xz` is the extended undercoat used by base ground and grassland micro, `content_rect_xz` is the static/chunk management area, and `minimap_rect_xz` remains the user-facing map normalization area. The current prototype values keep walkable/camera/minimap at `0..1024` while visual/content extend to `-256..1280`. The grassland micro area now references `visual_ground` instead of carrying its own temporary `-256..1280` rectangle.

During the current prototype review, the walkable boundary is drawn as a development cue even when the full debug overlay is off. This line uses `walkable_rect_xz`, not `visual_ground_rect_xz`, so the player can distinguish the extended scenic ground from the playable map area. The overlay is controlled by `world_debug.show_walkable_boundary` and can be removed or restyled when final map-edge art is available.

Manual drag movement still derives its world direction from the existing input camera, but when `projection.mode` is `affine` the travel distance is scaled so the resulting affine screen-space speed is close to the left/right reference speed. This compensates for the fixed affine basis where vertical screen drags project to fewer pixels per world unit than horizontal drags. Auto-move, collision, and perspective mode are unchanged.

GRS001 keeps the same grassland micro drawing path but gives the rectangular area a world-space boundary transition. The green base now fills the stable inner rectangle directly, while the outer `32` world units use deterministic world-cell noise at `4` world-unit intervals. The transition is drawn in two coverage layers: a soft intermediate grass color first, then the final grassland base color. Micro grass density uses the same boundary distance: the edge starts at `20%` density and ramps to `100%` in the inner area. The pattern and density are independent of screen coordinates, so camera pan, directional lookahead, and overview framing do not make the grass crawl across the ground. This Wave intentionally does not place `grass_edge_a`, `grass_scatter_a`, new high grass, or any new generic surface framework.

GRS002 keeps the same asset-safety boundary: `grass_edge_a`, `grass_scatter_a`, and low grass ground decals are still not placed because the earlier review showed large floor-projected grass sprites reading as flattened decals. Instead, the micro layer now adds world-space edge irregularity and deterministic density variation. The boundary transition can shift by `edge_irregularity_world` per world cell, and micro blade density is modulated by larger deterministic cells so the surface reads less like an even carpet. These values are fixed from world X/Z plus the area's phase, not from screen position, so camera movement and directional lookahead do not make the pattern crawl. No collision, pathing, source HEX pixels, tall grass billboards, or reactive grass behavior changed in this wave.

ENV002 naturalizes the grassland micro layer without adding new source art or a new surface system. Micro clump cells can now contain zero blades, blade height varies from `2` to `6` logical pixels, and deterministic world hashes select among several small blade shapes. The color mix is weighted toward normal and darker grass (`0.58` primary, `0.34` shadow, `0.08` accent) so the yellow dry blades remain occasional accents instead of an even screen-wide pattern. Inner density remains high, edge density is reduced to `0.14`, and larger density variation now uses `48` world-unit cells with a `0.45..1.0` multiplier. These choices remain world-space deterministic and continue to cull to the affine visible range; camera movement, overview, and directional lookahead do not change the underlying micro placement.

ENV003 is a composition pass over existing world placement data. It does not add a new forest generator, new collision shape, or new tree asset. The north-side tree field keeps its dense outer-rim feel, but the central `520..800 x 720..840` route is kept free of tree roots so Jack, Fuse, the maintenance unit, and the observation post remain readable. The large solid-to-sprite replacements keep their IDs, visuals, and collision extents, but `wall_02` and `wall_03` are moved into broader west/east clearings. Nearby tree and tall-grass positions are nudged away from these landmarks and from `rock_02` so upright billboards do not sit in the same foreground/background slot. Collision and pathing still use the authored AABBs, not the sprite silhouettes.

The approved giant-root stump pack v0.1 supersedes the active obstacle visuals from the earlier direct-extraction review. `rock_02` now uses `giant_tree_root_massive_a`, `rock_01` uses `giant_tree_root_hollow_c`, `wall_02` uses `giant_tree_root_arch_d`, and `wall_03` uses `giant_tree_root_spire_b`. These are all `128x128` HEX sources with `colkey=8`; palette index `0` remains visible black. The pack's non-square recommended display sizes are normalized to square world sizes (`120x120` or `118x118`) because the current HEX loader intentionally preserves the source aspect ratio and rejects non-uniform stretching.

After device review, detached non-colkey islands inside `giant_tree_root_massive_a`, `giant_tree_root_spire_b`, and `giant_tree_root_arch_d` are treated as extraction noise and restored to `colkey=8`. No palette remap, color replacement, or redraw is applied; the cleanup only removes components that are not connected to the main sprite body. `giant_tree_root_hollow_c` had no detached components and remains byte-equivalent to the approved source. The active giant-root obstacles use shallow AABB footprints tuned to the upright sprite edge in the affine view: `52x24` half extents for `120x120` world visuals and `51x24` half extents for `118x118` visuals. This keeps the screen-space collision edge close to the stump/root sprite edge without treating the full vertical billboard rectangle as ground collision. Existing object IDs, pathing rules, and occlusion flags remain the gameplay source of truth.

AFF007-B adds the first static/dynamic environment split. Reactive environment props remain static world objects for collision and rendering, but `WorldData` now indexes `reactive_prop` entries by chunk and `EffectSystem` queries only Jack's world-space neighborhood before promoting a prop into a short-lived active state. The active state stores trigger radius, visual radius, reaction strength, movement direction, and recovery progress for future grass/reed/water/hanging-object animation waves. This replaces the old full `world.objects` scan used by grass burst reactions without changing collision, pathing, camera, source sprites, or the current visible grass asset.

AFF007-C originally connected that active state to grass rendering with a row-wise screen displacement pass. After review, `reactive_environment.upright_deform_enabled` is now `false` by default, so tall grass and reeds are drawn as normal upright billboards even while their nearby active state exists. The current placed low grass also uses an upright billboard path to avoid floor-stuck grass silhouettes. This keeps collision, pathing, camera, source pixels, and SE unchanged while avoiding grid artifacts until a dedicated reaction asset/animation specification is available.

AFF007-C follow-up keeps the same static/dynamic split but refreshes active grass state while Jack remains inside the trigger radius. That state is retained for future use, but the visible upright deformation and split pass are disabled in the current prototype. If reactive tall grass/reeds return later, they should use supplied animation frames or a dedicated overlay asset instead of per-pixel row displacement on the existing authored sprite.

ENV001 stabilizes the current vegetation display contract. Low grass now treats `grass_low_a.hex` as the visual source for the placed `reactive_grass_low` objects through the `grass_low_a_upright_64` metadata variant. This keeps the multi-color received pixels, draws the sprite as an upright billboard, and keeps the object in the same reactive-prop atmosphere/depth path as tall grass. Tall grass and reeds remain upright billboards with no runtime geometry deformation: no shear, row displacement, mesh warp, or pixel-grid bend is applied. The reactive environment active state may still be recorded for future use, but it does not alter the visible sprite until dedicated reaction frames such as `idle`, `bend_left`, `bend_right`, and `recover` are supplied.

ENV004-A adds the reactive vegetation foundation only. Jack's actual world-foot movement is sampled as a swept X/Z segment, and tall grass / reed profiles use enter and exit radii with hysteresis so a plant is promoted only when Jack really crosses or remains inside its contact range. The active state now tracks `IDLE`, `PUSH`, `HOLD`, `REDIRECT`, and `RECOVER` phases plus left/right pose IDs, but `reactive_environment.pose_frames_enabled` remains `false` because no approved bend/recover sprite frames have been delivered. In that state the renderer keeps drawing the existing upright billboard frame, with no runtime shear, rotation, row displacement, duplicated overlay sprite, collision change, root movement, combat-local trigger, or Fuse/enemy trigger. The registered profiles currently target `reactive_grass_tall` / `grass_patch_tall_a` as tall grass and `grass_patch_tall_b` as the reed-like asset; `reactive_grass_low` remains a stable multi-color upright billboard and is not a reactive animation target until explicitly profiled later.

ENV004-B first-pass asset intake audited `ENV004_tall_grass_extraction_first_pass.zip`. The archive contains 7 normalized 64x64 RGBA PNG pose candidates (`idle`, `bend_left_1`, `bend_left_2`, `recover_left`, `bend_right_1`, `bend_right_2`, `recover_right`) plus extraction metadata, but it does not contain fixed Pyxel 16-color HEX sources or a runtime manifest. Each normalized PNG currently contains roughly 1,600-1,950 RGBA colors, so converting it to game HEX would require palette reduction / palette adjustment by Codex. That would violate the current art handoff boundary. The code now supports explicit multi-frame `reactive_pose_set` HEX assets for the approved pose set, but the received first-pass PNG pixels are not connected to production rendering.

ENV004-B1 connects the approved `ENV004B_tall_grass_reactive_HEX_v0.2.zip` pack for `grass_tall_a_64` only. The supplied 7 fixed-palette HEX poses are stored as separate source files (`idle_00`, `bend_left_1`, `bend_left_2`, `recover_left`, `bend_right_1`, `bend_right_2`, `recover_right`) with `64x64` cells, `colkey=8`, and anchor `(32,63)`. `grass_tall_a_64` now uses `animation: reactive_pose_set` and `reactive_environment.pose_frames_enabled` is enabled so the ENV004-A state machine can select the authored pose frame without runtime shear, rotation, row displacement, or overlay duplication. The old `grass_tall_a.hex` source remains in the repository as the v0.3 source-reference file, but runtime rendering for `reactive_grass_tall_asset` uses the coherent v0.2 7-pose set. Reeds (`grass_patch_tall_b`) and the large static tall-grass patch (`grass_patch_tall_a`) still have no approved reactive pose set, so they fall back to their normal upright billboard frame.

ENV004-B1 placement follow-up adds 32 additional small `reactive_grass_tall` instances after device review confirmed the 7-pose motion works. The new instances are deterministic world-data placements concentrated around the meadow-to-forest transition, tree bases, and the northern forest floor. They are non-solid and keep the same `24x24` world size and `reaction_radius=24` as the original `grass_01`, so collision, pathing, camera, combat, and Fuse behavior are unchanged. The existing `grass_01` remains in place as the stable test fixture and nearby query baseline.

The static hard-grass follow-up adds 8 more `grass_patch_tall_b` upright billboard instances around the northern forest edge, giant-tree approach, and east-side meadow. These are visual-only, non-solid placements and intentionally remain outside the reactive pose profile until a dedicated hard-grass/reed animation pack is supplied. They use the existing `52x52` world size, atmospheric depth path, and fixed root/depth anchor; no runtime deformation, collision change, camera change, combat trigger, or new asset source is introduced.

LIGHT001 adds a first static forest-light layer. This is not a dynamic lighting system and does not alter sprites, palette remaps, collision, pathing, camera projection, or atmospheric depth. It draws a sparse deterministic world-space pattern of small light flecks over configured forest/grove rectangles during affine exploration only. The layer is culled to the visible ground range, capped by `forest_light.max_visible_spots`, and hidden during combat so battle timing and zoom transitions are not affected. The current values are intended as a low-risk composition prototype before any future light-shaft, cloud-shadow, or particle work.

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

Tall grass remains an upright billboard. The current reactive low grass also uses an upright billboard metadata variant to preserve the original sprite silhouette on screen while using the multi-color `grass_low_a.hex` source. The clean low grass ground-decal definition and small nature props remain available for later review, but they are not placed in the current prototype.

Ground small objects and the v0.2 review surfaces use `ground_decal_source_v1`, which samples opaque HEX pixels and projects them onto the X/Z ground plane. This is intentionally separate from the vertical billboard path.

The grassland pack recommends `32 x 46` and `28 x 52` for the two tall grass billboards. The current upright billboard loader and Pyxel `blt` path use uniform scaling and require the runtime world aspect ratio to match the 64 x 64 source canvas, so the first connection keeps the intended heights and uses square runtime sizes (`46 x 46`, `52 x 52`). Preserving narrower visual widths for these upright sprites requires a later non-uniform or row-sliced drawing path.

## Gameplay Boundaries

No collision, AI, input, camera, resource, or SE behavior was changed.

World data changes are limited to:

- `bounds` separates walkable, camera target, visual ground, content, and minimap rectangles.
- `visual` identifiers for trees and grass.
- `sprite_world_size` for equipment and grass so visual culling matches the new sprites.
- `ground_surfaces` is empty; large pavement review sheets are no longer active by default.
- `ground_details` is empty for the current prototype; sparse pebbles, fallen leaves, crack sprout, and small rubble assets are retained but not placed.
- Grassland v0.1 low grass, edge, and scatter `ground_details` are currently not placed in the world because they are too large to read cleanly as ground-projected floor sprites.
- `grassland_micro.enabled` is `true` so the current grassland micro surface test remains visible.
- `objects` includes multiple upright grass `reactive_prop` entries for low grass and grassland tall grass. They are visual-only and do not change collision or pathing. The current review positions keep tall/low grass away from tree roots so their billboards do not visibly occupy the same foreground/background slot.
- `reactive_prop_strength` is `1.0`, so upright reactive grass and reeds receive the same atmospheric depth treatment as other distant nature props. This keeps them integrated with the forest/grassland depth pass while the runtime deformation path remains disabled.
- `reactive_environment.upright_deform_enabled` is `false`, so those upright grass/reed sprites are not bent, split, or redrawn through the row-sliced reactive pass.
- `forest_light` and `ambient_motes` add static, world-space atmosphere marks. They are drawn only in affine mode, hidden during combat, and do not use the runtime particle system. `forest_light` is ground-adjacent dapple light; `ambient_motes` is fixed-height photon / green mote scenery in selected forest and water-edge areas.
- `visual_detail_per_chunk` is `0`; random small-detail scatter is deferred until a cheaper tiling/sprite path is available.
- `player.solid_collision_margin` adds a small margin only for player-vs-solid movement/pathing so Jack does not visually sink into the box faces. Enemy contact still uses the original player collider size.

## Deferred

- Full-map `ground_material_source` pavement tiling.
- Road, sidewalk, intersection, and transition placement rules.
- Pyxres baking for environment assets.
- iPhone visual/performance verification.
- Seam review for pavement tiles.
