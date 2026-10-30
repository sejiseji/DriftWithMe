"""Synthetic worlds and storage: never opens a user's save."""

from collections import deque
from copy import deepcopy

import pytest

from drift_with_me.app import AppScreen
from drift_with_me.collectibles import BY_ID, CATALOG, PREFIX, owned_collectibles
from drift_with_me.collection_room import layer_position, room_config, visible_layers
from drift_with_me.save_state import ProgressStore, decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek
from test_field_visit import inspect
from test_save_state import Storage, payload
from test_week_debug_safety import debug_app


def week_app(item):
    storage = Storage()
    app = debug_app(storage)
    assert app.jump_to_debug_week(WorkWeek(*item.week))
    app.screen = AppScreen.PLAY
    return app, storage


def test_catalog_distributes_nine_pickups_and_three_existing_or_dialogue_gifts():
    assert len(BY_ID) == 12
    assert {x.week for x in CATALOG} == {(m, w) for m in (6, 7, 8) for w in range(1, 5)}
    assert sum(x.position is not None for x in CATALOG) == 9
    assert {x.id for x in CATALOG if not x.position} == {"fuji_pot", "sunglasses", "crayon_drawing"}


@pytest.mark.parametrize("item", [x for x in CATALOG if x.position], ids=lambda x: x.id)
def test_every_week_pickup_can_be_reached_acquired_and_resumed_without_normal_writes(item):
    app, storage = week_app(item)
    before = deepcopy(storage.items)
    obj = app.world.object_by_id(PREFIX + item.id)
    assert obj.visual == "collection_sparkle" and not obj.solid
    hx, hz = app.model.player_solid_half_x, app.model.player_solid_half_z
    start = (round(app.model.player.x / 8) * 8, round(app.model.player.z / 8) * 8)
    queue, seen, reached = deque([start]), {start}, False
    while queue:
        x, z = queue.popleft()
        tx, tz = item.position
        if (tx - x) ** 2 + (tz - z) ** 2 <= 24**2:
            reached = True
            break
        for dx, dz in ((8, 0), (-8, 0), (0, 8), (0, -8)):
            nxt = x + dx, z + dz
            if nxt not in seen and not app.world.collides_player(*nxt, hx, hz):
                seen.add(nxt)
                queue.append(nxt)
    assert reached, item.location
    assert not app.claim_collectible(item.id)  # No remote acquisition.
    inspect(app, PREFIX + item.id)
    assert app.field_conversation.lines[0][1] == item.name
    app.advance_field_conversation()
    app.advance_field_conversation()
    assert item.id in owned_collectibles(app)
    assert not any(x.id == PREFIX + item.id for x in app.world.objects)
    assert not app.claim_collectible(item.id)
    assert item.id in app.progress_store.load()[2].collectibles
    app.return_from_week_debug()
    assert storage.items == before


def test_failed_save_and_cancel_do_not_grant_or_remove_sparkle():
    item = BY_ID["herb_fine"]
    app, _ = week_app(item)
    inspect(app, PREFIX + item.id)
    app.process_events(app.model.cancel_interaction())
    assert item.id not in owned_collectibles(app)
    inspect(app, PREFIX + item.id)
    app.progress_store.write = lambda _: False
    assert not app.claim_collectible(item.id)
    assert item.id not in owned_collectibles(app)
    assert app.world.object_by_id(PREFIX + item.id)


def test_debug_second_guard_and_wrong_week_protect_normal_store():
    app, storage = week_app(BY_ID["herb_fine"])
    inspect(app, PREFIX + "herb_fine")
    app.progress_store = app.normal_progress_store
    app.progress_store.write = lambda _: pytest.fail("persistent write")
    assert not app.claim_collectible("herb_fine")
    assert not app.claim_collectible("herb_round")
    assert not app.claim_collectible("fuji_pot", source="gift")
    assert storage.items == {}


def test_old_save_and_standard_autosave_roundtrip_collectibles(tmp_path):
    app, p = payload()
    assert decode(encode(p))[2].collectibles == set()
    app.east_site_progress.collectibles = {"herb_fine", "stone_marble"}
    p = snapshot(app)
    store = ProgressStore(path=tmp_path / "synthetic.json")
    assert store.write(p)
    assert store.load()[2].collectibles == {"herb_fine", "stone_marble"}
    for invalid in (["fake"], ["herb_fine", "herb_fine"], True):
        q = deepcopy(p)
        q["collectibles"] = invalid
        with pytest.raises(ValueError):
            decode(encode(q))


