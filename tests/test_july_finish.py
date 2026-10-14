"""Finishing text, one-time gift checkpoints and optional map-asset integration."""

from types import SimpleNamespace

import pytest

from drift_with_me.july_week1 import (
    FUJI_ID,
    PROFESSOR_ID,
    RESEARCHER_MAP_SPRITES,
    STUDENT_ID,
    WATER_ID,
    install_july_world,
)
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek
from test_july_story import july_app
from test_week4 import read


@pytest.mark.parametrize("target", [FUJI_ID, WATER_ID])
def test_mid_confirmation_resume_keeps_cursor_and_marks_only_at_end(target):
    app = july_app()
    events = []
    obj = app.world.object_by_id(target)
    app.model.start_interaction(events, "inspect", obj, "確認", ("確認",), 0)
    app.process_events(events)
    assert app.field_conversation.index == 0
    app.advance_field_conversation()
    assert app.office.july_progress.positions[target] == 1
    _, offices, *_ = decode(encode(snapshot(app)))
    app.office = offices[WorkWeek(7, 1)]
    app.model.interaction = None
    app.field_conversation = None
    events = []
    app.model.start_interaction(events, "inspect", obj, "確認", ("確認",), 0)
    app.process_events(events)
    assert app.field_conversation.index == 1
    assert not (
        app.office.july_progress.materials_checked
        if target == FUJI_ID
        else app.office.july_progress.water_checked
    )
    while app.field_conversation:
        app.advance_field_conversation()
    assert (
        app.office.july_progress.materials_checked
        if target == FUJI_ID
        else app.office.july_progress.water_checked
    )
    if target == FUJI_ID:
        assert app.office.july_progress.souvenir_received
        assert not any(
            "持っていって" in text for _, text in app.office.july_progress.lines_for(target)
        )


def test_gift_text_is_not_offered_again_after_receipt_even_with_old_partial_flags():
    app = july_app()
    progress = app.office.july_progress
    assert len(progress.lines_for(FUJI_ID)) == 4
    assert "鉢" in progress.lines_for(FUJI_ID)[2][1] and "お礼" in progress.lines_for(FUJI_ID)[2][1]
    progress.souvenir_received = True
    assert not progress.materials_checked
    assert not any("持っていって" in text for _, text in progress.lines_for(FUJI_ID))
    read(app, FUJI_ID)
    saved = encode(snapshot(app))
    for _ in range(3):
        read(app, FUJI_ID)
    assert encode(snapshot(app)) == saved
    assert progress.souvenir_received and progress.materials_checked


@pytest.mark.parametrize("provided", [(), (PROFESSOR_ID,), (PROFESSOR_ID, STUDENT_ID)])
def test_registered_map_sprites_replace_only_their_own_placeholder(provided):
    app = july_app()
    progress = app.office.july_progress
    progress.researchers_arrived = True
    ids = {RESEARCHER_MAP_SPRITES[target] for target in provided}
    asset = SimpleNamespace(
        definition=SimpleNamespace(
            hex_width=32,
            hex_height=32,
            anchor_px=(16, 32),
            world_size=(32, 32),
            colkey=0,
            projection_mode="upright_height_billboard_v1",
        )
    )
    app.sprite_assets = SimpleNamespace(
        enabled=True, get=lambda ident: asset if ident in ids else None
    )
    install_july_world(app)
    for target in (PROFESSOR_ID, STUDENT_ID):
        obj = app.world.object_by_id(target)
        assert (obj.sprite_world_width, obj.sprite_world_height) == (32, 32)
        assert not obj.solid
        assert obj.kind == ("sprite_prop" if target in provided else "july_placeholder")
        if target in provided:
            assert obj.visual == RESEARCHER_MAP_SPRITES[target]
            assert app.model.config["assets"][obj.visual + "_asset"] == obj.visual
    assert app.world.object_by_id(FUJI_ID).visual == "jun_w4_fuji"


def test_real_supplied_map_assets_preserve_alpha_and_fuji_placement_contract():
    import hashlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    reports = json.loads((root / "docs/researcher_map_sprites/conversion_report.json").read_text())
    manifest = json.loads((root / "src/drift_with_me/assets/jack_sprite.json").read_text())
    assets = {a["id"]: a for a in manifest["source_assets"]}
    fuji = assets["jun_w4_fuji"]
    for report in reports:
        asset = assets[report["asset_id"]]
        for key in (
            "hex_width",
            "hex_height",
            "anchor_px",
            "world_size",
            "colkey",
            "projection_mode",
        ):
            assert asset[key] == fuji[key]
        text = (root / "src/drift_with_me/assets" / report["frame_file"]).read_text()
        pixels = bytes(int(c, 16) for c in "".join(text.split()))
        assert len(pixels) == 1024 and set(pixels) <= set(range(16))
        assert hashlib.sha256(pixels).hexdigest() == asset["source_hash"]
        assert (
            hashlib.sha256(bytes(int(c != 0) for c in pixels)).hexdigest()
            == report["alpha_mask_sha256"]
        )
        assert sum(c != 0 for c in pixels) == report["source"]["alpha_counts"]["255"]
