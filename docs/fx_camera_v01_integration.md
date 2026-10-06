# FX / Camera v0.1 Integration Notes

## Scope

- Source design pack: `drift_fx_camera_v01.zip`
- Baseline HEAD before implementation: `7404dd4`
- Implemented the first low-risk cue connection pass.
- Hitstop control is present for comparison, but remains disabled by default.
- Combat camera reactions are present for comparison, but remain disabled by default.
- New FX sprites, new SE shapes, and gameplay balance changes remain unimplemented.

## Cue Mapping

The game now maps existing model events to the proposed presentation cue IDs inside `EffectSystem`.

|Cue|Current model event|
|---|---|
|`DWF_REFILL_DONE`|`resource_refilled` with `resource == "water"`|
|`DWF_CHARGE_DONE`|`resource_refilled` with `resource == "energy"`|
|`DWF_GUARD_REPEL`|`barrier_repelled`|
|`DWF_BUBBLE_CAPTURE`|`enemy_captured`|
|`DWF_ZAP_HIT`|`discharge_succeeded`|
|`DWF_ABNORMAL_WINDUP`|`abnormal_windup_started`|

The `(event_id, cue_id)` pair is used to suppress duplicate presentation processing.

## Implemented Visuals

All visuals are code-driven temporary shapes:

- world particles with cue-specific color palettes
- expanding world-space rings
- short world-space strokes for guard knockback, bubble glints, ZAP bolts, and abnormal windup direction
- a short ZAP defeat enemy snapshot drawn from the existing enemy sprite/primitive path

These records are presentation-only. They are not collision, target selection, resource, AI, or camera inputs.

## ZAP Defeat Snapshot

`DWF_ZAP_HIT` now stores a small draw-only record for the defeated enemy.

Configured duration:

```json
"defeated_enemy_snapshot_ms": 100.0
```

The snapshot records only:

- target enemy ID
- enemy kind
- event world position
- remaining visual lifetime

It is mixed into the existing world draw command sort and uses the current enemy sprite asset when available. If the sprite asset is missing, it draws the existing primitive-style silhouette plus a small electric accent.

The model enemy remains `DEFEATED`; the snapshot is not collision, AI, capture state, ZAP target state, or a way to restore a removed enemy.

## Hitstop

`DriftWithMeApp` can now request hitstop from combat events when `effects.hitstop_enabled` is set to `true`.

Default runtime config keeps it disabled:

```json
"hitstop_enabled": false
```

Configured comparison values:

|Event|Duration|
|---|---:|
|`barrier_repelled`|16.6666666667ms|
|`enemy_captured`|33.3333333333ms|
|`discharge_succeeded`|50.0ms|

Requests merge by maximum duration, not by addition, and are capped by `hitstop_hard_cap_ms`.
The app records processed event IDs so the same event does not extend hitstop twice.

During hitstop:

- fixed model updates are skipped
- the accumulator is cleared, so stopped time is not caught up later
- FX time continues
- pending edge inputs can be observed before the stopped model update resumes
- a released guard input clears the visible barrier state

This is a comparison mechanism, not a default gameplay change.

## Combat Camera Reactions

`EffectSystem` can now create short camera impulses from presentation cues when the related flags are enabled.

Default runtime config keeps both controls disabled:

```json
"shake_enabled": false,
"combat_camera_pulse_enabled": false
```

Configured comparison values:

|Cue|Shake|Zoom|
|---|---:|---:|
|`DWF_GUARD_REPEL`|1.0px for 90ms|none|
|`DWF_ZAP_HIT`|1.5px for 100ms|peak +4%, 40ms attack / 30ms hold / 170ms return|

The offset is scaled from the 512x236 reference viewport and capped at `camera_offset_cap_px`.
Multiple active reactions are not added into a larger shake; the strongest offset and highest zoom multiplier are used.

These reactions are draw-camera only:

- model/input camera state is unchanged
- HUD and touch coordinates are unchanged
- yaw and pitch are unchanged
- FOCUS, event pan, and base camera blends suppress combat reactions instead of replaying them later
- when hitstop is active, camera reaction start can be delayed until the stop releases

This is a comparison mechanism, not a default gameplay change.

## Abnormal Windup Event

`start_abnormal_windup()` now emits `abnormal_windup_started` after the dash direction is fixed.

The event payload includes:

- `dash_x`
- `dash_z`

The direction calculation, windup duration, dash transition, enemy AI, and existing warning-line rendering were not changed.

## Explicitly Not Implemented

- new pyxres/HEX FX sprite assets
- new audio events for refill, charge, or abnormal windup
- full-screen flashes
- changes to player/enemy collision, water/energy costs, capture duration, or discharge behavior

## Verification

Automated tests cover:

- cue mapping for existing event names
- duplicate cue suppression
- local FX creation without model mutation
- abnormal windup event emission after dash direction fixation
- hitstop disabled-by-default behavior
- hitstop max-duration merge, event deduplication, and model-clock freeze
- combat camera reaction disabled-by-default behavior
- delayed shake / pulse transform and FOCUS suppression
- ZAP defeated-enemy snapshot lifetime and model-state invariance
- existing combat resource behavior
