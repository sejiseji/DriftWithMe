# July researcher map sprite handoff

Reference: `src/drift_with_me/assets/Fuji_32_normal.hex`, registered as `jun_w4_fuji` in `assets/jack_sprite.json`. The reference contains a 15×30 visible-pixel bbox (inclusive x8–22/y2–31) in a transparent32×32 canvas. Foot anchor is (16,32), world size32×32, transparent palette index0, `upright_height_billboard_v1`, no flips. Palette is the current Pyxel16 palette; use opaque dark palette colors instead of transparent0 for black hair/lines.

Supply each researcher as a separate transparent32×32 PNG (and optionally palette-index HEX). One static camera-facing direction and one normal frame suffice: neither character currently has a walking/moving map routine. Keep the head/hat top visible in the same mildly overhead/front-facing view as Fuji. The fixed map camera has yaw20°/pitch25°, but art already matching Fuji must not receive an extra pixel shear/rotation. The shared billboard renderer provides scene scale and depth.

Aim for approximately30 visible pixels of full height including horns/hair, feet on the bottom row, horizontally centered. Do not infer a numeric physical height for Yumesaki. Miyano's canon184cm does not require a different canvas. Both get the same anchor/world scale; silhouette may express their modest height difference. Character identity should remain legible at native size. The approved100×216 conversation portraits remain separate assets and are not resized into map sprites.

Reserved runtime asset IDs / suggested source basenames:

- `jul_w1_yumesaki_map`: `Yumesaki_32_normal.png` → `Yumesaki_32_normal.hex`
- `jul_w1_miyano_map`: `Miyano_32_normal.png` → `Miyano_32_normal.hex`

No missing/empty asset entries are added to the manifest. Once each valid32×32 asset is registered, `researcher_map_visual` activates it using the shared `sprite_prop` render path and configured asset alias. Wrong dimensions/anchor/world scale/transparency/projection or missing/disabled assets retain the explicit TEMP marker. Positions (580,480)/(620,488), non-solid interaction footprint, saves and conversation identities do not change. TEMP text disappears only for the supplied character, and the overall temporary-art banner disappears when both are real sprites.

The supplied32×32 RGBA material is now registered: Yumesaki Library `libfile_022b2e9247b08191aceab054e22b9ddc` version0, Miyano `libfile_024939199bdc81919dd01d684d161120` version0. Both use the exact Fuji canvas/anchor/world-size contract. Sources and game-palette PNG previews are preserved in `researcher_map_sprites/`; `conversion_report.json` records source and palette-index hashes, alpha masks and color mappings. The existing asset tool performs nearest RGB quantization with opaque candidates1–15, transparency0 and no dithering; there is no resizing, pixel movement or newly drawn art. Black clothing/hair stays opaque. TEMP fallback remains only for missing or invalid assets. The unchanged Fuji8× Library reference is `libfile_152c52d05808819186213c6866b8b8e1` version0.
