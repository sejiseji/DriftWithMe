from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.first_sight import (
    FIRST_SIGHT_LINES,
    FUSE_REPLIES,
    JACK_LINES,
    FirstSightQueue,
    first_sight_lines,
)
from test_field_visit import make_visit


def app_with_viewport():
    app = make_visit()
    app.first_sight_queue = FirstSightQueue()
    from drift_with_me.east_site import EastSiteProgress

    app.east_site_progress = EastSiteProgress()
    app.first_sight_seen = set()
    app.first_sight_conversation = None
    app.week_transition = None
    app.camera_controller.freezes_world = False
    app.scene_camera = lambda c: c
    app.key_pressed = lambda *n: False
    app.mouse_pressed_in = lambda r: False
    app.travel_input_held = lambda: False
    app.checkpoint_progress = lambda: False
    camera = SimpleNamespace(viewport_width=512, viewport_height=236)
    app.camera_controller.current = camera
    rects = {}
    app.renderer = SimpleNamespace(
        enemy_sprite_placement=lambda model, e, c: SimpleNamespace(
            rect=rects.get(e.id, (900, 900, 32, 32))
        )
    )
    app.model.player.x, app.model.player.z = 288, 384
    for e in app.model.enemies:
        e.x, e.z = app.model.player.x + 60, app.model.player.z
        e.home_x, e.home_z = e.x, e.z
        e.state = "IDLE"
    return app, rects


def test_only_drawn_viewport_intersection_can_start_and_abnormal_has_priority():
    app, rects = app_with_viewport()
    assert not app.update_first_sight(1 / 60)
    normal = next(e for e in app.model.enemies if e.kind == "normal")
    abnormal = next(e for e in app.model.enemies if e.kind == "abnormal")
    rects[normal.id] = (511, 70, 32, 32)
    rects[abnormal.id] = (120, 70, 32, 32)
    original = deepcopy(app.office.current_session.field_progress)
    assert app.update_first_sight(1 / 60)
    assert app.first_sight_conversation.kind == "abnormal"
    assert app.first_sight_conversation.lines == FIRST_SIGHT_LINES["abnormal"]
    assert not app.first_sight_seen
    assert app.office.current_session.field_progress == original


@pytest.mark.parametrize("blocked", ["combat", "inspection", "camera", "fade", "week"])
def test_queue_waits_for_safe_scene_and_discards_a_lost_subject(blocked):
    app, rects = app_with_viewport()
    e = app.model.enemies[0]
    rects[e.id] = (100, 70, 32, 32)
    if blocked == "combat":
        app.model.combat_session = object()
    elif blocked == "inspection":
        app.field_conversation = object()
    elif blocked == "camera":
        app.camera_controller.freezes_world = True
    elif blocked == "danger":
        e.x, e.z = app.model.player.x, app.model.player.z
    elif blocked == "fade":
        app.field_transition = object()
    else:
        app.week_transition = object()
    assert not app.update_first_sight(1 / 60)
    assert e.kind in app.first_sight_queue.targets
    rects.clear()
    assert not app.update_first_sight(1 / 60)
    assert not app.first_sight_queue.targets


def test_finish_marks_only_last_line_cancel_does_not_mark_and_gap_prevents_bursts():
    app, rects = app_with_viewport()
    for e in app.model.enemies:
        rects[e.id] = (100, 70, 32, 32)
    assert app.update_first_sight(0.01)
    assert app.update_first_sight(0.01)  # release
    app.key_pressed = lambda *n: "KEY_RETURN" in n
    assert app.update_first_sight(0.01)
    assert app.first_sight_conversation.index == 1 and not app.first_sight_seen
    app.key_pressed = lambda *n: False
    app.update_first_sight(0.01)
    app.key_pressed = lambda *n: "KEY_X" in n
    app.update_first_sight(0.01)
    assert app.first_sight_conversation is None and not app.first_sight_seen
    app.key_pressed = lambda *n: False
    assert not app.update_first_sight(3.0)
    assert app.update_first_sight(1.1)
    app.update_first_sight(0.01)
    app.key_pressed = lambda *n: "KEY_RETURN" in n
    app.update_first_sight(0.01)
    app.key_pressed = lambda *n: False
    app.update_first_sight(0.01)
    app.key_pressed = lambda *n: "KEY_RETURN" in n
    app.update_first_sight(0.01)
    assert not app.first_sight_seen and app.first_sight_conversation.index == 2
    app.key_pressed = lambda *n: False
    app.update_first_sight(0.01)
    app.key_pressed = lambda *n: "KEY_RETURN" in n
    app.update_first_sight(0.01)
    assert app.first_sight_seen == {"abnormal"}
    app.key_pressed = lambda *n: False
    assert not app.update_first_sight(3)
    assert app.update_first_sight(1.1)
    assert app.first_sight_conversation.kind == "normal"
    assert "\n".join(text for _, text in app.first_sight_conversation.lines[1:]) == FUSE_REPLIES[1]


