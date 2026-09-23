# WTR001 Wave2 Runtime Lite Spec v0.1

## Goal
Reduce the storage and distribution cost of the Wave2 four-layer animated phase set while preserving the exact palette-index results.

## Input
- base asset pack: `WTR001_Water_Layer_Sprite_Sources_v0.4.zip`
- phase source pack: `WTR001_Phase_Delta_Wave2_v0.1.zip`

## Encoded layers
- `water_mid_plane_c`
- `water_surface_plane_c`
- `water_surface_caustics_plane_c`
- `water_upper_lightnet_plane_c`

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

## Runtime schedules from Wave2
- mid: every 13 frames, start p00
- surface: every 9 frames, start p02
- surface_caustics: every 7 frames, start p05
- upper_lightnet: every 5 frames, start p01

## Stats summary
- full chunk hex bytes: 16,842,752
- total patch bytes: 1,497,899
- reduction ratio: 91.11%

## Notes
This pack is lossless relative to the Wave2 phase sources.
It does not recolor, requantize, or procedurally approximate any phase.
