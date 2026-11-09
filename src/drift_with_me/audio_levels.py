"""Shared output level, applied after note dynamics and before channel mixing."""

# One step down on Pyxel's 0-7 scale, without rounding quiet notes to silence.
# Keep authored note volumes and the half-volume dialogue/SE balance intact.
OUTPUT_GAIN = 6 / 7
