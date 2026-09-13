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

## Compact HUD corrections after play review

User screenshots on 2026-09-13 showed that the v0.2 action buttons and refill/charge popup still
covered too much of the zoomed character view. The following layout and drawing corrections were
applied without changing gameplay, camera, sprites, or SE:

| Element | Before | After | Reason |
|---|---:|---:|---|
| Low context / primary buttons | `(254,146,80,44)` / `(340,146,80,44)` | `(286,154,62,36)` / `(356,154,62,36)` | Keep touch controls available while exposing more playfield |
| Medium context / primary buttons | `(328,180,84,48)` / `(420,180,84,48)` | `(348,190,74,38)` / `(430,190,74,38)` | Reduce bottom-right footprint |
| High context / primary buttons | `(410,224,105,60)` / `(525,224,105,60)` | `(432,236,94,48)` / `(536,236,94,48)` | Same visual density as medium after scaling |
| Button font low/medium/high | `16/16/20` | `14/14/18` | Fit Japanese labels in smaller buttons |
| Progress popup low/medium/high | `156x64 / 160x64 / 200x80` | `132x36 / 148x40 / 180x48` | Convert refill/charge status to a compact chip |
| Progress placement | near Jack/Fuse candidate positions | fixed lower chip slot | Avoid covering the zoom target during refill/charge |
| Progress detail text | title + percent + meter + detail line | title + percent + meter only in compact chips | Prevent text clipping and character occlusion |

## Text fit corrections after device review

User screenshot review on 2026-09-13 showed the compact bottom UI still sitting too low, with
Japanese labels touching the lower window borders. The following UI-only corrections were applied:

| Element | Before | After | Reason |
|---|---:|---:|---|
| Low context / primary / progress Y | `154` | `148` | Lift lower UI away from the screen edge |
| Medium context / primary Y | `190` | `184` | Lift lower action windows |
| Medium progress Y | `188` | `182` | Keep progress chip aligned above the lower edge |
| High context / primary / progress Y | `236` | `228` | Preserve scaled spacing on high profile |
| Tooltip Y low/medium/high | `119/154/190` | `111/146/180` | Keep tooltip clear of button labels after the button lift |
| Button font low/medium/high | runtime `16/16/20` | runtime `14/14/18` | Match the compact layout font values and avoid lower-edge clipping |
| Button text baseline | centered only | centered, then lifted by 2 logical px | Compensate for the font's visual lower weight |
| Tooltip/resource/numeric text baseline | centered only | centered, then lifted by 1 logical px | Keep labels inside framed panels |

## Implementation notes

- Existing method names such as `action_button_rect()` and `interact_button_rect()` remain, but now resolve to the v0.2 numeric layout.
- The resource panel uses separate labels, right-aligned zero-padded numbers, and meters.
- The right button remains primary action: `GUARD`, `BUBBLE`, `ZAP`, or disabled `NONE`.
- The left button remains context: `CHECK`, `REFILL`, `CHARGE`, or `CANCEL_*` during refill/charge.
- Refill/charge progress uses a compact fixed bottom chip so it does not cover Jack/Fuse during zoomed resource animations.
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
