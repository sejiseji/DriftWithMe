# UI Numeric Layout v0.2 Implementation Notes

Date: 2026-09-13

Start HEAD: `39fe76a`

Pre-work tree: clean.

## Scope

Implemented the `drift_ui_numeric_v02` HUD redesign in the current DriftWithMe codebase.
Gameplay rules, camera parameters, sprite assets, `.pyxres`, and SE data were not changed.

## Adopted data

Added `src/drift_with_me/data/ui_numeric_layout.json` as the UI layout source for:

- resource panel
- sound/pause hit and visual rects
- context and primary action buttons
- minimap and location label
- tooltip rects
- pause modal rects
- inspect modal rects
- v0.2 color tokens

The low/medium/high rect values match the supplied `checks/reference_rects.json` for the
implemented rectangles.

## Numeric changes from the previous implementation

Medium profile examples:

| Element | Before | After | Reason |
|---|---:|---:|---|
| Resource panel | `(6,6,164,50)` | `(8,8,168,48)` | v0.2 panel position and size |
| Context button | `(308,164,90,60)` | `(328,180,84,48)` | fixed bottom-right context slot |
| Primary action | `(410,164,90,60)` | `(420,180,84,48)` | fixed bottom-right primary slot |
| Pause hit rect | `(426,8,74,44)` | `(472,8,32,32)` | compact system hit slot |
| Pause visual rect | same as hit | `(474,10,28,28)` | separate visual inside hit slot |
| Sound hit rect | `(10,186,90,40)` | `(436,8,32,32)` | compact top-right system slot |
| Sound visual rect | same as hit | `(438,10,28,28)` | separate visual inside hit slot |
| Inspect panel | old top chip `(centered,8,<=220,54)` | `(16,112,480,116)` | readable bottom modal |
| Inspect done button | old chip-local `76x24` | `(414,174,72,44)` | touch-sized modal action |
| Progress popup size | old top chip `<=220x54` | `160x64` | v0.2 compact progress card |

Font changes:

| Style | Before | After | Reason |
|---|---:|---:|---|
| Title low/medium/high | `18/18/22` | `20/20/25` | v0.2 modal heading size |
| Button/resource/tooltip | label style only | `16/16/20` | v0.2 readable Japanese UI |
| Numeric | hint/label style only | `14/14/18` | fixed-width resource numbers |
| Auxiliary | hint style | `12/12/15` | minimap label and status text |

## Fit corrections after device review

User screenshots on 2026-09-13 showed text spilling or degrading in compact windows. The following
layout-only corrections were applied without changing gameplay, camera, sprites, or SE:

| Element | Before | After | Reason |
|---|---:|---:|---|
| Start sound control | `音：入/音：切` text in `32x32` medium system slot | icon-only system button | The text is wider than the compact system slot |
| Start SE guide Y | `130` | `124` | Keep the guide clear of the preview buttons |
| Play wordmark | DotGothic auxiliary text `DriftWithMe` | built-in pixel text `DRIFTWITHME` | Small TTF lowercase rendering was visually unstable |
| Action button label position | fixed Y `25` medium / `31` high | centered inside the v0.2 label rect | Avoid baseline drift and lower-edge clipping |
| Resource labels/numbers | row Y only | centered inside explicit row rects | Keep `水/電力/000` inside the resource panel |
| Progress detail | auxiliary `12/15px` | body `16/20px` | Improve readability while still fitting the popup |

## Implementation notes

- Existing method names such as `action_button_rect()` and `interact_button_rect()` remain, but now resolve to the v0.2 numeric layout.
- The resource panel uses separate labels, right-aligned zero-padded numbers, and meters.
- The right button remains primary action: `GUARD`, `BUBBLE`, `ZAP`, or disabled `NONE`.
- The left button remains context: `CHECK`, `REFILL`, `CHARGE`, or `CANCEL_*` during refill/charge.
- Refill/charge progress uses a compact popup near Jack/Fuse when possible, with HUD/button blockers avoided. The full 160ms side hysteresis from the proposal is not implemented yet.
- Inspect uses the dedicated bottom modal and hides the normal action group, minimap, and tooltip.
- Minimap is read-only. It shows stage/object markers and Jack only; enemy radar and tap movement were not added.
- Pause uses the v0.2 modal rects for resume/reset/audio/dev. Existing debug hotkeys and direct debug helper methods remain.

## Safe Area and runtime checks

The implemented rects are Canvas logical pixels for the standard low/medium/high profiles.
No new JavaScript Safe Area measurement bridge was added in this pass. Safari/home-screen Safe
Area behavior still needs device verification against the generated web build.

## Verification

Run:

```text
.venv/bin/python -m pytest tests/test_ui_layout.py tests/test_japanese_ui.py
.venv/bin/python scripts/check_all.py
.venv/bin/python -c "from drift_with_me.app import DriftWithMeApp; DriftWithMeApp(headless=True, smoke_frames=3)"
```

Result: passed.

Not yet completed in this note: visual screenshots for every state, iPhone Safe Area measurement,
and performance comparison.
