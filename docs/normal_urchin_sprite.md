# Normal Urchin Sprite

## Scope

- Source pack: `urchin_natural_v03_download.zip`
- Baseline HEAD before v0.3 work: `a1e1201d69feb2ac4030ad48dd02b30e068658b8`
- Replaced only the normal urchin static idle sprite with the natural-object v0.3.0 art.
- Enemy AI, collision radius, guard/barrier behavior, abnormal urchin visuals, camera, input, SE, and palette were not changed.

## Runtime Asset

The pixels are baked into `src/drift_with_me/assets/jack_sprite.pyxres`.
The runtime manifest is `src/drift_with_me/assets/jack_sprite.json`.

|asset|frame|bank|rect|hash|
|---|---|---:|---|---|
|`normal_urchin_idle_64`|`idle_00`|0|`(64,160,64,64)`|`06fec2bbf7eeac8b6e8b9fab9e4ebc4584c2a364c2ba03d3e34ee41878b0dfa4`|

The delivered v0.3 manifest leaves the atlas UV unassigned. The actual placement uses the former normal urchin slot expanded to 64x64. It sits next to the abnormal urchin sprite at `(0,160,64,64)` and does not overlap existing Jack, Fuse, or abnormal urchin sprites.

Runtime values:

- canvas: 64x64
- colkey: 3
- anchor_px: `(32,60)`
- world_size: `(20.0,20.0)`
- opaque bounds: `[2,6,62,60)`

Color index 0 is visible opaque black for this asset. Do not reuse the retired normal-urchin `colkey=0` setting.

## Source Art

- `src/drift_with_me/assets/normal_urchin_idle_00.hex`

The file preserves the delivered 64x64 palette-index pixels.

## Rendering

- Normal enemies use `normal_urchin_idle_64` when sprite rendering is enabled and the asset loads successfully.
- Abnormal enemies continue to use `abnormal_urchin_inward_hands_64`.
- Existing enemy state overlays, such as approach, rest, windup/capture rings, remain code-driven.
- If the sprite asset is missing or invalid, the normal enemy falls back to the previous primitive urchin drawing.

## Not Changed

- `enemy.normal.radius`
- enemy movement or aggro behavior
- guard threat selection
- barrier repel and contact knockback
- SE and UI behavior

## Verification Notes

- The included `checks/validation.json` reports 53/53 PASS for static source, palette, PNG, and topology checks.
- The included `tools/verify.py` was not run locally because Pillow is not installed in the project virtualenv (`ModuleNotFoundError: No module named 'PIL'`).
- Repository tests validate the imported HEX dimensions, source hash, pyxres placement, colkey, anchor, and runtime drawing.
