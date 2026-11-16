"""Approved march routing follows the week, not encounter or save progress."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.config import load_data_json
from drift_with_me.music import MusicContext, context_for
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek
from test_august_wave1 import august_app, complete_week, dispatch
from test_explore_music import update
from test_office_music import setup


def app_for_week(month, week):
    return SimpleNamespace(
        screen=AppScreen.PLAY,
        work_week=WorkWeek(month, week),
        model=SimpleNamespace(combat_session=None, swarm_field=None),
    )


@pytest.mark.parametrize("month", [6, 7, 8])
@pytest.mark.parametrize("week", [1, 2, 3, 4])
def test_only_story_infestation_weeks_use_the_march(month, week):
    app = app_for_week(month, week)
    expected = "infestation" if month == 8 and week in (2, 3) else "explore"
    assert context_for(app).ambient == expected
    app.model.swarm_field = SimpleNamespace(battle=None, cleared={"northwest"})
    assert context_for(app).ambient == expected
    app.screen = AppScreen.OFFICE
    assert context_for(app).ambient == "office"
    app.screen = AppScreen.PLAY
    app.week_transition = object()
    assert not context_for(app).active


def test_score_is_exact_approved_preview():
    score = load_data_json("bgm_score.json")["infestation"]
    assert hashlib.sha256(json.dumps(score, sort_keys=True).encode()).hexdigest() == (
        "d38e8612a68357f4f75b70b8fe4fbdc223fc7514e11707cb6d6773cee8f130c8"
    )
    assert len(score["parts"]) == 1
    part = score["parts"][0]
    assert len(part["notes"].split()) * part["speed"] / 120 == 48


def test_live_swarm_context_keeps_week_ambient_and_victory():
    app = app_for_week(8, 2)
    battle = SimpleNamespace(phase="victory", elapsed=0)
    app.model.swarm_field = SimpleNamespace(battle=battle)
    ctx = context_for(app)
    assert ctx.battle is battle and ctx.victory and ctx.ambient == "infestation"


def test_pause_background_mute_loop_week_change_and_office():
    music, player = setup()
    ctx = MusicContext(True, ambient="infestation")
    update(music, ctx)
    player.playing[0] = (0, 7.5)
    update(music, MusicContext(True, paused=True))
    update(music, ctx, suspended=True, dt=100)
    assert music.position == 7.5 and not player.playing
    update(music, ctx)
    assert player.plays[-1][2]["sec"] == 7.5
    update(music, ctx, muted=True, dt=48)
    assert music.position == 7.5 and not player.playing
    update(music, ctx)
    update(music, MusicContext(True, ambient="office"))
    assert music.track == "office"
    update(music, ctx)
    assert music.track == "infestation" and set(player.playing) == {0}
    update(music, MusicContext(True))
    assert music.track == "explore"


@pytest.mark.parametrize("week", [2, 3])
@pytest.mark.parametrize("completed", [False, True])
def test_save_roundtrip_restores_week_music_without_new_save_fields(week, completed):
    app, _ = august_app()
    while app.work_week.number < week:
        complete_week(app)
        assert app.begin_next_week()
        app.update_week_transition(0.56)
        app.update_week_transition(4)
        app.week_input_wait_for_release = False
        app.office.begin_current_case()
    dispatch(app)
    if completed:
        app.east_site_progress.swarm_progress[f"8:{week}"] = ["northwest", "northeast", "southeast"]
    before = snapshot(app)
    restored_week, offices, sites, *_ = decode(encode(before))
    app.work_week = restored_week
    app.office = offices[restored_week]
    app.east_site_progress = sites
    app.model.swarm_field = None
    music, player = setup()
    music.reset()
    update(music, context_for(app))
    assert music.track == "infestation"
    assert player.plays[-1][:2] == (0, 43)
    assert snapshot(app) == before
