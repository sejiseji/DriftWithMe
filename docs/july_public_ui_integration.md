# July week-one and field objective UI integration

The integration retains both histories: July week-one/approved portraits/combat fixes from `7c1c4ae` and the published objective drawer, compact return control and iframe host from `8ff3c56`.

`DriftWithMeApp` runs objective input handling before July story handling. The drawer is blocked during July arrival/conversation/return scenes. July small goals show pest removal, researcher guidance, Fuji material confirmation and the water check. Showing goals does not mutate progress or saves. The HTML and manifests are regenerated with the published host build recipe.

Only the previously uncommitted July goal additions and their story-blocking assertion are included. Independent first-sight AI timing changes, robot description edits and font removals remain outside this integration. July and the published UI do not depend on those changes. Existing July-required font glyphs already in the local history remain included.

Validation covers full pytest/check_all, July goal/save regressions, live Mac Chrome week selection, researcher portraits/conversation, save encode/decode/resume, return and default Affine bubble/focus resource use. Small viewport checks use Mac Chrome with iPhone-sized portrait and landscape viewports; they are not physical iOS checks. Browser scenarios shorten progression by setting specific enemy/check flags in a debug-only test session, then exercise live pointer input and rendering.

No push or Pages publication is part of this integration.
