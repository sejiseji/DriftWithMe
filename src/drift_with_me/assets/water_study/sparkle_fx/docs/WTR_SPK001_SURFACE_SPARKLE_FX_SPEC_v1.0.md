# WTR-SPK001 Surface Sparkle FX – Production Integration Spec v1.0

## 1. Purpose

Use the six completed individual sparkle animations together with lightweight
micro-particles to create irregular water-surface glints above the existing
water animation.

This specification does NOT authorize Codex to redesign or generate the art.

## 2. Completed animation assets

| Asset | Canonical frame canvas | Frames | Runtime scale |
|---|---:|---:|---:|
| sparkle_cross_large | 64x64 | 4 | 1x only |
| sparkle_cross_medium | 48x48 | 4 | 1x only |
| sparkle_cross_small | 32x32 | 4 | 1x only |
| sparkle_glint_horizontal_large | 64x32 | 4 | 1x only |
| sparkle_glint_horizontal_medium | 48x24 | 4 | 1x only |
| sparkle_cluster_micro | 64x48 | 4 | 1x only |

All 24 frames fit in `water_sparkle_fx_bank0_256`, one 256x256 Pyxel bank.

### Size rule

**Never enlarge a sparkle sprite at runtime.**

The authored canvas size is also its maximum display size.
If a larger or smaller effect is needed, select another asset class.

This specifically prevents the low-resolution / jagged appearance observed
when a tiny sparkle was enlarged in the earlier implementation.

## 3. Animation rule

Each sprite is a one-shot four-frame twinkle:

1. f00 — normal / emerging
2. f01 — brighter / expanded
3. f02 — peak
4. f03 — settling

Default: 2 ticks per animation frame.
After f03, despawn the instance.

Do not loop one instance continuously at a fixed location.

## 4. Spawn mix

Initial target simultaneous population:

- large cross: 0–1
- medium cross: 1–3
- small cross: 2–5
- large horizontal glint: 0–1
- medium horizontal glint: 0–2
- micro cluster: 1–3
- independent 1–2 px particles: 6–14

These are caps, not required counts.

## 5. Placement

- water area only
- weighted pseudo-random position
- avoid repeated spawn near the previous sparkle
- keep large motifs at least 48 px apart
- general sparkle minimum spacing: 20 px
- avoid UI-critical areas when possible

No orbit motion.
No circle movement.
No continuous layer drift.

During its life an instance may use at most ±1 px jitter.

## 6. Micro particles

Micro particles are not enlarged copies of sprite assets.

Use 1–2 px points/short dashes using indices:
- 5
- C
- 6
- rare 7

Lifetime: 8–20 frames.
Maximum initial cap: 14.

Particle motion:
- zero or occasional one-pixel step
- no acceleration simulation required
- no continuous smooth trajectory required

## 7. Draw order

1. deep
2. mid
3. surface
4. caustics
5. existing highlights
6. micro-particles
7. individual sparkle sprites
8. Water Study UI

## 8. Performance

- preload the packed 256x256 bank at startup
- object pool for sparkle instances
- object pool for micro-particles
- no asset load on Water Study open
- do not regenerate sprite pixels at runtime
- runtime work = spawn selection + frame index + blt

## 9. Acceptance

The surface should feel intermittently glittering, not continuously flashing.

Reject if:
- stars appear everywhere at once
- an asset is drawn larger than canonical size
- sparkles become a synchronized blink
- sparkle motion looks orbital or UI-like
- particles become snow / dust noise

Start conservative. Increase density only after iPhone visual validation.
