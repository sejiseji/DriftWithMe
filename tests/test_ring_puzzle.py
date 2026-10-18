import json
from copy import deepcopy

import pytest

from drift_with_me.ring_puzzle import RingPreviewStore, RingPuzzle


def solve(puzzle):
    for i in range(5):
        puzzle.selected = i
        while puzzle.angles[i]:
            assert puzzle.rotate(-1)
            puzzle.tick(0.16)


def test_independent_rotation_wrap_and_input_lock():
    p = RingPuzzle()
    original = p.angles[:]
    assert p.rotate(-1)
    assert not p.rotate(1)
    assert p.angles[1:] == original[1:]
    assert p.display_angle(0) != RingPuzzle(p.angles[:]).display_angle(0)
    p.tick(0.16)
    p.angles[0] = 0
    assert p.rotate(-1)
    assert p.angles[0] == 11


def test_solve_light_and_no_story_or_reward_fields():
    p = RingPuzzle()
    solve(p)
    assert p.phase == "solved"
    assert not p.rotate(1)
    p.tick(0.35)
    assert p.phase == "unlocking"
    p.tick(1.4)
    assert p.phase == "celebrating"
    p.tick(3.2)
    assert p.phase == "unlocked"
    assert not p.rotate(1)
    assert not {"reward", "inventory", "story_week", "ed_sunglasses_granted"} & set(p.snapshot())
    assert not p.unassisted_candidate


@pytest.mark.parametrize("phase", ["rotating", "solved", "unlocking", "unlocked"])
def test_resume_each_phase(phase):
    p = RingPuzzle()
    if phase == "rotating":
        p.rotate(1)
        p.tick(0.07)
    else:
        solve(p)
        if phase in {"unlocking", "unlocked"}:
            p.tick(0.35)
        if phase == "unlocked":
            p.tick(1.4)
            p.tick(3.2)
    restored = RingPuzzle.restore(json.loads(json.dumps(p.snapshot())))
    assert restored == p
    p.tick(0.1)
    restored.tick(0.1)
    assert p == restored


@pytest.mark.parametrize(
    "patch",
    [
        {"angles": [0]},
        {"angles": [True, 1, 2, 3, 4]},
        {"angles": [12] * 5},
        {"selected": 5},
        {"phase": "unlocked"},
        {"elapsed": float("nan")},
        {"turn": 1},
        {"phase": "rotating", "turn": 1, "elapsed": 2},
    ],
)
def test_reject_corrupt_save(patch):
    raw = deepcopy(RingPuzzle().snapshot())
    raw.update(patch)
    with pytest.raises(ValueError):
        RingPuzzle.restore(raw)


def test_preview_store_roundtrip_and_retry_is_fresh():
    store = RingPreviewStore()
    p = RingPuzzle()
    p.rotate(1)
    assert store.save(p)
    assert store.load() == p
    assert store.save(RingPuzzle())
    assert store.load() == RingPuzzle()
    store.memory = "broken json"
    assert store.load() == RingPuzzle()


def test_polar_selection_boundaries_and_arrow_gutter():
    from drift_with_me.ring_puzzle import ring_pointer_action

    for i, radius in enumerate((15, 38, 54, 70, 86)):
        assert ring_pointer_action(256 + radius, 106) == f"ring{i}"
    for radius in (29, 30, 31, 45, 46, 47, 61, 62, 63, 77, 78, 79, 93, 94, 95, 100):
        assert ring_pointer_action(256 + radius, 106) is None
    assert ring_pointer_action(368, 106) == "right"
    assert ring_pointer_action(144, 106) == "left"
    assert ring_pointer_action(256, 6) is None
    assert ring_pointer_action(256, 218) is None


