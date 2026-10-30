"""Headless action-handler driver. No debug jumps or completion-state assignments.
Navigation/contact selection is invoked directly; it is NOT a real UI/playthrough QA.
"""

from copy import deepcopy

from drift_with_me.app import AppScreen
from drift_with_me.camera import CameraController
from drift_with_me.effects import EffectSystem
from drift_with_me.flowerbed import FlowerbedLayoutStore
from drift_with_me.math3d import Vec3
from drift_with_me.save_state import ProgressStore, snapshot
from drift_with_me.week_cycle import WorkWeek
from field_transition_helpers import finish_travel
from test_field_visit import drain, inspect, make_visit
from test_office import make_office_dialogue_app
from test_save_state import Storage


def new_game():
    app = (
        make_visit()
    )  # Hardware-only scaffold, then the public New Game path resets all domain state.
    app.camera_controller = CameraController(
        app.runtime.raw, app.world, 512, 236, Vec3(app.model.player.x, 0, app.model.player.z)
    )
    app.effects = EffectSystem(app.runtime.raw)
    storage = Storage()
    garden = Storage()
    app.progress_store = ProgressStore(browser_storage=storage)
    app.flowerbed_layout_store = FlowerbedLayoutStore(ProgressStore(browser_storage=garden))
    app.initialize_week_debug(False)
    app.ui_text = make_office_dialogue_app().ui_text
    app.saved_progress = None
    app.week_input_wait_for_release = False
    app.presentation_time = 0
    app.frame = 0
    app.start_game(new_game=True)
    app.key_pressed = lambda *_: False
    app.mouse_pressed_in = lambda *_: False
    assert app.work_week == WorkWeek() and app.office.current_index == 0
    assert not app.east_site_progress.facts and not app.east_site_progress.collectibles
    assert not app.office.complete and not app.can_begin_next_week()
    return app, storage, garden


def close_case(app):
    office = app.office
    drain(office)
    for question in office.current_case.questions:
        if question.question_id not in office.current_session.asked_question_ids:
            assert office.ask_question(question.question_id)
            drain(office)
    if office.current_session.state.name in {"HEARING", "READY_TO_CLASSIFY"}:
        assert office.classify(office.current_case.expected_classification), (
            app.work_week,
            office.current_case.case_id,
            office.current_session.feedback,
        )
        drain(office)


def read(app, target):
    inspect(app, target)
    assert app.field_conversation is not None, (app.work_week, target)
    for _ in range(50):
        if app.field_conversation is None:
            return
        assert app.advance_field_conversation()
    raise AssertionError("dialogue did not finish")


def dispatch(app):
    assert app.office.prepare_field_task() is not None
    app.enter_exploration_from_office()
    finish_travel(app)
    app.key_pressed = lambda *_: False
    assert app.screen == AppScreen.PLAY


def june(app):
    n = app.work_week.number
    while app.office.current_case:
        close_case(app)
        if app.office.current_session.state.name == "FIELD_CHECK_REQUIRED":
            break
        assert app.office.advance_case(), (
            app.work_week,
            app.office.current_case.case_id,
            app.office.current_session.state,
        )
    dispatch(app)
    collect_map(app)
    if n == 1:
        for target in ("tap_stopped", "maintenance_unit", "observation_post"):
            read(app, target)
    elif n == 2:
        from drift_with_me.east_site import SITE_FACTS

        for target in SITE_FACTS:
            read(app, target)
    elif n == 3:
        from drift_with_me.week3 import KEY_ID, SITE_FACTS

        for target in (*SITE_FACTS, KEY_ID):
            read(app, target)
    else:
        from drift_with_me.week4 import FLOWER_IDS, FUJI_ID

        read(app, FUJI_ID)
        for target in sorted(FLOWER_IDS):
            read(app, target)
        read(app, FUJI_ID)
    assert app.complete_office_field_task()
    finish_travel(app)
    while app.office.current_case:
        close_case(app)
        assert app.office.advance_case(), (
            app.work_week,
            app.office.current_case.case_id,
            app.office.current_session.state,
        )
    assert app.office.complete


