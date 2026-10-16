# July week2 flowerbed: accepted field preview

Open `?debug=weeks` → 7月 → 第2週・花壇試作 → start → フジと話す. Fuji's request and sighting discussion lead into planting. Inspecting Fuji/the actual plot uses the same flow. Only this field fragment is authored; the normal counter day, week transition, creature investigation and return-to-office sequence remain absent. See [the field fragment](july_week2_field_fragment.md).

## Accepted appearance and operation

The editor re-renders the actual map through `Renderer.draw_scene`, using the same world, soil divisions, surrounding terrain and calibrated projection. A temporary scene-camera copy targets `(184,0,382)` at2× zoom, screen anchor `(.5,.35)`. It is not a second diagram or screenshot composite, and the normal camera controller is preserved.

Tap each of the original five June species once to fill plots1–5 in order. Each chosen species plants six seedlings in that actual plot: two columns×three rows, thirty seedlings overall. Seedlings use115% of the original world size (`18.4×18.4`), with local x offsets4/12 and z rows366/375/384. This is the final user-approved appearance. Preview, confirmation and the normal map share the same depth-sorted plant draw path.

The header occupies logical y0–20, with the actual map visible above controls beginning at y126. Candidate and confirmation buttons are48 units tall at y130–232. Numbers mark chosen candidates; Undo removes the last species and its six seedlings. At five species the same real map asks この並びでいい？: yes commits and saves, no clears only the draft for reselection. Cancel/Escape preserves the prior confirmed layout. From final confirmation, no returns to the list with Cancel; Escape can also cancel directly.

## Simulation and persistence

Editing uses a transient `model.flowerbed_draft` reference; outside editing the renderer uses the committed order. All exits clear the draft. Confirmation saves only the five species IDs, not30 selections or new collection requirements. A failed save retains the editor and previous committed order/stage.

During dialogue/editing and the closing input-release gate, main simulation updates are skipped. Movement, enemies, contacts, resources, camera tracking and background interactions cannot advance. Gestures/auto movement are cleared at both edges. The original camera is restored unchanged and normal controls resume after input release.

The confirmed layout is empty or a permutation of the five June IDs, independent of story completion. Ordinary save versions1/2 accept optional `flowerbed` and `flowerbed_visit` fields; old records default to empty/unstarted. Drafts never serialize and the six-value decode API/resources are unchanged. This model can retain a completed garden later; no August scenario is added.

Week-debug retains normal progress/backup protection. Only the confirmed prototype layout and field-fragment stage/cursor save to `driftwithme.flowerbed.prototype.v1` (native `flowerbed-prototype.json`). Record version2 migrates old order-only version1 without completing the new request. Full reload and the same debug entry restore it. A completed bed can be rearranged without resetting completion.

## Validation and scope

Tests cover duplicate/undo/reselect/cancel, old and new save round trips, write failure rollback, exact dialogue cursor restoration, normal-slot preservation, completed revisits and UI bounds across three render profiles. Real Mac Chrome checks actual pointer conversations/editor, full reloads, ordinary title Continue and restored controls. Chrome touch emulation at568×320 verifies touch targets and all150 species/plot/seedling visible bounds against header/control boundaries; physical mobile hardware is not claimed tested.

Publication of the preview does not author or complete the July week2 counter day or normal weekly transition. The HUD minimap is removed and map area will not expand further; see [map scope policy](map_scope_policy.md). Existing world bounds, path finding, enemies and resources are preserved.
