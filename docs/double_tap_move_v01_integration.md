# Double Tap Move v0.1 Integration

## Scope

- Source design pack: `drift_double_tap_move_v01.zip`
- Implemented: double-tap / double-click destination movement for clear straight-line ground targets.
- Not implemented in this pass: A* obstacle avoidance, foreground-object tap rejection, target auto-interaction, new sprites, new SE, or pyxres changes.

## Runtime Behavior

- A short tap is accepted when press-to-release is at most `auto_move.short_tap_sec`.
- A pair is accepted when the second press starts within `auto_move.max_interval_sec` from the first release and within `auto_move.max_distance_ref_px` scaled to the current UI profile.
- The movement request fires on the second release.
- UI-owned presses, drags beyond the existing drag threshold, long holds, paused world state, and hitstop do not create movement requests.
- A new ground press, manual move input, barrier, action, interaction, pause, camera-freeze sequence, refill/charge/inspection, or enemy contact clears the active auto move.

## Picking and Movement

- `screen_to_ground_point()` in `math3d.py` uses the current presentation camera and intersects the input ray with the `y=0` ground plane.
- Accepted goals are stored as world X/Z coordinates. They are not re-picked as the camera follows Jack.
- The first movement version only accepts goals with a clear straight line from Jack to the destination, using the existing solid AABB line-of-sight check expanded by Jack's collider half extent.
- Movement uses the existing player speed and `WorldData.move_player_sliding()`.
- Arrival radius and stuck timeout are configured in `auto_move`.

## UI Feedback

- Accepted destinations draw a small world-space ground ring.
- Rejected invalid/blocked picks use existing denied text and SE.
- Japanese reasons:
  - `auto_move_blocked`: `そこへは行けません`
  - `auto_move_no_path`: `道が見つかりません`

## Verification

- Added unit coverage for double-tap recognition, UI/drag rejection, projection round-trip, clear-goal movement, manual cancellation, blocked-goal rejection, and wall-crossing rejection.
- `scripts/check_all.py` passes after this integration.
