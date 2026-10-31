from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from drift_with_me.app import AppScreen, PointerSnapshot
from drift_with_me.app import DriftWithMeApp as App
from drift_with_me.config import load_runtime_config
from drift_with_me.screen_flow import WEEK_FLOWS, FrameDispatch, dispatch_early, resolve_state
from drift_with_me.week_cycle import WorkWeek


def subject(month=6, number=1, phase="counter", screen=AppScreen.OFFICE):
    app = App.__new__(App)
    app.screen = screen
    app.work_week = WorkWeek(month, number)
    app.office = SimpleNamespace(
        august_progress=SimpleNamespace(phase=phase),
        week2_progress=SimpleNamespace(phase=phase),
        week3_progress=SimpleNamespace(phase=phase),
        week4_progress=SimpleNamespace(phase=phase),
    )
    app.runtime = load_runtime_config()
    app.presentation_time = 0
    app.week_debug_menu_open = False
    app.week_debug_active = False
    app.pointer_snapshot = PointerSnapshot(False, True, 494, 13)
    return app


def test_registry_covers_exactly_the_twelve_authored_weeks():
    assert set(WEEK_FLOWS) == {(m, n) for m in (6, 7, 8) for n in range(1, 5)}
    assert WEEK_FLOWS[7, 4].handlers == ("update_august", "update_july_week4")


@pytest.mark.parametrize("month,number", sorted(WEEK_FLOWS))
def test_visible_office_calendar_and_modal_use_same_frame_state(month, number):
    app = subject(month, number)
    assert app.office_calendar_visible()
    app.week_debug_menu_open = True
    assert not app.office_calendar_visible()
    assert resolve_state(app).modal == "week_debug_menu"


def test_august3_recovered_landscape_has_no_invisible_calendar_or_badge():
    app = subject(8, 3, "done")
    app.week_debug_active = True
    assert resolve_state(app).surface == "recovered_landscape"
    assert not app.office_calendar_visible()
    assert not app.week_debug_badge_visible()
    assert not app.update_week_debug()
    assert not app.week_debug_menu_open


@pytest.mark.parametrize(
    "name",
    [
        "flowerbed_editor",
        "flowerbed_dialogue",
        "week2_dialogue",
        "week3_dialogue",
        "week4_dialogue",
    ],
)
def test_debug_badge_cannot_intercept_an_invisible_entry_over_field_overlay(name):
    app = subject(7, 2, screen=AppScreen.PLAY)
    app.week_debug_active = True
    app.pointer_snapshot = PointerSnapshot(False, True, 40, 40)
    setattr(app, name, object())
    assert resolve_state(app).modal == name
    assert not app.week_debug_badge_visible()
    assert not app.update_week_debug()
    assert not app.week_debug_menu_open


@pytest.mark.parametrize("month,number", [(7, 3), (7, 4), (8, 1), (8, 2), (8, 4)])
def test_consultation_owns_input_before_month_office_handler_and_owns_draw(month, number):
    app = subject(month, number, "office")
    app.office_consultation = object()
    app.update_week_debug = Mock(return_value=False)
    app.update_office_shared_controls = Mock(return_value=True)
    app.sync_august_sighting_lock = Mock()
    app.update_patrol = Mock(return_value=False)
    assert dispatch_early(app, 1 / 60)
    app.update_office_shared_controls.assert_called_once()
    app.update_patrol.assert_not_called()
    assert app.last_ui_dispatch[1] == "office_consultation"
    app.draw_office = Mock()
    app.draw_august_overlay = Mock(return_value=True)
    App.draw_active_scene(app)
    app.draw_office.assert_called_once()
    app.draw_august_overlay.assert_not_called()


def test_owner_commits_a_state_transition_even_if_legacy_hook_returns_false():
    app = subject()
    frame = FrameDispatch(app)

    def transition():
        app.screen = AppScreen.PLAY
        return False

    assert frame.try_owner("transition", transition)
    with pytest.raises(RuntimeError):
        frame.try_owner("second_owner", lambda: True)


def test_transition_overlay_draws_even_when_base_scene_returns_early():
    app = subject()
    calls = []
    app.lifecycle_draw_allowed = lambda: True
    app.draw_active_scene = lambda: calls.append("base_early_return")
    app.draw_week_transition = lambda: calls.append("week")
    app.draw_field_transition = lambda: calls.append("field")
    app.draw_collectible_notice = lambda: calls.append("notice")
    app.lifecycle_did_draw = lambda: calls.append("drawn")
    app.draw()
    assert calls == ["base_early_return", "week", "field", "notice", "drawn"]