def test_thinking_animation_reuses_assets_and_is_presentation_only():
    from types import SimpleNamespace

    from drift_with_me.app import Rect
    from drift_with_me.ring_puzzle import RingPuzzlePreviewMixin, ring_pointer_action

    class Preview(RingPuzzlePreviewMixin):
        def office_rect(self, x, y, width, height):
            return Rect(x, y, width, height)

        def draw_office_text_in_rect(self, *args, **kwargs):
            pass

    calls = []
    frame = SimpleNamespace(width=32, height=32, image=0, u=0, v=0)
    asset = SimpleNamespace(frame=lambda: frame, definition=SimpleNamespace(colkey=0))
    app = Preview()
    app.ring_preview = RingPuzzle()
    app.runtime = SimpleNamespace(screen_width=512)
    app.sprite_assets = dict.fromkeys(
        ("jack_front_32", "jack_front_blink_32", "fuse_matte_thinking"), asset
    )
    app.pyxel = SimpleNamespace(
        blt=lambda *a, **k: calls.append((a, k)), circ=lambda *a: None, rect=lambda *a: None
    )
    for now in (0, 1.2, 2.4, 4.7):
        app.presentation_time = now
        app.draw_ring_thinking_characters()
    assert len(calls) == 8
    assert calls[0] != calls[2]
    assert all(abs(kwargs["rotate"]) <= 3 for _, kwargs in calls)
    assert ring_pointer_action(66, 148) is None
    assert ring_pointer_action(446, 146) is None


def test_character_reaction_rate_limit_and_unlocked_mood():
    from drift_with_me.ring_puzzle import RingPuzzlePreviewMixin

    preview = RingPuzzlePreviewMixin()
    preview.ring_preview_react(1.0)
    preview.ring_preview_react(1.5)
    assert preview.ring_reaction_at == 1.0
    preview.ring_preview_react(3.0)
    assert preview.ring_reaction_at == 3.0


def test_celebration_uses_all_eight_views_three_hops_and_resume_does_not_replay():
    from drift_with_me.ring_puzzle import celebration_pose

    views = {celebration_pose(i * 2.7 / 80, 0)[0] for i in range(81)}
    assert len(views) == 8
    assert celebration_pose(0.45, 0)[1] == pytest.approx(8)
    assert celebration_pose(1.35, 0)[1] == pytest.approx(8)
    assert celebration_pose(2.25, 0)[1] == pytest.approx(8)
    assert celebration_pose(0.1, 1) == ("front", 0)
    assert celebration_pose(3.2, 1) == ("front", 0)
    p = RingPuzzle(angles=[0] * 5, phase="celebrating", elapsed=1.0)
    restored = RingPuzzle.restore(p.snapshot())
    assert restored.phase == "unlocked"
    assert restored.elapsed == 0
    for _ in range(10):
        assert not restored.tick(1)
        assert restored.phase == "unlocked"


def test_legacy_unlocked_preview_stays_unlocked_without_new_celebration():
    raw = RingPuzzle(angles=[0] * 5, phase="unlocked").snapshot()
    raw = {k: raw[k] for k in ("version", "angles", "selected", "phase", "elapsed", "turn")}
    raw["version"] = 1
    assert RingPuzzle.restore(raw).phase == "unlocked"


def test_jack_happy_copy_changes_only_eyes_never_adds_a_mouth():
    from pathlib import Path
    from types import SimpleNamespace

    from drift_with_me.ring_puzzle import RingPuzzlePreviewMixin

    source = Path(__file__).parents[1] / "src/drift_with_me/assets/jack_front_00.hex"
    rows = [[int(c, 16) for c in row] for row in source.read_text().splitlines()]

    class Image:
        def __init__(self, width, height):
            self.pixels = [[0] * width for _ in range(height)]

        def blt(self, x, y, image, u, v, width, height):
            self.pixels = [row[:] for row in image]

        def rect(self, x, y, width, height, color):
            for yy in range(y, y + height):
                for xx in range(x, x + width):
                    self.pixels[yy][xx] = color

        def pset(self, x, y, color):
            self.pixels[y][x] = color

    app = RingPuzzlePreviewMixin()
    app.pyxel = SimpleNamespace(Image=Image)
    frame = SimpleNamespace(width=32, height=32, image=rows, u=0, v=0)
    happy = app.ring_happy_image("jack_front_32", frame)
    changes = {(x, y) for y in range(32) for x in range(32) if rows[y][x] != happy.pixels[y][x]}
    assert changes
    assert all(18 <= y <= 22 and (9 <= x <= 12 or 21 <= x <= 24) for x, y in changes)
    assert happy.pixels[23:] == rows[23:]
    assert app.ring_happy_image("jack_front_32", frame) is happy


