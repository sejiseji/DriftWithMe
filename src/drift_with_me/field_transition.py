"""Travel presentation; world simulation and reporting remain separate."""

from __future__ import annotations

import math
from dataclasses import dataclass

from drift_with_me.field_visit import FieldProgress
from drift_with_me.office import FieldResult


def travel_lines(
    direction: str,
    progress: FieldProgress | None,
    *,
    interrupted: bool = False,
    case_id: str | None = "OFF-PROT-003",
) -> tuple[tuple[str, str], ...]:
    if case_id != "OFF-PROT-003" and progress is not None:
        if direction == "out":
            return (
                ("ジャック", "近くから様子を見ていこう。"),
                ("ヒューズ", "ええ。足元には気をつけてね。"),
            )
        if progress.can_report:
            return (
                ("ジャック", "今見たことを、戻って伝えよう。"),
                ("ヒューズ", "ええ。分かったところから話しましょう。"),
            )
    if direction == "out":
        jack = (
            "北側の浅瀬だね。足元を見ながら行こう。"
            if progress is not None
            else "少し外を歩いてこよう。"
        )
        fuse = "ええ。無理せず、近くから見ていきましょう。"
    elif progress is None or (not progress.can_report and not interrupted):
        jack, fuse = (
            "まだ確かめられてないけど、一度戻ろうか。",
            "いいわよ。続きは、また見に来ましょう。",
        )
    elif progress.dealt_target_ids:
        jack, fuse = (
            "あの個体には対処できたね。戻ろう。",
            "ええ。でも音の原因は、まだ分からないわね。",
        )
    elif interrupted or progress.interrupted:
        jack, fuse = (
            "ここから先は危ないな。いったん戻ろう。",
            "ええ。無理しないで。見られたところまで伝えましょう。",
        )
    elif progress.enemy_ids:
        jack, fuse = (
            "変わった個体はいたけど、音の原因までは分からないな。",
            "そうね。確かめたことだけ伝えましょう。",
        )
    elif len(progress.observations) >= 3:
        jack, fuse = (
            "蛇口とロボと柱は見られたね。戻ろう。",
            "ええ。音の原因は、まだ決めつけないでおきましょう。",
        )
    else:
        jack, fuse = (
            "まだ見てない所もあるけど、いったん戻ろう。",
            "ええ。今分かったところを伝えましょう。",
        )
    return (("ジャック", jack), ("ヒューズ", fuse))


@dataclass
class FieldTransition:
    direction: str
    lines: tuple[tuple[str, str], ...]
    report: FieldResult | None = None
    phase: str = "fade_out"
    elapsed: float = 0.0
    index: int = 0
    applied: bool = False
    wait_release: bool = True
    fade_out: float = 0.45
    fade_in: float = 0.55

    def __post_init__(self) -> None:
        if self.direction not in {"out", "back"} or len(self.lines) != 2:
            raise ValueError("travel needs a direction and one exchange")
        if self.direction == "back":
            self.phase = "dialogue"

    @property
    def darkness(self) -> float:
        if self.phase == "fade_out":
            return min(1.0, self.elapsed / self.fade_out)
        if self.phase == "black":
            return 1.0
        if self.phase == "fade_in":
            return max(0.0, 1.0 - self.elapsed / self.fade_in)
        return 0.0

    def tick(self, dt: float) -> None:
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("elapsed must be finite and nonnegative")
        if self.phase not in {"fade_out", "fade_in"}:
            return
        self.elapsed += dt
        if self.phase == "fade_out" and self.elapsed >= self.fade_out:
            self.phase, self.elapsed = "black", 0.0
        elif self.phase == "fade_in" and self.elapsed >= self.fade_in:
            self.phase, self.elapsed = ("dialogue" if self.direction == "out" else "done"), 0.0
            self.wait_release = True

    def advance(self) -> None:
        if self.phase != "dialogue":
            return
        if self.index == 0:
            self.index = 1
        else:
            self.phase = "done" if self.direction == "out" else "fade_out"
            self.elapsed = 0.0
        self.wait_release = True
