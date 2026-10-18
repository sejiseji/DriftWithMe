"""Independent-ring prototype. Its save namespace never contains story progress."""

from __future__ import annotations

import json
import math
import random
import sys
from bisect import bisect_right
from dataclasses import dataclass, field
from functools import lru_cache

from drift_with_me.ring_linkage import (
    ASSIST_ORDER,
    LINKED_INITIAL,
    RULESET,
    move_deltas,
)

STEPS = 12
INITIAL = (2, 10, 3, 9, 1)
ROTATION_SECONDS = 0.16
SOLVED_SECONDS = 0.35
UNLOCK_SECONDS = 1.4
CELEBRATE_SECONDS = 3.2
GRID_PERIOD_SECONDS = 6.0
IDLE_HINT_TEXT = "外側から順に計7回転で解けそうな初期配置ね"
IDLE_HINT_LINES = ("外側から順に", "計7回転で", "解けそうな", "初期配置ね")
IDLE_HINT_SECONDS = 10.0
INTRO_LINES = ("解けたら、", "ご褒美あげちゃう！")
INTRO_DELAY = 3.0
INTRO_READING_SECONDS = 6.0
SAVE_KEY = "drift_with_me.debug.independent_rings.v1"
LEGACY_LINKED_SAVE_KEY = "drift_with_me.debug.linked_rings.v1"
LINKED_SAVE_KEY = "drift_with_me.debug.linked_rings.v2"


