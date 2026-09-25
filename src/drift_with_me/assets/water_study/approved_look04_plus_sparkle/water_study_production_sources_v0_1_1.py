"""Color-corrected source metadata, integration only."""

FRAME_COUNT = 24
FPS = 12
LOGICAL_SIZE = (1024, 512)
CHUNK_SIZE = (256, 256)
CHUNK_NAMING = "c{row}{column}"
LAYERS = [
    ("water_deep_plane_e", "deep", None),
    ("water_mid_plane_e", "mid", 8),
    ("water_surface_plane_e", "surface", 8),
    ("water_surface_caustics_plane_e", "surface_caustics", 8),
    ("water_highlights_plane_e", "highlights", 8),
    ("water_sparkle_plane_e", "sparkle", 8),
]
