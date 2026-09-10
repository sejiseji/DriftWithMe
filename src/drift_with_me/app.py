from __future__ import annotations

from dataclasses import dataclass
from math import cos, sin

from drift_with_me import config


@dataclass
class DriverState:
    x: float = config.SCREEN_WIDTH / 2
    y: float = config.SCREEN_HEIGHT / 2
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    angle: float = 0.0


@dataclass(frozen=True)
class DriverInput:
    steer: int = 0
    throttle: bool = False
    brake: bool = False
    boost: bool = False


def step_driver(state: DriverState, controls: DriverInput) -> DriverState:
    turn_rate = 0.08
    acceleration = 0.075 if controls.throttle else 0.0
    if controls.boost and controls.throttle:
        acceleration = 0.13

    next_angle = state.angle + controls.steer * turn_rate
    next_vx = state.velocity_x + cos(next_angle) * acceleration
    next_vy = state.velocity_y + sin(next_angle) * acceleration

    drag = 0.965
    if controls.brake:
        drag = 0.9

    next_vx *= drag
    next_vy *= drag
    next_x = (state.x + next_vx) % config.SCREEN_WIDTH
    next_y = (state.y + next_vy) % config.SCREEN_HEIGHT

    return DriverState(
        x=next_x,
        y=next_y,
        velocity_x=next_vx,
        velocity_y=next_vy,
        angle=next_angle,
    )


class DriftWithMeApp:
    def __init__(self, headless: bool = False, smoke_frames: int | None = None) -> None:
        import pyxel

        self.pyxel = pyxel
        self.driver = DriverState()
        self.frame = 0
        self.smoke_frames = smoke_frames

        pyxel.init(
            config.SCREEN_WIDTH,
            config.SCREEN_HEIGHT,
            title=config.WINDOW_TITLE,
            fps=config.FPS,
            headless=headless,
        )
        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        pyxel = self.pyxel

        if pyxel.btnp(pyxel.KEY_ESCAPE):
            pyxel.quit()
            return
        if pyxel.btnp(pyxel.KEY_R):
            self.driver = DriverState()

        steer = int(pyxel.btn(pyxel.KEY_RIGHT)) - int(pyxel.btn(pyxel.KEY_LEFT))
        controls = DriverInput(
            steer=steer,
            throttle=pyxel.btn(pyxel.KEY_UP),
            brake=pyxel.btn(pyxel.KEY_DOWN),
            boost=pyxel.btn(pyxel.KEY_Z),
        )
        self.driver = step_driver(self.driver, controls)

        self.frame += 1
        if self.smoke_frames is not None and self.frame >= self.smoke_frames:
            pyxel.quit()

    def draw(self) -> None:
        pyxel = self.pyxel
        pyxel.cls(config.BACKGROUND_COLOR)
        self.draw_track()
        self.draw_driver()
        pyxel.text(8, 8, config.WINDOW_TITLE, config.TEXT_COLOR)
        pyxel.text(8, 18, "SPEC PENDING", config.ACCENT_COLOR)

    def draw_track(self) -> None:
        pyxel = self.pyxel
        center_y = config.SCREEN_HEIGHT // 2
        pyxel.rect(0, center_y - 44, config.SCREEN_WIDTH, 88, config.ROAD_COLOR)
        for x in range(-32, config.SCREEN_WIDTH + 32, 32):
            offset = (self.frame // 2) % 32
            pyxel.line(x - offset, center_y, x + 14 - offset, center_y, config.ROAD_LINE_COLOR)

    def draw_driver(self) -> None:
        pyxel = self.pyxel
        x = self.driver.x
        y = self.driver.y
        angle = self.driver.angle
        nose_x = x + cos(angle) * 8
        nose_y = y + sin(angle) * 8
        left_x = x + cos(angle + 2.45) * 6
        left_y = y + sin(angle + 2.45) * 6
        right_x = x + cos(angle - 2.45) * 6
        right_y = y + sin(angle - 2.45) * 6

        pyxel.circ(int(x) + 2, int(y) + 2, 5, config.SHADOW_COLOR)
        pyxel.tri(
            int(nose_x),
            int(nose_y),
            int(left_x),
            int(left_y),
            int(right_x),
            int(right_y),
            config.PLAYER_COLOR,
        )
        pyxel.pset(int(nose_x), int(nose_y), config.TEXT_COLOR)


def main() -> None:
    DriftWithMeApp()


if __name__ == "__main__":
    main()
