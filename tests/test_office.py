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
    parse_case_definitions,
)
from drift_with_me.world import load_world_data

ROOT = Path(__file__).resolve().parents[1]
OFFICE_PORTRAIT_HASHES = {
    "succubus_green": "813471a9c901d2b1c464e3cd871d4c50755539d32d753984ed6a756acf0ef014",
    "tired_gray_oldman": "226b90cf1fdc909641fbe45f13254769718acaee38a9f77a65416ad5a474564c",
    "nervous_elf_woodsman": "f0e7d85f511754ff8cb57d7f1501ee0983efd8b2b48f8218bbc6bb2854250bf6",
    "smug_blond_hero": "da1d755d1be399591a653b08c7893d37b7ad710fb632d0ef7912c8850e99f1b2",
}


def drain_office_dialogue(office: OfficePrototype) -> str | None:
    while office.has_pending_dialogue_step():
        assert office.advance_dialogue_step()
    return office.complete_pending_question()


def ask_and_complete(office: OfficePrototype, question_id: str) -> None:
    assert office.ask_question(question_id)
    assert drain_office_dialogue(office) == question_id


def finish_app_office_dialogue(app: DriftWithMeApp) -> None:
    while True:
        playback = app.sync_office_dialogue_playback()
        assert playback.pages
        playback.page_index = len(playback.pages) - 1
        page = app.office_dialogue_current_page(playback)
        playback.revealed_chars = float(sum(len(line.text) for line in page))
        if app.office.has_pending_dialogue_step():
            assert app.advance_office_dialogue_page()
            continue
        app.update_office_dialogue_playback(0.0)
        return


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


def test_off001_counter_scripts_define_44_unique_extra_exchanges() -> None:
    office = OfficePrototype.load()
    turns = []
    for script in office.counter_scripts.values():
        turns.extend(script.opening)
        turns.extend(turn for group in script.after_question.values() for turn in group)
        turns.extend(script.resolution.turns)
        if script.field_return is not None:
            turns.extend(script.field_return.preamble)
            turns.extend(script.field_return.closing)

    assert len(turns) == 44
    assert len({turn.turn_id for turn in turns}) == 44
    assert set(office.counter_scripts) == {case.case_id for case in office.cases}


def test_off001_opening_and_question_followups_complete_in_order_once() -> None:
    office = OfficePrototype.load()
    session = office.current_session
    assert session is not None

    assert office.active_dialogue_lines()[0].text.startswith("お待たせしました")
    assert not office.ask_question("identity")
    drain_office_dialogue(office)

    assert office.ask_question("identity")
    assert session.pending_question_id == "identity"
    assert not session.asked_question_ids
    assert not session.memo_facts
    while office.has_pending_dialogue_step():
        assert office.advance_dialogue_step()
        assert not session.asked_question_ids
    assert office.complete_pending_question() == "identity"

    dialogue_count = len(session.dialogue)
    assert session.asked_question_ids == {"identity"}
    assert [fact.line for fact in session.memo_facts] == ["本人確認: 済"]
    assert not office.ask_question("identity")
    assert len(session.dialogue) == dialogue_count


def test_off001_resolution_requires_defined_questions_and_blocks_early_exit() -> None:
    office = OfficePrototype.load()
    drain_office_dialogue(office)
    ask_and_complete(office, "identity")
    session = office.current_session
    assert session is not None

    assert not office.classify(Classification.COUNTER_COMPLETE)
    assert "質問" in session.feedback
    ask_and_complete(office, "changes")
    assert office.classify(Classification.COUNTER_COMPLETE)
    assert office.has_pending_dialogue_step()
    assert not office.advance_case()
    drain_office_dialogue(office)
    assert office.advance_case()


def test_off001_field_return_uses_actual_result_lines() -> None:
    office = OfficePrototype.load()
    office.current_index = 2
    office.begin_current_case()
    drain_office_dialogue(office)
    ask_and_complete(office, "place")
    assert office.classify(Classification.FIELD_CHECK)
    assert office.prepare_field_task() is None
    drain_office_dialogue(office)
    task = office.prepare_field_task()
    assert task is not None

    actual_report = ("実機個体数2", "現場設備に傷あり")
    assert office.complete_field_task(
        FieldResult(
            task_id=task.task_id,
            case_id=task.case_id,
            result_code="CUSTOM_TEST_RESULT",
            discovered_fact_ids=("custom_fact",),
            report_lines=actual_report,
        )
    )
    drain_office_dialogue(office)
    session = office.current_session
    assert session is not None
    report_texts = tuple(line.text for line in session.dialogue if line.speaker == "確認記録")
    assert report_texts == actual_report


