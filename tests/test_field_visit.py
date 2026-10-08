from __future__ import annotations

from types import SimpleNamespace

import pytest

from drift_with_me.app import AppScreen, DriftWithMeApp
from drift_with_me.config import load_runtime_config
from drift_with_me.events import GameEvent
from drift_with_me.field_visit import ANOMALY_ID, FieldProgress, observation_conversation
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.office import CaseState, Classification, OfficePrototype
from drift_with_me.world import load_world_data
from field_transition_helpers import finish_travel


def drain(office):
    while office.has_pending_dialogue_step():
        office.advance_dialogue_step()
    office.complete_pending_question()


def make_visit(asked=("place",)):
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config()
    app.model = GameModel(app.runtime.raw, load_world_data())
    app.world = app.model.world
    app.office = OfficePrototype.load()
    app.office.current_index = 2
    app.office.begin_current_case()
    drain(app.office)
    for question in asked:
        assert app.office.ask_question(question)
        drain(app.office)
    assert app.office.classify(Classification.FIELD_CHECK)
    drain(app.office)
    assert app.office.prepare_field_task()
    app.pointer = SimpleNamespace(cancel=lambda: None)
    app.double_tap_move = SimpleNamespace(cancel=lambda: None)
    camera = CameraState.from_config(app.runtime.raw, Vec3(576, 0, 768), 512, 236)
    app.camera_controller = SimpleNamespace(
        current=camera,
        cancel_focus=lambda: None,
        start_focus_demo=lambda *args, **kwargs: None,
        start_focus_point=lambda *args, **kwargs: None,
    )
    app.effects = SimpleNamespace(process_events=lambda *args, **kwargs: None)
    app.audio = SimpleNamespace(play_events=lambda events: None)
    app.request_hitstop_from_events = lambda events: 0
    app.combat_camera_reactions_allowed = lambda: True
    app.start_combat_camera_restore = lambda: None
    app.show_location_label = lambda: None
    app.field_conversation = None
    app.enter_exploration_from_office()
    finish_travel(app)
    return app


def inspect(app, target_id):
    events = []
    obj = app.model.presentation_object(app.world.object_by_id(target_id))
    app.model.start_interaction(events, "inspect", obj, "CHECKED", (), 0.8)
    app.process_events(events)


@pytest.mark.parametrize("target_id", ("tap_stopped", "maintenance_unit", "observation_post"))
def test_unasked_hearing_is_not_recalled_and_all_points_are_optional(target_id):
    app = make_visit()
    inspect(app, target_id)
    lines = app.field_conversation.lines
    assert len(lines) == 2
    assert not any("ラメル" in text or "夜" in text or "低い音" in text for _, text in lines)
    assert not app.office.current_session.field_progress.observations
    while app.field_conversation:
        app.advance_field_conversation()
    assert app.model.interaction is None
    assert app.screen == AppScreen.PLAY
    assert app.complete_office_field_task()
    finish_travel(app)
    result = app.office.current_session.field_result
    assert result.result_code == "OBSERVED"
    assert len(result.discovered_fact_ids) == 1
    assert "no_facility_damage" not in result.discovered_fact_ids
    assert not any("通常個体" in line or "設備被害なし" in line for line in result.report_lines)
    drain(app.office)
    assert app.office.advance_case()
    assert app.office.current_case.case_id == "OFF-PROT-004"


def test_questions_select_context_and_repeat_is_one_line():
    for target, asked in [
        ("tap_stopped", {"sound"}),
        ("tap_stopped", {"damage"}),
        ("maintenance_unit", {"sound"}),
        ("observation_post", {"frequency"}),
    ]:
        assert len(observation_conversation(target, asked, False)) == 4
        assert len(observation_conversation(target, asked, True)) == 1
    assert len(observation_conversation("observation_post", {"frequency"}, False, False)) == 2


def test_global_inspection_is_separate_and_cancel_resumes_case_conversation():
    app = make_visit(("place", "sound"))
    app.model.inspected_object_ids.add("maintenance_unit")
    inspect(app, "maintenance_unit")
    assert len(app.field_conversation.lines) == 4
    app.advance_field_conversation()
    app.process_events(app.model.cancel_interaction())
    assert app.field_conversation is None
    assert not app.office.current_session.field_progress.can_report
    inspect(app, "maintenance_unit")
    assert app.field_conversation.index == 1
    while app.field_conversation:
        app.advance_field_conversation()
    inspect(app, "maintenance_unit")
    assert len(app.field_conversation.lines) == 1
    app.advance_field_conversation()
    assert len(app.office.current_session.field_progress.observations) == 1


def test_robot_moves_measures_holds_and_resumes_at_visible_target():
    app = make_visit()
    model = app.model
    robot = model.maintenance_robot
    anchor = app.world.object_by_id("maintenance_unit")
    model.player.x, model.player.z = 620, 768
    for _ in range(241):
        model.step(InputIntent(), app.camera(), 1 / 60)
    assert robot.phase == "MEASURE"
    moving_target = model.presentation_object(anchor)
    assert moving_target.x == pytest.approx(608)
    assert model.interaction_candidate().id == "maintenance_unit"
    model.player.x = anchor.x - 40
    assert model.interaction_candidate() is None
    model.player.x = 620
    inspect(app, "maintenance_unit")
    assert model.interaction.target_x == moving_target.x
    held = robot.clock
    for _ in range(120):
        model.step(InputIntent(), app.camera(), 1 / 60)
        model.update_paused(1 / 60)
    assert robot.clock == held
    while app.field_conversation:
        app.advance_field_conversation()
    model.step(InputIntent(), app.camera(), 1 / 60)
    assert robot.clock > held
    # The short whole patrol stays on land and clear of the original solids.
    for _ in range(720):
        model.step(InputIntent(), app.camera(), 1 / 60)
        obj = model.presentation_object(anchor)
        assert 576 <= obj.x <= 608 and obj.z == 768
        assert not app.world.collides_player(obj.x, obj.z, 6, 6)
        assert not any(a.rect.contains_point(obj.x, obj.z) for a in app.world.shallow_water_areas)
    assert anchor.x == 576


