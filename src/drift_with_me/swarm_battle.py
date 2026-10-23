"""Six-enemy capture timing, followed by a non-judged finisher wait."""

from __future__ import annotations

import math
from dataclasses import dataclass

CAPTURE_SHORT = "ジャック「足止めする水が足りない！補給してこよう！」"
NORMAL_SHORT = "ジャック「水が無くてとどめを刺せない！補給しよう！」"
ENERGY_SHORT = "ヒューズ「だめ！電力が足りない！充電が必要！」"
MIXED_SHORT = "ヒューズ「混ざってるからタイミングが・・・！水補給して同時に攻撃しよう！」"
RETREAT = "フジ「クソッ・・・いったん引くぞ！」"
ASSIST = "フジ「ここは俺が抑える！もう一度合わせろ！」"
# Left/right outward arcs of one ellipse, centered on Jack. Middle enemies
# are furthest OUT from Jack; the old inward-pointing formation is removed.
CENTER = (320.0, 174.0)
RADII = (250.0, 100.0)
ANGLES = (225, 180, 135, 315, 0, 45)
STARTS = tuple(
    (
        CENTER[0] + RADII[0] * math.cos(math.radians(a)),
        CENTER[1] + RADII[1] * math.sin(math.radians(a)),
    )
    for a in ANGLES
)
KINDS = ("urchin", "slug", "urchin", "slug", "urchin", "slug")
PRESETS = {
    "normal": (100, 100),
    "capture-water": (0, 100),
    "finish-water": (12, 100),
    "energy": (100, 0),
    "both": (12, 0),
}


@dataclass(frozen=True)
class Settings:
    capture_water: float = 12
    finish_water: float = 12
    finish_energy: float = 20
    entry: float = 0.83
    ready: float = 1.59
    finish_wait: float = 1.35
    cutin: float = 0.85
    knockback: float = 18
    float_height: float = 8
    sweep: float = 1.75
    target: float = 0.72
    radius: float = 0.09
    bound_hold: float = 0.65
    shock: float = 0.5
    assist: float = 1.6
    retreat_line: float = 2.2
    fade: float = 0.7
    electric: float = 0.8
    circle: float = 0.65
    converge: float = 0.55
    spear: float = 2.0


class SwarmBattle:
    def __init__(self, water=100, energy=100, settings=None, spawn=(160.0, 160.0)):
        self.settings = settings or Settings()
        self.water, self.energy = water, energy
        self.spawn = tuple(spawn)
        self.position = (512.0, 512.0)
        self.phase = "entry"
        self.elapsed = 0.0
        self.total_elapsed = 0.0
        self.capture_elapsed = 0.0
        self.finish_requested = False
        self.finisher_elapsed = 0.0
        self.progress = 0.0
        self.capture_progress = 0.0
        self.assists = 1
        self.failures = 0
        self.captured = False
        self.defeated = set()
        self.message = "全体捕縛：青い範囲で入力"
        self.events = []

    def enter(self, phase, message=None):
        self.phase, self.elapsed = phase, 0.0
        if message is not None:
            self.message = message
        self.events.append(phase)

    def enemy_position(self, index):
        x, y = STARTS[index]
        # Every enemy uses the same normalized bar progress from its own home.
        p = self.capture_progress if self.captured else self.progress
        return x + (320 - x) * p * 0.78, y + (CENTER[1] - y) * p * 0.78

    def retreat(self, message):
        self.enter("retreat_line", message)

    def fail(self):
        if self.phase != "approach":
            return
        self.failures += 1
        self.enter("shake", "タイミング失敗")

    def input(self):
        if self.phase == "finish_wait":
            self.finish_requested = True
            return
        if self.phase != "approach":
            return
        s = self.settings
        if abs(self.progress - s.target) > s.radius:
            self.fail()
            return
        if self.water < s.capture_water:
            self.retreat(CAPTURE_SHORT)
            return
        self.water -= s.capture_water
        self.captured = True
        self.capture_progress = self.progress
        self.capture_elapsed = 0
        self.enter("bound", "全体捕縛！")

    def finish(self):
        if self.phase != "finish_wait":
            return
        s = self.settings
        # Atomic preflight before either species dies; repeated input cannot pay twice.
        if self.energy < s.finish_energy:
            self.retreat(ENERGY_SHORT)
        elif self.water < s.finish_water:
            self.retreat(MIXED_SHORT)
        else:
            self.water -= s.finish_water
            self.energy -= s.finish_energy
            self.enter("electric", "ヒューズ：電撃！")

    def tick(self, dt):
        if dt < 0:
            raise ValueError("dt must be nonnegative")
        self.elapsed += dt
        self.total_elapsed += dt
        if self.captured:
            self.capture_elapsed += dt
        if self.phase in {"electric", "circle", "converge", "spear"}:
            self.finisher_elapsed += dt
        s = self.settings
        if self.phase == "finish_wait":
            if self.elapsed >= s.finish_wait or self.finish_requested and self.elapsed >= s.cutin:
                self.finish()
            return
        if self.phase == "approach":
            self.progress = min(1.0, self.elapsed / s.sweep)
            if self.progress >= 1:
                self.fail()
            return
        durations = {
            "entry": s.entry,
            "ready": s.ready,
            "bound": s.bound_hold,
            "shake": s.shock,
            "assist": s.assist,
            "retreat_line": s.retreat_line,
            "fade": s.fade,
            "electric": s.electric,
            "circle": s.circle,
            "converge": s.converge,
            "spear": s.spear,
        }
        if self.elapsed < durations.get(self.phase, float("inf")):
            return
        if self.phase == "entry":
            self.enter("ready", "捕縛の準備")
        elif self.phase == "ready":
            self.progress = 0
            self.enter("approach", "全体捕縛：ボタンで入力")
        elif self.phase == "bound":
            self.enter("finish_wait", "電撃 → 水槍：待機中（ボタンで開始予約）")
        elif self.phase == "shake":
            if self.assists:
                self.assists -= 1
                self.enter("assist", ASSIST)
            else:
                self.retreat(RETREAT)
        elif self.phase == "assist":
            self.progress = 0
            self.enter("ready", "もう一度！")
        elif self.phase == "retreat_line":
            self.enter("fade")
        elif self.phase == "fade":
            self.position = self.spawn
            self.enter("field", "南西の初期位置へ撤退。資源はそのまま。R：再戦")
        elif self.phase == "electric":
            self.defeated.update(i for i, kind in enumerate(KINDS) if kind == "urchin")
            self.enter("circle", "ジャック：水流を集めて・・・")
        elif self.phase == "circle":
            self.enter("converge")
        elif self.phase == "converge":
            self.enter("spear", "ジャック：水柱！")
        elif self.phase == "spear":
            self.defeated.update(range(6))
            self.enter("victory", "6体撃退！ 電撃 → 水槍、追加入力なし。R：再戦")

    def rematch(self):
        if self.phase in ("field", "victory"):
            self.__init__(self.water, self.energy, self.settings, self.spawn)
