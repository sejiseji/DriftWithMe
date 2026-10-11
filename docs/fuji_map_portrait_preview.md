# Fuji map conversation portrait (local prototype)

Only Fuji's June week 4 map conversation uses `fuji_map_knees`.
The counter portrait `fuji_matte` and map character `jun_w4_fuji` stay unchanged.
The new presentation has no save fields and no gameplay or delivery changes.

The immutable master is Library `libfile_55decb3c84148191a42eb0ad1d44e1b4`, version 0.
The portrait crops its 1024×1536 RGBA canvas at `(264, 40, 774, 1142)` and
scales uniformly to 100×216 (integer rounding below 0.1%). The existing matte
recipe uses nearest sampling, alpha threshold 128, source components of at least
64 pixels, the default Pyxel palette, colkey 8, no dithering, and hue classes.
Warm authored shadows retain a dark palette candidate below luminance 0.57;
invisible RGB never participates in the visible alpha mask.

The display fits the crop uniformly inside normalized `(360, 6, 132, 196)`.
Fuji dialogue uses a 306-unit text width; all other dialogue retains 400.
The existing page counter, cancel and next controls remain in their positions.
The portrait is drawn before the opaque conversation frame. The frame, dialogue
and advance controls cover the lower portrait; the visible head keeps its size
and position. Closing dialogue removes the portrait without persistent state.

Map NPC dialogue declares `FieldConversation.target_speaker`. Only body text
whose explicit speaker matches this metadata uses yellow (palette 10). Other
speakers and descriptions keep white (palette 7); speaker headings keep their
existing color. W4 assigns the metadata only to Fuji, and reconstructs it when
resuming a saved conversation. Counter dialogue is unaffected.
