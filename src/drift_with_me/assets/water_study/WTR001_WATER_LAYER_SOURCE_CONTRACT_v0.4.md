# WTR001 Water Layer Source Contract v0.4

- six `*_plane_c` sources are the canonical v0.4 visual sources
- each source is one logical 1024×512 plane
- physical packing is 256×256 × 4×2 only
- deep is opaque
- other five layers use colkey 8
- fixed Pyxel palette 0-F
- water palette indices 3 and B are forbidden
- canonical source is `hex_rows/*.hex.txt`
- do not requantize, recolor, resize, rotate, shear, or procedurally redraw
- chunks must never receive independent motion
- v0.4 correction goal: reduce coarse cell scale and increase caustic/lightnet density relative to v0.3
