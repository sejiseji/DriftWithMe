"""Real host JS -> Python -> full root update, with synthetic debug storage only.

The Node VM exercises browser event ordering and canvas geometry; it is not a
Safari/iPhone runtime. Domain completion flags and production save data are never
assigned or inspected. The actual UI handlers advance the Mina dialogue.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.build_web import HOST_JS

from drift_with_me.app import AppScreen
from drift_with_me.app import DriftWithMeApp as App
from drift_with_me.week_cycle import WorkWeek

HOST_EVENT_SERVER = r"""
const vm = require('vm');
const readline = require('readline');
let host;
function initialize(config) {
  const events = {}, windows = {};
  const [bw, bh, left, top, width, height] = config.geometry;
  const canvas = {
    width: bw, height: bh,
    getBoundingClientRect: () => ({left, top, width, height}),
    setPointerCapture() {}, releasePointerCapture() {}
  };
  const win = {
    top: {}, innerWidth: width, innerHeight: height,
    __driftWithMeLogicalSize: {width: 512, height: 236},
    addEventListener: (name, fn) => {windows[name] = fn;}
  };
  const doc = {
    querySelector: () => canvas,
    documentElement: {style: {setProperty() {}}},
    body: {classList: {toggle() {}}},
    addEventListener: (name, fn) => {events[name] = fn;}
  };
  vm.runInNewContext(config.source, {window: win, document: doc});
  const toEvent = (operation) => {
    const k = Math.min(bw / 512, bh / 236);
    const [x, y] = operation.point;
    return {
      type: operation.kind, pointerId: operation.id || 1,
      cancelable: true, preventDefault() {},
      clientX: left + ((bw - 512 * k) / 2 + x * k) * width / bw,
      clientY: top + ((bh - 236 * k) / 2 + y * k) * height / bh
    };
  };
  return {
    execute(operations) {
      for (const operation of operations) events[operation.kind](toEvent(operation));
      return {...win.__driftWithMePointer};
    }
  };
}
readline.createInterface({input: process.stdin}).on('line', (line) => {
  const command = JSON.parse(line);
  if (!host) host = initialize(command);
  console.log(JSON.stringify(host.execute(command.operations || [])));
});
"""


class HostEvents:
    """Keep the production host alive so it, not the test, issues sequences."""

    def __init__(self, geometry):
        self.process = subprocess.Popen(
            [shutil.which("node"), "-e", HOST_EVENT_SERVER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.sequence = 0
        self.publish({"source": HOST_JS, "geometry": geometry})

    def publish(self, command):
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()
        response = self.process.stdout.readline()
        if not response:
            raise AssertionError("Node host stopped: " + self.process.stderr.read())
        self.pointer = json.loads(response)
        assert self.pointer["sequence"] >= self.sequence
        self.sequence = self.pointer["sequence"]
        return self.pointer

    def emit(self, *operations):
        return self.publish({"operations": operations})

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=5)
        self.process.stdout.close()
        self.process.stderr.close()
        assert self.process.returncode == 0


def operation(kind, point):
    return {"kind": kind, "point": point}


def center(rect):
    return rect.x + rect.width / 2, rect.y + rect.height / 2


def run_mina_flow(monkeypatch, geometry):
    import pyxel

    monkeypatch.setattr(pyxel, "run", lambda *_: None)
    app = App(headless=True, week_debug=True)
    assert not app.normal_progress_store.enabled
    assert app.week_debug_menu_open
    monkeypatch.setattr(pyxel, "btn", lambda *_: False)
    monkeypatch.setattr(pyxel, "btnp", lambda *_: False)
    app.consume_elapsed = lambda: 1 / 60
    app._lifecycle_bridge = False
    host = HostEvents(geometry)
    bridge = SimpleNamespace(**host.pointer)
    monkeypatch.setitem(
        sys.modules,
        "js",
        SimpleNamespace(window=SimpleNamespace(__driftWithMePointer=bridge)),
    )
    trace = []
    actions = []

    def record(name):
        original = getattr(app, name)

        def around(*args, **kwargs):
            label = name
            if name == "ask_or_select_office_question":
                label += ":" + args[0].question_id
            actions.append((host.sequence, label))
            return original(*args, **kwargs)

        monkeypatch.setattr(app, name, around)

    record("advance_office_dialogue_page")
    record("ask_or_select_office_question")

    def tick(label, allow_menu=False):
        bridge.__dict__.update(host.pointer)
        before_count = len(actions)
        before_menu = app.week_debug_menu_open
        before_selection = (app.week_debug_month, app.week_debug_selection)
        app.update()
        if before_menu != app.week_debug_menu_open:
            action = "calendar:open" if app.week_debug_menu_open else "calendar:close"
            actions.append((host.sequence, action))
        elif app.week_debug_menu_open and before_selection != (
            app.week_debug_month,
            app.week_debug_selection,
        ):
            actions.append((host.sequence, "calendar:selection"))
        frame_actions = actions[before_count:]
        assert len(frame_actions) <= 1, (label, frame_actions)
        assert allow_menu or not app.week_debug_menu_open, (label, host.pointer)
        trace.append((host.sequence, label, app.pointer_snapshot.pressed, tuple(frame_actions)))

    def idle(frames=2, allow_menu=False):
        for _ in range(frames):
            host.emit()
            tick("idle", allow_menu)

    def tap(point, label, allow_menu=False):
        host.emit(operation("pointerdown", point), operation("pointerup", point))
        tick(label, allow_menu)
        idle(allow_menu=allow_menu)

    def arrow():
        rect = app.office_dialog_rect()
        # The actual advance prompt is 12x8 with a 3px bottom/right inset.
        return rect.x + rect.width - 9, rect.y + rect.height - 7

    def drain(label, predicate):
        for index in range(160):
            if not predicate():
                return
            tap(arrow(), label + str(index))
        raise AssertionError("Dialogue did not complete: " + label)

    try:
        # Launch through the real debug menu button; no jump/domain flags assigned.
        tap(center(app.week_debug_rects()["start"]), "start June1")
        assert app.work_week == WorkWeek(6, 1)
        assert app.screen == AppScreen.OFFICE
        assert app.office.current_case.case_id == "OFF-PROT-001"
        drain("opening", app.office_dialogue_requires_advance)
        identity_index = next(
            i
            for i, question in enumerate(app.office.current_case.questions)
            if question.question_id == "identity"
        )
        identity_point = center(
            app.office_question_rect(identity_index, len(app.office.current_case.questions))
        )
        tap(identity_point, "identity question")
        session = app.office.current_session
        assert session.pending_question_id == "identity"
        assert session.selected_question_id == "identity"
        assert "identity" not in session.asked_question_ids
        drain("identity answer", lambda: "identity" not in session.asked_question_ids)
        assert {
            "mina_identity_check",
            "mina_identity_return",
        } <= session.completed_dialogue_turn_ids
        assert session.pending_question_id is None

        # Consecutive frame-level short presses and retained snapshots cannot re-fire.
        for index in range(16):
            host.emit(operation("pointerdown", arrow()), operation("pointerup", arrow()))
            tick("extra quick tap " + str(index))
        count = len(actions)
        idle(5)
        assert len(actions) == count

        # A held touch is one activation, including its later release.
        point = arrow()
        host.emit(operation("pointerdown", point))
        count = len(actions)
        tick("held down")
        assert len(actions) == count + 1
        for _ in range(30):
            host.emit()
            tick("held idle")
        host.emit(operation("pointerup", point))
        tick("held up")
        assert len(actions) == count + 1

        # Down at the arrow, then move/up over the calendar before Python samples it.
        point, calendar_point = arrow(), center(app.office_calendar_rect())
        count = len(actions)
        host.emit(
            operation("pointerdown", point),
            operation("pointermove", calendar_point),
            operation("pointerup", calendar_point),
        )
        tick("arrow drift across calendar")
        assert len(actions) == count + 1
        idle()

        count = len(actions)
        host.emit(operation("pointerdown", point), operation("pointercancel", calendar_point))
        tick("cancelled arrow")
        idle()
        assert len(actions) == count

        # An unseen release/new-down pair uses the new question press once.
        host.emit(operation("pointerdown", point))
        tick("old arrow down")
        count = len(actions)
        host.emit(operation("pointerup", point), operation("pointerdown", identity_point))
        tick("release and question re-press")
        assert actions[count:] == [(host.sequence, "ask_or_select_office_question:identity")]
        host.emit(operation("pointerup", identity_point))
        tick("question release")
        idle()

        office, week = app.office, app.work_week
        page = app.office_dialogue_playback.page_index
        tap(calendar_point, "legitimate calendar", allow_menu=True)
        assert app.week_debug_menu_open
        tap(center(app.week_debug_rects()["month7"]), "choose month", allow_menu=True)
        assert app.week_debug_month == 7
        tap(center(app.week_debug_rects()["cancel"]), "close calendar")
        assert app.office is office and app.work_week == week
        assert app.office_dialogue_playback.page_index == page
        assert session.asked_question_ids == {"identity"}
        assert not app.normal_progress_store.enabled
        assert len(trace) > 100
        counts = {}
        for sequence, _ in actions:
            counts[sequence] = counts.get(sequence, 0) + 1
        assert all(value == 1 for value in counts.values()), counts
        print(json.dumps({"geometry": geometry, "frames": len(trace), "activations": len(actions)}))
    finally:
        host.close()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node required for actual host JS")
@pytest.mark.parametrize(
    "geometry",
    [
        (1280, 720, 0, 0, 1280, 720),
        (844, 390, 17, 11, 844, 390),
        (1170, 2532, 8, 28, 390, 844),
    ],
)
def test_mina_identity_full_root_flow_owns_each_host_press_once(geometry):
    # Pyxel is process-global and cannot be initialized twice; isolate native
    # initialization from the test suite and from the other geometry cases.
    tests = Path(__file__).parent
    root = tests.parent
    script = (
        "import sys, pytest; "
        f"sys.path[:0] = {[str(tests), str(root / 'src'), str(root)]!r}; "
        "from test_screen_flow_mina_bridge import run_mina_flow; "
        "monkeypatch = pytest.MonkeyPatch(); "
        f"run_mina_flow(monkeypatch, {geometry!r})"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout.splitlines()[-1])
    assert summary["frames"] > 100
    assert summary["activations"] > 30