def test_subject_lost_mid_dialog_and_defeated_enemies_do_not_become_seen():
    app, rects = app_with_viewport()
    e = app.model.enemies[0]
    rects[e.id] = (100, 70, 32, 32)
    app.update_first_sight(0.01)
    rects.clear()
    app.update_first_sight(0.01)
    assert not app.first_sight_seen and app.first_sight_conversation is None
    rects[e.id] = (100, 70, 32, 32)
    e.state = "DEFEATED"
    assert not app.update_first_sight(5)


def test_visible_abnormal_keeps_priority_while_waiting_for_clear_dialogue_space():
    queue = FirstSightQueue()
    queue.observe({"abnormal": "a", "normal": "n"}, set(), 0)
    assert queue.begin(set(), True, {"n"}) is None
    assert queue.begin(set(), True, {"a", "n"}).kind == "abnormal"


@pytest.mark.parametrize("order", [("normal", "abnormal"), ("abnormal", "normal")])
def test_reply_order_survives_cancellation_and_save_reload(order):
    from drift_with_me.save_state import decode, encode, snapshot
    from drift_with_me.week_cycle import WorkWeek

    app, rects = app_with_viewport()
    app.work_week = WorkWeek()
    app.week_office_history = {app.work_week: app.office}
    app.first_sight_seen = set()
    seen = app.first_sight_seen
    queue = FirstSightQueue()
    for occurrence, kind in enumerate(order):
        queue.observe({kind: kind}, seen, 5)
        interrupted = queue.begin(seen, True)
        assert interrupted.lines[0] == ("ジャック", JACK_LINES[kind])
        assert "\n".join(text for _, text in interrupted.lines[1:]) == FUSE_REPLIES[occurrence]
        interrupted.index = 2  # Cancel after part of Fuse's reply; no completion flag.
        app.first_sight_seen = seen
        loaded = decode(encode(snapshot(app)))
        seen = loaded[3]
        restarted = queue.begin(seen, True)
        assert restarted.index == 0 and restarted.lines == interrupted.lines
        seen.add(kind)  # Only the existing last-page close records completion.
        app.first_sight_seen = seen
        seen = decode(encode(snapshot(app)))[3]
    queue.observe({"normal": "n", "abnormal": "a"}, seen, 5)
    assert queue.begin(seen, True) is None


@pytest.mark.parametrize("previous", ["normal", "abnormal"])
def test_existing_one_kind_save_uses_second_reply(previous):
    from drift_with_me.save_state import decode, encode, snapshot
    from drift_with_me.week_cycle import WorkWeek

    app, _ = app_with_viewport()
    app.work_week = WorkWeek()
    app.week_office_history = {app.work_week: app.office}
    app.first_sight_seen = {previous}
    data = snapshot(app)
    data["version"] = 1
    del data["resources"], data["defeated"]
    seen = decode(encode(data))[3]
    remaining = "abnormal" if previous == "normal" else "normal"
    lines = first_sight_lines(remaining, seen)
    assert "\n".join(text for _, text in lines[1:]) == FUSE_REPLIES[1]


