from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from drift_with_me.app import (
    OFFICE_DIALOGUE_CHARS_PER_SEC,
    AppScreen,
    DriftWithMeApp,
)
from drift_with_me.config import load_runtime_config
from drift_with_me.events import GameEvent
from drift_with_me.input import Rect
from drift_with_me.model import GameModel
from drift_with_me.office import (
    CLASSIFICATION_ORDER,
    CaseState,
    Classification,
    FieldResult,
    OfficePrototype,
)
from drift_with_me.world import load_world_data

ROOT = Path(__file__).resolve().parents[1]
OFFICE_PORTRAIT_HASHES = {
    "succubus_green": "813471a9c901d2b1c464e3cd871d4c50755539d32d753984ed6a756acf0ef014",
    "tired_gray_oldman": "226b90cf1fdc909641fbe45f13254769718acaee38a9f77a65416ad5a474564c",
    "nervous_elf_woodsman": "f0e7d85f511754ff8cb57d7f1501ee0983efd8b2b48f8218bbc6bb2854250bf6",
    "smug_blond_hero": "da1d755d1be399591a653b08c7893d37b7ad710fb632d0ef7912c8850e99f1b2",
}


def test_off001_case_definitions_cover_each_classification_once() -> None:
    office = OfficePrototype.load()

    assert [case.case_id for case in office.cases] == [
        "OFF-PROT-001",
        "OFF-PROT-002",
        "OFF-PROT-003",
        "OFF-PROT-004",
    ]
    assert {case.expected_classification for case in office.cases} == set(CLASSIFICATION_ORDER)
    assert [case.case_id for case in office.cases if case.field_task is not None] == [
        "OFF-PROT-003"
    ]


def test_off001_cases_bind_approved_portrait_ids_in_order() -> None:
    office = OfficePrototype.load()

    assert [case.visitor.portrait_id for case in office.cases] == list(OFFICE_PORTRAIT_HASHES)


def test_off001_portrait_sources_preserve_asset_contract() -> None:
    manifest_path = ROOT / "src/drift_with_me/assets/jack_sprite.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = {asset["id"]: asset for asset in manifest["source_assets"]}

    for asset_id, expected_hash in OFFICE_PORTRAIT_HASHES.items():
        asset = assets[asset_id]
        assert (asset["hex_width"], asset["hex_height"]) == (64, 64)
        assert asset["colkey"] == 8
        assert asset["source_hash"] == expected_hash
        assert asset["ui_role"] == "office_visitor_portrait"
        source_path = manifest_path.parent / asset["frames"][0]["path"]
        rows = source_path.read_text(encoding="ascii").splitlines()
        pixels = bytes(int(char, 16) for row in rows for char in row)
        assert len(rows) == 64
        assert all(len(row) == 64 for row in rows)
        assert hashlib.sha256(pixels).hexdigest() == expected_hash


def test_off001_portrait_draw_uses_asset_colkey_and_fits_panel() -> None:
    calls: list[tuple[tuple, dict]] = []

    class FakePyxel:
        @staticmethod
        def rect(*args) -> None:
            del args

        @staticmethod
        def rectb(*args) -> None:
            del args

        @staticmethod
        def blt(*args, **kwargs) -> None:
            calls.append((args, kwargs))

    frame = SimpleNamespace(image="portrait", u=0, v=0, width=64, height=64)
    asset = SimpleNamespace(
        frame=lambda: frame,
        definition=SimpleNamespace(colkey=8),
    )
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.pyxel = FakePyxel()
    app.sprite_assets = SimpleNamespace(
        get=lambda asset_id: asset if asset_id == "succubus_green" else None
    )

    app.draw_office_portrait(Rect(10, 20, 48, 48), "succubus_green")

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == (10, 20, "portrait", 0, 0, 64, 64)
    assert kwargs == {"colkey": 8, "scale": 0.75}


def test_off001_hearing_updates_dialogue_and_memo_once() -> None:
    office = OfficePrototype.load()
    case = office.current_case
    session = office.current_session
    assert case is not None
    assert session is not None

    assert office.ask_question("identity")
    assert not office.ask_question("identity")

    assert session.state == CaseState.READY_TO_CLASSIFY
    assert session.asked_question_ids == {"identity"}
    assert [fact.line for fact in session.memo_facts] == ["本人確認: 済"]
    assert [line.speaker for line in session.dialogue] == ["ミナ", "Jack", "ミナ"]


