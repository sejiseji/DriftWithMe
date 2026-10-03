# Tree Foliage Left-to-Right Ripple

`DriftWithMe_left_to_right_ripple01.zip` replaces the former seven-pose tree sway for
`tree_leafy_a` and `tree_thin_b`.

## Runtime contract

- The supplied 96x128 leaf HEX frames are used without recoloring or regeneration.
- The trunk layer, `(48, 127)` anchor, 48x64 world size, and authored collision remain unchanged.
- The canonical 65-tick sequence is stored as 43 timeline states: tick 0, ticks 6 through 46,
  and the existing idle leaf frame matching tick 49.
- Runtime maps ticks 0-5 to `ripple_000`, ticks 6-46 to their matching frame, ticks 47-48
  to `ripple_046`, and tick 49 onward to `idle_00`.
- Individual trees retain deterministic phase offsets and 180-360 tick cycle lengths, so the
  whole grove does not shimmer in unison.
- Combat and distant-tree suppression still select `idle_00`.
- Each tree still costs two sprite draws: one trunk draw and one selected leaf draw.

`src/drift_with_me/assets/tree_foliage_ripple/manifest.json` records the selected canonical
frames and pixel hashes used by tests and the source-asset manifest.