def next_week(app):
    old = app.work_week
    before = snapshot(app)
    resources = app.model.water, app.model.energy
    retained = deepcopy(
        (
            app.east_site_progress.facts,
            app.east_site_progress.collectibles,
            app.east_site_progress.flowerbed_order,
            app.east_site_progress.flowerbed_visit,
        )
    )
    # The previous travel/editor tap must be released before a new Next tap.
    app.pointer_snapshot.down = False
    app.key_pressed = lambda *_: False
    app.mouse_pressed_in = lambda *_: False
    for _ in range(3):
        app.update_field_transition(0)
        app.update_flowerbed_modal()
    assert app.begin_next_week(), (old, "blocked")
    for _ in range(3):
        assert not app.begin_next_week()
    app.consume_elapsed = lambda: 0.1
    app.read_pointer_snapshot = lambda: app.pointer_snapshot
    app.key_pressed = lambda *_: False
    app.mouse_pressed_in = lambda *_: False
    app.pointer_snapshot.down = True
    for _ in range(80):
        app.update()
        if app.week_transition is None:
            break
    assert app.week_transition is None and app.week_input_wait_for_release
    for _ in range(3):
        app.update()
        assert app.week_input_wait_for_release and not app.begin_next_week()
    app.pointer_snapshot.down = False
    for _ in range(3):
        app.update()
        if not app.week_input_wait_for_release:
            break
    assert not app.week_input_wait_for_release
    assert app.work_week == old.following()
    assert (app.model.water, app.model.energy) == resources
    assert (
        app.east_site_progress.facts,
        app.east_site_progress.collectibles,
        app.east_site_progress.flowerbed_order,
        app.east_site_progress.flowerbed_visit,
    ) == retained
    assert not app.office.current_session.asked_question_ids
    return before


def collect_map(app):
    from drift_with_me.collectibles import CATALOG

    for item in CATALOG:
        if item.week == (app.work_week.month, app.work_week.number) and item.position:
            read(app, "collectible_" + item.id)


def fight(app, enemy):
    from drift_with_me.model import InputIntent

    events = []
    app.model.start_contact_combat(enemy, events)
    app.process_events(events)
    assert app.model.combat_session is not None
    for _ in range(10000):
        session = app.model.combat_session
        if session is None:
            break
        press = False
        if session.phase == "PARRY_TIMING":
            slider = app.model.combat_timing_slider_position(session)
            radius = app.model.combat_parry_hit_radius_normalized(session)
            press = any(
                j is None and abs(slider - marker) < radius * 0.5
                for marker, j in zip(
                    session.marker_positions, session.marker_judgements, strict=True
                )
            )
        intent = InputIntent(
            barrier=press,
            action_pressed=session.phase
            in {"PERFECT_BUBBLE_WINDOW", "PERFECT_ZAP_WINDOW", "FOCUS_LASER"},
        )
        events = []
        app.model.update_combat_session(intent, app.camera(), 0.005, events)
        app.process_events(events)
    assert enemy.state == "DEFEATED", (enemy.id, enemy.state, app.model.combat_session)


def july1(app):
    from drift_with_me.july_week1 import FUJI_ID, WATER_ID

    close_case(app)
    dispatch(app)
    for enemy in tuple(app.model.enemies):
        fight(app, enemy)
    app.update_july_story(0)
    for _ in range(30):
        p = app.office.july_progress
        if p.stage == "patrol" and p.researchers_talked:
            break
        app.travel_input_held = lambda: False
        app.key_pressed = lambda *_: False
        app.update_july_story(0.1)
        app.key_pressed = lambda *keys: "KEY_RETURN" in keys
        app.update_july_story(0.1)
    assert app.office.july_progress.researchers_talked
    app.key_pressed = lambda *_: False
    for target in (FUJI_ID, WATER_ID):
        read(app, target)
    app.update_july_story(0)
    finish_travel(app)
    assert app.office.complete