def test_off001_wrong_classification_returns_to_hearing_without_losing_facts() -> None:
    office = OfficePrototype.load()
    office.ask_question("identity")
    session = office.current_session
    assert session is not None

    assert not office.classify(Classification.FIELD_CHECK)

    assert session.state == CaseState.READY_TO_CLASSIFY
    assert session.feedback
    assert [fact.line for fact in session.memo_facts] == ["本人確認: 済"]
    assert office.current_index == 0


def test_off001_four_cases_follow_fixed_success_routes() -> None:
    office = OfficePrototype.load()
    expected_states = (
        CaseState.CLOSED_COUNTER,
        CaseState.WAITING_DOCUMENTS,
        CaseState.FIELD_CHECK_REQUIRED,
        CaseState.REFERRED,
    )

    for expected_state in expected_states:
        case = office.current_case
        session = office.current_session
        assert case is not None
        assert session is not None
        for question in case.questions:
            assert office.ask_question(question.question_id)
        assert office.classify(case.expected_classification)
        assert session.state == expected_state
        if expected_state == CaseState.FIELD_CHECK_REQUIRED:
            task = office.prepare_field_task()
            assert task is not None
            assert office.complete_field_task(
                FieldResult(
                    task_id=task.task_id,
                    case_id=task.case_id,
                    result_code="ANOMALOUS_URCHIN_FOUND",
                    discovered_fact_ids=("abnormal_urchin_present",),
                    report_lines=("異常個体1",),
                )
            )
            assert session.state == CaseState.FIELD_RETURNED
        assert office.advance_case()

    assert office.complete
    assert all(session.state == CaseState.RESOLVED for session in office.sessions.values())


def test_off001_field_bridge_preserves_ids_memo_and_result() -> None:
    office = OfficePrototype.load()
    office.current_index = 2
    office.begin_current_case()
    case = office.current_case
    session = office.current_session
    assert case is not None
    assert session is not None

    for question in case.questions:
        office.ask_question(question.question_id)
    assert office.classify(Classification.FIELD_CHECK)
    task = office.prepare_field_task()
    assert task is not None
    assert task.task_id == "FIELD-PROT-003"
    assert task.case_id == "OFF-PROT-003"
    assert task.location_id == "north_shallow"
    assert "場所: 北側浅瀬付近" in task.memo_lines

    result = FieldResult(
        task_id=task.task_id,
        case_id=task.case_id,
        result_code="ANOMALOUS_URCHIN_FOUND",
        discovered_fact_ids=("abnormal_urchin_present", "no_facility_damage"),
        report_lines=("通常個体3", "異常個体1", "設備被害なし"),
    )
    assert office.complete_field_task(result)
    assert session.field_result is result
    assert session.state == CaseState.FIELD_RETURNED


def test_off001_hearing_is_isolated_from_world_state() -> None:
    runtime = load_runtime_config("medium")
    world = load_world_data()
    model = GameModel(runtime.raw, world)
    office = OfficePrototype.load()
    before = (
        model.world_tick,
        model.player.x,
        model.player.z,
        model.buddy.x,
        model.buddy.z,
        model.water,
        model.energy,
        model.combat_session,
    )

    office.ask_question("identity")
    office.classify(Classification.COUNTER_COMPLETE)

    after = (
        model.world_tick,
        model.player.x,
        model.player.z,
        model.buddy.x,
        model.buddy.z,
        model.water,
        model.energy,
        model.combat_session,
    )
    assert after == before


def test_off001_office_layout_stays_inside_all_profiles() -> None:
    for profile in ("low", "medium", "high"):
        app = DriftWithMeApp.__new__(DriftWithMeApp)
        app.runtime = load_runtime_config(profile)
        screen = Rect(0, 0, app.runtime.screen_width, app.runtime.screen_height)
        rects = (
            app.office_header_rect(),
            app.office_visitor_rect(),
            app.office_dialog_rect(),
            app.office_questions_panel_rect(),
            app.office_memo_rect(),
            app.office_classification_panel_rect(),
            app.office_footer_rect(),
            app.office_footer_action_rect(),
        )
        assert all(
            rect.x >= screen.x
            and rect.y >= screen.y
            and rect.x + rect.width <= screen.width + 0.01
            and rect.y + rect.height <= screen.height + 0.01
            for rect in rects
        )


