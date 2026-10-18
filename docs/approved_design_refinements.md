# Approved local design refinements

## Implemented in existing July weeks

- July W2 Yoake/Merrill: retain authored opening, hearing and reply; reading the
  conversation completes the case without choosing a formal classification.
  Existing June decisions and July survey dispatch classification remain. No new
  outcome branch is authored. Legacy hearing cursors remain readable.
- July W1 explicitly names Fuji/material and water checks as duties; Jack's
  existing opening adds his wish to complete the summer assignment with Fuse and
  be trusted as a full colleague. No extra scene or new turn ID is introduced.
- July W2 explicitly asks for the five flowerbed plots to be finished this week.
  Existing four sites distinguish localized magenta leaves, unchanged roots,
  fallen stems and ground traces; no machine/chemical cause is asserted.
- Flowerbed/Fuji and Return hit targets are separated so resuming near the bed
  cannot open Fuji conversation when pressing Return.
- Completing W2 opens one return/stay choice rather than auto-returning. Stay
  leaves existing return available. A saved optional `return_prompt_seen` bit
  suppresses repeated prompts across re-entry/reload; old saves default false.
  Partial return, report and completion remain supported. July W1's authored
  professor scene and time-skip fade remain unchanged.
- Ring: assistance has no sunglasses penalty. Either completed linked route
  satisfies `clear_reward_available`; only special praise depends on help.
  `ring_rewards.RingRewardLedger` provides a serializable, idempotent story reward
  contract. Debug previews only show completion dialogue and never grant normal
  inventory. Legacy ring help/forfeiture fields are retained for compatibility;
  forfeiture affects only conservative special-praise handling.

## Approved ending intent: specification, not implemented story

Jack's personal arc should conclude with his and Fuse's assigned summer duties
completed: three devices stopped/recovered, materials handed over and continuing
investigation arranged. The devices' cause/identity can remain unresolved while
work has a clear endpoint. A short supervisor report can acknowledge completion
and let the pair leave for summer vacation; no researcher reappearance is needed.
No machine installer, chemical identity or biological causation is established.

Sunglasses are the default ring-clear present, including assisted clears; only a
special line is exclusive to an unassisted clear. When W3/ED is authored, its
normal story save must own/serialize the reward ledger and the ED wardrobe must
consume that flag. Neither integration exists yet. Do not treat debug completion
as a normal-game reward transaction.

## Out of scope

No supply-cost/frequency adjustment without measurement. No grass cutting,
terminal events, W3 through ED story expansion, deployment or new story branches.
