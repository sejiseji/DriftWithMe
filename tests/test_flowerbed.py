from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.flowerbed import (
    FLOWER_IDS,
    FlowerbedEditor,
    FlowerbedLayoutStore,
    install_flowerbed_world,
    validate_order,
)
from drift_with_me.save_state import SAVE_KEY, ProgressStore, decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek, load_week_office
from test_save_state import Storage, payload
from test_week_debug_safety import debug_app


def garden_app():
    storage = Storage()
    app = debug_app(storage)
    app.flowerbed_layout_store = FlowerbedLayoutStore(ProgressStore(browser_storage=storage))
    assert app.jump_to_debug_week(WorkWeek(7, 2))
    return app, storage


def test_draft_order_duplicate_rejection_undo_restart_and_confirmation():
    editor = FlowerbedEditor()
    assert editor.choose(FLOWER_IDS[2])
    assert not editor.choose(FLOWER_IDS[2])
    assert not editor.choose("unknown")
    editor.undo()
    assert editor.draft == []
    for ident in reversed(FLOWER_IDS):
        assert editor.choose(ident)
    assert editor.confirming and tuple(editor.draft) == tuple(reversed(FLOWER_IDS))
    assert not editor.choose(FLOWER_IDS[0])
    editor.undo()
    assert not editor.confirming
    editor.restart()
    assert editor.draft == []


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        ["x"] * 5,
        [FLOWER_IDS[0]] * 5,
        list(FLOWER_IDS[:4]),
        [[], *FLOWER_IDS[:4]],
        "north",
    ],
)
def test_reject_malformed_or_incomplete_committed_layout(raw):
    with pytest.raises(ValueError):
        validate_order(raw)


def test_debug_confirmation_separate_store_cancel_and_reload_leave_progress_slots_intact():
    app, storage = garden_app()
    _, old = payload()
    storage.items.update({SAVE_KEY: encode(old), SAVE_KEY + ".backup": encode(old)})
    before = deepcopy(storage.items)
    assert load_week_office(WorkWeek(7, 2)) is None  # no invented counter story
    assert app.office.cases == () and app.screen == AppScreen.PLAY
    camera = app.camera()
    assert app.start_flowerbed_editor()
    for ident in FLOWER_IDS:
        app.flowerbed_editor.choose(ident)
    assert app.east_site_progress.flowerbed_order == ()
    assert app.confirm_flowerbed()
    assert app.camera() == camera and app.flowerbed_input_wait_release
    assert app.model.flowerbed_order == FLOWER_IDS
    assert all(storage.items[k] == v for k, v in before.items())
    reloaded = FlowerbedLayoutStore(ProgressStore(browser_storage=storage))
    assert reloaded.load() == FLOWER_IDS
    assert app.start_flowerbed_editor()
    app.flowerbed_editor.choose(FLOWER_IDS[-1])
    app.close_flowerbed_editor()
    assert app.east_site_progress.flowerbed_order == FLOWER_IDS
    assert reloaded.load() == FLOWER_IDS
    assert not app.checkpoint_progress()
    assert all(storage.items[k] == v for k, v in before.items())


def test_write_failure_rolls_back_committed_map_and_leaves_editor_open():
    app, _ = garden_app()
    app.east_site_progress.flowerbed_order = FLOWER_IDS
    install_flowerbed_world(app)
    app.flowerbed_layout_store = SimpleNamespace(write=lambda order: False)
    app.start_flowerbed_editor()
    for ident in reversed(FLOWER_IDS):
        app.flowerbed_editor.choose(ident)
    assert not app.confirm_flowerbed()
    assert app.flowerbed_editor.confirming and app.flowerbed_editor.error
    assert app.model.flowerbed_order == app.east_site_progress.flowerbed_order == FLOWER_IDS


def test_optional_layout_round_trip_old_saves_and_resources_preserved():
    app, old = payload()
    assert decode(encode(old))[2].flowerbed_order == ()
    app.east_site_progress.flowerbed_order = tuple(reversed(FLOWER_IDS))
    data = snapshot(app)
    restored = decode(encode(data))
    assert restored[2].flowerbed_order == tuple(reversed(FLOWER_IDS))
    assert data["resources"] == old["resources"]
    assert data["offices"] == old["offices"]
    data["flowerbed"] = list(FLOWER_IDS[:4])
    with pytest.raises(ValueError):
        decode(encode(data))


