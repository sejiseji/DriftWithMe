# WTR001 Water Layer Sprite Source Contract v0.2

Canonical water-plane definition:

- six independent **1024×512 logical planes**
- each layer is one large sprite/source plane
- 256×256 chunk files are only physical packing helpers
- never animate or offset chunks independently
- Pyxel fixed palette `0-F`
- strict blue-only water policy
- palette indices `3` and `B` are deliberately excluded from water layers
- overlay transparency uses index `8`
- deep layer is opaque

Layers:
1. `water_deep_plane_a`
2. `water_mid_plane_a`
3. `water_surface_plane_a`
4. `water_surface_caustics_plane_a`
5. `water_upper_lightnet_plane_a`
6. `water_highlights_plane_a`

Codex must not:
- requantize
- recolor
- resize
- shear
- rotate
- replace with procedural circles, zigzags, horizontal bands or noise
- treat 256×256 chunks as visual tiles
