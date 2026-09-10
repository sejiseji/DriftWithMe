# E0 Manual Test Notes

Use this for JWP002 manual checks. Automated tests cover only model and input
contracts; device display, touch feel, and audible output still need human
confirmation.

## Desktop Native

```sh
source .venv/bin/activate
python main.py
```

1. Press Enter or tap START.
2. Move with Arrow keys or WASD.
3. Drag on the world with the mouse and confirm Jack keeps moving while the drag is held.
4. Hold the mouse without moving and confirm the barrier ring appears.
5. Drag first, then keep holding, and confirm the input does not convert into barrier.
6. Press Space and confirm the barrier ring appears while movement stops.
7. Press X or ACTION and confirm only the denied feedback/denied SE is used.
8. Press M and confirm sound toggles.
9. Press ESC, then R to reset, Enter/ESC to resume, Q to quit.

## Web Local

```sh
source .venv/bin/activate
python scripts/build_web.py
python -m http.server 8000
```

Open `http://127.0.0.1:8000/web/`.

1. Confirm the Pyxel virtual gamepad is not visible.
2. Confirm the START screen fits in the browser.
3. Confirm the portrait overlay appears when the viewport is taller than wide.
4. Confirm drag movement and stationary hold barrier with a mouse or touch-capable browser.
5. Confirm the five SE preview buttons are separate from game success events.

## iPhone

Status: NOT_RUN.

Expected checks:

- Safari tab in landscape.
- Home-screen standalone launch.
- Canvas aspect ratio and Safe Area in both landscape orientations.
- Touch drag, long hold, UI capture, and rotation/cancel behavior.
- Actual audible output after a user start action.