def test_celebration_spins_once_per_hop_without_changing_ring_input_speed():
    from drift_with_me.ring_puzzle import ROTATION_SECONDS, celebration_pose

    assert ROTATION_SECONDS == 0.16
    assert celebration_pose(0.03, 0)[0] == celebration_pose(0.93, 0)[0]
    assert len({celebration_pose(0.02 + i * 0.1125, 0)[0] for i in range(8)}) == 8


def test_grid_slow_period_and_palette_isolation_without_puzzle_mutation():
    from types import SimpleNamespace

    from drift_with_me.input import Rect
    from drift_with_me.ring_puzzle import RingPuzzlePreviewMixin, ring_grid_level

    class Colors:
        def __init__(self):
            self.data = list(range(16))

        def to_list(self):
            return self.data[:]

        def from_list(self, data):
            self.data = data[:]

    class Preview(RingPuzzlePreviewMixin):
        def office_rect(self, x, y, width, height):
            return Rect(x, y, width, height)

    assert 0 <= ring_grid_level(0, 0, 0) <= 63
    assert (
        max(
            abs(ring_grid_level(80, 120, i / 60) - ring_grid_level(80, 120, (i + 1) / 60))
            for i in range(480)
        )
        <= 2
    )
    colors, lines = Colors(), []
    app = Preview()
    app.runtime = SimpleNamespace(screen_width=512, screen_height=236)
    app.pyxel = SimpleNamespace(
        colors=colors, line=lambda *args: lines.append(args), rect=lambda *args: None
    )
    p = RingPuzzle()
    before = p.snapshot()
    for now in (0, 2, 4, 6, 8):
        app.presentation_time = now
        app.draw_ring_background_grid()
        assert colors.data[:16] == list(range(16))
        assert len(colors.data) == 112
    assert 0 < len(lines) <= 1300 * 5
    assert p.snapshot() == before
    app.restore_ring_grid_palette()
    assert colors.data == list(range(16))


def test_grid_waves_advance_in_both_diagonals_with_capped_crossings():
    from drift_with_me.ring_puzzle import ring_grid_components, ring_grid_level

    # Each front travels along its own downwards diagonal, at about 120px/s.
    for component in (0, 1):

        def peak(seconds, component=component):
            def sample(distance):
                x = distance / 2 if component == 0 else 512 - distance / 2
                return ring_grid_components(x, distance / 2, seconds)[component]

            return max(range(30, 500), key=sample)

        assert 45 <= peak(1.5) - peak(1) <= 75
    samples = [
        ring_grid_level(x, y, t / 10)
        for x in (0, 96, 384, 512)
        for y in (0, 120, 236)
        for t in range(160)
    ]
    assert min(samples) >= 0 and max(samples) <= 63
    assert len(set(samples)) > 40
    assert ring_grid_components(96, 120, 1)[0] != ring_grid_components(96, 120, 1)[1]


def test_wave_speed_is_exactly_double_previous_trajectory_only():
    import math

    from drift_with_me.ring_puzzle import (
        GRID_PERIOD_SECONDS,
        ROTATION_SECONDS,
        ring_grid_components,
    )

    assert GRID_PERIOD_SECONDS == 6.0
    assert ROTATION_SECONDS == 0.16
    for x, y, seconds in ((0, 0, 0.5), (120, 80, 2), (420, 200, 4.5)):
        old_time = seconds * 2
        a = (x + y + 20 * math.sin((x - y) / 135 + old_time * 0.32)) / 720 - old_time / 12
        b = (
            (512 - x + y + 20 * math.sin((x + y) / 145 - old_time * 0.29)) / 720
            - old_time / 12
            - 0.23
        )
        expected = tuple((0.5 + 0.5 * math.cos(math.tau * phase)) ** 5 for phase in (a, b))
        assert ring_grid_components(x, y, seconds) == pytest.approx(expected)


