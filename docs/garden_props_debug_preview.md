# Gardening props: local debug preview

The 18 approved `jlp1_` assets are registered in `jack_sprite.json`. Their HEX
pixels match the approved first-version package. This is a temporary placement
test, not an implemented July scenario or a permanent flowerbed.

Start the native game with `python main.py --week-debug`, or append
`?debug=weeks` to a locally rebuilt web game. Choose **Garden test** in the week
menu. This uses the existing temporary progress store; neither ordinary save
slot is written.

- **Layout** switches a rectangular fence to a corner layout. Each upright
  stake is an independent sprite. Short world-space string segments connect
  the posts at knot height and share the actor depth order.
- **Less** removes soil, gravel and curbs one by one, then restores them.
- **Overlap** places Jack behind and in front of a tray, then restores his
  starting position. Arrow keys/WASD move only the presentation actors.
- **Parts** shows all 18 registered assets. `sd_` means seedling, `tr_` means
  tray. The raw string source is shown top-down; it is an alternate input.
- **Week menu** discards the temporary placement scene. **Normal play** returns
  to the start screen and reattaches the unchanged ordinary progress store.

Preview updates do not call `GameModel.step`, advance the day clock, inspect
objects, progress field tasks or change enemy state. Existing scenery is
retained. Rendering shares `world_commands` depth sorting and culls each prop
by its full sprite bounds, including partial viewport overlap.

The preview uses the current affine camera. Stakes, seedlings and preprojected
trays/materials use `upright_height_billboard_v1` with equal X/Y scale. String
endpoints are projected directly from world coordinates at height 4; the
preprojected string image is not projected onto the ground again. The raw
ground source and preprojected assembly are available in Parts, but neither
is combined with another projection in the map view.

Collision is deliberately off: no gardening objects are added to `WorldData`,
the static spatial index, walkable masks, interaction targets or save data.
Permanent weekly placements and any physical curb boundaries need a separate
confirmed design. `GardenProp` records already separate asset IDs, world
coordinates and stable instance IDs; the template's fence vertices, material
anchors and tray anchors can be supplied independently of the rendering.

The preview is reachable only in an explicitly launched week-debug session.
Jumping weeks, reloading or returning to normal discards it. Ordinary weeks
do not display gardening props. Fuji's existing office and map sprites are
unchanged.

Related validation covers normal-session gating, valid/corrupt/absent save
slots, scenario preservation, actor movement without simulation, depth order,
full-bound culling, and separation of the top-down ground source. Native
low/medium/high and Mac Chrome checks supplement these tests.
