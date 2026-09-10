from __future__ import annotations

from drift_with_me.app import DriverInput, DriverState, step_driver


def test_driver_accelerates_when_throttle_is_pressed() -> None:
    before = DriverState()
    after = step_driver(before, DriverInput(throttle=True))

    assert after.x > before.x
    assert after.velocity_x > 0


def test_driver_wraps_inside_screen_bounds() -> None:
    before = DriverState(x=255.9, y=191.9, velocity_x=3.0, velocity_y=3.0)
    after = step_driver(before, DriverInput())

    assert 0 <= after.x < 256
    assert 0 <= after.y < 192