def july2(app):
    from drift_with_me.flowerbed import FLOWER_IDS
    from drift_with_me.july_week2 import SITES

    for index in range(3):
        close_case(app)
        if index < 2:
            assert app.office.advance_case()
    dispatch(app)
    collect_map(app)
    assert app.start_flowerbed_visit()
    while app.flowerbed_dialogue:
        assert app.advance_flowerbed_visit()
    for flower in FLOWER_IDS:
        assert app.flowerbed_editor.choose(flower)
    assert app.confirm_flowerbed_visit()
    while app.flowerbed_dialogue:
        assert app.advance_flowerbed_visit()
    for target in SITES:
        assert app.begin_week2_observation(target)
        while app.week2_dialogue:
            assert app.advance_week2_dialogue()
    assert app.week2_ready()
    assert app.return_week2()
    finish_travel(app)
    for _ in range(3):
        app.update_week2()
        if app.week2_dialogue:
            break
    while app.week2_dialogue:
        assert app.advance_week2_dialogue()
    assert app.office.complete


def july3(app):
    from drift_with_me.july_week3 import DURATIONS, PARENT, SMALL
    from drift_with_me.ring_linkage import solution_counts

    close_case(app)
    dispatch(app)
    collect_map(app)
    for target in (*SMALL, PARENT):
        assert app.begin_week3_target(target)
        while app.week3_dialogue:
            assert app.advance_week3_dialogue()
        if target == PARENT:
            break
        for duration in DURATIONS:
            app.update_july_week3(duration)
    assert app.open_story_ring()
    puzzle = app.ring_preview
    for index, count in enumerate(solution_counts(puzzle.angles, puzzle.disabled_links)):
        for _ in range(min(count, 12 - count)):
            puzzle.selected = index
            assert puzzle.rotate(1 if count <= 6 else -1)
            puzzle.tick(0.16)
    assert app.ring_preview_store.save_progress(puzzle)
    for seconds in (0.35, 1.4, 3.2):
        puzzle.tick(seconds)
    assert app.close_story_ring()
    for duration in DURATIONS:
        app.update_july_week3(duration)
    assert app.return_week3()
    finish_travel(app)
    app.update_july_week3(0)
    while app.week3_dialogue:
        assert app.advance_week3_dialogue()
    assert app.office.complete


def july4(app):
    from drift_with_me.july_week4 import PARK

    for index in range(3):
        close_case(app)
        if index < 2:
            assert app.advance_week4_case()
    dispatch(app)
    collect_map(app)
    for target in ("fuji", PARK):
        assert app.begin_week4_target(target)
        while app.week4_dialogue:
            assert app.advance_week4_dialogue()
    assert app.return_week4()
    finish_travel(app)
    app.update_july_week4(0)
    while app.week4_dialogue:
        assert app.advance_week4_dialogue()
    assert app.office.complete


def walk_to(app, tx, tz, radius=28):
    # Collision-respecting map navigation; elapsed AI/visual camera are not simulated.
    from collections import deque

    ox, oz = app.model.player.x, app.model.player.z
    hx, hz = app.model.player_solid_half_x, app.model.player_solid_half_z
    q = deque([(0, 0)])
    previous = {(0, 0): None}
    end = None
    while q:
        key = q.popleft()
        x, z = ox + key[0] * 8, oz + key[1] * 8
        if (x - tx) ** 2 + (z - tz) ** 2 <= radius**2:
            end = key
            break
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = key[0] + dx, key[1] + dz
            if nxt not in previous and not app.world.collides_player(
                ox + nxt[0] * 8, oz + nxt[1] * 8, hx, hz
            ):
                previous[nxt] = key
                q.append(nxt)
    assert end is not None, ("unreachable", app.work_week, tx, tz)
    path = []
    while previous[end] is not None:
        path.append(end)
        end = previous[end]
    for key in reversed(path):
        app.model.move_player_by_delta(
            ox + key[0] * 8 - app.model.player.x, oz + key[1] * 8 - app.model.player.z
        )
    assert (app.model.player.x - tx) ** 2 + (app.model.player.z - tz) ** 2 <= radius**2 + 1e-5


def refill(app):
    for kind, target_kind in [
        ("water_refill", "water_station"),
        ("energy_refill", "solar_station"),
    ]:
        target = next(
            o
            for o in app.world.objects
            if o.kind == target_kind and o.supply in {"working", "daylight"}
        )
        events = []
        app.model.start_interaction(events, kind, target, "REFILL", (), 1)
        app.process_events(events)
        events = app.model.complete_interaction()
        app.process_events(events)


