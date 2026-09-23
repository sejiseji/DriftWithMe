# WTR001 Revised Water Layer Source Contract v0.3

- six `*_plane_b` sources replace the prior `*_plane_a` visual definitions
- each source is one logical 1024×512 plane
- physical packing is 256×256 × 4×2 only
- deep is opaque
- other five layers use colkey 8
- fixed Pyxel palette 0-F
- water palette indices 3 and B are forbidden
- canonical source is `hex_rows/*.hex.txt`
- do not requantize, recolor, resize, rotate, shear, or procedurally redraw
- chunks must never receive independent motion
- this revision is the base for future phase-delta generation