def test_all_twelve_normal_weeks_cross_the_root_router_at_action_boundaries(monkeypatch):
    import twelve_week_driver as driver
    from screen_flow_helpers import probe

    rows = []

    def capture(app, label):
        result = probe(app, frames=3)
        for frame in result["frames"]:
            assert len(frame["owners"]) <= 1, (label, frame)
        rows.append(((app.work_week.month, app.work_week.number), label, result))

    for name in ("close_case", "dispatch", "read", "next_week", "resume"):
        original = getattr(driver, name)

        def around(app, *args, _original=original, _name=name, **kwargs):
            capture(app, "before:" + _name)
            result = _original(app, *args, **kwargs)
            capture(app, "after:" + _name)
            return result

        monkeypatch.setattr(driver, name, around)
    app, storage, garden, records = driver.run_all(reload_each_boundary=True)
    assert {week for week, label, result in rows} == set(WEEK_FLOWS)
    assert len(rows) >= 200
    assert len(records) == 12
    assert app.screen == AppScreen.COLLECTION_ROOM
    assert garden.items == {}


@pytest.fixture(scope="module")
def normal_week_milestones():
    """Reach all weeks with existing domain actions; never assign completion flags."""
    from copy import deepcopy

    from twelve_week_driver import new_game, next_week, play_week

    app, storage, garden = new_game()
    milestones = {}
    for index in range(12):
        key = (app.work_week.month, app.work_week.number)
        entry = deepcopy(app)
        play_week(app)
        app.checkpoint_progress()
        milestones[key] = {"entry": entry, "done": deepcopy(app)}
        if index < 11:
            next_week(app)
    assert len(milestones) == 12
    assert garden.items == {}
    return milestones


def root_mouse_frame(app, rect=None, *, down=False, pressed=False):
    """Actual App.update and native pointer snapshot; only hardware is synthetic."""
    if rect is not None:
        app.pyxel.mouse_x = rect.x + rect.width / 2
        app.pyxel.mouse_y = rect.y + rect.height / 2
    app.pyxel.down = down
    app.pyxel.pressed = pressed
    App.update(app)


def root_tap(app, rect, hold=1):
    root_mouse_frame(app, rect, down=True, pressed=True)
    for _ in range(hold - 1):
        root_mouse_frame(app, rect, down=True)
    root_mouse_frame(app, rect)


@pytest.mark.parametrize("week", sorted(WEEK_FLOWS))
@pytest.mark.parametrize("milestone", ["entry", "done"])
def test_full_root_calendar_open_close_preserves_each_normal_week(
    normal_week_milestones, week, milestone
):
    from copy import deepcopy

    from drift_with_me.save_state import snapshot
    from screen_flow_helpers import clone_for_root_update

    original = normal_week_milestones[week][milestone]
    original_state = snapshot(original)
    original_records = deepcopy(original.progress_store.browser.items)
    app = clone_for_root_update(original)
    before = snapshot(app)
    records = deepcopy(app.progress_store.browser.items)
    dialog_before = deepcopy(app.office_dialogue_playback)
    assert app.screen == AppScreen.OFFICE
    if week == (8, 3) and milestone == "done":
        # The recovered landscape has no calendar despite still using OFFICE.
        assert resolve_state(app).surface == "recovered_landscape"
        assert not app.office_calendar_visible()
        root_tap(app, app.office_calendar_rect())
        assert not app.week_debug_menu_open
    else:
        assert app.office_calendar_visible(), (week, milestone, resolve_state(app))
        # Holding a real pointer press must open only one modal, not select through it.
        root_tap(app, app.office_calendar_rect(), hold=4)
        assert app.week_debug_menu_open
        assert resolve_state(app).modal == "week_debug_menu"
        assert app.week_debug_month == week[0]
        assert app.week_debug_selection == week[1]
        assert not app.week_debug_active
        root_tap(app, app.week_debug_rects()["cancel"], hold=4)
        assert not app.week_debug_menu_open
        assert not app.week_debug_active
        assert app.office_dialogue_playback == dialog_before
    assert snapshot(app) == before
    assert app.progress_store.browser.items == records
    assert snapshot(original) == original_state
    assert original.progress_store.browser.items == original_records


