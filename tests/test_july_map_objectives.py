"""July goal presentation survives source integration and save reloads."""

import pytest

from drift_with_me.july_week1 import ENEMY_IDS
from drift_with_me.map_objectives import map_goals
from drift_with_me.save_state import decode, encode, snapshot
from test_july_story import july_app


def test_july_goal_completion_survives_save_resume():
    app = july_app()
    major, rows = map_goals(app)
    assert not major.done and [row.done for row in rows] == [False] * 4
    progress = app.office.july_progress
    progress.defeated = set(ENEMY_IDS)
    progress.researchers_arrived = True
    progress.researchers_talked = True
    progress.materials_checked = True
    progress.water_checked = True
    assert map_goals(app)[0].done
    assert all(row.done for row in map_goals(app)[1])
    _, offices, *_ = decode(encode(snapshot(app)))
    app.office = offices[app.work_week]
    assert map_goals(app)[0].done
    assert all(row.done for row in map_goals(app)[1])


@pytest.mark.parametrize("stage", ["after_clear", "arrival_fade", "researchers", "return_pending"])
def test_july_story_prevents_goal_drawer_clicks(stage):
    app = july_app()
    app.office.july_progress.stage = stage
    app.mouse_pressed_in = lambda rect: rect == app.map_objective_button_rect()
    before = snapshot(app)
    assert app.map_objectives_blocked()
    assert not app.update_map_objectives()
    assert not getattr(app, "map_objective_open", False)
    assert snapshot(app) == before