@dataclass
class RingPuzzle:
    angles: list[int] = field(default_factory=lambda: list(INITIAL))
    selected: int = 0
    phase: str = "idle"
    elapsed: float = 0.0
    turn: int = 0
    mode: str = "independent"
    disabled_links: list[int] = field(default_factory=list)
    help_history: list[int] = field(default_factory=list)
    eligibility_forfeited: bool = False
    turn_deltas: list[int] = field(default_factory=lambda: [0] * 5)
    legacy_help_history: list[int] = field(default_factory=list)

    move_count: int = field(default=0, compare=False)
    undo_history: list = field(default_factory=list, repr=False, compare=False)

    @classmethod
    def create(cls, mode="linked"):
        if mode not in {"linked", "independent"}:
            raise ValueError("invalid puzzle mode")
        return cls(angles=list(LINKED_INITIAL if mode == "linked" else INITIAL), mode=mode)

    @property
    def unassisted_candidate(self):
        return (
            self.mode == "linked"
            and not self.eligibility_forfeited
            and not self.help_history
            and not any(self.angles)
            and self.phase in {"solved", "unlocking", "celebrating", "unlocked"}
        )

    @property
    def clear_reward_available(self):
        return self.mode == "linked" and self.phase == "unlocked" and not any(self.angles)

    @property
    def special_praise_earned(self):
        # Historical forfeiture is retained solely for conservative old-save praise handling.
        return self.unassisted_candidate

    @property
    def completion_lines(self):
        return (
            "サングラスをどうぞ！",
            "一人で解けたね、すごい！" if self.special_praise_earned else "一緒に解けたね！",
        )

    def rotate(self, direction: int) -> bool:
        if self.phase != "idle" or direction not in (-1, 1):
            return False
        self.undo_history.append((self.angles[:], self.selected, self.move_count))
        self.move_count += 1
        self.turn_deltas = move_deltas(
            self.selected, direction, self.disabled_links, linked=self.mode == "linked"
        )
        self.angles = [(a + d) % STEPS for a, d in zip(self.angles, self.turn_deltas, strict=True)]
        self.turn = direction
        self.elapsed = 0.0
        self.phase = "rotating"
        return True

    @property
    def can_undo(self):
        return self.phase == "idle" and bool(self.undo_history)

    def undo(self):
        if not self.can_undo:
            return False
        angles, selected, count = self.undo_history.pop()
        self.angles, self.selected, self.move_count = angles, selected, count
        self.turn = 0
        self.turn_deltas = [0] * 5
        self.elapsed = 0.0
        return True

    def assist(self) -> bool:
        if self.mode != "linked" or self.phase != "idle":
            return False
        link = next((i for i in ASSIST_ORDER if i not in self.disabled_links), None)
        if link is None:
            return False
        self.undo_history.clear()
        self.disabled_links.append(link)
        self.help_history.append(link)
        self.eligibility_forfeited = True
        return True

    def retry(self):
        fresh = self.create(self.mode)
        fresh.disabled_links = self.disabled_links[:]
        fresh.help_history = self.help_history[:]
        fresh.eligibility_forfeited = self.eligibility_forfeited
        fresh.legacy_help_history = self.legacy_help_history[:]
        return fresh

    def tick(self, dt: float) -> bool:
        if not math.isfinite(dt) or dt < 0 or self.phase in {"idle", "unlocked"}:
            return False
        self.elapsed += dt
        duration = {
            "rotating": ROTATION_SECONDS,
            "solved": SOLVED_SECONDS,
            "unlocking": UNLOCK_SECONDS,
            "celebrating": CELEBRATE_SECONDS,
        }[self.phase]
        if self.elapsed < duration:
            return False
        self.elapsed = 0.0
        if self.phase == "rotating":
            self.turn = 0
            self.turn_deltas = [0] * 5
            self.phase = "solved" if all(a == 0 for a in self.angles) else "idle"
        elif self.phase == "solved":
            self.phase = "unlocking"
        elif self.phase == "unlocking":
            self.phase = "celebrating"
        else:
            self.phase = "unlocked"
        return True

    def display_angle(self, index: int) -> float:
        angle = float(self.angles[index])
        if self.phase == "rotating":
            angle -= self.turn_deltas[index] * (1 - min(1, self.elapsed / ROTATION_SECONDS))
        return angle * math.tau / STEPS - math.pi / 2

    def snapshot(self) -> dict:
        return {
            "version": 4,
            "angles": list(self.angles),
            "selected": self.selected,
            "phase": self.phase,
            "elapsed": self.elapsed,
            "turn": self.turn,
            "mode": self.mode,
            "disabled_links": self.disabled_links[:],
            "help_history": self.help_history[:],
            "eligibility_forfeited": self.eligibility_forfeited,
            "turn_deltas": self.turn_deltas[:],
            "ruleset": RULESET if self.mode == "linked" else "independent_v1",
            "legacy_help_history": self.legacy_help_history[:],
        }

    @classmethod
    def restore(cls, raw):
        basic = {"version", "angles", "selected", "phase", "elapsed", "turn"}
        extra = {"mode", "disabled_links", "help_history", "eligibility_forfeited", "turn_deltas"}
        if (
            not isinstance(raw, dict)
            or type(raw.get("version")) is not int
            or raw["version"] not in (1, 2, 3, 4)
        ):
            raise ValueError("invalid ring save")
        legacy = raw["version"] < 3
        if raw["version"] == 4:
            extra = extra | {"ruleset", "legacy_help_history"}
        if set(raw) != (basic if legacy else basic | extra):
            raise ValueError("invalid ring fields")
        angles = raw["angles"]
        if (
            not isinstance(angles, list)
            or len(angles) != 5
            or any(type(a) is not int or not 0 <= a < STEPS for a in angles)
            or type(raw["selected"]) is not int
            or not 0 <= raw["selected"] < 5
            or raw["phase"]
            not in {"idle", "rotating", "solved", "unlocking", "celebrating", "unlocked"}
            or type(raw["elapsed"]) not in (int, float)
            or not math.isfinite(raw["elapsed"])
            or raw["elapsed"] < 0
            or type(raw["turn"]) is not int
            or raw["turn"] not in (-1, 0, 1)
        ):
            raise ValueError("invalid ring state")
        phase, elapsed = raw["phase"], raw["elapsed"]
        duration = {
            "idle": 0,
            "rotating": ROTATION_SECONDS,
            "solved": SOLVED_SECONDS,
            "unlocking": UNLOCK_SECONDS,
            "celebrating": CELEBRATE_SECONDS,
            "unlocked": 0,
        }[phase]
        if (
            (duration and elapsed >= duration)
            or (not duration and elapsed != 0)
            or (phase == "rotating") != (raw["turn"] != 0)
            or (phase in {"solved", "unlocking", "celebrating", "unlocked"} and any(angles))
            or (phase == "idle" and not any(angles))
        ):
            raise ValueError("invalid ring phase")
        mode = "independent" if legacy else raw["mode"]
        if raw["version"] == 3 and mode == "linked":
            raise ValueError("previous linked rules require a fresh legal board")
        if raw["version"] == 4 and raw["ruleset"] != (
            RULESET if mode == "linked" else "independent_v1"
        ):
            raise ValueError("wrong ring ruleset")
        old_history = raw["legacy_help_history"] if raw["version"] == 4 else []
        if (
            not isinstance(old_history, list)
            or any(type(i) is not int or i not in range(4) for i in old_history)
            or len(set(old_history)) != len(old_history)
        ):
            raise ValueError("invalid previous-rules history")
        disabled = [] if legacy else raw["disabled_links"]
        history = [] if legacy else raw["help_history"]
        forfeited = False if legacy else raw["eligibility_forfeited"]
        if mode not in {"linked", "independent"} or type(forfeited) is not bool:
            raise ValueError("invalid ring mode")
        for links in (disabled, history):
            if (
                not isinstance(links, list)
                or any(type(i) is not int or i not in range(5) for i in links)
                or len(set(links)) != len(links)
            ):
                raise ValueError("invalid help history")
        if (
            set(disabled) != set(history)
            or ((history or old_history) and not forfeited)
            or (mode == "independent" and (history or disabled or old_history))
            or (
                mode == "linked"
                and (history != list(ASSIST_ORDER[: len(history)]) or disabled != history)
            )
            or (mode == "linked" and 4 not in disabled and sum(angles[:4]) % 2)
        ):
            raise ValueError("inconsistent help history")
        expected = (
            move_deltas(raw["selected"], raw["turn"], disabled, linked=mode == "linked")
            if phase == "rotating"
            else [0] * 5
        )
        deltas = expected if legacy else raw["turn_deltas"]
        if (
            not isinstance(deltas, list)
            or len(deltas) != 5
            or any(type(d) is not int for d in deltas)
            or deltas != expected
        ):
            raise ValueError("invalid motion deltas")
        if phase == "celebrating":
            phase, elapsed = "unlocked", 0.0
        return cls(
            angles[:],
            raw["selected"],
            phase,
            float(elapsed),
            raw["turn"],
            mode,
            disabled[:],
            history[:],
            forfeited,
            deltas[:],
            old_history[:],
        )