@pytest.mark.parametrize("order", [("normal", "abnormal"), ("abnormal", "normal")])
def test_actual_dialogue_pages_record_once_and_cancel_keeps_occurrence(order):
    app, rects = app_with_viewport()

    def advance():
        app.key_pressed = lambda *n: False
        app.update_first_sight(0.01)
        app.key_pressed = lambda *n: "KEY_RETURN" in n
        app.update_first_sight(0.01)
        app.key_pressed = lambda *n: False

    for occurrence, kind in enumerate(order):
        rects.clear()
        enemy = next(e for e in app.model.enemies if e.kind == kind)
        rects[enemy.id] = (100, 70, 32, 32)
        assert app.update_first_sight(5)
        lines = app.first_sight_conversation.lines
        assert "\n".join(text for _, text in lines[1:]) == FUSE_REPLIES[occurrence]
        advance()
        advance()
        assert app.first_sight_conversation.index == 2 and kind not in app.first_sight_seen
        app.update_first_sight(0.01)
        app.key_pressed = lambda *n: "KEY_X" in n
        app.update_first_sight(0.01)
        assert app.first_sight_conversation is None and kind not in app.first_sight_seen
        app.key_pressed = lambda *n: False
        assert app.update_first_sight(5)
        assert app.first_sight_conversation.lines == lines
        advance()
        advance()
        advance()
        assert app.first_sight_conversation is None and kind in app.first_sight_seen
    assert app.first_sight_seen == {"normal", "abnormal"}


@pytest.mark.parametrize("kind", ["normal", "abnormal"])
@pytest.mark.parametrize("offset, starts", [(0.001, False), (0, True), (-0.001, True)])
def test_intro_uses_exact_existing_aggro_boundary(kind, offset, starts):
    app, rects = app_with_viewport()
    enemy = next(e for e in app.model.enemies if e.kind == kind)
    radius = app.model.config["enemy"][kind]["aggro_radius"]
    enemy.x, enemy.z = app.model.player.x + radius + offset, app.model.player.z
    enemy.home_x, enemy.home_z = enemy.x, enemy.z
    rects[enemy.id] = (180, 130, 32, 32)  # Close subject may be behind the dialogue panel.
    assert app.update_first_sight(0.01) == starts
    if starts:
        assert enemy.state == "APPROACH"
        assert app.first_sight_conversation.kind == kind


def test_far_abnormal_does_not_block_near_normal_and_far_same_kind_does_not_hide_near():
    app, rects = app_with_viewport()
    normal = [e for e in app.model.enemies if e.kind == "normal"]
    abnormal = next(e for e in app.model.enemies if e.kind == "abnormal")
    abnormal.x = app.model.player.x + 200
    for e in [*normal, abnormal]:
        rects[e.id] = (100, 70, 32, 32)
    normal[0].x = app.model.player.x + 200
    assert app.update_first_sight(0.01)
    assert app.first_sight_conversation.kind == "normal"
    assert app.first_sight_conversation.target_id != normal[0].id


@pytest.mark.parametrize("remaining", [127.9, 0.1])
def test_boundary_crossing_callback_precedes_enemy_dash_contact_and_other_fixed_steps(remaining):
    from drift_with_me.math3d import CameraState, Vec3
    from drift_with_me.model import InputIntent

    app, rects = app_with_viewport()
    enemy = next(e for e in app.model.enemies if e.kind == "abnormal")
    rects[enemy.id] = (100, 70, 32, 32)
    enemy.x, enemy.z = app.model.player.x + 128.01, app.model.player.z
    enemy.home_x, enemy.home_z = enemy.x, enemy.z
    enemy.state = "WINDUP"
    enemy.state_timer = 0.0001
    assert not app.update_first_sight(0.01)
    # Model movement crosses the threshold before the enemy update of this tick.
    app.model.move_player_by_delta = lambda x, z: setattr(
        app.model.player, "x", enemy.x - remaining
    )
    camera = CameraState.from_config(app.runtime.raw, Vec3(288, 0, 384), 512, 236)
    hp = app.model.water
    events = app.model.step(
        InputIntent(screen_x=1, strength=1),
        camera,
        0.05,
        before_enemy_update=lambda: app.update_first_sight(0),
    )
    assert app.first_sight_conversation.kind == "abnormal"
    assert enemy.state == "WINDUP" and enemy.state_timer == 0.0001
    assert app.model.water == hp and app.model.combat_session is None
    assert not any(e.kind in {"combat_started", "player_damaged"} for e in events)
    positions = [(e.x, e.z, e.state_timer) for e in app.model.enemies]
    for _ in range(3):
        assert app.update_first_sight(0.1)
    assert positions == [(e.x, e.z, e.state_timer) for e in app.model.enemies]
