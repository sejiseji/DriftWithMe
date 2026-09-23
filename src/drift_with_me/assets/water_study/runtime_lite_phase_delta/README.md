# WTR001 Runtime Lite Wave2 v0.1

This pack converts the 4 animated Wave2 layers into sparse forward DHEX1 chunk patches.

Animated layers:
- water_mid_plane_c
- water_surface_plane_c
- water_surface_caustics_plane_c
- water_upper_lightnet_plane_c

Intended runtime strategies:
1. CACHE_ALL_PHASES (recommended first)
2. STREAM_ONE_PHASE (optional later)

Use canonical p00 from integrated `*_plane_c` assets, then apply per-transition patches to reconstruct later phases.
