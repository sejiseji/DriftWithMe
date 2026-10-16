"""Authored W2 counter, independent observations, transactional resume and completion."""

from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.field_visit import FieldConversation
from drift_with_me.flowerbed import FLOWER_IDS
from drift_with_me.flowerbed_visit import FlowerbedVisit
from drift_with_me.july_week2 import LINES, REPORT, SITES, TASK, Week2Progress
from drift_with_me.office import Classification
from drift_with_me.save_state import ProgressStore, decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek, load_week_office
from field_transition_helpers import finish_travel
from test_field_visit import drain
from test_save_state import Storage
from test_week_debug_safety import debug_app


def app2(field=False):
    storage = Storage()
    app = debug_app(storage)
    app.jump_to_debug_week(WorkWeek(7, 2))
    app.week_debug_active = False
    app.progress_store = ProgressStore(browser_storage=storage)
    app.key_pressed = lambda *keys: False
    app.mouse_pressed_in = lambda rect: False
    app.travel_input_held = lambda: False
    app.week2_wait_release = False
    if field:
        app.office.prepare_debug_field_task()
        app.screen = AppScreen.PLAY
    return app, storage


def observe(app, ident):
    assert app.begin_week2_observation(ident)
    while app.week2_dialogue is not None:
        assert app.advance_week2_dialogue()
    app.week2_wait_release = False


def test_counter_three_cases_normal_classification_and_exact_mid_dialogue_save():
    app, _ = app2()
    for i in range(3):
        drain(app.office)
        assert app.office.ask_question("talk")
        app.office.advance_dialogue_step()
        saved = snapshot(app)
        app.saved_progress = decode(encode(saved))
        app.start_game()
        assert snapshot(app) == saved
        drain(app.office)
        assert app.office.classify(
            Classification.FIELD_CHECK if i == 2 else Classification.COUNTER_COMPLETE
        )
        drain(app.office)
        if i < 2:
            assert app.office.advance_case()
    assert app.office.prepare_field_task() is not None
    app.enter_exploration_from_office()
    finish_travel(app)
    assert app.screen == AppScreen.PLAY and app.office.week2_progress.phase == "field"


@pytest.mark.parametrize("flower_first", [True, False])
def test_order_independence_partial_return_resume_final_report_and_no_next_week(flower_first):
    app, _ = app2(True)
    if flower_first:
        app.east_site_progress.flowerbed_order = FLOWER_IDS
        app.east_site_progress.flowerbed_visit = FlowerbedVisit("complete").snapshot()
    first, *others = SITES
    assert app.begin_week2_observation(first)
    assert app.advance_week2_dialogue()
    app.week2_dialogue = None  # cancellation preserves the already-saved cursor
    app.saved_progress = decode(encode(snapshot(app)))
    app.start_game()
    assert app.office.week2_progress.positions[first] == 1
    observe(app, first)
    assert app.return_week2()
    finish_travel(app)
    assert app.screen == AppScreen.OFFICE and app.office.week2_progress.phase == "office"
    app.enter_exploration_from_office()
    finish_travel(app)
    for ident in reversed(others):
        observe(app, ident)
    if not flower_first:
        assert not app.week2_ready()
        app.east_site_progress.flowerbed_order = FLOWER_IDS
        app.east_site_progress.flowerbed_visit = FlowerbedVisit("complete").snapshot()
    assert app.week2_ready() and app.update_week2()
    finish_travel(app)
    assert app.update_week2()
    assert app.week2_dialogue.target_id == "week2_report"
    app.advance_week2_dialogue()
    app.saved_progress = decode(encode(snapshot(app)))
    app.start_game()
    app.update_week2()
    assert app.week2_dialogue.index == 1
    while app.week2_dialogue:
        assert app.advance_week2_dialogue()
    assert app.office.complete and app.office.week2_progress.phase == "done"
    assert app.office.sessions[TASK].field_result.result_code == "JULY2_COMPLETED"
    assert not app.can_begin_next_week() and load_week_office(WorkWeek(7, 3)) is None
    assert decode(encode(snapshot(app)))[1][WorkWeek(7, 2)].week2_progress.phase == "done"


def test_save_failure_does_not_advance_observation_or_complete_week():
    app, storage = app2(True)
    ident = next(iter(SITES))
    assert app.begin_week2_observation(ident)
    before = snapshot(app)
    storage.fail = True
    assert not app.advance_week2_dialogue()
    assert snapshot(app) == before and app.week2_dialogue.index == 0
    storage.fail = False
    app.week2_dialogue = None
    app.office.week2_progress.checked = set(SITES)
    app.office.week2_progress.phase = "report"
    app.east_site_progress.flowerbed_order = FLOWER_IDS
    app.east_site_progress.flowerbed_visit = FlowerbedVisit("complete").snapshot()
    app.week2_dialogue = FieldConversation("week2_report", REPORT, 2)
    before = snapshot(app)
    storage.fail = True
    assert not app.advance_week2_dialogue()
    assert snapshot(app) == before and not app.office.complete


