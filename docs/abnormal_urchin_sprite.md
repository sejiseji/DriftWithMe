# Abnormal Urchin Sprite

## Scope

- Source pack: `drift_with_me_abnormal_urchin_redesign_v0_4.zip`
- Baseline HEAD before work: `89b41777a82e301ca11126c410a557069a3bcf98`
- Added only the abnormal urchin static composite sprite.
- Enemy AI, collision radius, bubble capture, discharge, guard/barrier behavior, normal urchin visuals, Jack, Fuse, camera, input, SE, and palette were not changed.

The source pack's `tools/verify.py` could not run in this local environment because Pillow is not installed. The included `checks/validation.json` reports PASS, and the repository tests validate the imported HEX dimensions, palette-index hashes, pyxres placement, and runtime drawing.

## Runtime Asset

The composite pixels are baked into `src/drift_with_me/assets/jack_sprite.pyxres`.
The runtime manifest is `src/drift_with_me/assets/jack_sprite.json`.

|asset|frame|bank|rect|hash|
|---|---|---:|---|---|
|`abnormal_urchin_inward_hands_64`|`composite_00`|0|`(0,160,64,64)`|`9def2c00c1daaf9642812966229d1f2d6afbc04269cad3e1bdd246fbb76e0f4b`|

The delivered UV was intentionally unassigned. The actual placement uses an empty bank 0 region and does not overlap existing Jack, Fuse, or normal urchin sprites.

## Source Art

- `src/drift_with_me/assets/abnormal_urchin_body_00.hex`
- `src/drift_with_me/assets/abnormal_urchin_composite_00.hex`
- `src/drift_with_me/assets/abnormal_urchin_hand_screen_left_00.hex`
- `src/drift_with_me/assets/abnormal_urchin_hand_screen_right_00.hex`
- `src/drift_with_me/assets/abnormal_urchin_hands_00.hex`

The game draws only the composite sprite. The part HEX files are preserved as received source material and are not drawn in addition to the composite.

## Rendering

- Abnormal enemies use `abnormal_urchin_inward_hands_64` when sprite rendering is enabled and the asset loads successfully.
- Normal enemies continue to use `normal_urchin_idle_64`.
- Existing enemy state overlays, such as approach, windup, dash, capture rings, and warning lines, remain code-driven.
- If the sprite asset is missing or invalid, the abnormal enemy falls back to the previous primitive drawing.

## Not Changed

- `enemy.abnormal.radius`
- abnormal movement, windup, dash, recover, capture, or discharge behavior
- bubble hit detection
- guard and barrier behavior
- SE and UI behavior
