# E0 Manual Test Notes

Use this for JWP002-JWP003 manual checks. Automated tests cover model, input,
and camera contracts; device display, touch feel, audible output, and camera
composition still need human confirmation.

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
9. Press F1 to show debug HUD.
10. Press F and confirm the camera focuses the nearest inspectable object, then returns.
11. Press P and confirm the pan_demo visits the maintenance unit and observation post.
12. Walk into the north overview zone around X/Z 640-896 and confirm yaw/zoom blend smoothly.
13. Press ESC, then R to reset, Enter/ESC to resume, Q to quit.

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
6. Confirm buddy remains near Jack and participates in world depth ordering.
7. Confirm tree placeholders can pass in front of Jack and show a temporary outline.

## iPhone

Status: JWP002 smoke passed by user; JWP003 needs another pass.

Expected checks:

- Safari tab in landscape.
- Home-screen standalone launch.
- Canvas aspect ratio and Safe Area in both landscape orientations.
- Touch drag, long hold, UI capture, and rotation/cancel behavior.
- Actual audible output after a user start action.
- Buddy readability, overview blend, focus demo, pan_demo, and tree occlusion outline.
