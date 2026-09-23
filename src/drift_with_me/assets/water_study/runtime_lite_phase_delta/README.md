# WTR001 Runtime Lite Wave2.1 v0.1

This pack converts the 4 animated WTR001 layers into sparse forward DHEX1 chunk patches.
Wave2.1 keeps the Wave2 cadence and initial phase offsets, but replaces the phase
content with local variation fields. The goal is subtle line-width, junction,
tone-boundary, and shimmer changes rather than large layer motion.

Animated layers:
- water_mid_plane_c: local tone-boundary breathing
- water_surface_plane_c: local surface edge variation
- water_surface_caustics_plane_c: local line-width and junction variation
- water_upper_lightnet_plane_c: local micro shimmer variation

Intended runtime strategies:
1. CACHE_ALL_PHASES (recommended first)
2. STREAM_ONE_PHASE (optional later)

Use canonical p00 from integrated `*_plane_c` assets, then apply per-transition
patches to reconstruct later phases. Static layers remain unchanged.
