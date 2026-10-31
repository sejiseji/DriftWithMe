"""Resolve screen ownership separately from authored week progression.

Input predicates remain pure: several owners inspect Escape twice to decide whether
an accepted action is cancellation. A frame is committed at the handler boundary,
never when a rect/key is merely queried.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WeekFlow:
    handlers: tuple[str, ...] = ()


WEEK_FLOWS = {
    **{(6, n): WeekFlow() for n in range(1, 5)},
    (7, 1): WeekFlow(),
    (7, 2): WeekFlow(("update_week2",)),
    (7, 3): WeekFlow(("update_july_week3",)),
    # August owns the already-authored automatic July4 -> August1 transition.
    (7, 4): WeekFlow(("update_august", "update_july_week4")),
    **{(8, n): WeekFlow(("update_august",)) for n in range(1, 5)},
}


@dataclass(frozen=True)
class ScreenState:
    screen: str
    week: tuple[int, int]
    surface: str
    modal: str | None
    transition: str | None
    phase: str | None

    @property
    def office_visible(self) -> bool:
        return self.screen == "OFFICE" and self.surface == "office" and self.modal is None


PREVIEWS = (
    "ring_preview",
    "park_preview_week",
    "portrait_preview",
    "garden_props_preview",
    "nudibranch_preview",
)


def resolve_state(app: Any) -> ScreenState:
    screen = getattr(getattr(app, "screen", None), "name", "START")
    week_obj = getattr(app, "work_week", None)
    week = (getattr(week_obj, "month", 6), getattr(week_obj, "number", 1))
    office = getattr(app, "office", None)
    progress = getattr(
        office, "august_progress" if week[0] == 8 else f"week{week[1]}_progress", None
    )
    phase = getattr(progress, "phase", None)
    transition = next(
        (n for n in ("field_transition", "week_transition") if getattr(app, n, None) is not None),
        None,
    )
    modal = None
    surface = screen.lower()
    if screen not in {"CREDITS", "COLLECTION_ROOM"}:
        if getattr(app, "week_debug_menu_open", False):
            modal = "week_debug_menu"
        else:
            modal = next((n for n in PREVIEWS if getattr(app, n, None) is not None), None)
            if modal is None:
                modal = next(
                    (
                        n
                        for n in ("flowerbed_dialogue", "flowerbed_editor")
                        if getattr(app, n, None) is not None
                    ),
                    None,
                )
        if modal is None and screen == "PLAY":
            modal = next(
                (
                    n
                    for n in ("week2_dialogue", "week3_dialogue", "week4_dialogue")
                    if getattr(app, n, None) is not None
                ),
                None,
            )
            if modal is None and week == (7, 3) and getattr(progress, "active_scene", None):
                modal = "week3_scene"
        if screen == "OFFICE" and week == (8, 3) and phase == "done":
            surface = "recovered_landscape"
    return ScreenState(screen, week, surface, modal, transition, phase)


def office_toolbar_visible(app: Any) -> bool:
    state = resolve_state(app)
    return (
        state.office_visible
        and state.transition is None
        and not any(getattr(app, n, False) for n in ("week_input_wait_for_release",))
    )


def debug_badge_visible(app: Any) -> bool:
    state = resolve_state(app)
    return bool(
        getattr(app, "week_debug_active", False)
        and state.screen in {"START", "PLAY", "PAUSE", "WATER_STUDY"}
        and state.modal is None
        and state.transition is None
        and not getattr(app, "week_input_wait_for_release", False)
        and not getattr(app, "field_input_wait_for_release", False)
    )


class FrameDispatch:
    """Exactly one accepted owner, including a transition caused by a probe."""

    def __init__(self, app):
        self.app = app
        self.start = resolve_state(app)
        self.owner = None

    def try_owner(self, name, callback, checkpoint=False):
        if self.owner is not None:
            raise RuntimeError("Frame input already belongs to an owner")
        before = resolve_state(self.app)
        handled = bool(callback())
        changed = before != resolve_state(self.app)
        if not handled and not changed:
            return False
        self.owner = name
        self.app.last_ui_dispatch = (self.start, name, resolve_state(self.app))
        if checkpoint:
            self.app.checkpoint_progress()
        return True


def dispatch_early(app, elapsed):
    """Modal/transition/common-office ownership, then authored weekly hooks."""
    frame = FrameDispatch(app)
    state = frame.start
    if state.screen == "CREDITS":
        frame.try_owner("ending", lambda: (app.update_ending(elapsed), True)[1])
        return True
    if state.screen == "COLLECTION_ROOM":
        frame.try_owner("collection_room", lambda: (app.update_collection_room(), True)[1])
        return True
    if frame.try_owner("week_debug", app.update_week_debug):
        return True
    if (
        state.transition
        or getattr(app, "field_input_wait_for_release", False)
        or getattr(app, "week_input_wait_for_release", False)
    ):
        if frame.try_owner("field_transition", lambda: app.update_field_transition(elapsed)):
            return True
        if frame.try_owner("week_transition", lambda: app.update_week_transition(elapsed)):
            return True
    if state.modal in {"flowerbed_dialogue", "flowerbed_editor"} and frame.try_owner(
        "flowerbed", app.update_flowerbed_modal
    ):
        return True
    if state.office_visible and frame.try_owner(
        "office_consultation", lambda: app.update_office_shared_controls(elapsed)
    ):
        return True
    app.sync_august_sighting_lock()
    if frame.try_owner("patrol", lambda: app.update_patrol(elapsed)):
        return True
    if frame.try_owner("swarm", lambda: app.update_swarm_frame(elapsed), checkpoint=True):
        return True
    if frame.try_owner("sighting", lambda: app.update_august_sightings(elapsed), checkpoint=True):
        return True
    for handler in WEEK_FLOWS.get(state.week, WeekFlow()).handlers:
        callback = getattr(app, handler)
        if frame.try_owner(
            handler,
            lambda callback=callback, handler=handler: (
                callback() if handler == "update_week2" else callback(elapsed)
            ),
            checkpoint=handler == "update_august",
        ):
            return True
    if frame.try_owner("flowerbed", app.update_flowerbed_modal):
        return True
    app.last_ui_dispatch = (frame.start, "screen:" + resolve_state(app).screen, resolve_state(app))
    return False
