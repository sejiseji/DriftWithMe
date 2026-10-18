# July week 3: linked ring difficulty prototype (local, unpublished)

Baseline: published `9c10ce1`. Existing `?debug=weeks` -> **5 Rings** opens the
linked prototype; **Solo rings** replays the approved independent prototype.
Both keep direct ring selection, arch arrows, round shortcuts, the background,
characters, mouth-free smiles and 0.9s celebration turns. Each ring has 12 positions
(30 degrees per tap), target zero at the gold top outlet.

## Five-link rules and legal starting position

Direct influences only: 1->2 same, 2->3 reverse, 3->4 same, 4->5 same,
and 4->3 reverse. Ring4 therefore moves itself and both direct neighbours,
without recursively activating either neighbour's links. Ring5 moves itself only.
All rings retain 12 positions / 30deg taps and the existing 0.16s input lock.

Initial angles: (1,0,5,0,11). Generated from solved with R1+, R2-, R3+, R3+,
R4-, R4-, R5+. The inverse R5-, R4+, R4+, R3-, R3-, R2+, R1- solves in 7 taps.
Full legal-subgroup BFS verifies the minimum is exactly7; this is a tuning value,
not a claim about player difficulty.

## Safe assistance order and reachability

First **Fuse help** MUST remove the new 4->3 reverse back-link. Later requests
remove 1->2, 2->3, 3->4, 4->5 in that order. Stable internal IDs are [4,0,1,2,3].
No angle or selection is reset on help. The panel shows Help n/5. Stored histories
must be a prefix of this order; invalid reordering is rejected.

The full matrix determinant is2 over Z/12. Exactly124,416 states are reachable:
the sum of the first4 offsets is even. Initial states are never sampled as
independent random ring angles. After the first back-link removal, determinant1
and the lower-triangular structure make all248,832 states solvable, for every
subset of the remaining4 links. Exhaustive audit covers all16 post-first-help
subsets, plus every full-matrix state (4,230,144 states checked), with actual BFS
of all124,416 legal states. Computed determinants through help stages0..5 are
[2,1,1,1,1,1]. Removing 1->2 first can strand legal state(1,1,0,0,0); tests reject
such histories. In the full case the 3/4 block is solved as 2*c4=rhs modulo12,
checking parity and both solutions rather than dividing by a non-unit.

## Session state, durable facts and undo

The UI never saves intermediate angles, selection, in-flight rotation, move count
or undo history. New `.progress` keys retain only removed links, current/legacy
help history, sticky eligibility forfeiture and sticky completion. Re-entry starts
at the approved initial board with those removed links; already unlocked previews
remain unlocked. Original v1/v2 board-save bytes are preserved and read only to
extract permanent facts. Old-rule v1 completion is never reinterpreted under the
new matrix. Invalid records withhold qualification. Ordinary story saves remain
untouched. Native previews use memory only.

UNDO restores the previous completed rotation's entire five-ring state, selected
ring and move count atomically. It is disabled with no history and during rotation,
solving, unlocking, celebration and unlocked phases. Assistance clears undo history;
neither undo, retry nor re-entry can revoke help usage or revive qualification.
Retry resets to the legal start while retaining help facts. Quit (`やめる`) closes
the preview without saving the board. No duplicate Save/Back action remains.

Phase order is idle -> rotating -> idle/solved -> unlocking -> celebrating ->
unlocked. Completion is durable once solved. The debug preview displays the future completion dialogue only; it issues no
normal-game inventory, ED reward or story completion. `RingRewardLedger` is a
pure story integration contract: either linked clear earns sunglasses once,
regardless of help. `special_praise_earned` alone depends on help history.
Legacy `eligibility_forfeited` is retained for old-save compatibility and
conservative praise handling, never as a sunglasses restriction. Main-story
progress serialization and ED wardrobe wiring remain unimplemented.

## Confirmed story additions (specification only)

W3 is a scheduled reserve survey. Supervisor opening, wording candidate:
「今日の保護区調査の件な、9時には調査開始してくれてええらしいわ。
例によってフジさんも現地おるかもしれん、造園の進捗も確認しつつよろしく頼むわ」
9時 is in-story schedule, not a real-time waiting gate. Fuji's possible presence does
not confirm a required meeting. Two small terminals are near last week's magenta
plant discoloration points. Positions remain unset; no paths, park equipment or
water/power access may be blocked. This prototype adds neither that week's story
nor the terminals, throw/electricity event, parent connection or handoffs.

