# July W1 construction placement: local first version

This local branch starts at published `d490b02`; it does not alter the old checkout or add scenarios. The existing 18-part approved pack supplies three material piles, five seedling trays, short stakes and tall entry stakes. Alternate preprojected assemblies/raw sources and loose seedlings are not stacked into the map. Strings reuse the existing world-space, depth-sorted preview rendering; no source pixels are regenerated.

Fuji stays at (288,384). All stock at x200–260/z430–478 projects to the left of Fuji under the actual fixed affine basis; the low/medium/high test uses that basis rather than assuming map X means screen left. The work plot spans x140–220/z352–412 and leaves a 36-world-unit east gate toward Fuji. It is an unplanted work boundary, without a new planting/collection task.

Only stake roots, five thin boundary edges and individual stock ground footprints collide. The interior and gate are walkable. Each pile/tray uses a 14×10 ground footprint offset two units from its visual root; sprite height does not become an invisible rectangular wall. String edges have 0.7 half-thickness. The existing spatial index, sliding collision and A* route finder handle these objects. Props and strings use the existing pixel anchors, palette/transparency and shared actor depth ordering. Invisible colliders are skipped by scenery rendering.

Start supplies (tap_start 128,192; solar_start 192,128) and east supplies (tap_east 816,256; solar_east 848,256), Fuji, researchers (580,480;620,488), July water survey (928,144) and departure root remain accessible. Native path checks cover all routes including through the gate. An entrance narrower than 36 failed the existing A* grid and was widened.

The layout is deterministic in install_july_world; it is rebuilt on July departure/resume and removed before installing June. It adds no save fields and no interactions or new story flags. Existing research portraits and map TEMP markers are unchanged.

Mac Chrome recording uses a separate debug session with defeated pests and researcher flags for navigation setup. The overview is the actual game render with a temporarily fixed zoom0.65 camera. Controlled InputIntent movement (headless DOM keyboard input did not reach Pyxel), the engine's standard pending navigation goals, pointer supply/NPC input and save encode/decode/departure are exercised live. Evidence is screenshots and canvas MediaRecorder, not composited or image-edited content. This verification build is the basis for the user-approved publication of construction placement and Jack navigation.

The initial placement recording exposed an existing A* contact-start limitation and stepped back before requesting a detour. That baseline limitation is addressed by the separate local change documented in double_tap_navigation_local.md; the construction geometry is unchanged.
