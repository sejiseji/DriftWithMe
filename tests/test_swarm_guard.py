import pytest

from drift_with_me.math3d import Vec3
from drift_with_me.swarm_guard import CYCLE, follow, guard_sample
from test_swarm_render import scene_setup


def test_screen_direction_mapping_and_quick_lower_sweep():
    assert pytest.approx(1.08) == CYCLE
    starts = [0, 0.30, 0.38, 0.46, 0.54, 0.84, 0.92, 1.0]
    expected = [
        ("right", "front_left"),
        ("front_right", "front_left"),
        ("front", "front"),
        ("front_left", "front_right"),
        ("left", "front_right"),
        ("front_left", "front_right"),
        ("front", "front"),
        ("front_right", "front_left"),
    ]
    assert [guard_sample(t + 0.001)[:2] for t in starts] == expected
    assert guard_sample(CYCLE + 0.15) == guard_sample(0.15)
    assert guard_sample(0.15)[2][0] < 0
    assert guard_sample(0.7)[2][0] > 0
    assert guard_sample(0.459)[2][1] < -17


def test_guard_is_presentation_only_and_returns_smoothly_after_capture_and_assist():
    model, camera, field, renderer, scene = scene_setup()
    model.buddy.x, model.buddy.z = model.player.x - 10, model.player.z
    scene.guard_ground = (model.buddy.x, model.buddy.z)
    original = (model.player.x, model.player.z, model.buddy.x, model.buddy.z)
    field.battle.phase = "approach"
    previous = scene.guard_ground
    for i in range(90):
        field.battle.elapsed = i / 60
        scene.prepare(i / 60)
        before = camera.project(Vec3(previous[0], 0, previous[1]))
        after = camera.project(Vec3(scene.guard_ground[0], 0, scene.guard_ground[1]))
        assert max(abs(after.x - before.x), abs(after.y - before.y)) < 12
        previous = scene.guard_ground
    for phase in [
        "bound",
        "assist",
        "approach",
        "finish_wait",
        "electric",
        "spear",
        "victory",
        "fade",
    ]:
        field.battle.phase = phase
        for i in range(60):
            field.battle.elapsed = i / 60
            scene.prepare(scene.guard_clock + 1 / 60)
    assert scene.guard_ground == pytest.approx((model.buddy.x, model.buddy.z), abs=0.001)
    assert scene.guard_view("player") is None
    assert original == (model.player.x, model.player.z, model.buddy.x, model.buddy.z)
    assert follow((1, 2), (5, 6), 0) == (1, 2)
