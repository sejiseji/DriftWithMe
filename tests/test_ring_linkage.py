from itertools import product

import pytest

from drift_with_me.ring_linkage import (
    ASSIST_ORDER,
    LINK_SIGNS,
    LINKED_INITIAL,
    SCRAMBLE,
    apply_move,
    move_deltas,
    solution_counts,
)
from drift_with_me.ring_puzzle import RingPreviewStore, RingPuzzle


def perform(p, index, direction):
    p.selected = index
    assert p.rotate(direction)
    p.tick(0.16)


def finish_with_counts(p):
    for i, count in enumerate(solution_counts(p.angles, p.disabled_links)):
        direction = 1 if count <= 6 else -1
        for _ in range(min(count, 12 - count)):
            perform(p, i, direction)


def test_fixed_scramble_and_minimum_seven_input_counts():
    state = (0,) * 5
    for i, direction in SCRAMBLE:
        state = apply_move(state, i, direction)
    assert state == LINKED_INITIAL == (1, 0, 5, 0, 11)
    assert sum(min(c, 12 - c) for c in solution_counts(state)) == 7
    p = RingPuzzle.create()
    finish_with_counts(p)
    assert p.phase == "solved" and p.unassisted_candidate


@pytest.mark.parametrize("selected", range(5))
def test_only_direct_outer_neighbour_moves_and_animates(selected):
    p = RingPuzzle.create()
    p.selected = selected
    before = p.angles[:]
    assert p.rotate(1)
    delta = move_deltas(selected, 1)
    assert p.angles == [(a + d) % 12 for a, d in zip(before, delta, strict=True)]
    assert sum(d != 0 for d in delta) == (3 if selected == 3 else 2 if selected < 4 else 1)
    for i in range(5):
        expected = before[i] * 3.141592653589793 / 6 - 3.141592653589793 / 2
        # Display remains at the pre-move angle (modulo a full turn) at animation start.
        assert (p.display_angle(i) - expected) % (2 * 3.141592653589793) == pytest.approx(0)
    saved = RingPuzzle.restore(p.snapshot())
    assert saved == p
    assert not p.assist()


def test_all_sixteen_assistance_subsets_have_unit_triangular_inverse():
    samples = [(0, 0, 0, 0, 0), LINKED_INITIAL, (11, 7, 3, 6, 9)]
    samples += list(product((0, 1, 6, 11), repeat=5))
    for mask in range(16):
        disabled = [4] + [i for i in range(4) if mask >> i & 1]
        for state in samples:
            counts = solution_counts(state, disabled)
            for i in range(5):
                previous = LINK_SIGNS[i - 1] * counts[i - 1] if i and i - 1 not in disabled else 0
                assert (state[i] + counts[i] + previous) % 12 == 0


def test_help_never_resets_board_and_retry_never_restores_eligibility():
    p = RingPuzzle.create()
    perform(p, 2, 1)
    for stage, _link in enumerate(ASSIST_ORDER):
        before = p.angles[:]
        assert p.assist()
        assert p.angles == before
        assert p.help_history == list(ASSIST_ORDER[: stage + 1])
        assert p.eligibility_forfeited
        saved = RingPuzzle.restore(p.snapshot())
        assert saved == p
        retried = saved.retry()
        assert retried.help_history == saved.help_history
        assert retried.disabled_links == saved.disabled_links
        assert retried.eligibility_forfeited
        finish_with_counts(retried)
        assert retried.phase == "solved"
        assert not retried.unassisted_candidate
    assert not p.assist()


def test_debug_modes_and_stores_do_not_mix():
    linked, solo = RingPreviewStore("linked"), RingPreviewStore()
    p = linked.load()
    assert p.mode == "linked" and tuple(p.angles) == LINKED_INITIAL
    assert p.assist() and linked.save(p)
    assert not solo.save(p)
    assert solo.load().mode == "independent"
    assert linked.load().help_history == [4]
    linked.memory = "bad record"
    assert linked.load().eligibility_forfeited