def test_existing_gifts_are_derived_without_new_reward_or_map_objects():
    app, _ = week_app(BY_ID["fuji_pot"])
    app.office.july_progress.souvenir_received = True
    assert "fuji_pot" in owned_collectibles(app)
    assert "fuji_pot" in decode(encode(snapshot(app)), debug_entry=app.work_week)[2].collectibles
    app, _ = week_app(BY_ID["sunglasses"])
    app.office.week3_progress.rewards.sunglasses_received = True
    assert "sunglasses" in owned_collectibles(app)
    assert not any(x.id.startswith(PREFIX) for x in app.world.objects)


def test_room_ownership_conditions_all_subsets_and_sleepers():
    ids = list(BY_ID)
    for mask in range(1 << 12):
        owned = {x for n, x in enumerate(ids) if mask & (1 << n)}
        names = {x["name"] for x in visible_layers(owned)}
        assert ("sleep_jack" in names) == (len(owned) == 12)
        assert ("sleep_fuse" in names) == (len(owned) == 12)
        assert ("stone_dish" in names) == bool(
            owned & {"stone_marble", "stone_lavender", "stone_honey"}
        )
        assert ("window_tray" in names) == bool(owned & {"pinecone", "winged_seed"})
        for x in ("herb_fine", "herb_round", "herb_flower", "crayon_drawing", "driftwood"):
            assert (x in names) == (x in owned)
        assert not names & {"photo_a", "photo_b", "framed_picture"}
    for layer in room_config()["layers"]:
        assert abs(layer_position(layer, 0)[1] - layer_position(layer, 72)[1]) <= 1


def test_room_only_after_final_report_and_close_has_no_save_effect():
    app, storage = week_app(BY_ID["crayon_drawing"])
    assert not app.open_collection_room()
    app.office.august_progress.phase = "done"
    before = snapshot(app)
    assert app.open_collection_room()
    app.key_pressed = lambda *keys: True
    app.update_collection_room()
    assert app.screen == AppScreen.OFFICE
    assert snapshot(app) == before and storage.items == {}


def test_children_gift_requires_completed_conversation_and_saves_once():
    from test_august_patrol import dispatch, patrol_app

    app, storage = patrol_app()
    dispatch(app)
    assert app.begin_patrol_target("aug_patrol_morris")
    app.travel_input_held = lambda: False
    app.mouse_pressed_in = lambda *_: False
    app.key_pressed = lambda *_: False
    app.update_patrol(0)
    app.key_pressed = lambda *keys: "KEY_ESCAPE" in keys
    app.update_patrol(0)
    assert "crayon_drawing" not in owned_collectibles(app)
    assert app.begin_patrol_target("aug_patrol_ruby")
    for index in range(4):
        app.key_pressed = lambda *_: False
        app.update_patrol(0)
        assert app.patrol_dialogue.index == index
        assert "crayon_drawing" not in owned_collectibles(app)
        app.key_pressed = lambda *keys: "KEY_RETURN" in keys
        app.update_patrol(0)
    assert app.patrol_dialogue is None
    assert "crayon_drawing" in owned_collectibles(app)
    assert "crayon_drawing" in app.progress_store.load()[2].collectibles
    assert app.begin_patrol_target("aug_patrol_morris")
    assert len(app.patrol_dialogue.lines) == 1


def test_normal_pickup_writes_regular_slot_and_leaves_other_storage_untouched():
    app, _ = week_app(BY_ID["herb_fine"])
    storage = Storage()
    storage.items["flowerbed-layout"] = "real layout stand-in"
    app.week_debug_active = False
    app.progress_store = ProgressStore(browser_storage=storage)
    inspect(app, PREFIX + "herb_fine")
    app.advance_field_conversation()
    app.advance_field_conversation()
    assert app.progress_store.load()[2].collectibles == {"herb_fine"}
    assert storage.items["flowerbed-layout"] == "real layout stand-in"


def test_runtime_room_uses_indexed_cache_and_viewport_clip(monkeypatch):
    import sys
    from types import SimpleNamespace

    from drift_with_me.collection_room import draw_room, image_for

    calls = []

    class FakeImage:
        def __init__(self, w, h):
            self.size = (w, h)

        def set(self, x, y, rows):
            assert len(rows) == self.size[1]
            assert all(len(row) == self.size[0] for row in rows)
            assert all(int(c, 16) < 16 for row in rows for c in row)

    fake = SimpleNamespace(
        width=512,
        height=236,
        Image=FakeImage,
        cls=lambda *a: None,
        clip=lambda *a: calls.append(a),
        blt=lambda *a, **kw: None,
        text=lambda *a: None,
    )
    image_for.cache_clear()
    monkeypatch.setitem(sys.modules, "pyxel", fake)
    draw_room(SimpleNamespace(presentation_time=0), set(BY_ID))
    assert calls == [(46, 0, 420, 236), ()]
    first = image_for.cache_info().misses
    draw_room(SimpleNamespace(presentation_time=0), set(BY_ID))
    assert image_for.cache_info().misses == first
    image_for.cache_clear()


