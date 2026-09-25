# WTR Sparkle FX Individual Assets v1.0

Completed, individually reusable water-surface sparkle animations for Pyxel.

## Key design fix

The prior full-screen sparkle overlay was being displayed at an unsuitable
effective resolution. This pack replaces that approach with **six canonical
sprite sizes** and explicitly forbids runtime enlargement.

All six 4-frame strips fit inside one 256x256 Pyxel bank.

## Assets

- sparkle_cross_large — 64x64
- sparkle_cross_medium — 48x48
- sparkle_cross_small — 32x32
- sparkle_glint_horizontal_large — 64x32
- sparkle_glint_horizontal_medium — 48x24
- sparkle_cluster_micro — 64x48

Use at 1x authored size only.

See `previews/individual_sparkle_assets_contact_sheet.png`.