Small-terminal shorting and parent connection/stop events consume zero power and
work at power zero; ordinary combat cost is unchanged. After W3 recovery, consult
the young male system worker, and next week hand over to Yumesaki. W3 has no
researcher appearance. Receipt/spraying is known; chemical identity, biological
impact, parent internals and installer remain unknown through August's ending.

## Larger board and thinking loop

Outer radius grows from 88 to 94 logical pixels; inner disk from 24 to 30.
The board is centered at (256,106), leaving 6px before the footer. Arrows move
to radius112 with disjoint polar hit regions. Existing approved Jack front/blink
and Fuse thinking assets are reused unchanged. Jack gently tilts/blinks; Fuse
floats and tilts, with a small 「うーん」 bubble. This presentation-only loop never
requests help, changes power or alters the puzzle or its saved state.

Pixel speech bubbles use 「うーん」, short operation exclamations (1.8s
rate limit, Fuse delayed 0.22s), and a bulb when aligned. No Unicode emoji glyphs
are required. After unlock the head tilt stops and the bulbs remain; no endless
worried pose. Bubbles stay in character side margins outside the polar hit regions.

## One-shot clear celebration

After the outward unlock light: celebrating (3.2s) -> unlocked. Reuses the
combat renderer victory eight-view order and sine jump convention; both actors
make three quick eight-direction turns (0.9s each), one per small hop (Fuse delayed 0.22s).
No planar sprite rotation during the turn. Jack front happy eyes (no mouth) and Fuse
front happy eyes are tiny cached face-only copies; original assets stay unchanged.
Fuse uses the approved smile portrait after settling. Only 12 analytical confetti
pieces plus four sparkles per actor, confined to side margins; no growing emitter.
Completion facts preserve the settled unlocked state on re-entry without replaying
the one-shot celebration. Original actor assets stay unchanged.

## Background grid: diagonal travelling waves

The fixed 24px grid carries two slow brightness fronts: top-left to bottom-right
and top-right to bottom-left. Their diagonal phase has a gentle sinusoidal bend
and a 0.23-cycle offset, with nominal travel period 6s (previously 12s). Maximum mixing caps
crossings at the previous brightness ceiling. Grid geometry never deforms and
there is no random noise/dither. Cached 8px line segments, with hidden board
segments omitted, keep drawing bounded. The reserved dark-green 64-shade palette
leaves foreground colors intact and is restored on exit. Both propagation and bending run at exactly twice the previous time scale, preserving
the trajectory, phase offset and brightness cap. No input/save changes;
mouth-free Jack and 0.9s-per-turn celebration are unchanged.

Three 3x3 background dots advance right at 36/30/42px/s. Each horizontal
intersection chooses straight or one vertical grid cell to an adjacent row;
after a vertical cell, moving right is mandatory before another decision.
Rows remain within 24..192. No backwards travel or vertical ping-pong.
After the dot exits beyond x=512, a new passage enters off-screen from the left
on a privately selected row. Each passage's independent seeded random route is
cached; no per-draw re-selection or global/story RNG use. Intersections glow for
0.32s with up to 4px arms. The 6s waves, palette limits, input/save and celebration
remain unchanged.

Round rotation shortcuts sit near the arch tops at (154,30)/(358,30), with
18px visual radius and 22px circular hit radius. The arches remain active. Both
return the same left/right action through a single dispatch; the same rotation
step and in-flight lock apply, with no second activation from overlapping areas.

## Idle initial-layout advice (presentation only)

The approved initial board and five links remain fixed. R5-, R4+, R4+, R3-,
R3-, R2+, R1- is an outer-to-inner monotone seven-tap clear. After10s without
input in an unsolved idle linked board, Fuse says exactly:
「外側から順に計7回転で解けそうな初期配置ね」
It refers to the original full-link initial layout, never the current remaining
moves (including when the current board or links have changed). Any input dismisses it; it never interrupts rotating,
unlocking or celebration and does not recur during the same preview visit.
Re-entering starts a fresh presentation timer; the timer is not serialized.
This advice never calls assist or changes qualification/history. Phase labels
and character names are hidden; actors sit12px lower, and the text bubble is
confined to the right margin. Fuse's icon bubble is suppressed while text is shown.

## Opening reward-condition message

Linked entry shows exactly these two lines after about 3 seconds, when idle:
「解けたら、」
「ご褒美あげちゃう！」

The message lasts 6 seconds, uses a compact 54px-high side balloon, and condenses
long lines horizontally while retaining native glyph height. It hides during
rotation and is cancelled on solving/unlocking/celebration. It is mutually
exclusive with the ten-second idle advice. Neither message marks help or changes
reward eligibility. Phase/name and linkage-description labels are hidden; UNDO remains
an independent fourth footer action. No later-week story has been added.
