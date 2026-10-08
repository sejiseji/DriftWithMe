from pathlib import Path

import pytest

from drift_with_me.app import OfficeDialogueLine
from drift_with_me.document_reading import reading_pose_pixels
from drift_with_me.office import OfficePrototype
from drift_with_me.week_cycle import WorkWeek, load_week_office
from test_office_jack_portrait import make_app

ROOT = Path(__file__).resolve().parents[1]


def base(name="jack_front_00.hex"):
    return tuple(
        tuple(int(c, 16) for c in row)
        for row in (ROOT / "src/drift_with_me/assets" / name).read_text().splitlines()
    )


def connected(pixels, start, end):
    queue = [start]
    seen = set(queue)
    for x, y in queue:
        if (x, y) == end:
            return True
        for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]:
            if (
                0 <= nx < 32
                and 0 <= ny < 44
                and (nx, ny) not in seen
                and pixels[ny][nx] in (1, 14, 15)
            ):
                seen.add((nx, ny))
                queue.append((nx, ny))
    return False


def test_all_reading_poses_keep_paper_and_holding_contact_connected():
    fixed = None
    shapes = set()
    for phase in range(4):
        for nod in (False, True):
            for blink in (False, True):
                pixels = reading_pose_pixels(
                    base("jack_front_blink_00.hex" if blink else "jack_front_00.hex"),
                    phase,
                    nod=nod,
                    blink=blink,
                )
                assert len(pixels) == 44 and all(len(row) == 32 for row in pixels)
                assert set(c for row in pixels for c in row) <= set(range(16))
                patch = tuple(row[4:10] for row in pixels[31:37])
                if fixed is None:
                    fixed = patch
                assert patch == fixed
                assert connected(pixels, (10, 26), (9, 33))
                tip = ((19, 33), (22, 33), (19, 35), (21, 37))[phase]
                assert connected(pixels, (21, 26), tip)
                assert pixels[40][4:28] == (1,) * 24
                shapes.add(pixels)
    assert len(shapes) >= 8


def test_original_office_dialogue_does_not_acquire_reading_metadata():
    office = OfficePrototype.load()
    assert all(q.visual_action is None for c in office.cases for q in c.questions)
    assert all(
        t.visual_action is None
        for script in office.counter_scripts.values()
        for t in (*script.opening, *script.resolution.turns)
    )


def test_grow_return_metadata_follows_only_jack_and_not_his_reply():
    office = load_week_office(WorkWeek(6, 2))
    assert office.advance_dialogue_step()
    lines = office.active_dialogue_lines()
    assert lines[0].visual_action == "read_document"
    assert lines[1].visual_action is None
    while office.has_pending_dialogue_step():
        office.advance_dialogue_step()
    assert office.ask_question("supplement")
    assert office.active_dialogue_lines()[0].visual_action == "read_document"
    assert office.active_dialogue_lines()[1].visual_action is None


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_reading_scope_and_stable_footprint_do_not_change_idle(profile):
    app, _ = make_app(profile)
    page = (
        OfficeDialogueLine(
            "Jack: 拝見しますね。", False, speaker="Jack", visual_action="read_document"
        ),
    )
    assert not app.office_document_reading_active(page)
    app.office = load_week_office(WorkWeek(6, 2))
    assert app.office_document_reading_active(page)
    content = app.office_dialogue_content_rect()
    positions = []
    for time in [0, 0.35, 1.2, 1.95, 2.3, 7.9]:
        app.presentation_time = time
        rect = app.office_jack_portrait_rect(reading=True)
        assert (rect.width, rect.height) == (32, 44)
        assert rect.y + rect.height <= content.y + content.height
        positions.append((rect.x, rect.y))
    assert len(set(positions)) == 1
    assert app.office_jack_portrait_rect().height == 32
    app.office_consultation = object()
    assert not app.office_document_reading_active(page)
    app.office_consultation = None
    assert not app.office_document_reading_active(
        (OfficeDialogueLine("返事", True, speaker="グロウ"),)
    )
    assert not app.office_document_reading_active(())
    assert not app.office_document_reading_active(
        (OfficeDialogueLine("担当へ渡します", False, speaker="Jack"),)
    )


def test_metadata_has_no_extra_dialogue_wait_and_clears_on_fast_forward():
    app, _ = make_app()
    app.office = load_week_office(WorkWeek(6, 2))
    app.office.advance_dialogue_step()
    app.office_dialogue_playback = None
    for _ in range(6):
        playback = app.sync_office_dialogue_playback()
        page = app.office_dialogue_current_page(playback)
        assert app.office_document_reading_active(page)
        playback.revealed_chars = 9999
        # Ordinary page advancement still succeeds immediately.
        assert app.advance_office_dialogue_page()
        page = app.office_dialogue_current_page(app.sync_office_dialogue_playback())
        assert not app.office_document_reading_active(page)
        app._office_reading_key = object()
        app.draw_office_jack(page)
        assert app._office_reading_key is None
        app.office = load_week_office(WorkWeek(6, 2))
        app.office.advance_dialogue_step()
        app.office_dialogue_playback = None


def test_original_outer_and_middle_arms_stay_while_inner_tips_are_replaced():
    original = base()
    for phase in range(4):
        pixels = reading_pose_pixels(original, phase, nod=False, blink=False)
        for y in range(26, 31):
            assert pixels[y][:7] == original[y][:7]
            assert pixels[y][25:] == original[y][25:]
        for y in range(27, 31):
            assert pixels[y][14:18] == original[y][14:18]
        # Both bends retain filled roots continuous with the body above.
        for x in (10, 21):
            assert pixels[25][x] in (14, 15)
            assert pixels[26][x] in (14, 15)
            assert pixels[27][x] in (14, 15)


def test_internal_join_dots_stay_skin_in_all_blinks_and_nods():
    for phase in range(4):
        for nod in (False, True):
            for blink in (False, True):
                original = base("jack_front_blink_00.hex" if blink else "jack_front_00.hex")
                pixels = reading_pose_pixels(original, phase, nod=nod, blink=blink)
                for y in range(24, 28):
                    for x in (*range(8, 13), *range(19, 24)):
                        if original[y][x] in (9, 14, 15):
                            assert pixels[y][x] in (9, 14, 15)
                # Original external boundary beside each attachment remains dark.
                assert pixels[27][7] == original[27][7] == 1
                assert pixels[27][24] == original[27][24] == 1
