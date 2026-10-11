from copy import deepcopy
from types import SimpleNamespace

import pytest

from drift_with_me.nudibranch_preview import DIRECTIONS, NudibranchPreview, preview_assets
from drift_with_me.save_state import SAVE_KEY, encode
from drift_with_me.week_cycle import WorkWeek
from test_save_state import Storage, payload
from test_week_debug_safety import debug_app


class Image:
    def __init__(self, width, height):
        self.width, self.height = width, height

    def set(self, x, y, rows):
        self.rows = rows

    def pget(self, x, y):
        return int(self.rows[y][x], 16)


def test_all64_frames_are_registered_with_approved_hashes_and_ground_anchor():
    library = preview_assets(SimpleNamespace(Image=Image))
    assert set(library.assets) == {"electric_nudibranch_normal", "electric_nudibranch_abnormal"}
    for asset in library.assets.values():
        assert asset.definition.anchor_px == (32, 58)
        assert asset.definition.world_size == (20, 20)
        assert asset.definition.colkey == 8
        assert set(asset.frames) == {f"{d}_{f:02d}" for d in DIRECTIONS for f in range(4)}
        assert len({f.source_hash for f in asset.frames.values()}) == 32


def test_four_to_one_loop_pause_and_all_directions():
    state = NudibranchPreview()
    for frame in range(20):
        state.tick(frame / 6)
        assert state.frame_index == frame % 4
    state.paused = True
    state.tick(10)
    assert state.frame_index == 3
    state.paused = False
    state.tick(10 + 1 / 6)
    assert state.frame_index == 0
    state = NudibranchPreview()
    for i, direction in enumerate(DIRECTIONS):
        state.tick(i * 2)
        assert state.direction_name == direction
    state.freeze_direction()
    state.tick(20)
    assert state.direction_name == "NW"


@pytest.mark.parametrize("record_kind", ["valid", "corrupt", "absent"])
def test_preview_next_terrain_exit_reentry_preserves_normal_and_backup(record_kind):
    _, valid = payload()
    storage = Storage()
    storage.items = {SAVE_KEY: encode(valid), SAVE_KEY + ".backup": encode(valid)}
    if record_kind == "corrupt":
        storage.items[SAVE_KEY] = "broken"
    elif record_kind == "absent":
        storage.items.pop(SAVE_KEY)
    before = deepcopy(storage.items)
    app = debug_app(storage)
    app.presentation_time = 0.0
    for _ in range(2):
        assert app.start_nudibranch_preview()
        assert app.model.nudibranch_preview is app.nudibranch_preview
        assert not app.checkpoint_progress()
        enemies = [(e.id, e.kind, e.state) for e in app.model.enemies]
        for action in ("next", "terrain", "terrain", "pause", "auto"):
            target = app.nudibranch_preview_rects()[action]
            app.mouse_pressed_in = lambda rect, target=target: rect == target
            app.update_nudibranch_preview()
        assert [(e.id, e.kind, e.state) for e in app.model.enemies] == enemies
        app.jump_to_debug_week(WorkWeek(6, 4))
        assert app.nudibranch_preview is None
        assert not hasattr(app.model, "nudibranch_preview")
        assert storage.items == before
    app.return_from_week_debug()
    assert app.nudibranch_preview is None
    assert app.progress_store is app.normal_progress_store
    assert not app.checkpoint_progress()
    assert storage.items == before


def test_normal_session_cannot_open_preview():
    app = debug_app(Storage(), enabled=False)
    assert not app.start_nudibranch_preview()
    assert not hasattr(app.model, "nudibranch_preview")
