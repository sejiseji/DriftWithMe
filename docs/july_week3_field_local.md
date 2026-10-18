# July W3 field connection — local implementation

Base: b16b4a8. Includes the W3 supervisor report and week completion.
No young system-worker appearance, W4 dialogue/ED, new enemies, map expansion or grass cutting is included.

## Route

Completed W2 -> W3 scheduled supervisor opening -> survey dispatch. 9am is a
story schedule, not a wall-clock gate. Fuji gives one brief construction-progress
observation. Existing W2 leaf discoloration persists in W3 and does not heal when
devices are stopped; no cause or biological effect is asserted.

Small cube sites: Fuji-area (274,440), northwest (278,752), near confirmed leaf
changes at (288,416)/(252,758). The initial Fuji trial at (316,406) was shifted to
avoid the existing wall hiding Jack. Parent: (948,826), outside the northeast
construction plot (800,840)-(904,912). All devices are non-solid and do not block
paths, supplies or NPCs. Approaches are tested for collision clearance.

Each small cube: inspect/discover -> zoom/pick up -> Jack tosses it -> Fuse shorts
it in midair -> collect -> return framing. The two actors are staged only on a
presentation copy; real transforms/camera/resources are unchanged. World simulation
and other input are held during scenes. Energy cost is zero, including at zero
energy. Existing battle state must end before starting an inspection/scene.

Parent can be inspected before both small cubes; this returns to exploration.
After two recoveries, inspect -> linked ring puzzle -> clear -> default sunglasses
record -> return to device -> Fuse disconnects it (not an electric short) ->
collect. Unassisted reward is only a special praise line, never a cosmetic gate.

## Save contract

The normal office save owns week3_progress, terminal discovery/recovery, dialogue
cursor, scene stage, parent stop/recovery, ring help facts and RingRewardLedger.
Scenes checkpoint stages; resuming does not replay earlier completed stages.
Collected devices are removed and cannot be collected or rewarded twice.

The ring board/rotation/selection/undo stack are never serialized. Leaving and
re-entering resets the legal board, retaining removed links/help/praise facts.
A solved ring is a durable completion; reward is idempotent even across interrupted
celebration/re-entry. A story adapter never touches debug ring storage. Week debug
continues using temporary state and cannot write the normal slot. Save failure
rolls back assistance before accepting it and prevents leaving an unsaved puzzle.

After all three recoveries, offer Return / Stay once and persist that prompt history.
Stay leaves the existing Return button available; reload does not repeat the prompt.
Early return keeps FIELD_ACTIVE and allows redispatch, without a completion report.
Completed return checkpoints phase=report before travel. Cancelling travel restores
phase=field transactionally; reloading travel resumes safely in the office.

The five-turn report uses the native office supervisor portrait, central dialogue
content rectangle, hanging text, typing/reveal and page-advance handlers. No
exploration conversation window is drawn in the office. Other panels cannot
advance the report or dispatch field work while reporting. Each
advance checkpoints report_index. The final advance alone atomically marks the
case RESOLVED, writes JULY3_COMPLETED with all three recovered IDs, clears the active
field task, and sets phase=done / professor_handoff_pending=true. Failed saves roll
back both cursor and office completion. Sunglasses/help/recovery facts remain intact.

Done uses the existing week-completion screen and records the plan to hand the
three physical devices to Yumesaki next week. W4 remains unauthored, so no Next
button is shown and repeated footer input cannot return to exploration or replay
report/rewards. No device is transferred to Yumesaki yet. The W3 office snapshot
retains the collected IDs and reward ledger for future week history. Older published
W3 saves gain defaults for the report cursor/prompt/handoff; no schema bump is needed.

The supervisor is formally named エトウ (user decision, 2026-10-18). The office
character register is the name source. Dialogue and portrait name fields use エトウ;
role/action labels such as 上司に相談 remain. Supervisor dialogue uses visitor-yellow
(palette 10); Jack stays white. Published counter saves labelled 上司 normalize the
speaker name before validation, without altering text, cursors or recovery/rewards.
