# WTR001 Water Layer Sprite Sources v0.2

Implementation-oriented sprite-source pack generated from the six approved layer concepts.

- Master generation: 1254×1254 retained
- Canonical implementation plane: 1024×512 per layer
- Six layers share one logical coordinate size
- Deep is opaque
- Other five layers use colkey 8
- HEX rows are canonical
- Strict water conversion excludes palette indices 3 and B to prevent green/teal drift
- 256×256 chunks are packing helpers only