def test_room_does_not_intercept_hidden_debug_badge_or_advance_world():
    from types import SimpleNamespace

    app, _ = week_app(BY_ID["crayon_drawing"])
    app.office.august_progress.phase = "done"
    assert app.open_collection_room()
    app.lifecycle_update_blocked = lambda: False
    app.consume_elapsed = lambda: 0.02
    app.presentation_time = 0
    app.frame = 0
    app.read_pointer_snapshot = lambda: SimpleNamespace(down=False)
    app.update_week_debug = lambda: pytest.fail("hidden debug badge handled room input")
    app.key_pressed = lambda *_: False
    app.mouse_pressed_in = lambda *_: False
    tick = app.model.world_tick
    app.update()
    assert app.screen == AppScreen.COLLECTION_ROOM and app.model.world_tick == tick


def test_room_dishes_stay_central_separate_and_above_table():
    layers = {layer["name"]: layer for layer in room_config()["layers"]}
    tray, stones = layers["window_tray"], layers["stone_dish"]
    assert tray["xy"] == [166, 112] and stones["xy"] == [228, 128]
    assert tray["xy"][0] + tray["size"][0] < stones["xy"][0]
    assert tray["z"] > layers["table"]["z"]
    assert stones["z"] > layers["table"]["z"]
    assert [layers[x]["xy"] for x in ("herb_fine", "herb_round", "herb_flower")] == [
        [293, 142],
        [298, 142],
        [302, 142],
    ]


def test_curtain_has_four_second_repeat_and_delayed_hem_only():
    from drift_with_me.curtain_motion import curtain_strips

    config = room_config()
    assert config["period_frames"] == 96 and config["fps"] == 24
    for frame in range(96):
        strips = curtain_strips(frame, config)
        assert strips == curtain_strips(frame + 96, config)
        assert strips[0] == ("curtain_0", 0, 60)
        assert [(row, height) for _, row, height in strips[1:]] == [
            (row, 5) for row in range(60, 90, 5)
        ]
    strips = curtain_strips(10, config)
    assert strips[1][0] == "curtain_1" and strips[-1][0] == "curtain_0"


def test_sleepers_are_eighty_five_percent_of_large_size_and_within_room_bounds():
    layers = {layer["name"]: layer for layer in room_config()["layers"]}
    for name, original, expected_position in (
        ("sleep_jack", (144, 93), [15, 152]),
        ("sleep_fuse", (72, 78), [159, 149]),
    ):
        layer = layers[name]
        assert layer["size"] == [round(original[0] * 0.85), round(original[1] * 0.85)]
        assert layer["xy"] == expected_position
        x, y = layer["xy"]
        w, h = layer["size"]
        assert x > 0 and x + w < 420 and y > 0 and y + h + 1 < 236
        assert layer["all_items"] and len(layer["requires"]) == 12
    assert layers["sleep_fuse"]["xy"][1] + 66 < layers["sleep_jack"]["xy"][1] + 79 - 8


@pytest.mark.parametrize(
    ("ident", "name"),
    [
        ("herb_fine", "ローズマリー"),
        ("herb_round", "スペアミント"),
        ("herb_flower", "マリーゴールド"),
    ],
)
def test_legacy_plant_id_resumes_and_pickup_dialogue_needs_no_other_plant(ident, name):
    item = BY_ID[ident]
    app, normal = week_app(item)
    before = deepcopy(normal.items)
    inspect(app, PREFIX + ident)
    assert app.field_conversation.lines[0] == ("ジャック", name)
    description = app.field_conversation.lines[1][1]
    assert not any(
        BY_ID[x].name in description
        for x in ("herb_fine", "herb_round", "herb_flower")
        if x != ident
    )
    app.advance_field_conversation()
    app.advance_field_conversation()
    assert owned_collectibles(app) == {ident}
    restored = decode(encode(snapshot(app)), debug_entry=app.work_week)
    assert restored[2].collectibles == {ident}
    assert normal.items == before
    # Existing ordinary records store IDs, never the old display labels.
    _, data = payload()
    data["collectibles"] = [ident]
    assert decode(encode(data))[2].collectibles == {ident}


def test_real_plant_room_layers_keep_existing_anchors_and_tagetes_identity():
    layers = {layer["name"]: layer for layer in room_config()["layers"]}
    for ident, xy in [
        ("herb_fine", [293, 142]),
        ("herb_round", [298, 142]),
        ("herb_flower", [302, 142]),
    ]:
        layer = layers[ident]
        assert layer["size"] == [19, 31] and layer["xy"] == xy
        assert layer["requires"] == [ident]
        assert layer["display_group"] == "夏に集めた草花の乾燥束"
    assert layers["herb_flower"]["botanical_taxon"].startswith("Tagetes")
