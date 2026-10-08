from types import SimpleNamespace

from drift_with_me.config import load_runtime_config


def finish_travel(app):
    if not hasattr(app, "runtime"):
        app.runtime = load_runtime_config()
    if not hasattr(app, "pyxel"):
        names = (
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
        )
        app.pyxel = SimpleNamespace(
            btn=lambda _: False, **{"KEY_" + n: i for i, n in enumerate(names)}
        )
    app.pointer_snapshot = SimpleNamespace(down=False)
    app.key_pressed = lambda *names: "KEY_RETURN" in names
    app.mouse_pressed_in = lambda rect: False
    for _ in range(100):
        if app.field_transition is None:
            break
        app.update_field_transition(0.1)
    assert app.field_transition is None
