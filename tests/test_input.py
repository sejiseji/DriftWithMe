from __future__ import annotations

from drift_with_me.input import DoubleTapMoveRecognizer, PointerInput, PointerState, Rect
from drift_with_me.math3d import CameraState, Vec3


def make_pointer() -> PointerInput:
    return PointerInput(hold_sec=0.22, drag_threshold_px=8.0, deadzone_px=8.0, radius_px=48.0)


def make_camera() -> CameraState:
    return CameraState(
        target=Vec3(160.0, 0.0, 160.0),
        yaw_deg=20.0,
        pitch_deg=25.0,
        horizontal_fov_deg=38.0,
        distance=480.0,
        near=8.0,
        far=1800.0,
        anchor_x=0.5,
        anchor_y=0.58,
        viewport_width=512,
        viewport_height=236,
    )


def make_double_tap() -> DoubleTapMoveRecognizer:
    return DoubleTapMoveRecognizer(
        short_tap_sec=0.18,
        max_interval_sec=0.3,
        max_distance_px=20.0,
        drag_threshold_px=8.0,
    )


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


def test_double_tap_fires_on_second_short_release() -> None:
    recognizer = make_double_tap()
    camera = make_camera()

    assert recognizer.update(True, 50.0, 60.0, 0.0, (), camera) is None
    assert recognizer.update(False, 50.0, 60.0, 0.06, (), camera) is None
    assert recognizer.update(False, 50.0, 60.0, 0.12, (), camera) is None
    assert recognizer.update(True, 56.0, 62.0, 0.0, (), camera) is None
    request = recognizer.update(False, 56.0, 62.0, 0.07, (), camera)

    assert request is not None
    assert request.screen_x == 56.0
    assert request.screen_y == 62.0
    assert request.camera == camera


def test_double_tap_ignores_ui_owned_press() -> None:
    recognizer = make_double_tap()
    camera = make_camera()
    ui_rects = (Rect(0.0, 0.0, 80.0, 80.0),)

    recognizer.update(True, 50.0, 60.0, 0.0, ui_rects, camera)
    recognizer.update(False, 50.0, 60.0, 0.05, ui_rects, camera)
    recognizer.update(True, 50.0, 60.0, 0.0, ui_rects, camera)
    request = recognizer.update(False, 50.0, 60.0, 0.05, ui_rects, camera)

    assert request is None


def test_double_tap_does_not_count_drag_release() -> None:
    recognizer = make_double_tap()
    camera = make_camera()

    recognizer.update(True, 50.0, 60.0, 0.0, (), camera)
    recognizer.update(True, 70.0, 60.0, 0.04, (), camera)
    assert recognizer.update(False, 70.0, 60.0, 0.04, (), camera) is None
    recognizer.update(True, 50.0, 60.0, 0.0, (), camera)
    request = recognizer.update(False, 50.0, 60.0, 0.04, (), camera)

    assert request is None