class RingPreviewStore:
    """Mode-specific browser debug storage, never a story save."""

    def __init__(self, mode="independent"):
        self.mode = mode
        self.memory = None
        self.legacy_memory = None
        self.message = "Preview save only"

    @property
    def key(self):
        return LINKED_SAVE_KEY if self.mode == "linked" else SAVE_KEY

    def save(self, puzzle):
        if puzzle.mode != self.mode:
            return False
        payload = json.dumps(puzzle.snapshot())
        try:
            if sys.platform == "emscripten":
                import js

                js.localStorage.setItem(self.key, payload)
            self.memory = payload
            self.message = "Saved (preview only)"
            return True
        except Exception:
            self.message = "Save unavailable; keep this preview open"
            return False

    def load(self):
        try:
            payload = self.memory
            if sys.platform == "emscripten":
                import js

                payload = js.localStorage.getItem(self.key)
            if not payload and self.mode == "linked":
                previous = self.legacy_memory
                if sys.platform == "emscripten":
                    previous = js.localStorage.getItem(LEGACY_LINKED_SAVE_KEY)
                if previous:
                    return self.migrate_previous(previous)
            puzzle = (
                RingPuzzle.restore(json.loads(str(payload)))
                if payload
                else RingPuzzle.create(self.mode)
            )
            if puzzle.mode != self.mode:
                raise ValueError("wrong preview namespace")
            return puzzle
        except Exception:
            self.message = "Invalid save; fresh preview, eligibility withheld"
            puzzle = RingPuzzle.create(self.mode)
            puzzle.eligibility_forfeited = self.mode == "linked"
            return puzzle

    @property
    def progress_key(self):
        return self.key + ".progress"

    def save_progress(self, puzzle):
        # Only durable facts; never persist angles, selection, motion or undo history.
        previous = getattr(self, "progress_memory", None)
        if sys.platform == "emscripten":
            import js

            previous = js.localStorage.getItem(self.progress_key)
        try:
            already_unlocked = bool(json.loads(str(previous))["unlocked"]) if previous else False
        except (ValueError, TypeError, KeyError):
            already_unlocked = False
        payload = json.dumps(
            {
                "disabled_links": puzzle.disabled_links,
                "help_history": puzzle.help_history,
                "legacy_help_history": puzzle.legacy_help_history,
                "eligibility_forfeited": puzzle.eligibility_forfeited,
                "unlocked": already_unlocked
                or puzzle.phase in {"solved", "unlocking", "celebrating", "unlocked"},
            }
        )
        try:
            if sys.platform == "emscripten":
                import js

                js.localStorage.setItem(self.progress_key, payload)
            self.progress_memory = payload
            return True
        except Exception:
            return False

    def load_session(self):
        payload = getattr(self, "progress_memory", None)
        if sys.platform == "emscripten":
            import js

            payload = js.localStorage.getItem(self.progress_key)
        if not payload:
            # Read old saves for permanent facts only; leave their bytes intact.
            old = self.load()
            fresh = old.retry()
            if old.phase in {"solved", "unlocking", "celebrating", "unlocked"}:
                fresh.angles, fresh.phase = [0] * 5, "unlocked"
            self.save_progress(fresh)
            return fresh
        try:
            facts = json.loads(str(payload))
            fresh = RingPuzzle.create(self.mode)
            for key in (
                "disabled_links",
                "help_history",
                "legacy_help_history",
                "eligibility_forfeited",
            ):
                setattr(fresh, key, facts[key])
            if type(facts["unlocked"]) is not bool:
                raise ValueError("invalid completion")
            if facts["unlocked"]:
                fresh.angles, fresh.phase = [0] * 5, "unlocked"
            return RingPuzzle.restore(fresh.snapshot())
        except (ValueError, TypeError, KeyError):
            fresh = RingPuzzle.create(self.mode)
            fresh.eligibility_forfeited = self.mode == "linked"
            return fresh

    def migrate_previous(self, payload):
        # Keep old namespace byte-for-byte; never import its board/completion under new rules.
        puzzle = RingPuzzle.create("linked")
        puzzle.eligibility_forfeited = True
        try:
            old = json.loads(str(payload))
            history = old.get("help_history")
            valid = (
                old.get("version") == 3
                and old.get("mode") == "linked"
                and isinstance(history, list)
                and len(history) <= 4
                and all(type(i) is int and i in range(4) for i in history)
                and len(set(history)) == len(history)
                and type(old.get("eligibility_forfeited")) is bool
            )
            if valid:
                puzzle.legacy_help_history = history[:]
                puzzle.eligibility_forfeited = bool(history) or old["eligibility_forfeited"]
        except (TypeError, ValueError, AttributeError):
            pass
        self.save(puzzle)
        self.message = "Previous rules archived; new legal board"
        return puzzle


# Logical coordinates share the existing office/input transform (512 x 236).
RING_CENTER = (256.0, 106.0)
RING_EDGES = (30.0, 46.0, 62.0, 78.0, 94.0)
ARROW_RADIUS = 112.0
ROTATION_TAP_BUTTONS = (("left", 154.0, 30.0), ("right", 358.0, 30.0))
ROTATION_TAP_RADIUS = 22.0


def ring_pointer_action(x: float, y: float) -> str | None:
    """Disjoint polar hit regions; boundaries do not select a neighbour."""
    for action, bx, by in ROTATION_TAP_BUTTONS:
        if math.hypot(x - bx, y - by) <= ROTATION_TAP_RADIUS:
            return action
    dx, dy = x - RING_CENTER[0], y - RING_CENTER[1]
    radius = math.hypot(dx, dy)
    angle = math.atan2(dy, dx)
    if 104 <= radius <= 124:
        if abs(angle) <= math.radians(55):
            return "right"
        if abs(angle) >= math.radians(125):
            return "left"
        return None
    if radius > RING_EDGES[-1] or any(abs(radius - e) < 2 for e in RING_EDGES):
        return None
    return next((f"ring{i}" for i, edge in enumerate(RING_EDGES) if radius < edge), None)


