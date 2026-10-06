import json
from copy import deepcopy
from pathlib import Path

import pytest

from drift_with_me.office import OfficePrototype
from test_office_supervisor import app_for, finish

ASSETS = Path(__file__).resolve().parents[1] / "src/drift_with_me/assets/office_supervisor"


@pytest.mark.parametrize(
    "elapsed,expected",
    [
        (0, "normal"),
        (0.7, "normal"),
        (3.999, "normal"),
        (4, "half"),
        (4.039, "half"),
        (4.04, "closed"),
        (4.099, "closed"),
        (4.10, "half"),
        (4.139, "half"),
        (4.14, "normal"),
        (4.24, "normal"),
        (8.24, "half"),
        (8.28, "closed"),
    ],
)
def test_production_blink_timeline(elapsed, expected):
    office = OfficePrototype.load()
    office.begin_current_case()
    finish(office)
    app = app_for(office)
    assert app.begin_office_consultation()
    start = app.presentation_time
    app.presentation_time = start + elapsed
    assert app.office_supervisor_blink_frame() == expected
    assert app._office_supervisor_blink["durations_ms"] == [4000, 40, 60, 40, 100]


def test_blink_only_in_consultation_and_restart_opens_eyes_without_mutating_state():
    office = OfficePrototype.load()
    office.begin_current_case()
    finish(office)
    app = app_for(office)
    before = deepcopy(office.current_session)
    normal = deepcopy(app.current_office_dialogue_playback())
    app.presentation_time = 100
    assert app.office_supervisor_blink_frame() == "normal"
    for _ in range(10):
        assert app.begin_office_consultation()
        assert not app.begin_office_consultation()
        app.presentation_time += 4.05
        assert app.office_supervisor_blink_frame() == "closed"
        assert app.office.current_session == before
        app.end_office_consultation()
        assert app.office_supervisor_blink_frame() == "normal"
        assert app.sync_office_dialogue_playback() == normal
        assert app.begin_office_consultation()
        assert app.office_supervisor_blink_frame() == "normal"
        app.end_office_consultation()


def test_full_frame_pose_changes_only_approved_eye_pixels():
    scope = json.loads((ASSETS / "blink_scope.json").read_text())
    allowed = {
        (x, int(y))
        for mask in scope["mask_rows"]
        for y, (start, end) in mask.items()
        for x in range(start, end + 1)
    }
    original = (ASSETS / "boss_116x149.hex").read_text().splitlines()
    assert (ASSETS / "normal.hex").read_text().splitlines() == original
    for pose, expected in [("half", 73), ("closed", 125)]:
        rows = (ASSETS / f"{pose}.hex").read_text().splitlines()
        assert len(rows) == 149 and all(len(row) == 116 for row in rows)
        changed = {(x, y) for y in range(149) for x in range(116) if rows[y][x] != original[y][x]}
        assert len(changed) == expected
        assert changed <= allowed
        assert all(
            (rows[y][x] == "8") == (original[y][x] == "8") for y in range(149) for x in range(116)
        )