def test_three_grid_lights_follow_lines_and_only_glow_on_arrival():
    from drift_with_me.ring_puzzle import grid_light_state

    for index in range(3):
        for step in range(500):
            x, y, ix, iy, glow = grid_light_state(step / 30, index)
            assert abs(x / 24 - round(x / 24)) < 1e-9 or abs(y / 24 - round(y / 24)) < 1e-9
            assert (ix % 24 == 0 or ix == -8) and iy % 24 == 0
            assert 0 <= glow <= 1
            if glow > 0:
                assert abs(x - ix) + abs(y - iy) <= 42 * 0.32
    assert len({grid_light_state(2, i)[:2] for i in range(3)}) == 3


def test_grid_light_speed_increase_preserves_paths_and_wave_period():
    from drift_with_me.ring_puzzle import GRID_PERIOD_SECONDS, grid_light_state

    assert GRID_PERIOD_SECONDS == 6
    for i, speed in enumerate((36, 30, 42)):
        x0, y0, *_ = grid_light_state(0, i)
        x1, y1, *_ = grid_light_state(0.1, i)
        assert abs(x1 - x0) + abs(y1 - y0) == pytest.approx(speed * 0.1)


def test_lights_branch_on_grid_without_global_rng_or_vertical_stalling():
    import random

    from drift_with_me.ring_puzzle import grid_light_route, grid_light_state

    rng_before = random.getstate()
    verticals = 0
    for index in range(3):
        for passage in range(4):
            points, distances = grid_light_route(index, passage)
            assert points[0][0] < 0 and points[-1][0] > 512
            for edge, (a, b) in enumerate(zip(points, points[1:], strict=False)):
                assert 24 <= b[1] <= 192
                assert b[0] >= a[0]
                assert b[0] == a[0] or b[1] == a[1]
                if b[1] != a[1]:
                    verticals += 1
                    assert abs(b[1] - a[1]) == 24
                    assert points[edge + 2][0] > b[0]
            assert all(b > a for a, b in zip(distances, distances[1:], strict=False))
        previous = grid_light_state(0, index)
        for step in range(1, 1200):
            current = grid_light_state(step / 30, index)
            if current[0] < previous[0]:
                assert previous[0] > 512 and current[0] < 0
            else:
                assert (
                    abs(current[0] - previous[0]) + abs(current[1] - previous[1]) <= 42 / 30 + 1e-8
                )
            previous = current
    assert verticals > 0
    for index in range(3):
        grid_light_state(1, index)
    misses = grid_light_route.cache_info().misses
    for index in range(3):
        for now in (1, 1.1, 1.2):
            grid_light_state(now, index)
    assert grid_light_route.cache_info().misses == misses
    assert random.getstate() == rng_before


def test_light_body_and_intersection_glow_stay_inside_vertical_screen_bounds():
    from types import SimpleNamespace

    from drift_with_me.input import Rect
    from drift_with_me.ring_puzzle import RingPuzzlePreviewMixin

    class Preview(RingPuzzlePreviewMixin):
        def office_rect(self, x, y, width, height):
            return Rect(
                x * self.w / 512, y * self.h / 236, width * self.w / 512, height * self.h / 236
            )

    for width, height in ((256, 118), (512, 236), (1024, 472)):
        app = Preview()
        app.w, app.h = width, height

        def rect(x, y, w, h, color, height=height):
            assert y >= 0 and y + h <= height

        def line(x1, y1, x2, y2, color, height=height):
            assert 0 <= min(y1, y2) <= max(y1, y2) < height

        app.pyxel = SimpleNamespace(rect=rect, line=line)
        for tick in range(1800):
            app.draw_ring_grid_lights(tick / 12, 80)


def test_light_body_is_fully_outside_right_before_reentering_left():
    from drift_with_me.ring_puzzle import grid_light_route, grid_light_state

    for index, (speed, offset) in enumerate(((36, 0), (30, 192), (42, 432))):
        total = 0
        for passage in range(5):
            total += grid_light_route(index, passage)[1][-1]
            crossing = (total - offset) / speed
            if crossing <= 0:
                continue
            before = grid_light_state(crossing - 0.001, index)
            after = grid_light_state(crossing + 0.001, index)
            assert before[0] - 1.5 > 512
            assert after[0] + 1.5 < 0
            assert 24 <= before[1] <= 192 and 24 <= after[1] <= 192


