from types import SimpleNamespace

import pytest

from drift_with_me.audio_levels import OUTPUT_GAIN
from drift_with_me.events import GameEvent
from drift_with_me.music import BATTLE_QUARTER_SEC, MusicContext, MusicController, context_for


class FakePyxel:
    def __init__(self):
        self.sounds = [SimpleNamespace(set=lambda *a: None) for _ in range(64)]
        self.channels = [SimpleNamespace(gain=0.125) for _ in range(4)]
        self.plays, self.stops, self.position = [], [], None

    def play(self, *a, **kw):
        self.plays.append((a, kw))

    def stop(self, ch):
        self.stops.append(ch)

    def play_pos(self, ch):
        return self.position


def setup():
    p = FakePyxel()
    m = MusicController()
    m.setup(p)
    return m, p


def update(m, context=None, dt=1 / 60, muted=False, suspended=False):
    m.update(context or MusicContext(True), dt, muted=muted, suspended=suspended)


def test_music_voices_and_live_round_anchor_never_use_se_channel():
    m, p = setup()
    update(m)
    assert m.track == "explore"
    battle = object()
    update(m, MusicContext(True, battle=battle, phase="COMBAT_ENTRY"))
    timing = MusicContext(True, battle=battle, phase="PARRY_TIMING", anchor_target=0.595)
    update(m, timing)
    assert p.plays[-1][1]["sec"] == pytest.approx((-0.595) % BATTLE_QUARTER_SEC)
    count = len(p.plays)
    update(m, timing)
    assert len(p.plays) == count
    assert all(a[0] in [0, 1, 2] for a, kw in p.plays)
    assert 3 not in p.stops and p.channels[3].gain == 0.125


def test_phrase_continues_after_map_return_then_exploration_fades():
    m, p = setup()
    battle = object()
    update(m, MusicContext(True, battle=battle, phase="VICTORY_CUE"))
    assert m.track == "battle"
    update(m, MusicContext(True, battle=battle, phase="COMBAT_RESTORE_JUMP", victory=True))
    for _ in range(60):
        update(m)
    assert m.track == "fanfare"
    for _ in range(80):
        update(m)
    assert m.track == "explore"
    for _ in range(80):
        update(m)
    assert p.channels[0].gain == pytest.approx(0.125 * OUTPUT_GAIN)


@pytest.mark.parametrize("outcome", ["defeat", "capture", "deflect"])
def test_no_burst_win_and_loss(outcome):
    m, p = setup()
    update(m, MusicContext(True, battle=object(), phase="VICTORY_CUE"))
    m.observe_events(
        [
            GameEvent(
                1, 0, "combat_restored", "player", "enemy", (0, 0, 0), {"combat_outcome": outcome}
            )
        ]
    )
    update(m)
    assert m.track == "fanfare"
    m.reset()
    update(m, MusicContext(True, battle=object(), phase="COMBAT_EXIT_PLAYER_KNOCKBACK"))
    update(m)
    assert m.track == "explore"


def test_pause_native_position_mute_expiry_and_screen_change():
    m, p = setup()
    update(m)
    p.position = (0, 0.7)
    update(m, MusicContext(True, paused=True))
    assert m.position == 0.7
    count = len(p.plays)
    update(m, suspended=True)
    assert len(p.plays) == count
    p.position = None
    update(m)
    assert p.plays[-1][1]["sec"] == 0.7
    update(m, MusicContext(True, battle=object(), phase="victory", victory=True), muted=True)
    for _ in range(140):
        update(m, muted=True)
    assert m.track == "explore" and not m.output_running
    update(m)
    assert m.track == "explore" and m.output_running
    update(m, MusicContext(False))
    assert m.track is None


def test_native_end_beats_slow_clock():
    m, p = setup()
    ctx = MusicContext(True, battle=object(), phase="victory", victory=True)
    update(m, ctx)
    p.position = (0, 0.5)
    update(m, ctx)
    p.position = None
    update(m, ctx)
    assert m.track == "explore"


def test_lifecycle_guards_and_context_policies():
    app = SimpleNamespace(screen=SimpleNamespace(name="PLAY"), _lifecycle_wait_draw=True)
    assert context_for(app).paused
    app._lifecycle_wait_draw = False
    app._lifecycle_wait_release = True
    assert context_for(app).paused
    app._lifecycle_wait_release = False
    enemy = SimpleNamespace(kind="normal")
    session = SimpleNamespace(
        enemy_id="x",
        phase="PARRY_TIMING",
        marker_positions=(0.34, 0.58, 0.82),
        timing_elapsed_sec=0,
        outcome=None,
        zap_used=False,
    )
    app.model = SimpleNamespace(
        combat_session=session, enemy_by_id=lambda _: enemy, combat_parry_sweep_sec=lambda: 1.75
    )
    assert context_for(app).anchor_target == pytest.approx(0.595)
    enemy.kind = "abnormal"
    assert context_for(app).anchor_target is None
    app.model.combat_session = None
    battle = SimpleNamespace(
        phase="approach", elapsed=0, settings=SimpleNamespace(target=0.72, sweep=1.75)
    )
    app.model.swarm_field = SimpleNamespace(battle=battle)
    assert context_for(app).anchor_target == pytest.approx(1.26)
    battle.phase = "victory"
    assert context_for(app).victory
