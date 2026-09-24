# WTR002-A Surface Caustics Frames

20 prebaked full-frame HEX frames for `water_surface_caustics_plane_d`. Runtime exposes them through the existing `water_surface_caustics_plane_c` layer slot so WTR001 profiles do not need to change.

- `f00` is byte-identical to the current canonical `water_surface_caustics_plane_c` chunks.
- Frames use local line-width, junction, break/reconnect, and pseudo-fade changes only.
- Loop boundary frames are weighted back toward `f00` to avoid a visible snap.
- Colkey is palette index `8`.
