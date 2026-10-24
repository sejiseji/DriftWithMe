"""Actual August events from a synthetic completed-July save, no achievement fixtures."""

import argparse
import json
import math
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retreat-supply", action="store_true")
    parser.add_argument("--stop-after-week1", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tests"))
    import pyxel

    from drift_with_me.app import AppScreen, DriftWithMeApp
    from drift_with_me.config import load_data_json
    from drift_with_me.save_state import ProgressStore, decode, encode, snapshot
    from drift_with_me.week_cycle import WorkWeek
    from test_august_wave1 import finished_july
    from test_save_state import Storage

    seed, _ = finished_july()
    payload = snapshot(seed)
    run = pyxel.run
    pyxel.run = lambda *_: None
    app = DriftWithMeApp(headless=True)
    pyxel.run = run
    app.progress_store = ProgressStore(browser_storage=Storage())
    assert app.progress_store.write(payload)
    app.saved_progress = decode(encode(payload))
    app.start_game()
    app.consume_elapsed = lambda: 1 / 60
    controls = set()
    held = set()
    pyxel.btnp = lambda key, *_: key in controls
    pyxel.btn = lambda key: key in held
    frame = 0
    saved = set()
    events = []
    partial = set()
    resumed = set()
    goal = None
    normal_sent = set()
    group_sent = set()
    group_number = 0
    last_battle = None
    retreat_done = False
    preset = False
    refills = []
    crosses = []
    last_cross = None
    pending_reloaded = False
    sites = load_data_json("swarm_config.json")["sites"]
    order = ["southeast", "northwest", "northeast"]
    original = app.process_events

    def process(items):
        nonlocal group_number, last_battle, retreat_done
        for e in items:
            if e.kind.startswith("swarm_") or e.kind == "resource_refilled":
                events.append(
                    {
                        "kind": e.kind,
                        "week": str(app.work_week),
                        "target": e.target_id,
                        "payload": e.payload,
                    }
                )
            if e.kind == "swarm_started":
                group_number += 1
            if e.kind == "swarm_restored" and not e.payload.get("won"):
                retreat_done = True
            if e.kind == "resource_refilled":
                refills.append(e.payload["resource"])
        original(items)

    app.process_events = process

    def request(x, z):
        nonlocal goal
        key = (round(x, 1), round(z, 1))
        if (
            goal != key
            or app.model.auto_move_goal is None
            and math.hypot(app.model.player.x - x, app.model.player.z - z) > 12
        ):
            es = []
            app.model.request_auto_move_goal(x, z, es)
            app.process_events(es)
            goal = key

    def update():
        nonlocal frame, goal, preset, last_cross, pending_reloaded
        frame += 1
        controls.clear()
        held.clear()
        if frame % 600 == 0:
            (out / "latest-checkpoint.json").write_text(encode(snapshot(app)))
            print(
                frame,
                app.work_week,
                app.screen,
                getattr(getattr(app.office, "august_progress", None), "phase", None),
                (round(app.model.player.x), round(app.model.player.z)),
                "goal",
                app.model.auto_move_goal,
                "paused",
                app.model.world_paused,
                "lock",
                getattr(app, "swarm_wait_release", None),
                getattr(app, "swarm_return_fade", None),
                flush=True,
            )
        if frame > 24000:
            raise RuntimeError("bounded capture timeout")
        if app.week_transition:
            app.update()
            return
        if app.field_transition:
            t = app.field_transition
            if t.phase == "dialogue":
                t.wait_release = False
                controls.add(pyxel.KEY_RETURN)
            app.update()
            return
        if not app.august_active():
            app.update()
            return
        p = app.office.august_progress
        n = app.work_week.number
        if app.screen == AppScreen.OFFICE:
            if p.phase == "counter" and frame % 5 == 0:
                o = app.office
                o.begin_current_case()
                if o.has_pending_dialogue_step():
                    o.advance_dialogue_step()
                elif o.current_session.pending_question_id:
                    o.complete_pending_question()
                elif not o.current_session.asked_question_ids:
                    o.ask_question("check")
                elif o.current_session.state.name in {"HEARING", "READY_TO_CLASSIFY"}:
                    o.classify(o.current_case.expected_classification)
                elif o.prepare_field_task():
                    app.enter_exploration_from_office()
                    goal = None
            elif p.phase == "office":
                if n not in resumed:
                    app.saved_progress = app.progress_store.load()
                    app.start_game()
                    resumed.add(n)
                    assert app.office.august_progress.phase == "office"
                app.enter_exploration_from_office()
                goal = None
            elif p.phase == "report" and frame % 30 == 0:
                app.advance_august_report()
            elif p.phase == "done":
                if n == 3 or args.stop_after_week1 and n == 1:
                    if n == 3:
                        assert not app.can_begin_next_week()
                    restored = app.progress_store.load()
                    assert (
                        restored[0] == WorkWeek(8, n)
                        and restored[1][restored[0]].august_progress.phase == "done"
                    )
                    (out / "result.json").write_text(
                        json.dumps(
                            {
                                "actual_app": True,
                                "achievement_fixtures": False,
                                "synthetic_previous_week_save": True,
                                "events": events,
                                "refills": refills,
                                "crossings": crosses,
                                "partial_returns": sorted(partial),
                                "resumed": sorted(resumed),
                                "week3_done_saved": n == 3,
                                "completed_week": n,
                                "pending_sighting_resumed": pending_reloaded,
                                "synthetic_resource_preset": args.retreat_supply,
                                "resources": [app.model.water, app.model.energy],
                            },
                            indent=2,
                        )
                    )
                    if n == 3:
                        # Inspect the completion view from its persisted checkpoint too.
                        app.saved_progress = restored
                        app.start_game()
                        assert not app.can_begin_next_week()
                        from drift_with_me.august_scenery import environment

                        assert environment(app) == (False, True)
                        for i in range(5):
                            app.presentation_time = i * 6.0
                            app.draw()
                            pyxel.screen.save(str(out / f"recovered-route-{i}.png"), 2)
                        (out / "completed-checkpoint.json").write_text(encode(snapshot(app)))
                    pyxel.screencast(str(out / "sequence.gif"), scale=2)
                    pyxel.quit()
                    return
                controls.add(pyxel.KEY_RETURN)
            app.update()
            return
        if p.phase != "field":
            app.update()
            return
        if args.retreat_supply and n == 2 and not preset:
            app.model.water, app.model.energy = 12, 0
            preset = True
        if n == 1 and p.pending_sighting:
            if getattr(app, "august_crossing", None):
                token = (n, p.pending_sighting)
                if token != last_cross:
                    crosses.append(token)
                    last_cross = token
                if app.august_crossing[1] > 0.65 and not pending_reloaded:
                    app.saved_progress = app.progress_store.load()
                    app.start_game()
                    assert app.august_crossing is None
                    assert app.office.august_progress.pending_sighting == token[1]
                    pending_reloaded = True
            else:
                last_cross = None
                if frame % 12 == 0:
                    controls.add(pyxel.KEY_RETURN)
            app.update()
            return
        b = getattr(getattr(app.model, "swarm_field", None), "battle", None)
        if b:
            if b.phase == "approach":
                target = 0.2 if args.retreat_supply and not retreat_done else b.settings.target
                token = (group_number, b.failures)
                if b.progress >= target and token not in group_sent:
                    held.add(pyxel.KEY_SPACE)
                    controls.add(pyxel.KEY_SPACE)
                    group_sent.add(token)
            app.update()
            return
        session = app.model.combat_session
        if session:
            if session.phase == "PARRY_TIMING":
                slider = app.model.combat_timing_slider_position(session)
                for i, marker in enumerate(session.marker_positions):
                    token = (
                        id(session),
                        session.successful_defense_count,
                        session.failed_round_count,
                        i,
                    )
                    if slider >= marker and token not in normal_sent:
                        held.add(pyxel.KEY_SPACE)
                        normal_sent.add(token)
                        break
            elif session.phase in {"PERFECT_BUBBLE_WINDOW", "PERFECT_ZAP_WINDOW"}:
                controls.add(pyxel.KEY_X)
            app.update()
            return
        if getattr(app, "first_sight_conversation", None):
            controls.add(pyxel.KEY_RETURN)
            app.update()
            return
        if app.model.interaction:
            app.update()
            return
        if len(p.sites) == 1 and n in (1, 2) and n not in partial:
            if app.complete_office_field_task():
                partial.add(n)
                goal = None
            app.update()
            return
        if p.ready:
            app.complete_office_field_task()
            goal = None
            app.update()
            return
        # Real replenishment via the existing station interaction, never assigning resources.
        if (app.model.water < 32 or app.model.energy < 25) and not (
            args.retreat_supply and n == 2 and not retreat_done
        ):
            kind = "water_station" if app.model.water < 32 else "solar_station"
            station = min(
                (
                    o
                    for o in app.world.objects
                    if o.kind == kind and (kind != "water_station" or o.supply == "working")
                ),
                key=lambda o: math.hypot(o.x - app.model.player.x, o.z - app.model.player.z),
            )
            request(station.x + (-18 if kind == "water_station" else 18), station.z + 18)
            candidate = app.model.interaction_candidate(app.camera())
            if candidate and candidate.id == station.id:
                controls.add(pyxel.KEY_E)
        else:
            site = next(s for s in order if s not in p.sites)
            request(*sites[site])
        app.update()
        if frame > 24000:
            raise RuntimeError("August capture timed out")

    def draw():
        app.draw()
        if not app.august_active():
            return
        p = app.office.august_progress
        label = f"w{app.work_week.number}-{app.screen.name.lower()}-{p.phase}"
        crossing = getattr(app, "august_crossing", None)
        if crossing:
            directory = out / ("juvenile-" + crossing[0] + "-frames")
            directory.mkdir(exist_ok=True)
            pyxel.screen.save(str(directory / f"{frame:06d}.png"), 2)
        if crossing and 0.35 < crossing[1] < 0.6:
            label = f"juveniles-{crossing[0]}"
        b = getattr(getattr(app.model, "swarm_field", None), "battle", None)
        if b:
            label = f"w{app.work_week.number}-{app.model.swarm_field.site_id}-{b.phase}"
            if b.phase == "victory" and b.elapsed > 0.5:
                clip = out / f"w{app.work_week.number}-{app.model.swarm_field.site_id}-attack.gif"
                if not clip.exists():
                    pyxel.screencast(str(clip), scale=2)
        if (
            b and b.elapsed > 0.2 or crossing and 0.35 < crossing[1] < 0.6 or not b and not crossing
        ) and label not in saved:
            pyxel.screen.save(str(out / (label + ".png")), 2)
            saved.add(label)

    run(update, draw)


if __name__ == "__main__":
    main()
