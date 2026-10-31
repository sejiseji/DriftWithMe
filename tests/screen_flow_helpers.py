"""Probe a COPY of a handler-driver milestone through the real App.update.
No domain completion flags are assigned, no real storage is accessed, and the
original driver app/records are not changed. This is synthetic UI dispatch QA.
"""

from copy import deepcopy

from drift_with_me.app import DriftWithMeApp as App
from drift_with_me.app import PointerSnapshot
from drift_with_me.input import DoubleTapMoveRecognizer, PointerInput
from drift_with_me.math3d import AffineProjectionProfile
from drift_with_me.save_state import snapshot


class Hardware:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.mouse_x = self.mouse_y = 0
        self.down = self.pressed = False
        self.held_keys, self.new_keys = set(), set()
        self.MOUSE_BUTTON_LEFT = -1
        for index, name in enumerate(
            (
                "RETURN",
                "Z",
                "ESCAPE",
                "X",
                "UP",
                "DOWN",
                "LEFT",
                "RIGHT",
                "W",
                "A",
                "S",
                "D",
                "E",
                "SPACE",
                "F",
                "F1",
                "M",
                "V",
                "P",
                "H",
            )
        ):
            setattr(self, "KEY_" + name, index)

    def btn(self, code):
        return self.down if code == self.MOUSE_BUTTON_LEFT else code in self.held_keys

    def btnp(self, code):
        return self.pressed if code == self.MOUSE_BUTTON_LEFT else code in self.new_keys

    def quit(self):
        raise AssertionError("unexpected quit in UI milestone probe")


def describe(app):
    office = app.office
    return dict(
        week=f"{app.work_week.month}:{app.work_week.number}",
        screen=app.screen.name,
        consultation=getattr(app, "office_consultation", None) is not None,
        calendar=getattr(app, "week_debug_menu_open", False),
        field_transition=getattr(app, "field_transition", None) is not None,
        week_transition=getattr(app, "week_transition", None) is not None,
        office_complete=office.complete,
        phases={
            name: getattr(getattr(office, name, None), "phase", None)
            for name in ("week2_progress", "week3_progress", "week4_progress", "august_progress")
        },
        case=office.current_case.case_id if office.current_case else None,
    )


def clone_for_root_update(original):
    app = deepcopy(original)
    app.pyxel = Hardware(app.runtime.screen_width, app.runtime.screen_height)
    for method in (
        "key_pressed",
        "mouse_pressed_in",
        "read_pointer_snapshot",
        "pointer_intent",
        "double_tap_move_intent",
    ):
        setattr(app, method, getattr(App, method).__get__(app, App))
    app.consume_elapsed = lambda: 1 / 60
    app._lifecycle_bridge = False
    app.pointer_snapshot = PointerSnapshot(False, False, 0, 0)
    scale = min(app.runtime.screen_width / 512, app.runtime.screen_height / 236)
    app.pointer = PointerInput(0.22, 8 * scale, 8 * scale, 48 * scale)
    app.double_tap_move = DoubleTapMoveRecognizer(0.18, 0.3, 20 * scale, 8 * scale)
    # Hardware/diagnostic defaults absent from __new__ scaffolds. Domain state
    # stays as copied from the normal driver; do not force any progress flags.
    defaults = {
        "debug_enabled": False,
        "smoke_frames": None,
        "last_combat_scene_camera": None,
        "combat_camera_restore": None,
        "combat_camera_snapshot_zoom": None,
        "previous_time": None,
        "pending_action_pressed": False,
        "pending_interact_pressed": False,
        "pending_auto_move_goal": None,
        "pending_cancel_auto_move": False,
        "last_denied_reason": "",
        "last_denied_remaining": 0,
        "location_label_remaining": 0,
        "browser_pointer_sequence_seen": 0,
        "frame": 0,
        "presentation_time": 0,
        "accumulator": 0,
        "hitstop_remaining": 0,
        "session_started": True,
        "renderer": None,
        "projection_mode": app.runtime.raw.get("projection", {}).get("mode", "perspective"),
        "affine_projection_profile": AffineProjectionProfile.from_config(app.runtime.raw),
    }
    for name, value in defaults.items():
        if not hasattr(app, name):
            setattr(app, name, value)
    return app


def probe(original, target=None, frames=3, resolve_view=None):
    if not hasattr(original.progress_store.browser, "items"):
        raise ValueError("probe accepts synthetic dictionary storage only")
    original_storage = deepcopy(original.progress_store.browser.items)
    old = snapshot(original)
    app = clone_for_root_update(original)
    result = {"before": describe(app), "frames": []}
    trace = []
    depth = [0]
    handlers = (
        "update_ending",
        "update_collection_room",
        "update_week_debug",
        "update_patrol",
        "update_swarm_frame",
        "update_august_sightings",
        "update_august",
        "update_july_week4",
        "update_july_week3",
        "update_week2",
        "update_flowerbed_modal",
        "update_field_transition",
        "update_week_transition",
        "update_flowerbed_entry",
        "update_map_objectives",
        "update_july_story",
        "update_first_sight",
        "update_start_screen",
        "update_office_screen",
        "update_pause_screen",
        "update_water_study_screen",
        "update_play_screen",
    )
    for name in handlers:
        if not hasattr(app, name):
            continue
        original_handler = getattr(app, name)

        def record(*args, _name=name, _handler=original_handler, **kwargs):
            before = app.screen.name
            call_depth = depth[0]
            depth[0] += 1
            try:
                value = _handler(*args, **kwargs)
            finally:
                depth[0] -= 1
            trace.append(
                dict(
                    handler=_name,
                    handled=value is True,
                    depth=call_depth,
                    screen_before=before,
                    screen_after=app.screen.name,
                )
            )
            return value

        setattr(app, name, record)
    if target:
        app.pyxel.mouse_x = target.x + target.width / 2
        app.pyxel.mouse_y = target.y + target.height / 2
    for index in range(frames):
        app.pyxel.down = bool(target and index == 0)
        app.pyxel.pressed = bool(target and index == 0)
        trace.clear()
        view_before = resolve_view(app) if resolve_view else None
        App.update(app)
        frame = describe(app)
        frame["handlers"] = list(trace)
        frame["view_before"] = view_before
        frame["view_after"] = resolve_view(app) if resolve_view else None
        owners = [
            row["handler"]
            for row in trace
            if row["depth"] == 0
            and (
                row["handled"]
                or row["handler"]
                in (
                    "update_start_screen",
                    "update_office_screen",
                    "update_pause_screen",
                    "update_water_study_screen",
                    "update_play_screen",
                    "update_ending",
                    "update_collection_room",
                )
            )
        ]
        frame["owners"] = owners
        result["frames"].append(frame)
    assert snapshot(original) == old, "probe mutated original normal-driver state"
    assert original.progress_store.browser.items == original_storage, "probe changed original store"
    return result


if __name__ == "__main__":
    import json

    from twelve_week_driver import new_game

    original, storage, garden = new_game()
    print(json.dumps(probe(original), indent=2))