def test_off001_japanese_text_uses_largest_style_that_fits_each_profile() -> None:
    expected_question_styles = {profile: "office_japanese" for profile in ("low", "medium", "high")}
    for profile, expected_style in expected_question_styles.items():
        app = DriftWithMeApp.__new__(DriftWithMeApp)
        app.runtime = load_runtime_config(profile)
        font = app.runtime.raw["ui"]["font"]
        styles = ("office_japanese", "office_japanese_button")
        sizes = {style: int(font[f"{style}_px"][profile]) for style in styles}
        app.ui_text = SimpleNamespace(
            text_height=lambda style, sizes=sizes: sizes[style],
            visual_vertical_metrics=lambda style, sizes=sizes: (0, sizes[style]),
        )

        question_rect = app.office_question_rect(0, 5)
        assert app.office_text_style(question_rect) == expected_style
        _, visible_height = app.ui_text.visual_vertical_metrics(expected_style)
        assert visible_height + 2 <= int(question_rect.height)
        assert app.office_text_style(app.office_classification_rect(0)) == "office_japanese"

        task_rect = app.field_task_hud_rect()
        task_row = Rect(task_rect.x, task_rect.y, task_rect.width, (task_rect.height - 4) / 2)
        assert app.office_text_style(task_row) == "office_japanese"


def test_off001_office_text_centers_japanese_without_global_baseline_shift() -> None:
    draws: list[tuple[int, int, str, int, str]] = []

    class FakeRenderer:
        @staticmethod
        def text_height(style_name: str) -> int:
            return {"office_japanese": 12, "office_japanese_button": 12}[style_name]

        @staticmethod
        def text_width(text: str, style_name: str) -> int:
            del style_name
            return len(text) * 8

        @classmethod
        def visual_vertical_metrics(cls, style_name: str) -> tuple[int, int]:
            return (0, cls.text_height(style_name))

        @staticmethod
        def fit_text(text: str, max_width: int, style_name: str) -> str:
            del max_width, style_name
            return text

        @staticmethod
        def draw(pyxel, x: int, y: int, text: str, color: int, style_name: str) -> None:
            del pyxel
            draws.append((x, y, text, color, style_name))

    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.ui_text = FakeRenderer()
    app.pyxel = object()

    app.draw_office_text_in_rect(Rect(10, 20, 80, 24), "現在の案件", 7)

    assert draws == [(10, 26, "現在の案件", 7, "office_japanese")]


def make_office_dialogue_app() -> DriftWithMeApp:
    class FixedWidthRenderer:
        @staticmethod
        def text_width(text: str, style_name: str) -> int:
            del style_name
            return sum(6 if ord(char) < 128 else 12 for char in text)

    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config("medium")
    app.office = OfficePrototype.load()
    app.ui_text = FixedWidthRenderer()
    return app


def test_off001_dialogue_wraps_without_ellipsis_and_paginates_full_exchange() -> None:
    app = make_office_dialogue_app()
    assert app.office.ask_question("identity")

    playback = app.sync_office_dialogue_playback()
    session = app.office.current_session
    assert session is not None
    expected = "".join(f"{line.speaker}: {line.text}" for line in session.dialogue[-2:])
    visible = "".join(line for page in playback.pages for line in page)
    max_width = int(app.office_dialogue_content_rect().width)

    assert len(playback.pages) >= 2
    assert visible == expected
    assert all(
        app.ui_text.text_width(line, "office_japanese") <= max_width
        for page in playback.pages
        for line in page
    )


def test_off001_dialogue_typewriter_tap_completes_then_advances_page() -> None:
    app = make_office_dialogue_app()
    assert app.office.ask_question("identity")
    playback = app.sync_office_dialogue_playback()
    first_page = app.office_dialogue_current_page(playback)
    first_page_characters = sum(len(line) for line in first_page)

    app.update_office_dialogue_playback(1.0 / OFFICE_DIALOGUE_CHARS_PER_SEC)
    assert int(playback.revealed_chars) == 1

    assert app.advance_office_dialogue_page()
    assert playback.page_index == 0
    assert playback.revealed_chars == first_page_characters

    assert app.advance_office_dialogue_page()
    assert playback.page_index == 1
    assert playback.revealed_chars == 0.0