def test_off001_answer_summary_is_independent_with_reply_fallback() -> None:
    data_path = ROOT / "src/drift_with_me/data/office_cases.json"
    raw = json.loads(data_path.read_text(encoding="utf-8"))
    first_question = raw["cases"][0]["questions"][0]
    first_question["answer_summary"] = "本人確認書類あり"
    raw["cases"][0]["questions"][1].pop("answer_summary")

    cases = parse_case_definitions(raw)

    assert cases[0].questions[0].answer_summary == "本人確認書類あり"
    assert cases[0].questions[1].answer_summary == cases[0].questions[1].visitor_reply


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
    drain_office_dialogue(office)
    case = office.current_case
    session = office.current_session
    assert case is not None
    assert session is not None

    ask_and_complete(office, "identity")
    assert not office.ask_question("identity")

    assert session.state == CaseState.READY_TO_CLASSIFY
    assert session.asked_question_ids == {"identity"}
    assert [fact.line for fact in session.memo_facts] == ["本人確認: 済"]
    assert [line.speaker for line in session.dialogue[-6:]] == [
        "Jack",
        "ミナ",
        "Jack",
        "ミナ",
        "Jack",
        "ミナ",
    ]
    assert {"mina_identity_check", "mina_identity_return"} <= (session.completed_dialogue_turn_ids)


def test_off001_wrong_classification_returns_to_hearing_without_losing_facts() -> None:
    office = OfficePrototype.load()
    drain_office_dialogue(office)
    ask_and_complete(office, "identity")
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
        drain_office_dialogue(office)
        for question in case.questions:
            ask_and_complete(office, question.question_id)
        assert office.classify(case.expected_classification)
        assert session.state == expected_state
        drain_office_dialogue(office)
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
            drain_office_dialogue(office)
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

    drain_office_dialogue(office)
    for question in case.questions:
        ask_and_complete(office, question.question_id)
    assert office.classify(Classification.FIELD_CHECK)
    drain_office_dialogue(office)
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
    drain_office_dialogue(office)