def test_round_rotation_buttons_have_large_separate_targets_and_keep_arches():
    from drift_with_me.ring_puzzle import ROTATION_TAP_BUTTONS, ring_pointer_action

    for action, x, y in ROTATION_TAP_BUTTONS:
        for dx, dy in ((0, 0), (21, 0), (-21, 0), (0, 21), (0, -21)):
            assert ring_pointer_action(x + dx, y + dy) == action
    assert ring_pointer_action(144, 106) == "left"
    assert ring_pointer_action(368, 106) == "right"
    assert ring_pointer_action(271, 106) == "ring0"


@pytest.mark.parametrize("x,direction", [(154, -1), (358, 1)])
def test_round_button_uses_one_step_and_same_rotation_lock(x, direction):
    from types import SimpleNamespace

    from drift_with_me.ring_puzzle import RingPuzzlePreviewMixin

    app = RingPuzzlePreviewMixin()
    app.runtime = SimpleNamespace(screen_width=512, screen_height=236)
    app.office_rect = lambda *args: SimpleNamespace()
    app.mouse_pressed_in = lambda rect: False
    app.key_pressed = lambda *args: False
    app.pointer_snapshot = SimpleNamespace(pressed=True, x=x, y=30)
    app.presentation_time = app.ring_preview_time = 0
    app.ring_preview = RingPuzzle()
    saved = []
    app.ring_preview_store = SimpleNamespace(save=lambda puzzle: saved.append(puzzle.snapshot()))
    app.update_ring_preview()
    assert app.ring_preview.angles[0] == (2 + direction) % 12
    assert len(saved) == 0
    app.presentation_time = 0.01
    app.update_ring_preview()
    assert app.ring_preview.angles[0] == (2 + direction) % 12
    assert len(saved) == 0


def test_idle_hint_at_ten_seconds_once_and_never_marks_help_or_save():
    from drift_with_me.ring_puzzle import IDLE_HINT_LINES, IDLE_HINT_TEXT, RingIdleHint

    assert IDLE_HINT_TEXT == "外側から順に計7回転で解けそうな初期配置ね"
    assert "".join(IDLE_HINT_LINES) == IDLE_HINT_TEXT
    p = RingPuzzle.create()
    before = p.snapshot()
    hint = RingIdleHint(0)
    hint.update(9.99, activity=False, eligible=True)
    assert not hint.visible and not hint.shown_once
    hint.update(10, activity=False, eligible=True)
    assert hint.visible and hint.shown_once
    assert p.snapshot() == before
    hint.update(10.1, activity=True, eligible=True)
    assert not hint.visible
    hint.update(30, activity=False, eligible=True)
    assert not hint.visible
    assert not p.eligibility_forfeited and p.help_history == []


def test_idle_hint_activity_resets_clock_and_blocked_phases_do_not_interrupt():
    from drift_with_me.ring_puzzle import RingIdleHint

    hint = RingIdleHint(0)
    hint.update(9, activity=True, eligible=True)
    hint.update(10, activity=False, eligible=True)
    assert not hint.visible
    hint.update(19, activity=False, eligible=False)
    assert not hint.visible and not hint.shown_once
    hint.update(20, activity=False, eligible=True)
    assert hint.visible
    hint.update(20.1, activity=False, eligible=False)
    assert not hint.visible


def test_idle_hint_rectangle_is_clear_of_puzzle_circle_buttons_and_footer():
    from types import SimpleNamespace

    from drift_with_me.ring_puzzle import RingIdleHint, RingPuzzlePreviewMixin

    app = RingPuzzlePreviewMixin()
    app.office_rect = lambda x, y, width, height: SimpleNamespace(
        x=x, y=y, width=width, height=height
    )
    app.ring_preview = RingPuzzle.create()
    app.ring_idle_hint = RingIdleHint(0, shown_once=True, visible=True)
    box = app.ring_idle_hint_rect()
    assert box.x > 380 and box.x + box.width <= 512
    assert box.y >= 44 and box.y + box.height < 134
    assert box.y + box.height < app.ring_preview_rects()["help"].y
    assert app.ring_idle_hint_visible()
    app.ring_preview.phase = "rotating"
    assert not app.ring_idle_hint_visible()
    app.ring_preview.phase = "unlocked"
    assert not app.ring_idle_hint_visible()
    app.ring_preview.phase = "idle"
    app.ring_preview.assist()
    assert app.ring_idle_hint_visible()