def test_off001_new_exchange_restarts_dialogue_reveal() -> None:
    app = make_office_dialogue_app()
    playback = app.sync_office_dialogue_playback()
    playback.revealed_chars = 999.0
    previous_signature = playback.signature

    assert app.office.ask_question("identity")
    playback = app.sync_office_dialogue_playback()

    assert playback.signature != previous_signature
    assert playback.page_index == 0
    assert playback.revealed_chars == 0.0


def test_off001_dialogue_tap_is_consumed_before_question_buttons() -> None:
    app = make_office_dialogue_app()
    playback = app.sync_office_dialogue_playback()
    page = app.office_dialogue_current_page(playback)
    page_characters = sum(len(line) for line in page)
    rect = app.office_dialog_rect()
    app.pointer = SimpleNamespace(cancel=lambda: None)
    app.double_tap_move = SimpleNamespace(cancel=lambda: None)
    app.model = SimpleNamespace(cancel_auto_move=lambda: None)
    app.pointer_snapshot = SimpleNamespace(
        pressed=True,
        x=rect.x + rect.width / 2,
        y=rect.y + rect.height / 2,
    )

    app.update_office_screen(0.0)

    session = app.office.current_session
    assert session is not None
    assert playback.revealed_chars == page_characters
    assert not session.asked_question_ids


def test_off001_active_field_event_only_matches_designated_anomaly() -> None:
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.office = OfficePrototype.load()
    app.office.current_index = 2
    app.office.begin_current_case()
    case = app.office.current_case
    assert case is not None
    for question in case.questions:
        app.office.ask_question(question.question_id)
    app.office.classify(Classification.FIELD_CHECK)
    assert app.office.prepare_field_task() is not None

    assert app.office_field_event_matches("urchin_abnormal_04")
    assert not app.office_field_event_matches("urchin_abnormal_03")
    assert not app.office_field_event_matches(None)


def test_off001_start_game_enters_office_without_advancing_world() -> None:
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.pointer = SimpleNamespace(cancel=lambda: None)
    app.double_tap_move = SimpleNamespace(cancel=lambda: None)
    app.model = SimpleNamespace(cancel_auto_move=lambda: None)
    app.previous_time = 1.0
    app.accumulator = 2.0
    app.hitstop_remaining = 3.0
    app.pending_auto_move_goal = (1.0, 2.0)
    app.pending_cancel_auto_move = True
    app.last_combat_scene_camera = object()
    app.combat_camera_restore = object()
    app.screen = AppScreen.START

    app.start_game()

    assert app.screen == AppScreen.OFFICE
    assert app.previous_time is None
    assert app.accumulator == 0.0
    assert app.hitstop_remaining == 0.0


def test_off001_inspection_event_returns_active_field_task_to_same_case() -> None:
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.office = OfficePrototype.load()
    app.office.current_index = 2
    app.office.begin_current_case()
    case = app.office.current_case
    assert case is not None
    for question in case.questions:
        app.office.ask_question(question.question_id)
    app.office.classify(Classification.FIELD_CHECK)
    assert app.office.prepare_field_task() is not None

    app.pointer = SimpleNamespace(cancel=lambda: None)
    app.double_tap_move = SimpleNamespace(cancel=lambda: None)
    app.model = SimpleNamespace(cancel_auto_move=lambda: None)
    app.camera_controller = SimpleNamespace(cancel_focus=lambda: None)
    app.effects = SimpleNamespace(process_events=lambda *args, **kwargs: None)
    app.audio = SimpleNamespace(play_events=lambda events: None)
    app.request_hitstop_from_events = lambda events: 0.0
    app.combat_camera_reactions_allowed = lambda: True
    app.show_location_label = lambda: None
    app.pending_action_pressed = False
    app.pending_interact_pressed = False
    app.pending_auto_move_goal = None
    app.pending_cancel_auto_move = False
    app.accumulator = 0.0
    app.previous_time = 1.0
    app.screen = AppScreen.PLAY
    event = GameEvent(
        event_id=1,
        world_tick=10,
        kind="inspection_completed",
        actor_id="player",
        target_id="urchin_abnormal_04",
        world_position=(800.0, 0.0, 704.0),
    )

    app.process_events([event])

    session = app.office.current_session
    assert app.screen == AppScreen.OFFICE
    assert session is not None
    assert session.case_id == "OFF-PROT-003"
    assert session.state == CaseState.FIELD_RETURNED
    assert session.field_result is not None
    assert session.field_result.task_id == "FIELD-PROT-003"
