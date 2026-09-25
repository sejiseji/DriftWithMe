PACKAGE_NAME = "WTR_LOOK04_Plus_Sparkle_Production_Assetization_v0.1"
FRAME_COUNT = 24
FPS = 12
LOGICAL_SIZE = (1024, 512)
CHUNK_SIZE = (256, 256)
LAYERS = [
    ("water_deep_plane_e", "deep", None),
    ("water_mid_plane_e", "mid", 8),
    ("water_surface_plane_e", "surface", 8),
    ("water_surface_caustics_plane_e", "surface_caustics", 8),
    ("water_highlights_plane_e", "highlights", 8),
    ("water_sparkle_plane_e", "sparkle", 8),
]
