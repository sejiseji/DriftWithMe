"""Render-only wind pilot: bounded motion, stable membership, eligibility and no carry-over."""

from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

from drift_with_me.config import load_runtime_config
from drift_with_me.grass_sway import sample_gust
from drift_with_me.math3d import (
    AffineProjectionProfile,
    CameraState,
    Vec3,
    affine_camera_from_perspective,
)
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.render import Renderer
from drift_with_me.wind_life import (
    TREE_IDS,
    allowed,
    leaf_phase_shift,
    shore_angle,
    shore_candidate,
)
from drift_with_me.world import load_world_data


def scene():
    raw = load_runtime_config().raw
    m = GameModel(raw, load_world_data())
    c = CameraState.from_config(raw, Vec3(400, 0, 370), 512, 236)
    c = affine_camera_from_perspective(
        c, AffineProjectionProfile.from_config(raw), base_distance=raw["camera"]["base_distance"]
    )
    r = Renderer(SimpleNamespace())
    r.wind_life_context = True
    return m, c, r


def test_guard_and_toggle_are_stateless_for_all_excluded_scenes():
    m, c, r = scene()
    assert allowed(r, m, c)
    for name in ("wind_life_context", "wind_life_enabled"):
        setattr(r, name, False)
        assert not allowed(r, m, c)
        setattr(r, name, True)
        assert allowed(r, m, c)
    for attr, value in (
        ("august_rain", True),
        ("august_sighting_view", object()),
        ("combat_session", object()),
        ("interaction", object()),
    ):
        previous = getattr(m, attr, None)
        setattr(m, attr, value)
        assert not allowed(r, m, c)
        setattr(m, attr, previous)
        assert allowed(r, m, c)
    m.config["simulation"]["day_phase"] = "night"
    assert not allowed(r, m, c)
    # A fresh ED/preview renderer never opts into normal exploration context.
    assert not allowed(Renderer(SimpleNamespace()), m, c)


def test_tree_phase_uses_existing_wind_and_keeps_other_trees_unchanged():
    m, c, r = scene()
    cfg = m.config["grass_sway"]
    shifts = {ident: [] for ident in TREE_IDS}
    for frame in range(1200):
        t = frame / 60
        gust = sample_gust(t, cfg["gust_seed"])
        for ident in TREE_IDS:
            shift = leaf_phase_shift(m.world.object_by_id(ident), t, cfg, gust)
            assert 0 <= shift <= 8
            shifts[ident].append(shift)
        assert leaf_phase_shift(m.world.object_by_id("tree_03"), t, cfg, gust) == 0
    assert any(max(v) > 0 for v in shifts.values())
    assert shifts["tree_01"] != shifts["tree_02"]
    # The offset cannot reverse the original animation clock.
    for values in shifts.values():
        assert all(1 + b - a >= 0 for a, b in zip(values, values[1:], strict=False))
    r._wind_life_active = True
    r._grass_wind_time = 1
    r._grass_sway_config = cfg
    r._grass_sway_gust = sample_gust(1)
    obj = m.world.object_by_id("tree_01")
    r.wind_life_enabled = False
    baseline = [r.tree_foliage_frame_id(m, obj, 1) for _ in range(2)]
    r.wind_life_enabled = True
    r.tree_foliage_frame_id(m, obj, 1)
    r.wind_life_enabled = False
    assert r.tree_foliage_frame_id(m, obj, 1) == baseline[0]


def test_shore_cohort_is_world_fixed_and_never_inside_water():
    m, c, r = scene()
    selected = []
    for cell_z in range(11, 16):
        for cell_x in range(12, 22):
            for index in range(6):
                x, z = cell_x * 24 + 12, cell_z * 24 + 12
                if shore_candidate("spawn_grassland_micro", cell_x, cell_z, index, x, z, m.world):
                    selected.append((cell_x, cell_z, index))
                    assert not any(a.rect.contains_point(x, z) for a in m.world.shallow_water_areas)
    assert 0 < len(selected) <= 24
    assert not shore_candidate("other_area", 14, 13, 0, 350, 328, m.world)