def run_combat(app, success):
    model = app.model
    enemy = model.enemy_by_id(ANOMALY_ID)
    events = []
    model.start_contact_combat(enemy, events)
    app.process_events(events)
    if success:
        session = model.combat_session
        session.phase = "PARRY_TIMING"
        session.marker_judgements = tuple("HIT" for _ in session.marker_positions)
        model.resolve_combat_round(session, events=[])
    for _ in range(4000):
        if model.combat_session is None:
            break
        events = []
        counter = success and model.combat_session.phase in {
            "PERFECT_BUBBLE_WINDOW",
            "PERFECT_ZAP_WINDOW",
        }
        model.update_combat_session(
            InputIntent(action_pressed=counter), app.camera(), 1 / 60, events
        )
        app.process_events(events)
    assert model.combat_session is None
    return enemy


def test_three_no_input_failures_return_as_interrupted_without_success_claims():
    app = make_visit()
    enemy = run_combat(app, False)
    assert enemy.state != "DEFEATED"
    assert app.screen == AppScreen.PLAY
    assert app.office.current_session.field_progress.interrupted
    assert app.complete_office_field_task()
    finish_travel(app)
    result = app.office.current_session.field_result
    assert result.result_code == "INTERRUPTED"
    assert "anomaly_dealt_with" not in result.discovered_fact_ids
    assert any("切り上げ" in text for text in result.report_lines)
    assert not any("被害なし" in text or "対処でき" in text for text in result.report_lines)


def test_retry_then_actual_counter_success_upgrades_result():
    app = make_visit()
    run_combat(app, False)
    enemy = run_combat(app, True)
    assert enemy.state == "DEFEATED"
    assert app.complete_office_field_task()
    finish_travel(app)
    result = app.office.current_session.field_result
    assert result.result_code == "DEALT_WITH"
    assert "anomaly_dealt_with" in result.discovered_fact_ids
    assert "原因は、まだ" in result.report_lines[-1]
    assert not app.complete_office_field_task()
    drain(app.office)
    assert app.office.advance_case()


def test_duplicate_stale_or_unverified_events_cannot_invent_success():
    app = make_visit()
    progress = app.office.current_session.field_progress
    event = GameEvent(10, 10, "inspection_completed", "player", "tap_stopped", (400, 0, 256))
    app.process_events([event, event])
    assert len(progress.observations) == 1
    fake_victory = GameEvent(
        11, 11, "combat_restored", ANOMALY_ID, "player", (800, 0, 704), {"combat_outcome": "defeat"}
    )
    app.process_events([fake_victory])
    assert not progress.dealt_target_ids
    progress.event_floor = 20
    app.process_events(
        [GameEvent(12, 12, "inspection_completed", "player", "observation_post", (768, 0, 800))]
    )
    assert "post_present" not in progress.observations


def test_deflection_and_capture_are_not_reported_as_defeat():
    for outcome in ("deflect", "capture"):
        app = make_visit()
        event = GameEvent(
            1,
            1,
            "combat_restored",
            ANOMALY_ID,
            "player",
            (800, 0, 704),
            {"combat_outcome": outcome},
        )
        app.process_events([event])
        assert app.complete_office_field_task()
        finish_travel(app)
        assert app.office.current_session.field_result.result_code == "OBSERVED"
        assert not app.office.current_session.field_progress.interrupted


def test_different_results_change_lamel_reply_and_other_cases_still_advance():
    replies = []
    for code in ("OBSERVED", "DEALT_WITH", "INTERRUPTED"):
        app = make_visit()
        progress = app.office.current_session.field_progress
        progress.observe("tap_stopped")
        progress.interrupted = code == "INTERRUPTED"
        if code == "DEALT_WITH":
            progress.dealt_target_ids.add(ANOMALY_ID)
        assert app.complete_office_field_task()
        finish_travel(app)
        replies.append(
            tuple(
                line.text
                for line in app.office.current_session.dialogue
                if line.speaker == "ラメル"
            )[-1]
        )
    assert len(set(replies)) == 3
    office = OfficePrototype.load()
    for index in (0, 1, 3):
        office.current_index = index
        office.begin_current_case()
        drain(office)
        case = office.current_case
        for question in case.questions:
            assert office.ask_question(question.question_id)
            drain(office)
        assert office.classify(case.expected_classification)
        drain(office)
        assert office.advance_case()


def test_unconfirmed_return_keeps_the_active_task_for_another_visit():
    app = make_visit()
    assert app.complete_office_field_task()
    finish_travel(app)
    assert app.office.current_session.field_result is None
    assert app.office.current_session.state == CaseState.FIELD_ACTIVE
    progress = FieldProgress()
    progress.observe("tap_stopped")
    assert progress.can_report
