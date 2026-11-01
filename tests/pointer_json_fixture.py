"""Adapters for synthetic browser fixtures; production uses the actual HOST reader."""

import json
from types import SimpleNamespace


def attach_pointer_snapshot(window):
    def read():
        p = window.__driftWithMePointer
        if p is None:
            raise AttributeError("missing fixture pointer")
        if hasattr(p, "snapshotJSON"):
            return p.snapshotJSON
        epoch = getattr(getattr(window, "__driftWithMeLifecycle", None), "inputEpoch", 0)
        return json.dumps(
            {
                "schema": 1,
                "sequence": p.sequence,
                "epoch": epoch,
                "down": p.down,
                "pressed": p.pressed,
                "released": getattr(p, "released", not p.down),
                "inside": getattr(p, "inside", True),
                "cancelled": getattr(p, "cancelled", False),
                "current": {"x": p.x, "y": p.y},
                "press": {
                    "x": getattr(p, "pressedX", p.x),
                    "y": getattr(p, "pressedY", p.y),
                    "sequence": p.sequence,
                    "epoch": epoch,
                },
                "logical": {"width": 512, "height": 236},
            }
        )

    window.__driftWithMeReadPointerSnapshot = read
    return window


def pointer_window(pointer):
    return attach_pointer_snapshot(SimpleNamespace(__driftWithMePointer=pointer))
