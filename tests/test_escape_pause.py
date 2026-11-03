"""Real initialization and explicit pause/quit routes in a fresh native runtime."""

import os
import subprocess
import sys
from pathlib import Path


def test_escape_is_reserved_for_app_pause_and_explicit_quit_still_works():
    script = r"""
import pyxel
from drift_with_me.app import DriftWithMeApp, AppScreen
from drift_with_me.week_cycle import WorkWeek
seen = {}
init = pyxel.init
def inspect_init(*args, **kwargs):
    seen.update(kwargs)
    kwargs['capture_sec'] = 0
    return init(*args, **kwargs)
pyxel.init = inspect_init
pyxel.run = lambda *_: None
app = DriftWithMeApp(headless=True, week_debug=True)
assert seen['quit_key'] == pyxel.KEY_NONE
assert not app.normal_progress_store.enabled
assert app.jump_to_debug_week(WorkWeek(6, 1))
app.screen = AppScreen.PLAY
app.field_conversation = app.first_sight_conversation = None
app.field_transition = app.week_transition = None
app.week_debug_menu_open = app.week_debug_wait_release = False
app.draw()
assert app.renderer._pixel_stability_active
assert app.renderer._stable_nearest.builds > 0  # Production B defaults on, no A switch.
pyxel.btn = lambda *_: False
pyxel.btnp = lambda key: key == pyxel.KEY_ESCAPE
app.update_play_screen(1 / 60)
assert app.screen == AppScreen.PAUSE
pyxel.btnp = lambda key: key == pyxel.KEY_RETURN
app.update_pause_screen()
assert app.screen == AppScreen.PLAY
quit_calls = []
pyxel.quit = lambda: quit_calls.append(True)
app.screen = AppScreen.PAUSE
pyxel.btnp = lambda key: key == pyxel.KEY_Q
app.update_pause_screen()
assert quit_calls == [True]
"""
    source = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "PYTHONPATH": source},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
