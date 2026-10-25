import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.app import (
    OFFICE_PORTRAIT_BLINK_DURATION_FRAMES,
    OFFICE_PORTRAIT_BLINK_INTERVAL_FRAMES,
    DriftWithMeApp,
)
from drift_with_me.august_patrol import (
    W4_BLINK_ORIGINAL_IDS,
    W4_DIALOGUE_PORTRAITS,
    W4_DIALOGUE_SMILE_PORTRAITS,
    patrol_dialogue_frame,
)
from drift_with_me.config import load_runtime_config

ROOT = Path(__file__).parents[1] / "src/drift_with_me/assets"
ASSETS = {a["id"]: a for a in json.loads((ROOT / "jack_sprite.json").read_text())["source_assets"]}
BOXES = {
    "ramel": [(78, 98, 112, 118), (125, 94, 160, 113)],
    "hero": [(96, 73, 135, 96), (140, 89, 166, 110)],
    "mina": [(80, 89, 117, 113), (125, 96, 157, 121)],
    "grow": [(72, 90, 104, 110), (110, 90, 144, 110)],
}


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
@pytest.mark.parametrize("key", list(W4_BLINK_ORIGINAL_IDS))
@pytest.mark.parametrize("smile", [False, True])
def test_w4_every_blink_frame_matches_old_timing_seed_and_stays_232(profile, key, smile):
    app = SimpleNamespace(
        runtime=load_runtime_config(profile),
        office_portrait_blink_pose=DriftWithMeApp.office_portrait_blink_pose,
        frame=0,
    )
    original = W4_BLINK_ORIGINAL_IDS[key]
    intervals = tuple(
        app.runtime.raw["ui"]["office_portrait_blink_interval_frames"].get(
            original, OFFICE_PORTRAIT_BLINK_INTERVAL_FRAMES
        )
    )
    period = sum(intervals) + OFFICE_PORTRAIT_BLINK_DURATION_FRAMES * len(intervals)
    ident = (W4_DIALOGUE_SMILE_PORTRAITS if smile else W4_DIALOGUE_PORTRAITS)[key]
    frames = {f["id"] for f in ASSETS[ident]["frames"]}
    seen = set()
    for tick in range(period * 2):
        app.frame = tick
        old = app.office_portrait_blink_pose(tick, original, intervals=intervals)
        expected = (
            {None: "open", "half": "half", "closed": "normal"}[old]
            if smile
            else ("normal" if old is None else old)
        )
        assert patrol_dialogue_frame(app, key, ident) == expected
        assert expected in frames
        seen.add(expected)
    assert seen == frames
    assert ASSETS[ident]["hex_width"] == ASSETS[ident]["hex_height"] == 232


@pytest.mark.parametrize(
    "key", ["iwama", "merrill", "morris", "ruby", "takanashi", "yoake", "sagan", "ura"]
)
def test_preceding_static_portraits_do_not_gain_or_lose_existing_blink(key):
    app = SimpleNamespace(
        runtime=load_runtime_config(),
        office_portrait_blink_pose=DriftWithMeApp.office_portrait_blink_pose,
        frame=0,
    )
    for tick in range(1400):
        app.frame = tick
        assert patrol_dialogue_frame(app, key, W4_DIALOGUE_PORTRAITS[key]) is None


@pytest.mark.parametrize("key", list(W4_BLINK_ORIGINAL_IDS))
@pytest.mark.parametrize("smile", [False, True])
def test_w4_blink_changes_only_edited_eye_regions_and_keeps_anchor_palette(key, smile):
    ident = (W4_DIALOGUE_SMILE_PORTRAITS if smile else W4_DIALOGUE_PORTRAITS)[key]
    a = ASSETS[ident]
    assert a["anchor_px"] == [116, 116] and a["colkey"] == 8
    rows = [(ROOT / f["path"]).read_text().splitlines() for f in a["frames"]]
    assert len(rows) == 3 and len({tuple(r) for r in rows}) == 3
    for frame in rows[1:]:
        changes = 0
        for y in range(232):
            for x in range(232):
                assert frame[y][x] in "0123456789ABCDEF"
                if frame[y][x] != rows[0][y][x]:
                    changes += 1
                    assert any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in BOXES[key])
        assert changes > 0
