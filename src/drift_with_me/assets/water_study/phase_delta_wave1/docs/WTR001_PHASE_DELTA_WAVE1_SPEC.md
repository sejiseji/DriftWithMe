# WTR001 Phase Delta Wave 1 Spec v0.1

## Scope
Wave 1 generates eight loopable phases for:

- `water_surface_caustics_plane_c`
- `water_upper_lightnet_plane_c`

Base source pack:
- `WTR001_Water_Layer_Sprite_Sources_v0.4.zip`

## Core contract
- 8 phases: `p00` ... `p07`
- `p00` is exactly the canonical v0.4 base source
- p01..p07 are palette-index-preserving micro-deformations
- logical size stays `1024x512`
- chunk packing stays `256x256 x 4x2`
- colkey remains `8`
- no new palette index is introduced
- indices `3` and `B` remain forbidden
- no runtime procedural generation is required

## Deformation method
A toroidal inverse mapping is applied to the canonical palette-index plane.

Properties:
- nearest-neighbor sampling
- wrap-around in X/Y
- no recoloring
- no interpolation
- no alpha blending
- small periodic displacement fields
- p07 -> p00 closes the cycle

## Parameters

### surface_caustics
- x amplitude: 1.75 px
- y amplitude: 1.45 px
- recommended step: 8 frames

### upper_lightnet
- x amplitude: 1.3 px
- y amplitude: 1.05 px
- recommended step: 10 frames

## Runtime expectation
Runtime should:
- select phase by integer index
- cycle independently per layer
- combine this with the existing XY parallax
- not animate physical chunks independently

Initial runtime blend is NOT required.

## Visual prohibition
Do not add:
- circles
- bubble motifs
- jagged random noise
- crack/lightning patterns
- scanlines
- horizontal stripe replacements