def celebration_pose(elapsed: float, actor: int) -> tuple[str, float]:
    from drift_with_me.render import Renderer

    t = elapsed - actor * 0.22
    if t <= 0 or t >= 2.7:
        return "front", 0.0
    progress = t / 2.7
    views = Renderer.SPIN_DIRECTION_VIEWS
    # Three quick eight-direction turns, one per hop; settle at front.
    start = views.index("front")
    view = views[(start + int(progress * 24)) % 8]
    jump = abs(math.sin(progress * math.pi * 3)) * 8
    return view, jump


def ring_grid_components(x: float, y: float, seconds: float) -> tuple[float, float]:
    """Two gently bent diagonal fronts; neither grid geometry nor random noise moves."""
    advance = seconds / GRID_PERIOD_SECONDS
    bend_time = seconds * 12.0 / GRID_PERIOD_SECONDS
    bend_a = 20 * math.sin((x - y) / 135 + bend_time * 0.32)
    bend_b = 20 * math.sin((x + y) / 145 - bend_time * 0.29)
    phase_a = (x + y + bend_a) / 720 - advance
    phase_b = (512 - x + y + bend_b) / 720 - advance - 0.23
    return tuple((0.5 + 0.5 * math.cos(math.tau * phase)) ** 5 for phase in (phase_a, phase_b))


def ring_grid_level(x: float, y: float, seconds: float) -> int:
    # Maximum, not additive mixing: crossings cannot overexpose the foreground.
    return round(63 * max(ring_grid_components(x, y, seconds)))


@lru_cache(maxsize=96)
def grid_light_route(index: int, passage: int):
    # One private random choice per horizontal intersection, cached for the passage.
    rng = random.Random(0xD71F7 + index * 104729 + passage * 65537)
    row = rng.choice(tuple(range(24, 193, 24)))
    points = [(-8, row), (0, row)]
    for x in range(0, 505, 24):
        choices = [0, 0, 0, 0]
        if row > 24:
            choices.append(-24)
        if row < 192:
            choices.append(24)
        move = rng.choice(choices)
        if move:
            row += move
            points.append((x, row))
        # Arrival after a vertical move never branches again until moving right.
        points.append((min(x + 24, 520), row))
    cumulative = [0.0]
    for a, b in zip(points, points[1:], strict=False):
        cumulative.append(cumulative[-1] + abs(b[0] - a[0]) + abs(b[1] - a[1]))
    return tuple(points), tuple(cumulative)


_GRID_LIGHT_PASSAGE_ENDS = [[], [], []]


def grid_light_state(seconds: float, index: int) -> tuple[float, float, float, float, float]:
    speed, offset = ((36.0, 0.0), (30.0, 192.0), (42.0, 432.0))[index]
    travelled = max(0.0, seconds) * speed + offset
    ends = _GRID_LIGHT_PASSAGE_ENDS[index]
    while not ends or ends[-1] <= travelled:
        length = grid_light_route(index, len(ends))[1][-1]
        ends.append((ends[-1] if ends else 0) + length)
    passage = bisect_right(ends, travelled)
    along = travelled - (ends[passage - 1] if passage else 0)
    points, cumulative = grid_light_route(index, passage)
    edge = min(len(points) - 2, bisect_right(cumulative, along) - 1)
    a, b = points[edge], points[edge + 1]
    distance = along - cumulative[edge]
    amount = distance / (cumulative[edge + 1] - cumulative[edge])
    x, y = a[0] + (b[0] - a[0]) * amount, a[1] + (b[1] - a[1]) * amount
    age = distance / speed
    on_cross = a[0] % 24 == 0 and a[1] % 24 == 0
    glow = 0.5 + 0.5 * math.cos(math.pi * age / 0.32) if on_cross and age < 0.32 else 0.0
    return x, y, a[0], a[1], glow


@dataclass
class RingIdleHint:
    last_activity: float
    shown_once: bool = False
    visible: bool = False

    def update(self, now, *, activity, eligible):
        if activity:
            self.last_activity = now
            self.visible = False
        elif not eligible:
            self.visible = False
        elif not self.shown_once and now - self.last_activity >= IDLE_HINT_SECONDS:
            self.shown_once = self.visible = True