def test_off001_hearing_is_isolated_from_world_state() -> None:
    runtime = load_runtime_config("medium")
    world = load_world_data()
    model = GameModel(runtime.raw, world)
    office = OfficePrototype.load()
    drain_office_dialogue(office)
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

    ask_and_complete(office, "identity")
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
            app.office_classification_panel_rect(),
            app.office_footer_rect(),
            app.office_answer_footer_rect(),
            app.office_footer_action_rect(),
        )
        assert all(
            rect.x >= screen.x
            and rect.y >= screen.y
            and rect.x + rect.width <= screen.width + 0.01
            and rect.y + rect.height <= screen.height + 0.01
            for rect in rects
        )
        assert app.office_dialog_rect().x == app.office_questions_panel_rect().x
        assert app.office_dialog_rect().width == app.office_questions_panel_rect().width
        assert (
            app.office_dialog_rect().y + app.office_dialog_rect().height
            < app.office_questions_panel_rect().y
        )

        question_rects = [app.office_question_rect(index, 5) for index in range(5)]
        assert all(rect.height >= app.office_rect(0, 0, 0, 14).height for rect in question_rects)
        assert all(
            not (
                left.x < right.x + right.width
                and left.x + left.width > right.x
                and left.y < right.y + right.height
                and left.y + left.height > right.y
            )
            for index, left in enumerate(question_rects)
            for right in question_rects[index + 1 :]
        )

        classification_rects = [app.office_classification_rect(index) for index in range(4)]
        assert classification_rects[0].x == classification_rects[2].x
        assert classification_rects[1].x == classification_rects[3].x
        assert classification_rects[0].y == classification_rects[1].y
        assert classification_rects[2].y == classification_rects[3].y
        assert all(
            not (
                left.x < right.x + right.width
                and left.x + left.width > right.x
                and left.y < right.y + right.height
                and left.y + left.height > right.y
            )
            for index, left in enumerate(classification_rects)
            for right in classification_rects[index + 1 :]
        )
        feedback_rect = app.office_classification_feedback_rect()
        assert max(rect.y + rect.height for rect in classification_rects) < feedback_rect.y
        assert feedback_rect.y + feedback_rect.height <= (
            app.office_classification_panel_rect().y + app.office_classification_panel_rect().height
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
    drain_office_dialogue(app.office)
    app.ui_text = FixedWidthRenderer()
    return app


def test_off001_dialogue_wraps_without_ellipsis_and_paginates_full_exchange() -> None:
    app = make_office_dialogue_app()
    assert app.office.ask_question("identity")

    playback = app.sync_office_dialogue_playback()
    session = app.office.current_session
    assert session is not None
    expected = "".join(f"{line.speaker}: {line.text}" for line in session.dialogue[-2:])
    visible = "".join(line.text for page in playback.pages for line in page)
    max_width = int(app.office_dialogue_content_rect().width)

    assert playback.pages
    assert visible == expected
    assert all(
        app.ui_text.text_width(line.text, "office_japanese") <= max_width - line.indent_px
        for page in playback.pages
        for line in page
    )
    assert any(line.indent_px > 0 for page in playback.pages for line in page)
    assert all(len({line.visitor for line in page}) == 1 for page in playback.pages)
    assert [page[0].visitor for page in playback.pages] == [False, True]


def test_off001_dialogue_typewriter_tap_completes_then_advances_page() -> None:
    app = make_office_dialogue_app()
    app.ui_text = SimpleNamespace(text_width=lambda text, style_name: len(text) * 32)
    assert app.office.ask_question("identity")
    playback = app.sync_office_dialogue_playback()
    assert len(playback.pages) > 1
    first_page = app.office_dialogue_current_page(playback)
    first_page_characters = sum(len(line.text) for line in first_page)

    app.update_office_dialogue_playback(1.0 / OFFICE_DIALOGUE_CHARS_PER_SEC)
    assert int(playback.revealed_chars) == 1

    assert app.advance_office_dialogue_page()
    assert playback.page_index == 0
    assert playback.revealed_chars == first_page_characters

    assert app.advance_office_dialogue_page()
    assert playback.page_index == 1
    assert playback.revealed_chars == 0.0


def test_off001_dialogue_draws_visitor_speech_in_yellow() -> None:
    app = make_office_dialogue_app()
    assert app.office.ask_question("identity")
    playback = app.sync_office_dialogue_playback()
    playback.page_index = next(
        index for index, candidate in enumerate(playback.pages) if candidate[0].visitor
    )
    page = app.office_dialogue_current_page(playback)
    playback.revealed_chars = float(sum(len(line.text) for line in page))
    draws: list[tuple[str, int, float]] = []
    app.draw_office_text_in_rect = lambda rect, text, color, **kwargs: draws.append(
        (text, color, rect.x)
    )
    app.pyxel = SimpleNamespace(rect=lambda *args: None)
    app.frame = 0

    app.draw_office_dialogue(app.office_dialog_rect())

    content_x = app.office_dialogue_content_rect().x
    expected = [(line.text, 10 if line.visitor else 7, content_x + line.indent_px) for line in page]
    assert draws == expected


def test_off001_dialogue_draws_pointing_prompt_only_when_next_speech_is_ready() -> None:
    app = make_office_dialogue_app()
    assert app.office.ask_question("identity")
    playback = app.sync_office_dialogue_playback()
    page = app.office_dialogue_current_page(playback)
    prompt_pixels: list[tuple[int, int, int, int, int]] = []
    app.draw_office_text_in_rect = lambda *args, **kwargs: None
    app.pyxel = SimpleNamespace(rect=lambda *args: prompt_pixels.append(args))
    app.frame = 0

    app.draw_office_dialogue(app.office_dialog_rect())
    assert not prompt_pixels

    playback.revealed_chars = float(sum(len(line.text) for line in page))
    app.draw_office_dialogue(app.office_dialog_rect())

    assert prompt_pixels
    assert {pixel[-1] for pixel in prompt_pixels} == {7, 10}
    dialog_rect = app.office_dialog_rect()
    assert all(
        dialog_rect.x <= x < dialog_rect.x + dialog_rect.width
        and dialog_rect.y <= y < dialog_rect.y + dialog_rect.height
        for x, y, _width, _height, _color in prompt_pixels
    )


def test_off001_visitor_info_is_complete_yellow_content_without_documents() -> None:
    app = make_office_dialogue_app()
    app.office.current_index = 2
    app.office.begin_current_case()
    case = app.office.current_case
    assert case is not None
    lines = app.office_visitor_info_lines(case)
    max_width = int(app.office_visitor_info_rect().width)
    wrapped = tuple(
        wrapped_line
        for line in lines
        for wrapped_line in app.wrap_office_hanging_text(line, max_width)
    )

    assert lines == (
        "名前: ラメル",
        "種別: 魔族（海棲型）",
        "用件: 夜になると水辺から異常音がする",
    )
    assert all("書類" not in line.text and "..." not in line.text for line in wrapped)
    assert "".join(line.text for line in wrapped) == "".join(lines)
    assert all(
        app.ui_text.text_width(line.text, "office_japanese") <= max_width - line.indent_px
        for line in wrapped
    )
    expected_indent = app.ui_text.text_width("種別: ", "office_japanese")
    assert any(line.indent_px == expected_indent for line in wrapped)


def test_off001_visitor_info_fits_every_case_and_display_profile() -> None:
    class FixedWidthRenderer:
        @staticmethod
        def text_width(text: str, style_name: str) -> int:
            del style_name
            return sum(6 if ord(char) < 128 else 12 for char in text)

    for profile in ("low", "medium", "high"):
        app = DriftWithMeApp.__new__(DriftWithMeApp)
        app.runtime = load_runtime_config(profile)
        app.ui_text = FixedWidthRenderer()
        info_rect = app.office_visitor_info_rect()
        for case in OfficePrototype.load().cases:
            wrapped = tuple(
                wrapped_line
                for line in app.office_visitor_info_lines(case)
                for wrapped_line in app.wrap_office_hanging_text(
                    line,
                    int(info_rect.width),
                )
            )
            assert len(wrapped) * 12 <= info_rect.height + 0.5


def test_off001_question_buttons_use_short_labels_without_ellipsis() -> None:
    expected_labels = (
        "本人確認",
        "登録内容",
        "添付書類",
        "発生時期",
        "発生頻度",
        "発生場所",
        "音の特徴",
        "被害状況",
        "来訪目的",
    )
    office = OfficePrototype.load()
    labels = tuple(question.button_label for case in office.cases for question in case.questions)

    assert labels == expected_labels
    assert all("..." not in label and "…" not in label for label in labels)
    for profile in ("low", "medium", "high"):
        app = DriftWithMeApp.__new__(DriftWithMeApp)
        app.runtime = load_runtime_config(profile)
        for case in office.cases:
            for index, question in enumerate(case.questions):
                rect = app.office_question_rect(index, len(case.questions))
                available_width = int(rect.width - 6)
                rendered_width = sum(
                    6 if ord(char) < 128 else 12
                    for char in f"{app.office_question_number(index)} 済 {question.button_label}"
                )
                assert rendered_width <= available_width


def test_off001_only_referenced_answer_colors_circled_number_yellow() -> None:
    draws: list[tuple[int, str, int]] = []

    class FakeRenderer:
        @staticmethod
        def text_width(text: str, style_name: str) -> int:
            del style_name
            return len(text) * 8

        @staticmethod
        def visual_vertical_metrics(style_name: str) -> tuple[int, int]:
            del style_name
            return (0, 12)

        @staticmethod
        def draw(pyxel, x: int, y: int, text: str, color: int, style_name: str) -> None:
            del pyxel, y, style_name
            draws.append((x, text, color))

    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.ui_text = FakeRenderer()
    app.pyxel = object()

    app.draw_office_question_label(Rect(10, 20, 160, 24), 0, "本人確認", True, True)

    assert [(text, color) for _x, text, color in draws] == [
        ("①", 10),
        (" 済 本人確認", 13),
    ]
    assert draws[1][0] == draws[0][0] + 8

    draws.clear()
    app.draw_office_question_label(Rect(10, 20, 160, 24), 1, "登録変更", True, False)

    assert [(text, color) for _x, text, color in draws] == [
        ("②", 13),
        (" 済 登録変更", 13),
    ]


def test_off001_answer_reference_auto_selects_without_reasking() -> None:
    app = make_office_dialogue_app()
    case = app.office.current_case
    session = app.office.current_session
    assert case is not None
    assert session is not None
    question = case.questions[0]

    assert app.ask_or_select_office_question(question)
    finish_app_office_dialogue(app)
    dialogue_count = len(session.dialogue)
    assert app.sync_office_answer_reference() == question.question_id

    assert app.ask_or_select_office_question(question)
    assert len(session.dialogue) == dialogue_count
    assert session.asked_question_ids == {question.question_id}
    assert app.sync_office_answer_reference() == question.question_id


def test_off001_answer_footer_cycles_answered_questions_in_definition_order() -> None:
    app = make_office_dialogue_app()
    app.office.current_index = 2
    app.office.begin_current_case()
    drain_office_dialogue(app.office)
    case = app.office.current_case
    assert case is not None
    first = case.questions[0]
    third = case.questions[2]
    ask_and_complete(app.office, first.question_id)
    ask_and_complete(app.office, third.question_id)
    assert app.select_office_answer_reference(third.question_id)

    assert app.cycle_office_answer_reference()
    assert app.sync_office_answer_reference() == first.question_id
    assert app.cycle_office_answer_reference()
    assert app.sync_office_answer_reference() == third.question_id


def test_off001_answer_footer_tap_cycles_reference_without_changing_dialogue() -> None:
    app = make_office_dialogue_app()
    case = app.office.current_case
    session = app.office.current_session
    assert case is not None
    assert session is not None
    assert app.ask_or_select_office_question(case.questions[0])
    finish_app_office_dialogue(app)
    assert app.ask_or_select_office_question(case.questions[1])
    finish_app_office_dialogue(app)
    playback = app.sync_office_dialogue_playback()
    playback.page_index = len(playback.pages) - 1
    final_page = app.office_dialogue_current_page(playback)
    playback.revealed_chars = float(sum(len(line.text) for line in final_page))
    dialogue_count = len(session.dialogue)
    footer = app.office_answer_footer_rect()
    app.pointer_snapshot = SimpleNamespace(
        pressed=True,
        x=footer.x + footer.width / 2,
        y=footer.y + footer.height / 2,
    )
    app.pointer = SimpleNamespace(cancel=lambda: None)
    app.double_tap_move = SimpleNamespace(cancel=lambda: None)
    app.model = SimpleNamespace(cancel_auto_move=lambda: None)
    app.pyxel = SimpleNamespace(KEY_RETURN=1, KEY_Z=2, btnp=lambda key: False)

    app.update_office_screen(0.0)

    assert app.sync_office_answer_reference() == case.questions[0].question_id
    assert len(session.dialogue) == dialogue_count


def test_off001_answer_footer_draws_only_number_in_yellow_and_fits_profiles() -> None:
    draws: list[tuple[str, int]] = []

    class FakeRenderer:
        @staticmethod
        def text_width(text: str, style_name: str) -> int:
            del style_name
            return sum(6 if ord(char) < 128 else 12 for char in text)

        @staticmethod
        def visual_vertical_metrics(style_name: str) -> tuple[int, int]:
            del style_name
            return (0, 12)

        @staticmethod
        def draw(pyxel, x: int, y: int, text: str, color: int, style_name: str) -> None:
            del pyxel, x, y, style_name
            draws.append((text, color))

    app = make_office_dialogue_app()
    app.ui_text = FakeRenderer()
    app.pyxel = object()
    case = app.office.current_case
    assert case is not None
    assert app.ask_or_select_office_question(case.questions[0])
    finish_app_office_dialogue(app)

    app.draw_office_answer_reference()

    assert draws == [
        ("回答", 13),
        ("①", 10),
        ("：本人請求で本人確認書類を提示済み", 13),
    ]
    for profile in ("low", "medium", "high"):
        profile_app = DriftWithMeApp.__new__(DriftWithMeApp)
        profile_app.runtime = load_runtime_config(profile)
        footer_width = int(profile_app.office_answer_footer_rect().width)
        for candidate_case in OfficePrototype.load().cases:
            for index, question in enumerate(candidate_case.questions):
                text = f"回答{profile_app.office_question_number(index)}：{question.answer_summary}"
                rendered_width = sum(6 if ord(char) < 128 else 12 for char in text)
                assert rendered_width <= footer_width


def test_off001_classification_labels_are_equal_length_for_two_column_grid() -> None:
    assert [
        DriftWithMeApp.office_classification_label(classification)
        for classification in CLASSIFICATION_ORDER
    ] == ["窓口完結", "他部署へ", "書類不足", "現地確認"]


def test_off001_wrapped_feedback_keeps_japanese_punctuation_with_previous_text() -> None:
    app = make_office_dialogue_app()
    text = "本人確認済みで、窓口で完了できる案件です。"
    wrapped = app.wrap_office_dialogue_text(text, 120)

    assert "".join(wrapped) == text
    assert all(line[0] not in "、。！？" for line in wrapped if line)


def test_off001_hanging_indent_starts_continuation_after_colon() -> None:
    app = make_office_dialogue_app()
    text = "用件: 夜になると水辺から異常音がする"
    max_width = 108
    wrapped = app.wrap_office_hanging_text(text, max_width)
    expected_indent = app.ui_text.text_width("用件: ", "office_japanese")

    assert "".join(line.text for line in wrapped) == text
    assert wrapped[0].indent_px == 0
    assert all(line.indent_px == expected_indent for line in wrapped[1:])
    assert all(
        app.ui_text.text_width(line.text, "office_japanese") <= max_width - line.indent_px
        for line in wrapped
    )


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
    page_characters = sum(len(line.text) for line in page)
    rect = app.office_dialog_rect()
    app.pointer = SimpleNamespace(cancel=lambda: None)
    app.double_tap_move = SimpleNamespace(cancel=lambda: None)
    app.model = SimpleNamespace(cancel_auto_move=lambda: None)
    app.pointer_snapshot = SimpleNamespace(
        pressed=True,
        x=rect.x + rect.width / 2,
        y=rect.y + rect.height / 2,
    )
    app.pyxel = SimpleNamespace(KEY_RETURN=1, KEY_Z=2, btnp=lambda key: False)

    app.update_office_screen(0.0)

    session = app.office.current_session
    assert session is not None
    assert playback.revealed_chars == page_characters
    assert not session.asked_question_ids


def test_off001_next_question_is_locked_until_visitor_reply_is_shown() -> None:
    app = make_office_dialogue_app()
    assert app.office.ask_question("identity")
    playback = app.sync_office_dialogue_playback()
    page = app.office_dialogue_current_page(playback)
    playback.revealed_chars = float(sum(len(line.text) for line in page))
    second_question = app.office_question_rect(1, len(app.office.current_case.questions))
    app.pointer_snapshot = SimpleNamespace(
        pressed=True,
        x=second_question.x + second_question.width / 2,
        y=second_question.y + second_question.height / 2,
    )
    app.pointer = SimpleNamespace(cancel=lambda: None)
    app.double_tap_move = SimpleNamespace(cancel=lambda: None)
    app.model = SimpleNamespace(cancel_auto_move=lambda: None)
    app.pyxel = SimpleNamespace(KEY_RETURN=1, KEY_Z=2, btnp=lambda key: False)

    app.update_office_screen(0.0)

    session = app.office.current_session
    assert session is not None
    assert not session.asked_question_ids
    assert session.pending_question_id == "identity"
    assert playback.page_index == 0


def test_off001_dialogue_tap_advances_from_jack_to_visitor_reply() -> None:
    app = make_office_dialogue_app()
    assert app.office.ask_question("identity")
    playback = app.sync_office_dialogue_playback()
    jack_page = app.office_dialogue_current_page(playback)
    playback.revealed_chars = float(sum(len(line.text) for line in jack_page))
    rect = app.office_dialog_rect()
    app.pointer_snapshot = SimpleNamespace(
        pressed=True,
        x=rect.x + rect.width / 2,
        y=rect.y + rect.height / 2,
    )
    app.pointer = SimpleNamespace(cancel=lambda: None)
    app.double_tap_move = SimpleNamespace(cancel=lambda: None)
    app.model = SimpleNamespace(cancel_auto_move=lambda: None)
    app.pyxel = SimpleNamespace(KEY_RETURN=1, KEY_Z=2, btnp=lambda key: False)

    app.update_office_screen(0.0)

    reply_page = app.office_dialogue_current_page(playback)
    assert playback.page_index == 1
    assert playback.revealed_chars == 0.0
    assert all(line.visitor for line in reply_page)


def test_off001_active_field_event_only_matches_designated_anomaly() -> None:
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.office = OfficePrototype.load()
    app.office.current_index = 2
    app.office.begin_current_case()
    drain_office_dialogue(app.office)
    case = app.office.current_case
    assert case is not None
    for question in case.questions:
        ask_and_complete(app.office, question.question_id)
    assert app.office.classify(Classification.FIELD_CHECK)
    drain_office_dialogue(app.office)
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


def make_active_office_field_event_app() -> DriftWithMeApp:
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.office = OfficePrototype.load()
    app.office.current_index = 2
    app.office.begin_current_case()
    drain_office_dialogue(app.office)
    case = app.office.current_case
    assert case is not None
    for question in case.questions:
        ask_and_complete(app.office, question.question_id)
    assert app.office.classify(Classification.FIELD_CHECK)
    drain_office_dialogue(app.office)
    assert app.office.prepare_field_task() is not None

    app.pointer = SimpleNamespace(cancel=lambda: None)
    app.double_tap_move = SimpleNamespace(cancel=lambda: None)
    app.model = SimpleNamespace(cancel_auto_move=lambda: None)
    app.camera_controller = SimpleNamespace(cancel_focus=lambda: None)
    app.effects = SimpleNamespace(process_events=lambda *args, **kwargs: None)
    app.audio = SimpleNamespace(play_events=lambda events: None)
    app.request_hitstop_from_events = lambda events: 0.0
    app.combat_camera_reactions_allowed = lambda: True
    app.start_combat_camera_restore = lambda: None
    app.show_location_label = lambda: None
    app.pending_action_pressed = False
    app.pending_interact_pressed = False
    app.pending_auto_move_goal = None
    app.pending_cancel_auto_move = False
    app.accumulator = 0.0
    app.previous_time = 1.0
    app.screen = AppScreen.PLAY
    return app


def test_off001_inspection_event_returns_active_field_task_to_same_case() -> None:
    app = make_active_office_field_event_app()
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


def test_off001_exploration_discharge_returns_active_field_task_to_same_case() -> None:
    app = make_active_office_field_event_app()
    event = GameEvent(
        event_id=1,
        world_tick=10,
        kind="discharge_succeeded",
        actor_id="buddy",
        target_id="urchin_abnormal_04",
        world_position=(800.0, 0.0, 704.0),
        payload={"energy_cost": 20.0},
    )

    app.process_events([event])

    session = app.office.current_session
    assert app.screen == AppScreen.OFFICE
    assert session is not None
    assert session.state == CaseState.FIELD_RETURNED
    assert session.field_result is not None
    assert session.field_result.task_id == "FIELD-PROT-003"


def test_off001_combat_discharge_waits_for_combat_restore_before_returning() -> None:
    app = make_active_office_field_event_app()
    discharge = GameEvent(
        event_id=1,
        world_tick=10,
        kind="discharge_succeeded",
        actor_id="buddy",
        target_id="urchin_abnormal_04",
        world_position=(800.0, 0.0, 704.0),
        payload={"energy_cost": 20.0, "combat_counter": True},
    )

    app.process_events([discharge])

    session = app.office.current_session
    assert app.screen == AppScreen.PLAY
    assert session is not None
    assert session.state == CaseState.FIELD_ACTIVE

    restored = GameEvent(
        event_id=2,
        world_tick=11,
        kind="combat_restored",
        actor_id="urchin_abnormal_04",
        target_id="player",
        world_position=(800.0, 0.0, 704.0),
        payload={"combat_outcome": "defeat"},
    )
    app.process_events([restored])

    assert app.screen == AppScreen.OFFICE
    assert session.state == CaseState.FIELD_RETURNED