def test_shore_rotation_keeps_roots_stroke_count_and_one_pixel_limit():
    records = []
    r = Renderer(
        SimpleNamespace(
            line=lambda *a: records.append(("line", a)), pset=lambda *a: records.append(("pset", a))
        )
    )
    cfg = load_runtime_config().raw["grass_sway"]
    for height in range(2, 7):
        for shape in range(4):
            records.clear()
            r.draw_micro_grass_blade(20, 30, height, 11, 3, 1, shape)
            baseline = list(records)
            for t in (0, 1, 2, 3, 4, 5, 8, 14):
                records.clear()
                angle = shore_angle(400, 328, t, 0.5, cfg, sample_gust(t), height)
                r.draw_micro_grass_blade(20, 30, height, 11, 3, 1, shape, angle)
                assert len(records) == len(baseline)
                for (kind, a), (old_kind, b) in zip(records, baseline, strict=True):
                    assert kind == old_kind and a[-1] == b[-1]
                    assert all(abs(x - y) <= 1 for x, y in zip(a[:-1], b[:-1], strict=True))
                    if kind == "line":
                        assert a[:2] == b[:2]


def test_pure_wind_samples_do_not_change_gameplay_or_random_state():
    import random

    m, c, r = scene()
    m.enemies.clear()
    other = deepcopy(m)
    logical = CameraState.from_config(m.config, Vec3(400, 0, 370), 512, 236)
    state = random.getstate()
    for frame in range(360):
        intent = InputIntent(
            screen_x=1 if frame < 120 else -1 if frame < 240 else 0,
            strength=1 if frame < 240 else 0,
        )
        a = m.step(intent, logical, 1 / 60, movement_camera=c)
        for obj in m.world.objects:
            if obj.id in TREE_IDS:
                leaf_phase_shift(obj, frame / 60, m.config["grass_sway"], sample_gust(frame / 60))
        b = other.step(intent, logical, 1 / 60, movement_camera=c)
        assert (
            a == b
            and asdict(m.player) == asdict(other.player)
            and asdict(m.buddy) == asdict(other.buddy)
        )
    assert random.getstate() == state


def test_authored_dialogues_ed_preview_and_transitions_never_inherit_context():
    from drift_with_me.week_cycle import WorkWeek
    from drift_with_me.wind_life import normal_context

    m, c, r = scene()
    app = SimpleNamespace(
        screen=SimpleNamespace(name="PLAY"),
        model=m,
        work_week=WorkWeek(6, 1),
        office=SimpleNamespace(),
    )
    assert normal_context(app)
    for attr in (
        "week2_dialogue",
        "week3_dialogue",
        "week4_dialogue",
        "field_conversation",
        "flowerbed_dialogue",
        "first_sight_conversation",
        "patrol_dialogue",
        "field_transition",
        "week_transition",
        "august_crossing",
    ):
        setattr(app, attr, object())
        assert not normal_context(app)
        setattr(app, attr, None)
        assert normal_context(app)
    app.work_week = WorkWeek(7, 1)
    app.office.july_progress = SimpleNamespace(stage="patrol")
    assert normal_context(app)
    for stage in ("after_clear", "researchers", "arrival_fade"):
        app.office.july_progress.stage = stage
        assert not normal_context(app)
    app.office.july_progress.stage = "patrol"
    assert normal_context(app)
    app.work_week = WorkWeek(7, 3)
    app.office.week3_progress = SimpleNamespace(active_scene="arrival")
    assert not normal_context(app)
    app.office.week3_progress.active_scene = None
    assert normal_context(app)
    for screen in ("CREDITS", "PAUSE", "OFFICE", "WATER_STUDY"):
        app.screen.name = screen
        assert not normal_context(app)
    app.screen.name = "PLAY"
    app.ending_playback = object()  # stale metadata is not an active ED screen
    assert normal_context(app)


def test_swarm_battle_never_inherits_prior_exploration_context():
    from drift_with_me.swarm_render import SwarmModelView
    from drift_with_me.week_cycle import WorkWeek
    from drift_with_me.wind_life import normal_context

    m, c, r = scene()
    assert allowed(r, m, c)
    view = SwarmModelView(m, SimpleNamespace(enemies=[]))
    assert r.wind_life_context is True
    assert not allowed(r, view, c)
    app = SimpleNamespace(
        screen=SimpleNamespace(name="PLAY"),
        model=m,
        work_week=WorkWeek(6, 1),
        office=SimpleNamespace(),
    )
    m.swarm_field = SimpleNamespace(battle=object())
    assert not normal_context(app)
    m.swarm_field.battle = None
    assert normal_context(app)
    assert allowed(r, m, c)
