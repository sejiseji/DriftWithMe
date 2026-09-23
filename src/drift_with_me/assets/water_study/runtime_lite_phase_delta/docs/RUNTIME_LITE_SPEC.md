# WTR001 Runtime-Lite Phase Delta Spec v0.1

## Purpose
Reduce repository / web-bundle source size for Wave1 phase animation while preserving the exact generated phase data.

This pack does **not** change the visual result.
It changes only how p01..p07 / loop transitions can be stored and reconstructed.

## Encoding
`DHEX1` sparse chunk-local forward patches.

Each patch line is:

```text
OOOO:HEXDATA
```

- `OOOO`: 4-digit hex flat offset inside one `256x256` chunk
- `HEXDATA`: replacement palette-index sequence
- run length is `len(HEXDATA)`

No interpolation and no recoloring occur.

## Storage result
- full Wave1 logical phase HEX: 8,396,800 bytes
- full Wave1 chunk phase HEX: 8,421,376 bytes
- DHEX1 transition patches: 979,054 bytes
- source-size saving vs full chunk HEX: **88.37%**

## Runtime profiles

### Profile A — CACHE_ALL_PHASES
Reconstruct p01..p07 from p00 when Water Study is opened, then keep all phase images cached.

Advantages:
- simplest draw loop
- no transition-time patch cost
- safest visual timing

Approx raw palette-index storage for both 8-phase layers:
- 8 MiB total if all 16 logical phase planes are separately cached
- about 7 MiB additional if p00 aliases the already loaded base planes

Use as the **desktop/reference implementation** first.

### Profile B — STREAM_ONE_PHASE
Keep only one mutable image per animated layer and apply DHEX1 transition patches when advancing phase.

Advantages:
- roughly 1 MiB raw palette-index working set for two 1024x512 active planes
- minimal phase-image memory

Risk:
- patch application may create frame-time spikes on browser/iPhone

Do not choose this as default until measured on device.

### Profile C — HYBRID
Cache caustics, stream lightnet, or vice versa based on measured cost.

## Recommended implementation sequence
1. Integrate v0.4 static source first.
2. Add DHEX1 loader + verification tests.
3. Implement `CACHE_ALL_PHASES` as the reference mode.
4. Measure Pages / iPhone.
5. Only then test `STREAM_ONE_PHASE` or HYBRID.

## Important
- p00 is the canonical v0.4 base source.
- patches are forward transitions p00->p01 ... p07->p00.
- physical chunks remain packing units only.
- no procedural deformation at runtime.
- no phase source regeneration in the game.
