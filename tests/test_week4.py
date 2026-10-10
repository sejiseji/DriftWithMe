"""Independent W4 lifecycle checks: plants are carried before acknowledged delivery."""

from copy import deepcopy
from itertools import combinations, permutations
from math import hypot

import pytest

from drift_with_me.app import AppScreen, OfficeDialogueLine
from drift_with_me.east_site import EastSiteProgress
from drift_with_me.events import GameEvent
from drift_with_me.office import CaseState
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week4 import FLOWER_IDS, FUJI_ID, Week4Progress, install_week4_world
from drift_with_me.week_cycle import WorkWeek, load_week_office
from field_transition_helpers import finish_travel
from test_field_visit import inspect, make_visit
from test_week2_loop import resolve


def app4():
    app = make_visit()
    app.office = load_week_office(WorkWeek(6, 4))
    app.work_week = app.map_work_week = WorkWeek(6, 4)
    app.week_office_history = {app.work_week: app.office}
    app.east_site_progress = EastSiteProgress()
    app.first_sight_seen = set()
    install_week4_world(app)
    for _ in range(2):
        resolve(app.office)
        assert app.office.active_field_task is None
        assert app.office.advance_case()
    resolve(app.office)
    assert app.office.prepare_field_task()
    app.enter_exploration_from_office()
    finish_travel(app)
    return app


def read(app, target):
    inspect(app, target)
    assert app.field_conversation is not None
    for _ in range(30):
        if app.field_conversation is None:
            return
        assert app.advance_field_conversation()
    pytest.fail("field dialogue did not finish")


def roundtrip(app):
    week, offices, sites, *_ = decode(encode(snapshot(app)))
    assert week == WorkWeek(6, 4)
    app.office = offices[week]
    app.week_office_history = offices
    app.east_site_progress = sites
    return app.office.plant_progress


def test_fuji_plan_uses_document_reading_pose_only_on_tagged_page():
    app = app4()
    app.office = load_week_office(WorkWeek(6, 4))
    for _ in range(2):
        resolve(app.office)
        app.office.advance_case()
    question = app.office.current_case.questions[0]
    page = (
        OfficeDialogueLine(
            question.jack_text,
            False,
            speaker=question.jack_speaker,
            visual_action=question.visual_action,
        ),
    )
    assert app.office_document_reading_active(page)
    assert not app.office_document_reading_active(
        (OfficeDialogueLine("サガン、フジさんがいらしてる", False, speaker="ジャック"),)
    )


@pytest.mark.parametrize("order", list(permutations(sorted(FLOWER_IDS))))
def test_all_collection_orders_require_delivery(order):
    app = app4()
    read(app, FUJI_ID)
    assert app.office.plant_progress.instructed
    for target in order:
        read(app, target)
        progress = roundtrip(app)
        assert target in progress.carried and target not in progress.delivered
        assert not progress.complete
    assert progress.carried == FLOWER_IDS and not progress.delivered
    read(app, FUJI_ID)
    progress = roundtrip(app)
    assert not progress.carried and progress.delivered == FLOWER_IDS and progress.complete
    assert app.complete_office_field_task()
    finish_travel(app)
    assert (
        app.office.current_session is None
        or app.office.current_session.state != CaseState.FIELD_ACTIVE
    )


@pytest.mark.parametrize("target", sorted(FLOWER_IDS))
def test_collection_cancel_resume_and_duplicate_event_are_safe(target):
    app = app4()
    read(app, FUJI_ID)
    inspect(app, target)
    app.process_events(app.model.cancel_interaction())
    progress = roundtrip(app)
    assert not progress.collected
    read(app, target)
    before = deepcopy(app.office.plant_progress.collected)
    read(app, target)
    assert app.office.plant_progress.collected == before
    app.process_events(
        [GameEvent(900, 0, "inspection_completed", "player", "jun_w4_east", (0, 0, 0))]
    )
    assert app.office.plant_progress.collected == before


