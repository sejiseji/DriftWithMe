"""Browser visibility suspension; no save, screen, conversation or battle transition."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LifecycleSnapshot:
    active: bool
    generation: int
    input_epoch: int


class LifecycleMixin:
    def browser_lifecycle_snapshot(self) -> LifecycleSnapshot | None:
        if not hasattr(self, "_lifecycle_bridge"):
            try:
                import js

                self._lifecycle_bridge = getattr(js.window, "__driftWithMeLifecycle", False)
            except ImportError:
                self._lifecycle_bridge = False
        bridge = self._lifecycle_bridge
        if not bridge:
            return None
        try:
            return LifecycleSnapshot(
                bool(bridge.active), int(bridge.generation), int(bridge.inputEpoch)
            )
        except Exception:
            # Once a browser bridge exists, an unavailable bridge must not run the game.
            return LifecycleSnapshot(False, -1, -1)

    def reset_lifecycle_input_and_clock(self) -> None:
        self.previous_time = None
        self.clear_world_input_latches()
        self.model.cancel_auto_move()
        self.pointer_snapshot = type(self.pointer_snapshot)(False, False, 0.0, 0.0)

    def sync_browser_lifecycle(self) -> LifecycleSnapshot | None:
        state = self.browser_lifecycle_snapshot()
        if state is None:
            return None
        previous = getattr(self, "_lifecycle_state", None)
        self._lifecycle_state = state
        if previous == state:
            return state
        if previous is None and state.active and state.generation == 0 and state.input_epoch == 0:
            return state
        self.reset_lifecycle_input_and_clock()
        self._lifecycle_wait_release = True
        self._lifecycle_wait_draw = True
        self.audio.suspend_for_lifecycle()
        if state.active:
            self.audio.resume_from_lifecycle()
            bridge = getattr(self, "_lifecycle_bridge", None)
            if bridge:
                bridge.acknowledge(state.generation)
        return state

    def lifecycle_input_held(self) -> bool:
        if self.read_pointer_snapshot().down:
            return True
        for name in dir(self.pyxel):
            if (name.startswith("KEY_") or name == "MOUSE_BUTTON_LEFT") and self.pyxel.btn(
                getattr(self.pyxel, name)
            ):
                return True
        return False

    def lifecycle_update_blocked(self) -> bool:
        state = self.sync_browser_lifecycle()
        if state is None:
            return False
        if not state.active or getattr(self, "_lifecycle_wait_draw", False):
            self.previous_time = None
            return True
        if getattr(self, "_lifecycle_wait_release", False):
            if not self.lifecycle_input_held():
                self._lifecycle_wait_release = False
            self.previous_time = None
            return True  # Also swallow the release edge rather than treating it as an action.
        return False

    def lifecycle_draw_allowed(self) -> bool:
        state = self.sync_browser_lifecycle()
        return state is None or state.active

    def lifecycle_did_draw(self) -> None:
        self._lifecycle_wait_draw = False
