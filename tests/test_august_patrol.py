from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.august_patrol import BY_ID, NPCS
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek
from test_august_wave1 import august_app, complete_week, dispatch


def patrol_app():
    app, storage = august_app()
    for _ in range(3):
        complete_week(app)
        assert app.begin_next_week()
        app.update_week_transition(0.56)
        app.update_week_transition(4)
        app.week_input_wait_for_release = False
        app.office.begin_current_case()
    assert app.work_week == WorkWeek(8, 4)
    return app, storage


def test_patrol_dispatch_is_enemy_free_optional_and_retains_resources_and_save():
    app, _ = patrol_app()
    app.model.water, app.model.energy = 42, 37
    dispatch(app)
    assert not app.model.enemies
    assert len([o for o in app.world.objects if o.id in BY_ID]) == 15
    assert all(not app.world.object_by_id(i).solid for i in BY_ID)
    assert not app.office.august_progress.sites
    assert app.return_august()
    app.field_transition = None
    app.screen = AppScreen.OFFICE
    assert app.office.august_progress.phase == "office"
    app.key_pressed = lambda *keys: "KEY_F" in keys
    app.mouse_pressed_in = lambda *_: False
    assert app.update_patrol(0)
    assert app.office.august_progress.phase == "report"
    for _ in range(2):
        assert app.advance_august_report()
    assert app.office.complete and not app.can_begin_next_week()
    restored = decode(encode(snapshot(app)))
    assert restored[0] == WorkWeek(8, 4)
    assert restored[1][restored[0]].august_progress.phase == "done"
    assert (app.model.water, app.model.energy) == (42, 37)


@pytest.mark.parametrize("ident", BY_ID)
def test_each_optional_conversation_locks_faces_and_releases_without_advancing_sites(ident):
    app, _ = patrol_app()
    dispatch(app)
    resources = (app.model.water, app.model.energy)
    assert app.begin_patrol_target(ident)
    assert app.model.world_paused
    assert app.patrol_dialogue.target_speaker == BY_ID[ident].name
    app.travel_input_held = lambda: False
    app.key_pressed = lambda *_: False
    app.mouse_pressed_in = lambda *_: False
    assert app.update_patrol(0)
    app.key_pressed = lambda *_: True
    assert app.update_patrol(0)
    assert app.patrol_dialogue is None and not app.model.world_paused
    assert app.office.august_progress.sites == []
    assert (app.model.water, app.model.energy) == resources
    assert app.field_input_wait_for_release


def test_patrol_install_is_idempotent_and_does_not_touch_other_weeks():
    app, _ = patrol_app()
    dispatch(app)
    before = deepcopy(app.world.raw)
    app.install_patrol()
    assert app.world.raw == before
    app.work_week = WorkWeek(8, 2)
    app.install_patrol()
    assert app.world.raw == before
    assert len({n.position for n in NPCS}) == 15


def test_no_old_flowerbed_entry_or_collision_and_no_required_visit_goal():
    from drift_with_me.map_objectives import map_goals

    app, _ = patrol_app()
    dispatch(app)
    assert map_goals(app) == (None, ())
    assert not app.flowerbed_entry_available()
    assert not app.start_flowerbed_visit()
    assert app.world.object_by_id("jul_w2_fuji") is None
    assert not app.world.object_by_id("jul_w2_flowerbed").inspectable
    for n in NPCS:
        assert not app.world.collides_player(*n.position, 4, 4), n.key


def test_native_assets_have_fixed_feet_palette_and_small_glance_frames():
    import json
    from pathlib import Path
    from types import SimpleNamespace

    from drift_with_me.august_patrol import patrol_pose

    root = Path(__file__).parents[1] / "src/drift_with_me/assets"
    manifest = json.loads((root / "jack_sprite.json").read_text())
    assets = {a["id"]: a for a in manifest["source_assets"]}
    for n in NPCS:
        a = assets[n.map_asset]
        size = 64 if n.key in {"iwama", "merrill"} else 32
        assert (a["hex_width"], a["hex_height"]) == (size, size)
        assert a["anchor_px"] == [size // 2, size] and a["colkey"] == 0
        assert a["world_size"] == [32, 32]
        poses = [(root / f["path"]).read_text().splitlines() for f in a["frames"]]
        assert len(poses) == 3
        assert all(len(v) == size and all(len(row) == size for row in v) for v in poses)
        if len(poses) == 3:
            assert poses[0][-16:] == poses[1][-16:] == poses[2][-16:]
        model = SimpleNamespace(world_tick=0, patrol_talking=None)
        names = set()
        for tick in range(18 * 60):
            model.world_tick = tick
            names.add(patrol_pose(model, "aug_patrol_" + n.key))
        assert names == {"normal", "look_left", "look_right"}
        model.patrol_talking = "aug_patrol_" + n.key
        assert patrol_pose(model, model.patrol_talking) == "normal"


def test_iwama64_is_new_detail_with_jack_density_and_preserved_world_size():
    import json
    from pathlib import Path

    root = Path(__file__).parents[1] / "src/drift_with_me/assets"
    manifest = json.loads((root / "jack_sprite.json").read_text())
    jack = manifest["assets"]["jack_idle_32"]
    iwama = next(a for a in manifest["source_assets"] if a["id"] == "aug_npc_iwama")
    assert iwama["hex_width"] / iwama["world_size"][0] == 32 / jack["world_size"][0] == 2
    old = (
        (Path(__file__).parent / "fixtures/august_iwama_32_reference.hex").read_text().splitlines()
    )
    new = (root / iwama["frames"][0]["path"]).read_text().splitlines()
    enlarged = ["".join(c * 2 for c in row) for row in old for _ in range(2)]
    assert new != enlarged
    assert any(
        len({new[y][x], new[y][x + 1], new[y + 1][x], new[y + 1][x + 1]}) > 1
        for y in range(0, 64, 2)
        for x in range(0, 64, 2)
    )
    assert iwama["animation"] == "reactive_pose_set"


def test_pair_turns_keep_approved_neutral_and_planted_body_without_mirroring():
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).parents[1] / "src/drift_with_me/assets"
    manifest = json.loads((root / "jack_sprite.json").read_text())
    for key in ("iwama", "merrill"):
        a = next(a for a in manifest["source_assets"] if a["id"] == "aug_npc_" + key)
        rows = [(root / f["path"]).read_text().splitlines() for f in a["frames"]]
        assert [f["id"] for f in a["frames"]] == ["normal", "look_left", "look_right"]
        assert len({tuple(r) for r in rows}) == 3
        assert rows[0][24:] == rows[1][24:] == rows[2][24:]
        assert rows[1] != [r[::-1] for r in rows[2]]
        assert a["world_size"] == [32, 32] and a["anchor_px"] == [32, 64]
        if key == "iwama":
            pixels = bytes(int(c, 16) for row in rows[0] for c in row)
            assert (
                hashlib.sha256(pixels).hexdigest()
                == "c19d6a7d2d586064963883840a82f18cc0ddeb50a8d4ad9282d87e128913a3d9"
            )
