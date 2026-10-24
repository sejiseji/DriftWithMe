"""Headless actual-app rendering of Wave 1, using isolated in-memory seed saves.

This checks the office/transition foundation, NOT unimplemented field encounters.
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tests"))
    import pyxel

    from drift_with_me.app import AppScreen, DriftWithMeApp
    from drift_with_me.save_state import ProgressStore, decode, encode, snapshot
    from test_august_wave1 import finished_july
    from test_save_state import Storage

    seed, _ = finished_july()
    payload = snapshot(seed)
    run = pyxel.run
    pyxel.run = lambda *_: None
    app = DriftWithMeApp(headless=True)
    pyxel.run = run
    assert not app.progress_store.enabled
    app.progress_store = ProgressStore(browser_storage=Storage())
    assert app.progress_store.write(payload)
    app.saved_progress = decode(encode(payload))
    app.start_game()
    app.consume_elapsed = lambda: 1 / 60
    app.pyxel.btn = lambda *_: False
    app.pyxel.btnp = lambda *_: False
    out.mkdir(parents=True, exist_ok=True)
    frame = 0
    saved = set()
    roundtrips = []
    stage = "bridge"

    def capture(name):
        if name not in saved:
            if app.screen == AppScreen.OFFICE:
                app.sync_office_dialogue_playback().revealed_chars = 10000
            app.draw()
            pyxel.screen.save(str(out / (name + ".png")), 2)
            saved.add(name)

    def update():
        nonlocal frame, stage
        frame += 1
        app.update()
        if stage == "bridge":
            if app.week_transition and app.week_transition.showing_title:
                capture("august-week-title")
            if app.work_week.month == 8 and not app.week_transition:
                app.week_input_wait_for_release = False
                app.office.begin_current_case()
                stage = "counter"
        elif stage == "counter":
            capture("august-counter")
            if frame % 24 == 0:
                o = app.office
                if o.has_pending_dialogue_step():
                    o.advance_dialogue_step()
                elif o.current_session.pending_question_id:
                    o.complete_pending_question()
                elif not o.current_session.asked_question_ids:
                    o.ask_question("check")
                elif o.current_session.state.name in {"HEARING", "READY_TO_CLASSIFY"}:
                    o.classify(o.current_case.expected_classification)
                else:
                    if o.prepare_field_task():
                        app.enter_exploration_from_office()
                        stage = "departure"
        elif stage in {"departure", "return"}:
            t = app.field_transition
            if t and t.phase == "dialogue" and frame % 30 == 0:
                t.wait_release = False
                t.advance()
            if t is None:
                stage = "field" if stage == "departure" else "office"
        elif stage == "field":
            capture("august-field-no-auto-completion")
            assert not app.office.august_progress.ready
            roundtrips.append(
                decode(encode(snapshot(app)))[1][app.work_week].august_progress.snapshot()
            )
            if frame % 30 == 0:
                assert app.complete_office_field_task()
                stage = "return"
        elif stage == "office":
            capture("august-unfinished-return")
            assert not app.office.complete
            app.saved_progress = decode(encode(snapshot(app)))
            app.start_game()
            assert app.office.august_progress.phase == "office"
            capture("august-unfinished-resumed")
            # Explicitly seeded completion is only a fixture to inspect report/done UI.
            o = app.office
            o.august_progress.sites = ["northwest", "northeast", "southeast"]
            o.august_progress.phase = "report"
            app.saved_progress = decode(encode(snapshot(app)))
            app.start_game()
            assert app.office.august_progress.phase == "report"
            stage = "report-fixture"
        elif stage == "report-fixture":
            capture("august-report-fixture")
            if frame % 45 == 0:
                app.advance_august_report()
                if app.office.august_progress.phase == "done":
                    stage = "done"
        elif stage == "done":
            capture("august-done-fixture")
            pyxel.screencast(str(out / "foundation.gif"), scale=2)
            (out / "result.json").write_text(
                json.dumps(
                    {
                        "actual_app": True,
                        "user_storage_enabled": False,
                        "storage": "synthetic in-memory Storage",
                        "field_auto_completion": False,
                        "roundtrips": roundtrips,
                        "report_completion": "explicit fixture; field producers absent",
                        "week": str(app.work_week),
                        "captures": sorted(saved),
                    },
                    indent=2,
                )
            )
            pyxel.quit()
        if frame > 1800:
            raise RuntimeError("Wave1 capture timed out: " + stage)

    def draw():
        app.draw()

    run(update, draw)


if __name__ == "__main__":
    main()
