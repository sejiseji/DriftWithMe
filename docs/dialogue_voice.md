# Dialogue sound

Office text naturally revealing letters or numbers makes a quiet native Pyxel tick.
There are six sound-design presets: male child/adult/elder and female child/adult/elder.
These are sound-design labels, not new demographic canon. Following the user's
request, the actual runtime portraits were inspected and all 19 office characters
were assigned explicitly in `data/dialogue_voices.json`. The age groups mean
school-child-like, approximately twenties/thirties, and older-than-that; the internal
`elder` key includes middle-aged designs. Human ages are not inferred for the octopus
Jack or robot Fuse. Jack retains the provisional workplace-role choice. Fuse now uses the young-adult feminine preset explicitly requested on November 10.
Jack/ジャック, エトウ/上司 and ミズノ/清掃業者 aliases resolve consistently.
The non-character report label 確認記録 is silent. Future unknown speakers retain an
explicitly provisional fallback. A line can also provide `voice_preset` directly.

The six tiny sounds occupy slots 16–21 on SE channel 3. Existing effects use 0–15,
and BGM uses channels 0–2 with slots 32+. A tick never interrupts anything, including
another tick; every normal SE can replace a tick. At most one tick is attempted every
66.7 ms of dialogue updates (frame quantization applies), without per-character queues.
Slow frames emit at most one tick. Spaces, punctuation and symbols are silent.
Instant reveal and direct story-page changes do not enqueue skipped letters. Pause
stops reveal updates; mute and lifecycle suspension discard ticks without replay.
No sample decoding, waveform allocation or external audio files are used at runtime.


## Approved quiet playback level

The six approved note/tone/envelope shapes are unchanged. Dialogue alone plays at
half the channel's configured baseline gain (about -6 dB relative to the approved
preview). The office BGM gain is unchanged. Every ordinary SE restores the baseline
channel-3 gain before starting, including effects that interrupt a dialogue tick.
Mute, lifecycle suspension and reset stop the tick and restore the channel baseline.


## Character casting

- Male child: モリス.
- Female child: ルビィ.
- Male adult: Jack/ジャック, 旅の勇者, サガン, ミズノ/清掃業者.
- Female adult: ヒューズ, ミナ, ラメル, タカナシ, ヨアケ, ウラ, ユメサキ, ミヤノ.
- Male older group: エトウ/上司, グロウ, フジ, イワマ.
- Female older group: メリル.

Each entry records the actual portrait asset and a brief casting rationale. ラメル
and イワマ additionally retain their explicit authored-description sources. Except for the explicit Fuse request, other
visual/role-based assignments are provisional sound casting, as requested. Existing
character/story metadata is unchanged. Portraits use the current counter remaps,
including the refined researcher busts, rather than obsolete source art.


## Field dialogue (November 10 update)

The field-style windows now reveal at the same 72 characters/second as the office.
This covers ordinary field/collectible conversation, first sightings, travel exchanges,
flowerbed visits, July week scenes and return choices, August sightings and patrols.
The portrait debug preview uses the same presentation. Existing office/report playback
is preserved; the July week-two report uses its existing field-style window.

Speaker names and portraits remain immediately visible. Body wrapping is computed
from the complete text before revealing, so already visible punctuation does not move.
A confirm/tap during reveal shows the full current line without a skipped-character
sound burst or a progress/save/award action. The next press reaches the original
scene handler. Cancel/Back, input-release gates and pause retain their existing actions.
Reopening a closed conversation starts its text reveal again; saved dialogue positions
and all game progress retain their existing schema and semantics.

Natural revealed letters/numbers reuse the quiet office voice engine, including
speaker changes and Fuse's female_adult preset. Punctuation, unnamed narration and
confirmation-record labels stay silent. Ticks are throttled, never queued, and never
interrupt gameplay SE. Pause/background freezes presentation; mute reveals silently.
The single exploration music channel and dialogue SE channel 3 can coexist; combat,
results, office music and the existing feedback SE are not disabled by this change.
