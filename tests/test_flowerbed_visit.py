import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.flowerbed import BED_ID, FLOWER_IDS, FlowerbedLayoutStore
from drift_with_me.flowerbed_visit import REQUEST, THANKS, FlowerbedVisit
from drift_with_me.save_state import SAVE_KEY, decode, encode, snapshot
from test_flowerbed import garden_app
from test_save_state import payload


def finish_dialogue(app):
    while app.flowerbed_dialogue is not None:
        assert app.advance_flowerbed_visit()


def test_request_edit_cancel_retry_confirm_and_repeat_are_monotonic():
    app, storage = garden_app()
    storage.items[SAVE_KEY] = "normal untouched"
    storage.items[SAVE_KEY + ".backup"] = "backup untouched"
    app.start_flowerbed_visit()
    assert app.flowerbed_dialogue.lines == REQUEST
    assert not app.flowerbed_visit_state().sighting_recorded
    finish_dialogue(app)
    assert app.flowerbed_visit_state().stage == "plant"
    assert app.flowerbed_visit_state().sighting_recorded
    assert app.flowerbed_editor is not None
    app.flowerbed_editor.choose(FLOWER_IDS[0])
    app.close_flowerbed_editor()
    assert app.flowerbed_visit_state().stage == "plant"
    app.start_flowerbed_visit()
    assert len(app.flowerbed_dialogue.lines) == 2  # full sighting discussion does not repeat
    finish_dialogue(app)
    for ident in FLOWER_IDS:
        app.flowerbed_editor.choose(ident)
    assert app.confirm_flowerbed()
    assert app.flowerbed_visit_state().stage == "thanks"
    assert app.flowerbed_dialogue.lines == THANKS
    assert app.model.flowerbed_draft is None and app.model.flowerbed_order == FLOWER_IDS
    finish_dialogue(app)
    assert app.flowerbed_visit_state().complete
    app.start_flowerbed_visit()
    finish_dialogue(app)
    assert app.flowerbed_visit_state().complete
    assert storage.items[SAVE_KEY] == "normal untouched"
    assert storage.items[SAVE_KEY + ".backup"] == "backup untouched"
    app.start_flowerbed_visit(BED_ID)
    assert app.flowerbed_editor is not None  # completed garden still editable
    app.close_flowerbed_editor()
    assert app.flowerbed_visit_state().complete


def test_mid_request_and_pending_completion_reload_exact_cursor():
    app, _ = garden_app()
    app.start_flowerbed_visit()
    app.advance_flowerbed_visit()
    app.advance_flowerbed_visit()
    saved = decode(encode(snapshot(app)))
    app.saved_progress = saved
    app.start_game()
    assert app.flowerbed_dialogue.index == 2
    assert not app.flowerbed_visit_state().sighting_recorded
    finish_dialogue(app)
    for ident in reversed(FLOWER_IDS):
        app.flowerbed_editor.choose(ident)
    assert app.confirm_flowerbed()
    app.advance_flowerbed_visit()
    assert app.flowerbed_visit_state() == FlowerbedVisit("thanks", 1)
    app.saved_progress = decode(encode(snapshot(app)))
    app.start_game()
    assert app.flowerbed_dialogue.index == 1 and app.model.flowerbed_draft is None
    finish_dialogue(app)
    assert app.flowerbed_visit_state().complete
    assert app.east_site_progress.flowerbed_order == tuple(reversed(FLOWER_IDS))


def test_layout_only_v1_record_migrates_without_marking_new_request_complete():
    app, storage = garden_app()
    storage = app.flowerbed_layout_store.backend.browser
    storage.items[FlowerbedLayoutStore.key] = json.dumps({"version": 1, "order": FLOWER_IDS})
    order, visit = app.flowerbed_layout_store.load_state()
    assert order == FLOWER_IDS and visit == FlowerbedVisit()
    assert app.flowerbed_layout_store.write_state(order, FlowerbedVisit("plant"))
    assert json.loads(storage.items[FlowerbedLayoutStore.key])["version"] == 2
    assert app.flowerbed_layout_store.load_state() == (FLOWER_IDS, FlowerbedVisit("plant"))


def test_save_failure_does_not_advance_dialogue_or_confirm_arrangement():
    app, _ = garden_app()
    app.start_flowerbed_visit()
    app.flowerbed_layout_store = SimpleNamespace(write_state=lambda *args: False)
    assert not app.advance_flowerbed_visit()
    assert app.flowerbed_dialogue.index == 0 and app.flowerbed_dialogue.error
    assert app.flowerbed_visit_state() == FlowerbedVisit()
    app.flowerbed_dialogue = None
    app.east_site_progress.flowerbed_visit = FlowerbedVisit("plant").snapshot()
    app.flowerbed_visit_editing = True
    app.start_flowerbed_editor()
    for ident in FLOWER_IDS:
        app.flowerbed_editor.choose(ident)
    assert not app.confirm_flowerbed()
    assert app.flowerbed_editor.error and app.flowerbed_visit_state().stage == "plant"
    assert app.east_site_progress.flowerbed_order == () and app.model.flowerbed_order == ()


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {"stage": "thanks", "index": True},
        {"stage": "thanks", "index": 2},
        {"stage": "complete", "index": 1},
        {"stage": "unknown", "index": 0},
        {"stage": "plant", "index": -1},
    ],
)
def test_invalid_flow_state_rejected(raw):
    with pytest.raises(ValueError):
        FlowerbedVisit.restore(raw)


def test_old_progress_loads_and_impossible_completed_garden_is_rejected():
    _, old = payload()
    assert decode(encode(old))[2].flowerbed_visit == {}
    bad = deepcopy(old)
    bad["flowerbed_visit"] = FlowerbedVisit("complete").snapshot()
    with pytest.raises(ValueError):
        decode(encode(bad))
