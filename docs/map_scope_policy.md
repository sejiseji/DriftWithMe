# Map scope and minimap decision

The user approved removing the HUD minimap and decided against any further expansion of the map area. Future work should use the existing shared map and its locations rather than enlarge the playable, camera, visual or content bounds.

This change removes only minimap drawing, per-frame marker traversal/projection, dedicated HUD rectangles, UI input capture and popup-reservation entries, and obsolete minimap-only tests. The minimap had no independent simulation update or tap navigation feature. Remaining controls, location labels and goal panels retain their current layout.

World data is unchanged. Walkable/camera bounds remain0–1024 and the existing visual/content undercoat remains−256–1280; this does not enlarge either. Legacy `world.minimap_rect` / `minimap_rect_xz` metadata is retained because it is also used by the debug ground grid and older world data. Keeping that shared field does not expose a minimap. Path finding, collision, camera tracking, world-to-ground picking and double-tap movement continue to use their existing data and code.

The uncommitted July week2 flowerbed/Fuji field fragment remains intact. The accepted115% flowers, six seedlings per plot/thirty total, on-map closeup and dialogue/save progression are unaffected. This map-scope decision adds no new area or scenario.