@pytest.mark.parametrize(
    "patch",
    [
        {"help_history": [0], "disabled_links": [0]},
        {"help_history": [0, 0], "disabled_links": [0], "eligibility_forfeited": True},
        {"help_history": [0], "disabled_links": [], "eligibility_forfeited": True},
        {"disabled_links": [5]},
        {"mode": "story"},
        {"turn_deltas": [1, 0, 0, 0, 0]},
    ],
)
def test_reject_inconsistent_help_or_motion_save(patch):
    raw = RingPuzzle.create().snapshot()
    raw.update(patch)
    with pytest.raises(ValueError):
        RingPuzzle.restore(raw)


def test_new_fourth_ring_has_two_direct_neighbours_without_recursive_feedback():
    assert move_deltas(3, 1) == [0, 0, -1, 1, 1]
    assert move_deltas(3, -1) == [0, 0, 1, -1, -1]
    assert move_deltas(2, 1) == [0, 0, 1, 1, 0]
    p = RingPuzzle.create()
    before = p.angles[:]
    assert p.assist()
    assert p.disabled_links == [4] and p.angles == before
    assert move_deltas(3, 1, p.disabled_links) == [0, 0, 0, 1, 1]


def test_full_links_parity_and_unsafe_first_removal_are_detected():
    from drift_with_me.ring_linkage import all_solution_counts

    assert not all_solution_counts((1, 0, 0, 0, 0))
    reachable = apply_move((0,) * 5, 0, 1)
    assert all_solution_counts(reachable)
    assert not all_solution_counts(reachable, (0,))
    assert all_solution_counts(reachable, (4,))
    raw = RingPuzzle.create().snapshot()
    raw["angles"] = [1, 0, 0, 0, 0]
    with pytest.raises(ValueError):
        RingPuzzle.restore(raw)
    raw = RingPuzzle.create().snapshot()
    raw.update(disabled_links=[0], help_history=[0], eligibility_forfeited=True)
    with pytest.raises(ValueError):
        RingPuzzle.restore(raw)


def test_previous_linked_save_archived_fresh_legal_board_and_forfeiture_kept():
    import json

    old = RingPuzzle.create().snapshot()
    old.pop("ruleset")
    old.pop("legacy_help_history")
    old.update(
        version=3,
        angles=[1, 0, 2, 2, 11],
        disabled_links=[0],
        help_history=[0],
        eligibility_forfeited=True,
    )
    payload = json.dumps(old)
    with pytest.raises(ValueError):
        RingPuzzle.restore(old)
    store = RingPreviewStore("linked")
    store.legacy_memory = payload
    p = store.load()
    assert tuple(p.angles) == LINKED_INITIAL
    assert p.phase == "idle" and p.help_history == p.disabled_links == []
    assert p.legacy_help_history == [0] and p.eligibility_forfeited
    assert store.legacy_memory == payload
    assert store.load() == p
    assert p.retry().legacy_help_history == [0]
    assert p.retry().eligibility_forfeited
    assert not p.unassisted_candidate


def test_previous_independent_schema_three_still_loads():
    p = RingPuzzle()
    p.rotate(1)
    old = p.snapshot()
    old.pop("ruleset")
    old.pop("legacy_help_history")
    old["version"] = 3
    restored = RingPuzzle.restore(old)
    assert restored.mode == "independent"
    assert restored.angles == p.angles and restored.turn_deltas == p.turn_deltas


def test_approved_outer_to_inner_seven_rotations_match_hint_without_assistance():
    p = RingPuzzle.create()
    assert tuple(p.angles) == (1, 0, 5, 0, 11)
    moves = ((4, -1), (3, 1), (3, 1), (2, -1), (2, -1), (1, 1), (0, -1))
    assert [i for i, _ in moves] == sorted((i for i, _ in moves), reverse=True)
    for i, direction in moves:
        perform(p, i, direction)
    assert len(moves) == 7 and p.angles == [0] * 5
    assert p.unassisted_candidate and p.help_history == []