class RingPuzzlePreviewMixin:
    def ring_preview_rects(self):
        return {
            "quit": self.office_rect(8, 206, 116, 28),
            "help": self.office_rect(132, 206, 116, 28),
            "retry": self.office_rect(256, 206, 116, 28),
            "undo": self.office_rect(380, 206, 124, 28),
        }

    def start_ring_preview(self, mode="linked"):
        if not getattr(self, "week_debug_active", False):
            return False
        stores = getattr(self, "ring_preview_stores", None)
        if stores is None:
            stores = self.ring_preview_stores = {}
        if mode not in stores:
            stores[mode] = RingPreviewStore(mode)
        self.ring_preview_store = stores[mode]
        self.ring_preview = self.ring_preview_store.load_session()
        self.ring_preview_time = self.presentation_time
        self.ring_idle_hint = RingIdleHint(self.presentation_time)
        self.ring_intro_started = None
        self.ring_intro_done = False
        self.ring_intro_entry = self.presentation_time
        self.week_debug_menu_open = False
        return True

    def update_ring_preview(self):
        puzzle = self.ring_preview
        now = self.presentation_time
        changed = puzzle.tick(max(0.0, now - self.ring_preview_time))
        self.ring_preview_time = now
        if changed and puzzle.phase in {"solved", "unlocked"}:
            self.ring_preview_store.save_progress(puzzle)
        action = None
        for name, rect in self.ring_preview_rects().items():
            if self.mouse_pressed_in(rect):
                action = name
                break
        if action is None and self.pointer_snapshot.pressed:
            point = self.pointer_snapshot
            action = ring_pointer_action(
                point.x * 512 / self.runtime.screen_width,
                point.y * 236 / self.runtime.screen_height,
            )
        if self.key_pressed("KEY_ESCAPE"):
            action = "quit"
        elif self.key_pressed("KEY_LEFT", "KEY_A"):
            action = "left"
        elif self.key_pressed("KEY_RIGHT", "KEY_D"):
            action = "right"
        elif puzzle.phase == "idle" and self.key_pressed("KEY_UP", "KEY_W"):
            action = f"ring{(puzzle.selected - 1) % 5}"
        elif puzzle.phase == "idle" and self.key_pressed("KEY_DOWN", "KEY_S"):
            action = f"ring{(puzzle.selected + 1) % 5}"
        hint = getattr(self, "ring_idle_hint", None)
        if hint is None:
            hint = self.ring_idle_hint = RingIdleHint(now)
        intro = self.update_ring_intro(now)
        hint.update(
            now,
            activity=bool(self.pointer_snapshot.pressed or action is not None),
            eligible=puzzle.mode == "linked" and puzzle.phase == "idle" and not intro,
        )
        if action == "quit":
            self.restore_ring_grid_palette()
            self.ring_preview = None
            self.week_debug_menu_open = True
        elif action == "retry" and puzzle.phase in {"idle", "unlocked"}:
            self.ring_preview = puzzle.retry()
        elif action == "help":
            if puzzle.assist():
                self.ring_preview_react(now)
                self.ring_preview_store.save_progress(puzzle)
        elif action in {"left", "right"}:
            if puzzle.rotate(-1 if action == "left" else 1):
                self.ring_preview_react(now)
        elif action == "undo":
            puzzle.undo()
        elif puzzle.phase == "idle" and action is not None and action.startswith("ring"):
            puzzle.selected = int(action[-1])
            self.ring_preview_react(now)

    def draw_ring_preview(self):
        p = self.pyxel
        puzzle = self.ring_preview
        p.cls(0)
        self.draw_ring_background_grid()
        self.draw_office_text_in_rect(self.office_rect(8, 5, 114, 20), "5 RINGS / power 0", 7)

        # Use the same logical-to-screen transform for geometry and hit testing.
        def point(x, y):
            r = self.office_rect(x, y, 0, 0)
            return int(r.x), int(r.y)

        def line(x1, y1, x2, y2, color):
            p.line(*point(x1, y1), *point(x2, y2), color)

        cx, cy = RING_CENTER
        # Annuli are rasterised in logical coordinates, including non-square profiles.
        for i in range(4, -1, -1):
            outer = RING_EDGES[i]
            inner = RING_EDGES[i - 1] if i else 0
            left, top = point(cx - outer, cy - outer)
            right, bottom = point(cx + outer, cy + outer)
            p.elli(left, top, right - left + 1, bottom - top + 1, 5 if i % 2 else 1)
            angle = puzzle.display_angle(i)
            for offset in (-2, -1, 0, 1, 2):
                dx, dy = -math.sin(angle) * offset, math.cos(angle) * offset
                line(
                    cx + inner * math.cos(angle) + dx,
                    cy + inner * math.sin(angle) + dy,
                    cx + outer * math.cos(angle) + dx,
                    cy + outer * math.sin(angle) + dy,
                    7,
                )
        for i, radius in enumerate(RING_EDGES):
            widths = (-1, 0, 1) if i == puzzle.selected else (0,)
            for offset in widths:
                left, top = point(cx - radius - offset, cy - radius - offset)
                right, bottom = point(cx + radius + offset, cy + radius + offset)
                p.ellib(
                    left,
                    top,
                    right - left + 1,
                    bottom - top + 1,
                    10 if i == puzzle.selected else 13,
                )
        # Curved arrows occupy a separate annulus, beyond a 10px no-action gutter.
        for direction, start, end in ((-1, 225, 135), (1, -45, 45)):
            color = 12 if puzzle.phase == "idle" else 5
            for degree in range(min(start, end), max(start, end) + 1):
                t = math.radians(degree)
                for offset in (-1, 0, 1):
                    r = ARROW_RADIUS + offset
                    previous = math.radians(degree - 1)
                    line(
                        cx + r * math.cos(previous),
                        cy + r * math.sin(previous),
                        cx + r * math.cos(t),
                        cy + r * math.sin(t),
                        color,
                    )
            t = math.radians(end)
            x, y = cx + ARROW_RADIUS * math.cos(t), cy + ARROW_RADIUS * math.sin(t)
            tx, ty = -math.sin(t) * direction, math.cos(t) * direction
            nx, ny = math.cos(t), math.sin(t)
            p.tri(
                *point(x + tx * 3, y + ty * 3),
                *point(x - tx * 11 + nx * 7, y - ty * 11 + ny * 7),
                *point(x - tx * 11 - nx * 7, y - ty * 11 - ny * 7),
                color,
            )
        # Additional circular targets share exactly the same one-action input path.
        for action, bx, by in ROTATION_TAP_BUTTONS:
            left, top = point(bx - 18, by - 18)
            right, bottom = point(bx + 18, by + 18)
            p.elli(left, top, right - left + 1, bottom - top + 1, 1)
            color = 12 if puzzle.phase == "idle" else 5
            p.ellib(left, top, right - left + 1, bottom - top + 1, color)
            direction = -1 if action == "left" else 1
            start = 45 if direction == -1 else 135
            previous = None
            for step in range(21):
                angle = math.radians(start + direction * 270 * step / 20)
                pos = (bx + 9 * math.cos(angle), by + 9 * math.sin(angle))
                if previous is not None:
                    line(*previous, *pos, color)
                previous = pos
            tx, ty = -math.sin(angle) * direction, math.cos(angle) * direction
            nx, ny = math.cos(angle), math.sin(angle)
            x, y = previous
            p.tri(
                *point(x + tx * 2, y + ty * 2),
                *point(x - tx * 4 + nx * 3, y - ty * 4 + ny * 3),
                *point(x - tx * 4 - nx * 3, y - ty * 4 - ny * 3),
                color,
            )
        p.circ(*point(cx, cy), 3, 10)
        line(cx - 5, cy - 100, cx + 5, cy - 100, 10)
        if puzzle.phase in {"unlocking", "celebrating", "unlocked"}:
            progress = min(1, puzzle.elapsed / UNLOCK_SECONDS) if puzzle.phase == "unlocking" else 1
            line(cx, cy, cx, cy - 100 * progress, 10)
            p.circ(*point(cx, cy - 100 * progress), 3, 10)
        for name, label in (
            ("quit", "やめる"),
            ("help", "Fuse help"),
            ("retry", "Retry"),
            ("undo", "UNDO"),
        ):
            disabled = name == "help" and (
                puzzle.mode != "linked" or puzzle.phase != "idle" or len(puzzle.disabled_links) == 5
            )
            disabled = disabled or (name == "undo" and not puzzle.can_undo)
            disabled = disabled or (name == "retry" and puzzle.phase not in {"idle", "unlocked"})
            self.draw_week_debug_button(self.ring_preview_rects()[name], label, disabled=disabled)
        self.draw_office_text_in_rect(
            self.office_rect(8, 45, 112, 22),
            f"Ring {puzzle.selected + 1} selected",
            10,
            align="center",
        )
        self.draw_office_text_in_rect(
            self.office_rect(392, 5, 112, 20),
            f"Help {len(puzzle.help_history)}/5" if puzzle.mode == "linked" else "Solo test",
            7,
            align="center",
        )

        self.draw_ring_thinking_characters()
        self.draw_ring_idle_hint()

    def ring_preview_react(self, now):
        if now - getattr(self, "ring_reaction_at", -100.0) >= 1.8:
            self.ring_reaction_at = now

    def draw_ring_thinking_characters(self):
        """Reuse approved sprites; presentation-only idle motion never requests help."""
        assets = getattr(self, "sprite_assets", None)
        if assets is None:
            return
        now = float(getattr(self, "presentation_time", 0.0))
        solved = self.ring_preview.phase in {"solved", "unlocking", "celebrating", "unlocked"}
        sway = 0 if solved else math.sin(math.tau * now / 4.8)
        profiles = (
            (
                "jack_front_blink_32" if now % 4.8 > 4.6 else "jack_front_32",
                66,
                160,
                2.0,
                3 * sway,
                0,
                "Jack",
            ),
            (
                "fuse_matte_thinking",
                446,
                158,
                0.62,
                -2 * sway,
                3 * math.sin(math.tau * now / 3.2),
                "Fuse",
            ),
        )
        scale = self.runtime.screen_width / 512
        for index, (asset_id, x, y, size, tilt, bob, _name) in enumerate(profiles):
            asset = assets.get(asset_id)
            if asset is None:
                continue
            celebration = self.ring_preview.phase == "celebrating"
            happy = self.ring_preview.phase in {"celebrating", "unlocked"}
            if celebration:
                view, jump = celebration_pose(self.ring_preview.elapsed, index)
                asset_id = f"jack_{view}_32" if index == 0 else f"fuse_{view}_neutral_48"
                asset = assets.get(asset_id) or asset
                size, tilt, bob = (2.0 if index == 0 else 3.0), 0, -jump
            elif happy:
                asset_id = "jack_front_32" if index == 0 else "fuse_matte_smile"
                asset = assets.get(asset_id) or asset
                tilt = 0
            frame = asset.frame()
            image, u, v = frame.image, frame.u, frame.v
            if happy and asset_id in {"jack_front_32", "fuse_front_neutral_48"}:
                image = self.ring_happy_image(asset_id, frame)
                u = v = 0
            center = self.office_rect(x, y + bob, 0, 0)
            self.pyxel.blt(
                round(center.x - frame.width / 2),
                round(center.y - frame.height / 2),
                image,
                u,
                v,
                frame.width,
                frame.height,
                colkey=asset.definition.colkey,
                rotate=tilt,
                scale=size * scale,
            )
            age = now - getattr(self, "ring_reaction_at", -100.0) - index * 0.22
            ready = solved and not (
                self.ring_preview.phase == "solved" and self.ring_preview.elapsed < index * 0.18
            )
            mode = "bulb" if ready else "bang" if 0 <= age < 0.65 else "thinking"
            if not (
                index == 1
                and (
                    self.ring_idle_hint_visible()
                    or self.ring_intro_visible()
                    or self.ring_preview.clear_reward_available
                )
            ):
                self.draw_ring_thought_bubble(x + 18, 108 - index * 2, mode, now + index * 0.8)
            if celebration:
                self.draw_ring_celebration_particles(x, self.ring_preview.elapsed, index)

    def draw_ring_thought_bubble(self, x, y, mode, now):
        # Small native pixel shapes, confined to the character side margins.
        p = self.pyxel

        def rect(dx, dy, width, height, color):
            r = self.office_rect(x + dx, y + dy, width, height)
            p.rect(round(r.x), round(r.y), max(1, round(r.width)), max(1, round(r.height)), color)

        width = 44 if mode == "thinking" else 28
        rect(-width // 2, -10, width, 19, 13)
        rect(-width // 2 + 1, -9, width - 2, 17, 7)
        rect(-9, 9, 4, 2, 13)
        rect(-8, 7, 3, 3, 7)
        if mode == "thinking":
            self.draw_office_text_in_rect(
                self.office_rect(x - 20, y - 7, 40, 14), "うーん", 1, align="center"
            )
        elif mode == "bang":
            rect(-2, -6, 4, 8, 8)
            rect(-2, 4, 4, 3, 8)
        else:
            rect(-4, -6, 8, 2, 10)
            rect(-6, -4, 12, 6, 10)
            rect(-3, 2, 6, 3, 9)
            rect(-3, 6, 6, 2, 1)
            rect(-10, -5, 2, 2, 9)
            rect(8, -5, 2, 2, 9)

    def ring_happy_image(self, asset_id, frame):
        """Tiny face-only derived overlay. Canonical images and silhouettes stay intact."""
        cache = getattr(self, "ring_happy_images", None)
        if cache is None:
            cache = self.ring_happy_images = {}
        if asset_id not in cache:
            image = self.pyxel.Image(frame.width, frame.height)
            image.blt(0, 0, frame.image, frame.u, frame.v, frame.width, frame.height)
            if asset_id == "jack_front_32":
                for left in (9, 21):
                    image.rect(left, 18, 4, 5, 14)
                    for dx, dy in ((0, 2), (1, 1), (2, 1), (3, 2)):
                        image.pset(left + dx, 18 + dy, 1)
            else:
                for left in (20, 26):
                    image.rect(left - 1, 24, 4, 4, 0)
                    for dx, dy in ((-1, 1), (0, 0), (1, 0), (2, 1)):
                        image.pset(left + dx, 25 + dy, 10)
            cache[asset_id] = image
        return cache[asset_id]

    def draw_ring_celebration_particles(self, x, elapsed, index):
        # Fixed small count, analytical positions; no event queue or per-frame spawning.
        t = elapsed - index * 0.22
        if not 0 <= t < 2.8:
            return
        for i in range(12):
            age = (t + i * 0.13) % 2.0
            px = x - 42 + (i * 17 % 84) + 3 * math.sin(age * 4 + i)
            py = 82 + age * 43 + i % 3
            r = self.office_rect(px, py, 3, 2)
            self.pyxel.rect(
                round(r.x),
                round(r.y),
                max(1, round(r.width)),
                max(1, round(r.height)),
                (10, 12, 14, 7)[i % 4],
            )
        for i in range(4):
            px = x - 34 + i * 23
            py = 118 + 13 * math.sin(t * 3 + i)
            r = self.office_rect(px - 2, py, 5, 1)
            self.pyxel.rect(round(r.x), round(r.y), max(1, round(r.width)), 1, 10)
            r = self.office_rect(px, py - 2, 1, 5)
            self.pyxel.rect(round(r.x), round(r.y), 1, max(1, round(r.height)), 7)

    def draw_ring_background_grid(self):
        """Cached, bounded segments; the reserved ramp never modifies asset colors."""
        p = self.pyxel
        original = getattr(self, "ring_grid_original_palette", None)
        if original is None:
            original = p.colors.to_list()
            self.ring_grid_original_palette = original
            ramp = []
            for i in range(64):
                amount = i / 63
                red, green, blue = (
                    round(3 + 4 * amount),
                    round(18 + 40 * amount),
                    round(12 + 22 * amount),
                )
                ramp.append((red << 16) | (green << 8) | blue)
            lights = [
                ((5 + i) << 16) | (round(25 + 103 * i / 31) << 8) | round(15 + 64 * i / 31)
                for i in range(32)
            ]
            p.colors.from_list(original + ramp + lights)
        profile = (self.runtime.screen_width, self.runtime.screen_height)
        if getattr(self, "ring_grid_profile", None) != profile:
            segments = []
            for vertical, fixeds, extent in (
                (True, range(0, 513, 24), 236),
                (False, range(0, 237, 24), 512),
            ):
                for fixed in fixeds:
                    for start in range(0, extent, 8):
                        end = min(start + 8, extent)
                        x, y = (
                            (fixed, (start + end) / 2) if vertical else ((start + end) / 2, fixed)
                        )
                        # The opaque board covers this area; do not spend draw calls under it.
                        if math.hypot(x - RING_CENTER[0], y - RING_CENTER[1]) < RING_EDGES[-1] - 5:
                            continue
                        a = self.office_rect(
                            fixed if vertical else start, start if vertical else fixed, 0, 0
                        )
                        b = self.office_rect(
                            fixed if vertical else end, end if vertical else fixed, 0, 0
                        )
                        segments.append((round(a.x), round(a.y), round(b.x), round(b.y), x, y))
            self.ring_grid_segments = segments
            self.ring_grid_profile = profile
        seconds = float(getattr(self, "presentation_time", 0.0))
        for x1, y1, x2, y2, x, y in self.ring_grid_segments:
            p.line(x1, y1, x2, y2, len(original) + ring_grid_level(x, y, seconds))
        self.draw_ring_grid_lights(seconds, len(original) + 64)

    def draw_ring_grid_lights(self, seconds, color_base):
        # Three analytic dots only. Draw before every foreground object; never spawn particles.
        for index in range(3):
            x, y, ix, iy, glow = grid_light_state(seconds, index)
            dot = self.office_rect(x - 1.5, y - 1.5, 3, 3)
            self.pyxel.rect(
                round(dot.x),
                round(dot.y),
                max(1, round(dot.width)),
                max(1, round(dot.height)),
                color_base + 24,
            )
            if glow > 0.02:
                arm = 1 + round(3 * glow)
                color = color_base + round(31 * glow)
                a, b = self.office_rect(ix - arm, iy, 0, 0), self.office_rect(ix + arm, iy, 0, 0)
                self.pyxel.line(round(a.x), round(a.y), round(b.x), round(b.y), color)
                a, b = self.office_rect(ix, iy - arm, 0, 0), self.office_rect(ix, iy + arm, 0, 0)
                self.pyxel.line(round(a.x), round(a.y), round(b.x), round(b.y), color)

    def restore_ring_grid_palette(self):
        original = getattr(self, "ring_grid_original_palette", None)
        if original is not None:
            self.pyxel.colors.from_list(original)
            self.ring_grid_original_palette = None

    def update_ring_intro(self, now):
        if getattr(self, "ring_intro_done", True) or self.ring_preview.mode != "linked":
            return False
        if self.ring_preview.phase in {"solved", "unlocking", "celebrating", "unlocked"}:
            self.ring_intro_done = True
            return False
        start = self.ring_intro_started
        if (
            start is None
            and now - self.ring_intro_entry >= INTRO_DELAY
            and self.ring_preview.phase == "idle"
        ):
            self.ring_intro_started = start = now
        if start is not None and now - start >= INTRO_READING_SECONDS:
            self.ring_intro_done = True
        return self.ring_intro_visible()

    def ring_intro_visible(self):
        return (
            getattr(self, "ring_intro_started", None) is not None
            and not getattr(self, "ring_intro_done", True)
            and self.ring_preview.phase == "idle"
        )

    def draw_ring_intro_lines(self, lines=INTRO_LINES):
        # Condense only horizontally when needed; retain the native 12px glyph height.
        # The side balloon stays clear of both the board and every input target.
        p = self.pyxel
        area = self.office_rect(387, 80, 114, 40)
        width = max(1, int(area.width))
        cache = getattr(self, "ring_intro_text_cache", {})
        key = (width, lines)
        if key not in cache:
            font = self.ui_renderer.styles["office_japanese"].font
            images = []
            for line in lines:
                source_width = self.ui_renderer.text_width(line, "office_japanese")
                source = p.Image(source_width, 16)
                source.cls(7)
                source.text(0, 0, line, 1, font)
                target_width = min(width, source_width)
                image = p.Image(target_width, 16)
                image.cls(7)
                for x in range(target_width):
                    for y in range(16):
                        image.pset(
                            x,
                            y,
                            source.pget(
                                min(source_width - 1, int(x * source_width / target_width)), y
                            ),
                        )
                images.append((image, target_width))
            cache[key] = images
            self.ring_intro_text_cache = cache
        for i, (image, w) in enumerate(cache[key]):
            p.blt(round(area.x), round(area.y + i * 18), image, 0, 0, w, 16, colkey=7)

    def ring_idle_hint_visible(self):
        hint = getattr(self, "ring_idle_hint", None)
        return bool(
            hint is not None
            and hint.visible
            and self.ring_preview.mode == "linked"
            and self.ring_preview.phase == "idle"
        )

    def ring_idle_hint_rect(self):
        return self.office_rect(382, 44, 122, 82)

    def draw_ring_idle_hint(self):
        intro = self.ring_intro_visible()
        completed = self.ring_preview.clear_reward_available
        if not intro and not completed and not self.ring_idle_hint_visible():
            return
        p = self.pyxel
        box = (
            self.office_rect(382, 72, 122, 54)
            if (intro or completed)
            else self.ring_idle_hint_rect()
        )
        p.rect(round(box.x), round(box.y), round(box.width), round(box.height), 13)
        inside = (
            self.office_rect(383, 73, 120, 52)
            if (intro or completed)
            else self.office_rect(383, 45, 120, 80)
        )
        p.rect(round(inside.x), round(inside.y), round(inside.width), round(inside.height), 7)
        a, b, c = (self.office_rect(x, y, 0, 0) for x, y in ((438, 124), (454, 124), (446, 133)))
        p.tri(round(a.x), round(a.y), round(b.x), round(b.y), round(c.x), round(c.y), 7)
        if intro or completed:
            self.draw_ring_intro_lines(
                self.ring_preview.completion_lines if completed else INTRO_LINES
            )
        else:
            self.draw_office_wrapped_lines(self.office_rect(390, 54, 106, 62), IDLE_HINT_LINES, 1)
