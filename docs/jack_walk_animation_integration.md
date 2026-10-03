# Jack Walk Animation Integration

The `jack-swim-prototype-local` delivery supplies four locomotion frames and four idle frames for each of Jack's eight authored directions. The exploration runtime uses the supplied `swim_000..003` sources as Jack's walk cycle because they animate the fins/tentacles while preserving the existing 32 x 32 canvas, `(16, 32)` anchor, palette, and direction silhouettes.

## Runtime Contract

- The 32 locomotion HEX files are preserved under `assets/jack_walk/<direction>/`.
- Each direction is loaded as a four-frame `frame_loop` source asset.
- Frames advance every `0.14` seconds, matching the supplied 140 ms preview timing.
- Manual movement and auto-move use the loop.
- Stopping returns immediately to the existing directional static sprite.
- Existing blink sprites remain authoritative during blink windows.
- Combat, interactions, and Water Study do not opt into the walk loop.
- Direction changes share the presentation clock, so changing direction does not restart or hitch the loop.

The supplied idle animation remains unconnected in this pass. Exploration already has hover and blink behavior, and keeping that path unchanged limits this integration to the requested walking motion.