def test_existing_completed_and_legacy_order_only_do_not_require_replanting():
    app, _ = app2(True)
    app.east_site_progress.flowerbed_order = FLOWER_IDS
    app.east_site_progress.flowerbed_visit = FlowerbedVisit("complete").snapshot()
    assert app.start_flowerbed_visit()
    assert app.flowerbed_dialogue.action == "repeat"
    app.flowerbed_dialogue = None
    app.east_site_progress.flowerbed_visit = {}
    app.start_flowerbed_visit()
    while app.flowerbed_dialogue:
        app.advance_flowerbed_visit()
    assert app.flowerbed_editor.confirming
    assert tuple(app.flowerbed_editor.draft) == FLOWER_IDS
    app.close_flowerbed_editor()
    assert app.east_site_progress.flowerbed_order == FLOWER_IDS


def test_combat_and_danger_reject_modal_and_only_completed_site_is_recorded():
    app, _ = app2(True)
    ident = next(iter(SITES))
    app.model.combat_session = object()
    assert not app.begin_week2_observation(ident)
    assert not app.start_flowerbed_visit()
    app.model.combat_session = None
    app.model.player.x, app.model.player.z = app.model.enemies[0].x, app.model.enemies[0].z
    assert not app.begin_week2_observation(ident)
    app.model.player.x, app.model.player.z = 288, 440
    observe(app, ident)
    assert app.office.week2_progress.checked == {ident}
    old = deepcopy(app.office.week2_progress.snapshot())
    observe(app, ident)
    assert app.office.week2_progress.snapshot() == old


def test_bad_progress_and_legacy_empty_office_migration():
    with pytest.raises(ValueError):
        Week2Progress.restore(dict(checked=[], positions={}, phase="done", report_index=0))
    with pytest.raises(ValueError):
        Week2Progress.restore(
            dict(
                checked=[],
                positions={next(iter(SITES)): len(next(iter(LINES.values())))},
                phase="field",
                report_index=0,
            )
        )
    app, _ = app2()
    saved = snapshot(app)
    saved["offices"]["7:2"] = {"index": 0, "sessions": {}}
    restored = decode(encode(saved))
    assert len(restored[1][WorkWeek(7, 2)].cases) == 3
    assert restored[1][WorkWeek(7, 2)].week2_progress.checked == set()


def test_cancel_inside_dialogue_panel_is_not_also_an_advance_or_a_return():
    app, _ = app2(True)
    ident = next(iter(SITES))
    assert app.begin_week2_observation(ident)
    app.week2_wait_release = False
    app.mouse_pressed_in = lambda rect: True
    assert app.update_week2()
    assert app.week2_dialogue is None and not app.office.week2_progress.checked
    assert app.office.week2_progress.positions == {}
    assert app.update_week2()  # release barrier consumes the old click
    app.week2_dialogue = FieldConversation(ident, LINES[ident], 0)
    assert not app.return_week2()


def test_normal_header_cannot_skip_counter_cases_but_debug_can_prepare_field():
    app, _ = app2()
    assert not app.activate_office_field_debug()
    assert app.office.current_index == 0 and app.field_transition is None
    app.week_debug_active = True
    assert app.activate_office_field_debug()
    assert app.office.current_index == 2


def test_magenta_palette_preserves_existing_colors_and_uses_leaf_triangles():
    from types import SimpleNamespace

    from drift_with_me.july_week2 import draw_week2_ground

    triangles = []
    colors = list(range(16))
    px = SimpleNamespace(colors=list(colors), tri=lambda *args: triangles.append(args[-1]))
    renderer = SimpleNamespace(pyxel=px, draw_world_line=lambda *args: None)
    camera = SimpleNamespace(project=lambda p: SimpleNamespace(x=p.x, y=p.z - p.y))
    model = SimpleNamespace(week2_scenery_enabled=True)
    draw_week2_ground(renderer, model, camera)
    draw_week2_ground(renderer, model, camera)
    from drift_with_me.grass_wind import SHADES

    assert px.colors[:16] == colors and px.colors[16:20] == list(SHADES)
    assert px.colors[20:22] == [0xFF00FF, 0xFF65F0]
    assert len(triangles) == 24 and set(triangles) == {20, 21}