def test_partial_handoff_cancel_and_repeat_do_not_double_submit():
    app = app4()
    read(app, FUJI_ID)
    first, second = sorted(FLOWER_IDS)[:2]
    read(app, first)
    inspect(app, FUJI_ID)
    app.process_events(app.model.cancel_interaction())
    p = roundtrip(app)
    assert p.carried == {first} and not p.delivered
    read(app, FUJI_ID)
    p = roundtrip(app)
    assert p.delivered == {first} and not p.carried and not p.complete
    read(app, FUJI_ID)
    assert app.office.plant_progress.delivered == {first}
    read(app, first)
    assert not app.office.plant_progress.carried
    read(app, second)
    read(app, FUJI_ID)
    assert app.office.plant_progress.delivered == {first, second}


@pytest.mark.parametrize("count", range(6))
def test_return_with_carried_plants_is_unfinished_and_redeployable(count):
    app = app4()
    read(app, FUJI_ID)
    for target in sorted(FLOWER_IDS)[:count]:
        read(app, target)
    before = deepcopy(app.office.plant_progress.collected)
    assert app.complete_office_field_task()
    assert not app.complete_office_field_task()
    finish_travel(app)
    assert app.screen == AppScreen.OFFICE and not app.office.complete
    assert app.office.current_session.state == CaseState.FIELD_ACTIVE
    assert not app.office.advance_case()
    roundtrip(app)
    app.activate_office_footer_action()
    finish_travel(app)
    assert app.office.plant_progress.collected == before


def test_direct_progress_completion_requires_pending_token():
    p = Week4Progress()
    for target in FLOWER_IDS | {FUJI_ID}:
        assert not p.complete_target(target)
    assert not p.collected and not p.instructed
    p.pending_completion = FUJI_ID
    p.complete_target(FUJI_ID)
    assert p.instructed
    target = sorted(FLOWER_IDS)[0]
    p.pending_completion = target
    p.complete_target(target)
    assert p.carried == {target}
    assert not p.complete_target(target)
    assert not p.complete


@pytest.mark.parametrize("size", range(6))
def test_progress_subset_roundtrip(size):
    app = app4()
    read(app, FUJI_ID)
    for group in combinations(sorted(FLOWER_IDS), size):
        p = app.office.plant_progress
        p.carried = set(group)
        p.delivered = set()
        restored = roundtrip(app)
        assert restored.carried == set(group) and not restored.delivered


def test_fourth_week_stops_before_unauthored_july():
    assert load_week_office(WorkWeek(7, 1)) is None
    app = app4()
    assert not app.begin_next_week()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda flowers: flowers.update(carried=["unknown"]),
        lambda flowers: flowers.update(delivered=["unknown"]),
        lambda flowers: flowers.update(instructed=1),
        lambda flowers: flowers.update(carried=["jun_w4_north"], delivered=["jun_w4_north"]),
        lambda flowers: flowers.update(instructed=False, delivered=["jun_w4_north"]),
        lambda flowers: flowers.update(positions={"unknown": 0}),
        lambda flowers: flowers.update(positions={"jun_w4_north": True}),
        lambda flowers: flowers.update(positions={"jun_w4_north": -1}),
        lambda flowers: flowers.update(positions={"jun_w4_north": 999}),
    ],
)
def test_malformed_flower_save_rejected(mutation):
    app = app4()
    read(app, FUJI_ID)
    payload = snapshot(app)
    mutation(payload["offices"]["6:4"]["flowers"])
    with pytest.raises(ValueError):
        decode(encode(payload))


def test_week3_to_four_transition_applies_once_and_stops_at_july():
    from drift_with_me.world import load_world_data
    from test_week_cycle import completed_app

    app = completed_app()
    app.world = load_world_data()
    app.model = type("ModelStub", (), {"world": app.world})()
    app.office = load_week_office(WorkWeek(6, 3))
    for session in app.office.sessions.values():
        session.state = CaseState.RESOLVED
    app.office.current_index = len(app.office.cases)
    app.work_week = app.map_work_week = WorkWeek(6, 3)
    previous = app.office
    app.week_office_history = {app.work_week: previous}
    assert app.begin_next_week()
    assert not app.begin_next_week()
    app.update_week_transition(0.6)
    assert app.work_week == app.map_work_week == WorkWeek(6, 4)
    current = app.office
    app.update_week_transition(10)
    assert app.office is current and app.week_office_history[WorkWeek(6, 3)] is previous
    assert sum(o.id == FUJI_ID for o in app.world.objects) == 1
    for session in app.office.sessions.values():
        session.state = CaseState.RESOLVED
    app.office.current_index = len(app.office.cases)
    assert not app.begin_next_week()