def test_prototype_resume_has_committed_order_and_never_serializes_draft():
    app, _ = garden_app()
    app.east_site_progress.flowerbed_order = FLOWER_IDS
    app.start_flowerbed_editor()
    app.flowerbed_editor.choose(FLOWER_IDS[-1])
    data = snapshot(app)
    assert data["flowerbed"] == list(FLOWER_IDS)
    app.saved_progress = decode(encode(data))
    app.start_game()
    assert app.screen == AppScreen.PLAY and app.flowerbed_editor is None
    assert app.east_site_progress.flowerbed_order == FLOWER_IDS
    assert app.model.flowerbed_order == FLOWER_IDS
    assert app.model.flowerbed_visible
    assert app.jump_to_debug_week(WorkWeek(6, 4))
    assert not app.model.flowerbed_visible and app.model.flowerbed_order == ()


def test_native_and_corrupt_prototype_store_does_not_replace_normal_save(tmp_path):
    backend = ProgressStore(path=tmp_path / "normal.json")
    store = FlowerbedLayoutStore(backend)
    assert store.write(FLOWER_IDS) and store.load() == FLOWER_IDS
    assert not (tmp_path / "normal.json").exists()
    path = tmp_path / "flowerbed-prototype.json"
    path.write_text('{"version":1,"order":["unknown"]}')
    assert store.load() == ()


def test_all_tap_targets_fit_all_profiles_and_five_candidates_do_not_overlap():
    from test_office_jack_portrait import make_app

    for profile in ("low", "medium", "high"):
        app, _ = make_app(profile)
        rects = app.flowerbed_rects()
        width, height = app.runtime.screen_width, app.runtime.screen_height
        for rect in rects.values():
            assert 0 <= rect.x < rect.x + rect.width <= width
            assert 0 <= rect.y < rect.y + rect.height <= height
            assert rect.height / height * 294 >= 44
        for a, b in zip(FLOWER_IDS, FLOWER_IDS[1:], strict=False):
            assert rects[a].x + rects[a].width < rects[b].x


def test_actual_world_plants_follow_draft_and_cancel_restores_committed(monkeypatch):
    from drift_with_me.flowerbed import flowerbed_draw_commands

    monkeypatch.setattr(
        "drift_with_me.garden_props_preview.garden_preview_draw_commands",
        lambda renderer, model, camera, state: state.props,
    )
    app, _ = garden_app()
    app.east_site_progress.flowerbed_order = FLOWER_IDS
    install_flowerbed_world(app)
    app.start_flowerbed_editor()
    for ident in reversed(FLOWER_IDS[-2:]):
        app.flowerbed_editor.choose(ident)
    props = flowerbed_draw_commands(None, app.model, None)
    assert [p.asset_id for p in props] == [
        ident for ident in reversed(FLOWER_IDS[-2:]) for _ in range(6)
    ]
    assert len({(p.x, p.z) for p in props}) == 12
    for p in props:
        section = int(p.instance_id.split(":")[1])
        assert 140 + section * 18 < p.x < 156 + section * 18
        assert 365 < p.z < 397 and p.world_scale == 1.15
    assert app.model.flowerbed_order == app.east_site_progress.flowerbed_order == FLOWER_IDS
    app.flowerbed_editor.undo()
    assert len(flowerbed_draw_commands(None, app.model, None)) == 6
    app.flowerbed_editor.restart()
    assert flowerbed_draw_commands(None, app.model, None) == []
    app.close_flowerbed_editor()
    assert [p.asset_id for p in flowerbed_draw_commands(None, app.model, None)] == [
        ident for ident in FLOWER_IDS for _ in range(6)
    ]


def test_closeup_frames_real_soil_above_controls_without_mutating_normal_camera():
    from drift_with_me.math3d import (
        AffineProjectionProfile,
        Vec3,
        affine_camera_from_perspective,
    )

    app, _ = garden_app()
    app.start_flowerbed_editor()
    normal = app.camera()
    app.scene_camera = lambda camera: affine_camera_from_perspective(
        camera,
        AffineProjectionProfile.from_config(app.runtime.raw),
        base_distance=480,
    )
    closeup = app.flowerbed_closeup_camera()
    assert app.camera() == normal
    assert closeup.target == Vec3(184, 0, 382) and closeup.zoom == 2
    for x, z in [(138, 363), (230, 363), (230, 399), (138, 399)]:
        point = closeup.project(Vec3(x, 0, z))
        assert 16 <= point.x <= 496 and 24 <= point.y < 126
    app.close_flowerbed_editor()
    assert app.camera() == normal and app.model.flowerbed_draft is None