@pytest.mark.parametrize("week", sorted(WEEK_FLOWS))
def test_full_root_consultation_respects_each_weeks_real_availability(normal_week_milestones, week):
    from copy import deepcopy

    from drift_with_me.save_state import snapshot
    from screen_flow_helpers import clone_for_root_update

    original = normal_week_milestones[week]["entry"]
    original_state = snapshot(original)
    app = clone_for_root_update(original)
    # Read the existing opening with actual pointer taps, rather than forcing a
    # ready-to-consult phase or replacing the normal office handlers.
    for _ in range(80):
        root_mouse_frame(app)
        if not app.office_dialogue_requires_advance():
            break
        root_tap(app, app.office_dialog_rect())
    assert not app.office_dialogue_requires_advance(), week
    assert app.office_calendar_visible(), (week, resolve_state(app))
    before = snapshot(app)
    records = deepcopy(app.progress_store.browser.items)
    available = app.office.supervisor_advice() is not None or app.week4_follow_available()
    root_tap(app, app.office_consultation_button_rect())
    if available:
        assert app.office_consultation is not None, week
        assert app.last_ui_dispatch[1] == "office_consultation"
        # The next release/idle frame cannot dispatch the same press into a
        # report, case or calendar owner beneath the consultation.
        root_mouse_frame(app)
        assert app.office_consultation is not None
        root_tap(app, app.office_consultation_button_rect())
        assert app.office_consultation is None
    else:
        assert app.office_consultation is None
    assert not app.week_debug_menu_open
    assert snapshot(app) == before
    assert app.progress_store.browser.items == records
    assert snapshot(original) == original_state


@pytest.mark.parametrize("week", sorted(WEEK_FLOWS))
def test_actual_host_short_taps_cross_full_root_modal_for_each_week(
    monkeypatch, normal_week_milestones, week
):
    import json
    import shutil
    import subprocess
    import sys
    from copy import deepcopy

    from scripts.build_web import HOST_JS

    from drift_with_me.save_state import snapshot
    from screen_flow_helpers import clone_for_root_update

    if shutil.which("node") is None:
        pytest.skip("Node required to execute the actual host bridge")
    original = normal_week_milestones[week]["entry"]
    original_state = snapshot(original)
    app = clone_for_root_update(original)
    before = snapshot(app)
    records = deepcopy(app.progress_store.browser.items)
    assert app.office_calendar_visible()
    calendar = app.office_calendar_rect()
    # Opening the calendar selects the compact modal; ask the real layout for
    # its Cancel target on a separate layout-only copy, not the progressed app.
    layout = clone_for_root_update(original)
    layout.week_debug_compact = True
    cancel = layout.week_debug_rects()["cancel"]
    targets = [[rect.x + rect.width / 2, rect.y + rect.height / 2] for rect in (calendar, cancel)]
    harness = r"""
const fs=require('fs'),vm=require('vm'),events={};
const targets=JSON.parse(process.argv[1]);
const rect={left:13,top:47,width:844,height:390};
const canvas={width:2048,height:1200,getBoundingClientRect:()=>rect,
setPointerCapture(){},releasePointerCapture(){}};
const win={top:{},innerWidth:844,innerHeight:390,
__driftWithMeLogicalSize:{width:512,height:236},addEventListener(){}};
const doc={querySelector:()=>canvas,documentElement:{style:{setProperty(){}}},
body:{classList:{toggle(){}}},addEventListener:(n,f)=>events[n]=f};
vm.runInNewContext(fs.readFileSync(0,'utf8'),{window:win,document:doc});
function event(x,y,type){
 const scale=Math.min(canvas.width/512,canvas.height/236);
 return {type,pointerId:1,cancelable:true,preventDefault(){},
 clientX:rect.left+((canvas.width-512*scale)/2+x*scale)*rect.width/canvas.width,
 clientY:rect.top+((canvas.height-236*scale)/2+y*scale)*rect.height/canvas.height};
}
const samples=[];
for(const [x,y] of targets){
 events.pointerdown(event(x,y,'pointerdown'));
 // Both edges occur before Python gets a sample. Release at a different
 // location also verifies that the owned press position cannot be replaced.
 events.pointerup(event(494,13,'pointerup'));
 samples.push({...win.__driftWithMePointer});
}
console.log(JSON.stringify(samples));
"""
    result = subprocess.run(
        ["node", "-e", harness, json.dumps(targets)],
        input=HOST_JS,
        text=True,
        capture_output=True,
        check=True,
    )
    samples = json.loads(result.stdout)
    assert [sample["sequence"] for sample in samples] == [1, 2]
    bridge = SimpleNamespace(**samples[0])
    monkeypatch.setitem(
        sys.modules,
        "js",
        SimpleNamespace(window=SimpleNamespace(__driftWithMePointer=bridge)),
    )
    App.update(app)
    assert app.week_debug_menu_open
    assert app.pointer_snapshot.pressed and not app.pointer_snapshot.down
    # The same latched sequence is not a second action on the following frame.
    App.update(app)
    assert app.week_debug_menu_open and not app.pointer_snapshot.pressed
    bridge.__dict__.update(samples[1])
    App.update(app)
    assert not app.week_debug_menu_open
    App.update(app)
    assert not app.week_debug_menu_open
    assert not app.week_debug_active
    assert snapshot(app) == before
    assert app.progress_store.browser.items == records
    assert snapshot(original) == original_state
