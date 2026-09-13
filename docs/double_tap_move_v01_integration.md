# Double Tap Move v0.1 Integration

## Scope

- Source design pack: `drift_double_tap_move_v01.zip`
- Implemented: double-tap / double-click destination movement, straight-line movement, and static-obstacle A* fallback.
- Not implemented in this pass: foreground-object tap rejection, dynamic enemy avoidance, target auto-interaction, new sprites, new SE, or pyxres changes.

## Runtime Behavior

- A short tap is accepted when press-to-release is at most `auto_move.short_tap_sec`.
- A pair is accepted when the second press starts within `auto_move.max_interval_sec` from the first release and within `auto_move.max_distance_ref_px` scaled to the current UI profile.
- The movement request fires on the second release.
- UI-owned presses, drags beyond the existing drag threshold, long holds, paused world state, and hitstop do not create movement requests.
- A new ground press, manual move input, barrier, action, interaction, pause, camera-freeze sequence, refill/charge/inspection, or enemy contact clears the active auto move.

## Picking and Movement

- `screen_to_ground_point()` in `math3d.py` uses the current presentation camera and intersects the input ray with the `y=0` ground plane.
- Accepted goals are stored as world X/Z coordinates. They are not re-picked as the camera follows Jack.
- The movement code first accepts a direct line when possible, using the existing solid AABB line-of-sight check expanded by Jack's collider half extent plus `auto_move.nav_clearance_world`.
- If the direct line is blocked, a static A* fallback searches a `auto_move.nav_grid_world` grid and links the real start/goal to safe grid nodes. Jack never teleports to a grid cell center.
- The generated route is smoothed only by replacing segments that pass the same expanded line-of-sight check.
- The route uses static world solids only. It does not predict moving enemies or auto-avoid future enemy contact.
- Movement uses the existing player speed and `WorldData.move_player_sliding()`.
- Arrival radius, waypoint radius, stuck timeout, grid size, clearance, search budget, and link candidate count are configured in `auto_move`.

## UI Feedback

- Accepted destinations draw a small world-space ground ring.
- Rejected invalid/blocked picks use existing denied text and SE.
- Japanese reasons:
  - `auto_move_blocked`: `そこへは行けません`
  - `auto_move_no_path`: `道が見つかりません`

## Verification

- Added unit coverage for double-tap recognition, UI/drag rejection, projection round-trip, clear-goal movement, manual cancellation, blocked-goal rejection, and static-wall pathing.
- `scripts/check_all.py` passes after the static A* integration.