def august(app):
    from drift_with_me.august import REPORTS
    from drift_with_me.config import load_data_json
    from drift_with_me.model import InputIntent

    n = app.work_week.number
    close_case(app)
    dispatch(app)
    collect_map(app)
    if n == 1:
        for _site, (x, z) in load_data_json("swarm_config.json")["sites"].items():
            walk_to(app, x, z)
            assert app.update_august_sightings(0.01)
            for _ in range(20):
                app.update_august_sightings(0.1)
            assert app.advance_august_sighting()
            assert app.advance_august_sighting()
        assert app.office.august_progress.ready
    elif n in (2, 3):
        refill(app)
        field = app.ensure_swarm_field()
        for site, (x, z) in field.config["sites"].items():
            walk_to(app, x, z)
            for _ in range(200):
                events = []
                field.step(InputIntent(), app.camera(), 0.02, events)
                app.process_events(events)
                if field.battle:
                    break
            assert field.battle is not None, (n, site, field.cooldown)
            for _ in range(4000):
                b = field.battle
                if b is None:
                    break
                press = b.phase == "finish_wait" or (
                    b.phase == "approach"
                    and abs(b.progress - b.settings.target) < b.settings.radius * 0.5
                )
                events = []
                field.step(InputIntent(action_pressed=press), app.camera(), 0.01, events)
                app.process_events(events)
            assert site in field.cleared, (n, site, field.battle)
            app.sync_august_swarm_sites()
        assert app.office.august_progress.ready
    else:
        assert app.begin_patrol_target("aug_patrol_morris")
        app.travel_input_held = lambda: False
        while app.patrol_dialogue:
            app.key_pressed = lambda *_: False
            app.update_patrol(0)
            app.key_pressed = lambda *keys: "KEY_RETURN" in keys
            app.update_patrol(0)
    app.key_pressed = lambda *_: False
    assert app.return_august()
    finish_travel(app)
    if n == 4:
        app.key_pressed = lambda *keys: "KEY_F" in keys
        assert app.update_patrol(0)
    for _ in REPORTS[n]:
        assert app.advance_august_report()
    assert app.office.complete and app.office.august_progress.phase == "done"


def resume(app):
    before = snapshot(app)
    app.saved_progress = app.progress_store.load()
    assert app.saved_progress is not None
    app.start_game()
    assert snapshot(app) == before, (app.work_week, "resume changed progress")
    app.key_pressed = lambda *_: False
    app.mouse_pressed_in = lambda *_: False


def play_week(app):
    week = app.work_week
    if week.month == 6:
        june(app)
    elif week == WorkWeek(7, 1):
        july1(app)
    elif week == WorkWeek(7, 2):
        july2(app)
    elif week == WorkWeek(7, 3):
        july3(app)
    elif week == WorkWeek(7, 4):
        july4(app)
    else:
        august(app)


def run_all(reload_each_boundary=False):
    from drift_with_me.collectibles import owned_collectibles

    app, storage, garden = new_game()
    records = []
    for index in range(12):
        week = app.work_week
        assert not app.can_begin_next_week()
        play_week(app)
        app.checkpoint_progress()
        loaded = app.progress_store.load()
        assert loaded is not None and loaded[0] == week
        assert len(owned_collectibles(app)) == index + 1, (week, owned_collectibles(app))
        if reload_each_boundary:
            resume(app)
        records.append(
            dict(
                week=week.label,
                complete=app.office.complete,
                collectibles=len(owned_collectibles(app)),
                history=len(app.week_office_history),
            )
        )
        print(records[-1], flush=True)
        if index < 11:
            next_week(app)
            assert app.progress_store.load()[0] == app.work_week
            if reload_each_boundary:
                resume(app)
    assert not app.can_begin_next_week()
    assert app.begin_ending()
    # The new ending dialogue is reading-gated, followed by all three native cuts.
    from drift_with_me.ending_prelude import AUTOMATIC_SECONDS, LINES

    for _ in LINES:
        app.ending_playback.prelude.next_line()
    app.update_ending(AUTOMATIC_SECONDS)
    app.update_ending(111.4)
    assert app.screen == AppScreen.COLLECTION_ROOM
    return app, storage, garden, records


if __name__ == "__main__":
    run_all(reload_each_boundary=True)
