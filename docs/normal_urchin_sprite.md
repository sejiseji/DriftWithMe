# Normal Urchin Sprite

## Scope

- Source pack: `drift_with_me_normal_urchin_v0_1.zip`
- Baseline HEAD before work: `2e2d05f262ff036ce1cbc2eba969e34355ba18b7`
- Added only the normal urchin static idle sprite.
- Enemy AI, collision radius, guard/barrier behavior, abnormal urchin visuals, camera, input, SE, and palette were not changed.

## Runtime Asset

The pixels are baked into `src/drift_with_me/assets/jack_sprite.pyxres`.
The runtime manifest is `src/drift_with_me/assets/jack_sprite.json`.

|asset|frame|bank|rect|hash|
|---|---|---:|---|---|
|`normal_urchin_idle_32`|`idle_00`|0|`(64,160,32,32)`|`a9e16f5b554a53f4492849cf05f937e3657a2b0aed64bd46f13357148f850d03`|

The delivered manifest suggested `(0,288)`, but the current image banks are 256x256. The actual placement uses an empty bank 0 region and does not overlap existing Jack or Fuse sprites.

## Source Art

- `src/drift_with_me/assets/normal_urchin_idle_00.hex`

The file preserves the delivered 32x32 palette-index pixels.

## Rendering

- Normal enemies use `normal_urchin_idle_32` when sprite rendering is enabled and the asset loads successfully.
- Abnormal enemies continue to use the existing primitive drawing.
- Existing enemy state overlays, such as approach, rest, windup/capture rings, remain code-driven.
- If the sprite asset is missing or invalid, the normal enemy falls back to the previous primitive urchin drawing.

## Not Changed

- `enemy.normal.radius`
- enemy movement or aggro behavior
- guard threat selection
- barrier repel and contact knockback
- SE and UI behavior
