from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from drift_with_me import config
from drift_with_me.office import (
    OfficePrototype,
    parse_case_definitions,
    parse_counter_script_definitions,
)


@dataclass(frozen=True)
class WorkWeek:
    month: int = 6
    number: int = 1

    def __post_init__(self) -> None:
        if self.month not in (6, 7, 8) or self.number not in (1, 2, 3, 4):
            raise ValueError("week outside the twelve summer workdays")

    @property
    def label(self) -> str:
        return f"{self.month}月 第{self.number}週"

    def following(self) -> WorkWeek | None:
        if self.number < 4:
            return WorkWeek(self.month, self.number + 1)
        return WorkWeek(self.month + 1, 1) if self.month < 8 else None


def load_week_office(week: WorkWeek) -> OfficePrototype | None:
    if week == WorkWeek(6, 4):
        from drift_with_me.week4 import Week4Office

        return Week4Office()
    if week == WorkWeek(6, 3):
        from drift_with_me.week3 import Week3Office

        return Week3Office()
    # Unauthored days remain absent.
    if week != WorkWeek(6, 2):
        return None
    raw = config.load_data_json("office_week2_grow.json")
    cases = parse_case_definitions(raw)
    scripts = parse_counter_script_definitions(raw["counter_scripts"], cases)
    return OfficePrototype(cases, scripts)


@dataclass
class WeekTransition:
    target: WorkWeek
    fade_out: float = 0.55
    title_hold: float = 1.25
    fade_in: float = 0.65
    elapsed: float = 0.0
    applied: bool = False

    def __post_init__(self) -> None:
        if any(not math.isfinite(v) or v <= 0 for v in self.durations):
            raise ValueError("week transition durations must be positive and finite")

    @property
    def durations(self) -> tuple[float, float, float]:
        return self.fade_out, self.title_hold, self.fade_in

    @property
    def total(self) -> float:
        return sum(self.durations)

    @property
    def complete(self) -> bool:
        return self.elapsed >= self.total

    @property
    def showing_title(self) -> bool:
        return self.fade_out <= self.elapsed < self.fade_out + self.title_hold

    @property
    def darkness(self) -> float:
        if self.elapsed < self.fade_out:
            return self.elapsed / self.fade_out
        if self.showing_title:
            return 1.0
        return max(0.0, 1 - (self.elapsed - self.fade_out - self.title_hold) / self.fade_in)

    def advance(self, dt: float, apply_at_black: Callable[[], None]) -> None:
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("elapsed time must be finite and nonnegative")
        target_time = min(self.total, self.elapsed + dt)
        if not self.applied and target_time >= self.fade_out:
            self.elapsed = self.fade_out
            apply_at_black()
            self.applied = True
        self.elapsed = target_time
