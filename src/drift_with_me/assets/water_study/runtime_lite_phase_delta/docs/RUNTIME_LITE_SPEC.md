# WTR001 Wave2.1 Runtime Lite Spec v0.1

## Goal
Reduce the storage and distribution cost of the four-layer animated phase set while
preserving the exact palette-index results. Wave2.1 keeps the Wave2 runtime cadence
but changes phase content from large layer motion to local water-surface variation.
This integrated build applies the iPhone visibility tuning pass, increasing local
variation density without reintroducing global motion fields.

## Input
- base asset pack: `WTR001_Water_Layer_Sprite_Sources_v0.4.zip`
- local variation source pack: `WTR001_Wave2_1_Local_Variation_Phase_Pack_v0.1.zip`

## Encoded layers
- `water_mid_plane_c`: local tone-boundary breathing
- `water_surface_plane_c`: local surface edge variation
- `water_surface_caustics_plane_c`: local line-width and junction variation
- `water_upper_lightnet_plane_c`: local micro shimmer variation

## Runtime tuning
- Layer offset speeds and amplitudes are intentionally modest but visible at
  mobile display scale.
- Phase content remains local: no whole-plane rotation, Lissajous field, or
  runtime pixel deformation is used.
- The p00 canonical frame remains the integrated source asset.

## Encoding
- chunk-local sparse forward patch (`DHEX1`)
- per chunk size: `256x256`
- transition files: `p00_to_p01`, `p01_to_p02`, ..., `p07_to_p00`
- patch lines: `OOOO:HEXDATA`

## Recommended integration strategy
### 1. CACHE_ALL_PHASES
- load canonical p00 from integrated source assets
- apply DHEX1 transitions offline during Water Study init
- build p01..p07 in memory
- runtime playback simply selects phase images

### 2. STREAM_ONE_PHASE
- keep only one mutable phase image per animated layer
- apply DHEX1 transition at each step
- lower memory, potentially higher live CPU cost
- use only after measurement

## Runtime schedules retained from Wave2
- mid: every 13 frames, start p00
- surface: every 9 frames, start p02
- surface_caustics: every 7 frames, start p05
- upper_lightnet: every 5 frames, start p01

## Stats summary
- full chunk hex bytes: 16,777,216
- total patch bytes: 825,524
- reduction ratio: 95.08%
- total changed pixels per loop: 148,934

## Notes
This pack is lossless relative to the generated Wave2.1 local-variation phase
fields. It does not recolor or requantize; all DHEX patches preserve the source
palette indices.
