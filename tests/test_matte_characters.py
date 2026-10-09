from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.app import OFFICE_STATIC_PORTRAIT_IDS
from drift_with_me.office import CaseState
from drift_with_me.save_state import decode, encode, snapshot
from drift_with_me.week_cycle import WorkWeek, load_week_office
from test_document_reading import make_app
from test_office_supervisor import app_for, finish
from test_week2_loop import hero_app


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
@pytest.mark.parametrize("portrait", sorted(OFFICE_STATIC_PORTRAIT_IDS))
def test_static_portrait_footprint_and_no_blink_contamination(profile, portrait):
    app = app_for(load_week_office(WorkWeek(6, 2)), profile)
    calls, requests = [], []

    def asset(key):
        requests.append(key)
        frame = SimpleNamespace(width=116, height=116, image=key, u=0, v=0)
        return SimpleNamespace(frame=lambda: frame, definition=SimpleNamespace(colkey=8))

    app.sprite_assets = SimpleNamespace(get=asset)
    app.pyxel = SimpleNamespace(
        rect=lambda *a: None,
        rectb=lambda *a: None,
        blt=lambda *a, **kw: calls.append((a, kw)),
    )
    rect = app.office_visitor_portrait_rect()
    for smile in (False, True):
        for tick in (0, 170, 999):
            app.frame = tick
            app.draw_office_portrait(rect, portrait, smile=smile)
    assert requests == [portrait] * 6 and len(calls) == 6
    assert all(c == calls[0] for c in calls)
    args, kw = calls[0]
    scale = kw["scale"]
    left, top = args[0] + 58 * (1 - scale), args[1] + 58 * (1 - scale)
    assert rect.x - 0.51 <= left and left + 116 * scale <= rect.x + rect.width + 0.51
    assert rect.y - 0.51 <= top and top + 116 * scale <= rect.y + rect.height + 0.51


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_receipt_reading_contact_handover_and_consultation_resume(profile):
    app, _ = make_app(profile)
    app.office = load_week_office(WorkWeek(6, 2))
    app.office.current_index = 1
    app.office.begin_current_case()
    assert app.office.current_case.visitor.name == "タカナシ"
    app.office.advance_dialogue_step()
    app.office_dialogue_playback = None
    page = app.office_dialogue_current_page(app.sync_office_dialogue_playback())
    assert app.office_document_reading_active(page)
    session = deepcopy(app.office.current_session)
    playback = deepcopy(app.current_office_dialogue_playback())
    # W2 has no authored supervisor advice; an unavailable consultation must
    # leave the active reading page intact.
    assert not app.begin_office_consultation()
    assert app.office.current_session == session
    assert app.current_office_dialogue_playback() == playback
    finish(app.office)
    assert app.office.ask_question("receipt")
    assert app.office.active_dialogue_lines()[0].visual_action == "internal_contact"
    finish(app.office)
    assert app.office.classify(app.office.current_case.expected_classification)
    finish(app.office)
    assert app.office.current_session.state == CaseState.CLOSED_COUNTER
    assert "お預かりしていた納税証明書" in "".join(
        line.text for line in app.office.current_session.dialogue
    )


def test_save_load_keeps_roles_and_completed_receipt():
    app = hero_app()
    app.week_office_history = {WorkWeek(6, 2): app.office}
    app.first_sight_seen = set()
    week, offices, *_ = decode(encode(snapshot(app)))
    office = offices[week]
    assert office.cases[1].visitor.name == "タカナシ"
    assert office.cases[3].visitor.name == "サガン"
    assert office.sessions["OFF-JUN-W2-RECEIPT"].state == CaseState.RESOLVED
    assert office.cases[3].visitor.portrait_id == "sagan_matte"
