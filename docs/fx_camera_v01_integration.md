# FX / Camera v0.1 Integration Notes

## Scope

- Source design pack: `drift_fx_camera_v01.zip`
- Baseline HEAD before implementation: `7404dd4`
- Implemented only the first low-risk cue connection pass.
- Hitstop, combat camera pulse, new FX sprites, new SE shapes, and gameplay balance changes remain unimplemented.

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

These records are presentation-only. They are not collision, target selection, resource, AI, or camera inputs.

## Abnormal Windup Event

`start_abnormal_windup()` now emits `abnormal_windup_started` after the dash direction is fixed.

The event payload includes:

- `dash_x`
- `dash_z`

The direction calculation, windup duration, dash transition, enemy AI, and existing warning-line rendering were not changed.

## Explicitly Not Implemented

- hitstop / simulation time pause for combat impacts
- non-modal combat camera pulse or render-offset shake
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
- existing combat resource behavior

