# WTR001 Runtime Lite Wave2.5 v0.1

This pack converts the 4 animated WTR001 layers into sparse forward DHEX1 chunk patches.
Wave2.5 keeps the Wave2 8-phase cadence but replaces the phase contents with
decoupled motion fields so the animated layers no longer appear to share the same
cycle.

Animated layers:
- water_mid_plane_c: low-frequency 2D sine drift
- water_surface_plane_c: elliptic orbit with weak sine drift
- water_surface_caustics_plane_c: small circular motion plus oblique helper drift
- water_upper_lightnet_plane_c: small reverse circular/Lissajous drift

Intended runtime strategies:
1. CACHE_ALL_PHASES (recommended first)
2. STREAM_ONE_PHASE (optional later)

Use canonical p00 from integrated `*_plane_c` assets, then apply per-transition
patches to reconstruct later phases. Static layers remain unchanged.