@pytest.mark.parametrize("case_index", range(3))
def test_counter_partial_dialogue_roundtrip_preserves_case(case_index):
    app = app4()
    app.office = load_week_office(WorkWeek(6, 4))
    for _ in range(case_index):
        resolve(app.office)
        app.office.advance_case()
    expected = app.office.current_case.case_id
    if app.office.has_pending_dialogue_step():
        app.office.advance_dialogue_step()
    roundtrip(app)
    assert app.office.current_case.case_id == expected
    assert app.office.current_index == case_index and not app.office.complete
    resolve(app.office)


def test_all_week4_targets_have_collision_free_paths_from_player():
    from collections import deque

    from drift_with_me.week4 import WORLD_POSITIONS

    app = app4()
    world = app.world
    hx, hz = app.model.player_solid_half_x, app.model.player_solid_half_z
    step = 8
    start = (round(app.model.player.x / step) * step, round(app.model.player.z / step) * step)
    queue = deque([start])
    seen = {start}
    reached = set()
    while queue and len(reached) < len(WORLD_POSITIONS):
        x, z = queue.popleft()
        for target, (tx, tz) in WORLD_POSITIONS.items():
            if (tx - x) ** 2 + (tz - z) ** 2 <= 24**2:
                reached.add(target)
        for dx, dz in ((step, 0), (-step, 0), (0, step), (0, -step)):
            nxt = (x + dx, z + dz)
            if nxt in seen or world.collides_player(*nxt, hx, hz):
                continue
            seen.add(nxt)
            queue.append(nxt)
    assert reached == set(WORLD_POSITIONS)


def test_week4_targets_have_room_to_inspect_outside_existing_enemy_zones():
    from drift_with_me.week4 import WORLD_POSITIONS

    app = app4()
    danger = float(app.model.config["interaction"]["danger_block_radius"])
    for target, (x, z) in WORLD_POSITIONS.items():
        for enemy in app.model.enemies:
            aggro = float(app.model.config["enemy"][enemy.kind]["aggro_radius"])
            assert hypot(x - enemy.home_x, z - enemy.home_z) > max(danger, aggro) + 24, (
                target,
                enemy.id,
            )


@pytest.mark.parametrize("target", [FUJI_ID, *sorted(FLOWER_IDS)])
def test_unread_field_cursor_survives_save_and_cancel(target):
    app = app4()
    if target != FUJI_ID:
        read(app, FUJI_ID)
    inspect(app, target)
    app.advance_field_conversation()
    assert app.field_conversation.index == 1
    app.process_events(app.model.cancel_interaction())
    p = roundtrip(app)
    assert p.positions[target] == 1 and not p.collected
    if target == FUJI_ID:
        assert not p.instructed
    inspect(app, target)
    assert app.field_conversation.index == 1
    while app.field_conversation:
        app.advance_field_conversation()
    p = roundtrip(app)
    assert target not in p.positions
    assert p.instructed if target == FUJI_ID else target in p.carried


def test_final_handoff_is_not_committed_until_last_acknowledgement():
    app = app4()
    read(app, FUJI_ID)
    for target in FLOWER_IDS:
        read(app, target)
    inspect(app, FUJI_ID)
    while app.field_conversation.index < len(app.field_conversation.lines) - 1:
        app.advance_field_conversation()
        assert not app.office.plant_progress.complete
    app.process_events(app.model.cancel_interaction())
    p = roundtrip(app)
    assert p.carried == FLOWER_IDS and not p.delivered
    inspect(app, FUJI_ID)
    assert app.field_conversation.index == len(app.field_conversation.lines) - 1
    app.advance_field_conversation()
    assert app.office.plant_progress.complete