def test_quit_closes_without_save_and_removes_duplicate_back():
    from types import SimpleNamespace

    from drift_with_me.ring_puzzle import RingPuzzlePreviewMixin

    app = RingPuzzlePreviewMixin()
    app.office_rect = lambda x, y, w, h: (x, y, w, h)
    app.mouse_pressed_in = lambda r: r == (8, 206, 116, 28)
    app.key_pressed = lambda *args: False
    app.pointer_snapshot = SimpleNamespace(pressed=True)
    app.presentation_time = app.ring_preview_time = 0
    app.ring_preview = RingPuzzle.create()
    saved = []
    app.ring_preview_store = SimpleNamespace(save=lambda p: saved.append(p.snapshot()))
    app.restore_ring_grid_palette = lambda: None
    assert set(app.ring_preview_rects()) == {"quit", "help", "retry", "undo"}
    app.update_ring_preview()
    assert app.ring_preview is None and app.week_debug_menu_open
    assert saved == []


def test_session_discards_old_midgame_bytes_but_preserves_help_and_completion():
    store = RingPreviewStore("linked")
    p = RingPuzzle.create()
    p.assist()
    p.rotate(1)
    p.tick(1)
    store.save(p)
    old = store.memory
    fresh = store.load_session()
    assert fresh.angles == [1, 0, 5, 0, 11]
    assert fresh.disabled_links == fresh.help_history == [4]
    assert fresh.eligibility_forfeited and not fresh.undo_history
    assert store.memory == old
    p.angles, p.phase = [0] * 5, "unlocked"
    store.save_progress(p)
    assert store.load_session().phase == "unlocked"
    store.save_progress(p.retry())
    assert store.load_session().phase == "unlocked"
    assert store.memory == old
    assert (
        not {"angles", "selected", "turn", "undo_history"}
        & json.loads(store.progress_memory).keys()
    )


def test_undo_is_atomic_completed_rotation_only_and_cannot_undo_help():
    p = RingPuzzle.create()
    before = p.angles[:]
    assert not p.undo()
    p.selected = 3
    p.rotate(1)
    assert not p.undo()
    p.tick(1)
    assert p.move_count == 1 and p.can_undo
    assert p.undo() and p.angles == before and p.move_count == 0
    p.rotate(-1)
    p.tick(1)
    p.assist()
    assert not p.undo() and p.eligibility_forfeited
    after_help = p.angles[:]
    p.rotate(1)
    p.tick(1)
    assert p.undo() and p.angles == after_help
    assert p.help_history == [4] and p.eligibility_forfeited
    for phase in ("rotating", "solved", "unlocking", "celebrating", "unlocked"):
        p.phase = phase
        assert not p.undo()


def test_intro_two_lines_three_second_delay_and_no_help_or_overlap():
    from drift_with_me.ring_puzzle import INTRO_LINES, RingPuzzlePreviewMixin

    app = RingPuzzlePreviewMixin()
    app.ring_preview = RingPuzzle.create()
    app.ring_intro_started = None
    app.ring_intro_done = False
    app.ring_intro_entry = 0
    before = app.ring_preview.snapshot()
    assert INTRO_LINES == ("解けたら、", "ご褒美あげちゃう！")
    assert not app.update_ring_intro(2.99)
    assert app.update_ring_intro(3)
    assert app.update_ring_intro(8.99)
    assert not app.update_ring_intro(9)
    assert app.ring_preview.snapshot() == before
    app.ring_intro_done = False
    app.ring_preview.phase = "unlocking"
    assert not app.update_ring_intro(5)
    assert app.ring_intro_done
