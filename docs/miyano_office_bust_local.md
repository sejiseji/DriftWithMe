> 公開対象として承認済み。以下の「ローカル」「未公開」「commit/pushなし」は制作・検証時点の記録です。統合内容と最終検証は `july_week2_release.md` を参照してください。

# Miyano flat counter bust (local)

`miyano_bust_normal` uses the new 116×116 flat bust derived by reference editing
from the approved fullbody Base v5 (Library version 4). It preserves the warm
smile, tan skin, low blonde tie with brown inner hair, teal tank over black
camisole, and student card. Only this normal face is authored; no expression
variants or new dialogue were added.

Explicit color rules map blonde to 10, tan to 9 with shadow 4, teal to 3 with
dark shadow 1, lipstick to 2/14, and white/gray card to 7/13. Colkey 8 remains
transparent. Existing deterministic indexed conversion, no dithering, guarded
color patches and protected-feature tiny-component cleanup produce the final
HEX. The face/eye/mouth structure is from the image edit, not a new design.

Only the W2 researcher counter speaker branch uses the bust. Existing Miyano
knees/fullbody/map assets remain unchanged. The Yumesaki five-bust registry and
expression logic are retained. Speaker identity is derived from the current
page/turn after save restoration; no new save fields or emotion state exist.

This is local integration in the existing working checkout. No commit, push,
public deployment or write to the separate original checkout.
