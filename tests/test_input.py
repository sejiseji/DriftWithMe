from __future__ import annotations

from drift_with_me.input import PointerInput, PointerState, Rect


def make_pointer() -> PointerInput:
    return PointerInput(hold_sec=0.22, drag_threshold_px=8.0, deadzone_px=8.0, radius_px=48.0)


def test_drag_keeps_move_ownership_even_after_hold_time() -> None:
    pointer = make_pointer()

    pointer.update(True, 10.0, 10.0, 0.0)
    first = pointer.update(True, 30.0, 10.0, 0.05)
    second = pointer.update(True, 30.0, 10.0, 0.5)

    assert pointer.state is PointerState.MOVE
    assert first.strength > 0.0
    assert second.strength > 0.0
    assert not second.barrier


def test_stationary_hold_becomes_barrier() -> None:
    pointer = make_pointer()

    pointer.update(True, 10.0, 10.0, 0.0)
    intent = pointer.update(True, 12.0, 10.0, 0.23)

    assert pointer.state is PointerState.BARRIER
    assert intent.barrier


def test_ui_capture_does_not_leak_into_world_drag() -> None:
    pointer = make_pointer()

    pointer.update(True, 10.0, 10.0, 0.0, (Rect(0.0, 0.0, 44.0, 44.0),))
    intent = pointer.update(True, 120.0, 10.0, 0.5, (Rect(0.0, 0.0, 44.0, 44.0),))

    assert pointer.state is PointerState.UI_CAPTURE
    assert intent.strength == 0.0
    assert not intent.barrier


def test_cancel_waits_for_release_before_world_input() -> None:
    pointer = make_pointer()

    pointer.cancel()
    held = pointer.update(True, 40.0, 40.0, 0.3)
    released = pointer.update(False, 40.0, 40.0, 0.0)
    pointer.update(True, 40.0, 40.0, 0.0)
    moved = pointer.update(True, 80.0, 40.0, 0.05)

    assert held.strength == 0.0
    assert not held.barrier
    assert released.strength == 0.0
    assert pointer.state is PointerState.MOVE
    assert moved.strength > 0.0
