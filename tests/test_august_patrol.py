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
        size = {
            "iwama": 64,
            "merrill": 64,
            "morris": 56,
            "ruby": 48,
            "ramel": 64,
            "hero": 64,
            "yumesaki": 64,
            "miyano": 64,
            "fuji": 64,
            "sagan": 64,
            "ura": 64,
            "takanashi": 64,
            "yoake": 64,
            "mina": 64,
            "grow": 64,
        }.get(n.key, 32)
        assert (a["hex_width"], a["hex_height"]) == (size, size)
        assert a["anchor_px"] == [size // 2, size] and a["colkey"] == 0
        assert a["world_size"] == [n.map_size, n.map_size]
        assert size / n.map_size == 2
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


def test_siblings_density_stature_and_stationary_body():
    import json
    from pathlib import Path

    from drift_with_me.august_patrol import BY_ID

    root = Path(__file__).parents[1] / "src/drift_with_me/assets"
    manifest = json.loads((root / "jack_sprite.json").read_text())
    assets = {a["id"]: a for a in manifest["source_assets"]}
    expected = {"morris": (56, 28, 24), "ruby": (48, 24, 22)}
    for key, (size, world, cut) in expected.items():
        a = assets["aug_npc_" + key]
        assert (a["hex_width"], a["hex_height"]) == (size, size)
        assert a["world_size"] == [world, world] and size / world == 2
        assert BY_ID["aug_patrol_" + key].map_size == world
        rows = [(root / f["path"]).read_text().splitlines() for f in a["frames"]]
        assert len(set(tuple(r) for r in rows)) == 3
        assert rows[0][cut:] == rows[1][cut:] == rows[2][cut:]
        assert rows[1] != [r[::-1] for r in rows[2]]
    assert expected["morris"][1] > expected["ruby"][1]


def test_river_npcs_keep_scale_identity_and_fixed_idle_body():
    import json
    from pathlib import Path

    from drift_with_me.august_patrol import BY_ID

    root = Path(__file__).parents[1] / "src/drift_with_me/assets"
    manifest = json.loads((root / "jack_sprite.json").read_text())
    assets = {a["id"]: a for a in manifest["source_assets"]}
    for key, portrait, position, cut in [
        ("ramel", "nervous_elf_woodsman", (480, 280), 20),
        ("hero", "smug_blond_hero", (950, 286), 21),
    ]:
        n = BY_ID["aug_patrol_" + key]
        assert n.portrait == portrait and n.position == position
        a = assets[n.map_asset]
        assert a["hex_width"] == a["hex_height"] == 64
        assert a["world_size"] == [32, 32] and a["anchor_px"] == [32, 64]
        assert a["colkey"] == 0 and a["flip_policy"] == "none"
        rows = [(root / f["path"]).read_text().splitlines() for f in a["frames"]]
        assert len(set(tuple(r) for r in rows)) == 3
        assert rows[0][cut:] == rows[1][cut:] == rows[2][cut:]
        assert rows[1] != [r[::-1] for r in rows[2]]
    cases = json.loads((root.parent / "data/office_cases.json").read_text())
    visitor = next(c["visitor"] for c in cases["cases"] if c["case_id"] == "OFF-PROT-003")
    assert visitor["name"] == "ラメル"
    assert visitor["portrait_id"] == "nervous_elf_woodsman"


def test_entrance_npcs_preserve_identity_size_and_fixed_idle_body():
    import json
    from pathlib import Path

    from drift_with_me.august_patrol import BY_ID

    root = Path(__file__).parents[1] / "src/drift_with_me/assets"
    assets = {
        a["id"]: a for a in json.loads((root / "jack_sprite.json").read_text())["source_assets"]
    }
    for key, portrait, position, cut in [
        ("mina", "succubus_green", (108, 124), 23),
        ("grow", "tired_gray_oldman", (202, 256), 26),
    ]:
        n = BY_ID["aug_patrol_" + key]
        assert n.portrait == portrait and n.position == position
        a = assets[n.map_asset]
        assert a["hex_width"] == a["hex_height"] == 64
        assert a["world_size"] == [32, 32] and a["anchor_px"] == [32, 64]
        assert a["colkey"] == 0 and a["flip_policy"] == "none"
        rows = [(root / f["path"]).read_text().splitlines() for f in a["frames"]]
        assert len(set(tuple(r) for r in rows)) == 3
        assert rows[0][cut:] == rows[1][cut:] == rows[2][cut:]
        assert rows[1] != [r[::-1] for r in rows[2]]
    cases = json.loads((root.parent / "data/office_cases.json").read_text())["cases"]
    visitors = {c["visitor"]["name"]: c["visitor"]["portrait_id"] for c in cases}
    assert visitors["ミナ"] == "succubus_green"
    assert visitors["グロウ"] == "tired_gray_oldman"


def test_walkway_npcs_preserve_identity_size_and_fixed_idle_body():
    import json
    from pathlib import Path

    from drift_with_me.august_patrol import BY_ID

    root = Path(__file__).parents[1] / "src/drift_with_me/assets"
    assets = {
        a["id"]: a for a in json.loads((root / "jack_sprite.json").read_text())["source_assets"]
    }
    for key, portrait, position, cut in [
        ("takanashi", "takanashi_matte", (274, 342), 23),
        ("yoake", "yoake_matte", (286, 454), 22),
    ]:
        n = BY_ID["aug_patrol_" + key]
        assert n.portrait == portrait and n.position == position
        a = assets[n.map_asset]
        assert a["hex_width"] == a["hex_height"] == 64
        assert a["world_size"] == [32, 32] and a["anchor_px"] == [32, 64]
        assert a["colkey"] == 0 and a["flip_policy"] == "none"
        rows = [(root / f["path"]).read_text().splitlines() for f in a["frames"]]
        assert len(set(tuple(r) for r in rows)) == 3
        assert rows[0][cut:] == rows[1][cut:] == rows[2][cut:]
        assert rows[1] != [r[::-1] for r in rows[2]]
    registrations = json.loads((root.parent / "data/office_characters.json").read_text())
    people = {c["id"]: c for c in registrations["characters"]}
    assert people["takanashi"]["portrait_id"] == "takanashi_matte"
    assert people["yoake"]["portrait_id"] == "yoake_matte"


def test_maintenance_npcs_preserve_identity_size_and_fixed_idle_body():
    import json
    from pathlib import Path

    from drift_with_me.august_patrol import BY_ID

    root = Path(__file__).parents[1] / "src/drift_with_me/assets"
    assets = {
        a["id"]: a for a in json.loads((root / "jack_sprite.json").read_text())["source_assets"]
    }
    for key, portrait, position, cut in [
        ("sagan", "sagan_matte", (394, 450), 22),
        ("ura", "ura_matte", (904, 144), 23),
    ]:
        n = BY_ID["aug_patrol_" + key]
        assert n.portrait == portrait and n.position == position
        a = assets[n.map_asset]
        assert a["hex_width"] == a["hex_height"] == 64
        assert a["world_size"] == [32, 32] and a["anchor_px"] == [32, 64]
        assert a["colkey"] == 0 and a["flip_policy"] == "none"
        rows = [(root / f["path"]).read_text().splitlines() for f in a["frames"]]
        assert len(set(tuple(r) for r in rows)) == 3
        assert rows[0][cut:] == rows[1][cut:] == rows[2][cut:]
        assert rows[1] != [r[::-1] for r in rows[2]]
    registrations = json.loads((root.parent / "data/office_characters.json").read_text())
    people = {c["id"]: c for c in registrations["characters"]}
    assert people["sagan"]["portrait_id"] == "sagan_matte"
    assert people["ura"]["portrait_id"] == "ura_matte"


def test_w4_fuji_preserves_size_pose_and_other_scene_assets():
    import json
    from pathlib import Path

    from drift_with_me.august_patrol import BY_ID

    root = Path(__file__).parents[1] / "src/drift_with_me/assets"
    assets = {
        a["id"]: a for a in json.loads((root / "jack_sprite.json").read_text())["source_assets"]
    }
    for key, portrait, position, cut in [
        ("fuji", "fuji_map_knees", (214, 362), 22),
    ]:
        n = BY_ID["aug_patrol_" + key]
        assert n.portrait == portrait and n.position == position
        a = assets[n.map_asset]
        assert a["hex_width"] == a["hex_height"] == 64
        assert a["world_size"] == [32, 32] and a["anchor_px"] == [32, 64]
        assert a["colkey"] == 0 and a["flip_policy"] == "none"
        rows = [(root / f["path"]).read_text().splitlines() for f in a["frames"]]
        assert len(set(tuple(r) for r in rows)) == 3
        assert rows[0][cut:] == rows[1][cut:] == rows[2][cut:]
        assert rows[1] != [r[::-1] for r in rows[2]]
    assert assets["jun_w4_fuji"]["hex_width"] == 32
    assert assets["jun_w4_fuji"]["frames"][0]["path"] == "Fuji_32_normal.hex"
    assert assets["fuji_map_knees"]["hex_height"] == 216


def test_w4_researchers_preserve_size_pose_and_july_assets():
    import json
    from pathlib import Path

    from drift_with_me.august_patrol import BY_ID

    root = Path(__file__).parents[1] / "src/drift_with_me/assets"
    assets = {
        a["id"]: a for a in json.loads((root / "jack_sprite.json").read_text())["source_assets"]
    }
    for key, portrait, position, cut in [
        ("yumesaki", "yumesaki_map_knees", (80, 636), 22),
        ("miyano", "miyano_map_knees", (104, 614), 22),
    ]:
        n = BY_ID["aug_patrol_" + key]
        assert n.portrait == portrait and n.position == position
        a = assets[n.map_asset]
        assert a["hex_width"] == a["hex_height"] == 64
        assert a["world_size"] == [32, 32] and a["anchor_px"] == [32, 64]
        assert a["colkey"] == 0 and a["flip_policy"] == "none"
        rows = [(root / f["path"]).read_text().splitlines() for f in a["frames"]]
        assert len(set(tuple(r) for r in rows)) == 3
        assert rows[0][cut:] == rows[1][cut:] == rows[2][cut:]
        assert rows[1] != [r[::-1] for r in rows[2]]
    assert assets["jul_w1_yumesaki_map"]["hex_width"] == 32
    assert assets["jul_w1_miyano_map"]["hex_width"] == 32
    assert assets["yumesaki_map_knees"]["hex_height"] == 216
    assert assets["miyano_map_knees"]["hex_height"] == 216
