# Local double-tap navigation recovery

This change preserves the uncommitted July construction placement and starts from published d490b02. Enemy AI, player speed, resources and story progression are unchanged.

## Diagnosis

The original A* used a square inflated by max(player half-extents) plus two extra world units, while physical movement uses the actual rectangle with separate half-X/half-Z. A contact point could therefore be legal physically but have no navigation start link. Smoothing also used the general line-of-sight query rather than the navigation landing/bounds rules. Invisible construction colliders could incorrectly act as foreground boxes and reject ground taps before reaching the planner.

## Limited changes

- Swept segment checks use the same rectangular body as physical sliding, including locked landings and world bounds. Preferred grid nodes retain the optional comfort margin. Existing A* runs on the ordinary grid first; one half-grid/body-size fallback handles a narrow passage without retaining the extra margin.
- A blocked target is corrected within 48 world units, considering at most eight nearby free candidates ordered by tap distance and player distance. A free but unreachable target is not silently replaced. A new invalid/unreachable request cancels the old goal.
- Smoothing and early waypoint completion both require a body-clear segment. Corners cannot be cut by dropping a waypoint too early.
- A goal receives at most one automatic recovery attempt, after 0.5 seconds of insufficient progress or a world identity change. Failure or a second stall stops movement with ordinary denied feedback. No per-frame path search is added.
- Invisible construction collision records no longer act as visible foreground boxes. Real foreground scenery, non-solid NPCs and UI picking remain protected. Combat, conversations, manual input cancellation and save handling keep their existing gates.
- Navigation paths and retry state stay transient and are not added to the save schema. Layout replacement triggers a bounded replan; ordinary scene-reset cancellation still applies.

## Checks and limits

Tests cover contact starts, plot interior/exterior, thin strings, corners, a narrow corridor, blocked targets, unreachable areas, repeated requests, manual cancellation, locked-landing smoothing, world replacement, save roundtrip and bounded recovery. Existing save/weekly/resource/UI tests remain.

Five warm local trials: contact request changed from rejection at median74.8ms to a valid route at86.1ms; clear direct requests0.019→0.023ms; blocked stock requests0.009ms rejection→0.501ms correction. Normal following ran720 steps with zero additional A* searches. Timings are local samples, not a hardware/CI performance guarantee. An artificial permanent stall invokes one recovery and stops; no infinite retries.

Mac Chrome comparison captures identical debug contact starts and a fixed real game camera. All movement goals are actual timed double mouse clicks or CDP touchStart/touchEnd events through the host pointer bridge and ordinary recognizer. No keyboard/movement stub or pending-goal injection is used. Enemy defeat/research flags only shorten setup. Touch emulation is not physical iOS testing.

This publication includes the approved construction placement and Jack navigation only. No new art/scenario or enemy AI changes are included.
