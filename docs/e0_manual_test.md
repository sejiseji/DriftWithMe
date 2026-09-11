# E0 Manual Test Notes

Use this for JWP002-JWP007 manual checks. Automated tests cover model, input,
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
6. Press Space and confirm the water barrier ring appears, Jack stops, and WATER decreases.
7. Lure a normal urchin near the barrier and confirm it is pushed away once, then rests.
8. Let a normal urchin reach barrier range and confirm ACTION changes to GUARD.
9. Hold GUARD and confirm the barrier appears, WATER decreases, and the normal urchin is pushed away once.
10. Approach a normal urchin without the barrier and confirm Jack is knocked back, not damaged.
11. Stand near a working tap and press E or REFILL; confirm the compact chip freezes the world and WATER returns to 100 only at completion.
12. Start a refill and press ESC before completion; confirm the refill is cancelled and the resource value is unchanged.
13. Check the stopped tap and confirm it opens a short investigation chip but does not refill water.
14. Press Enter or DONE during an investigation chip and confirm the chip closes without moving Jack.
15. Press F1 and confirm the debug inspect count increments only for first reads.
16. Move near the abnormal urchin and confirm it shows windup, fixed-direction dash, then recover.
17. Press X or BUBBLE near the abnormal urchin and confirm WATER decreases by 12 and a bubble travels.
18. Confirm a bubble hit produces the capture ring and does not automatically discharge.
19. Press X or ZAP again and confirm ENERGY decreases by 20, the abnormal urchin disappears, and the discharge SE is used once.
20. Confirm pressing ACTION with no abnormal target, low water, or low energy gives denied feedback without spending the resource.
21. Walk through grass placeholders and confirm small particles appear without changing movement.
22. Press M and confirm sound toggles.
23. Press F1 to show debug HUD.
24. Press F and confirm the camera focuses the nearest inspectable object, then returns.
25. Press P and confirm the pan_demo visits the maintenance unit and observation post.
26. Walk into the north overview zone around X/Z 640-896 and confirm yaw/zoom blend smoothly.
27. Press F1 and confirm `vis`, `chunks`, and `active` counters change smoothly while walking.
28. Press ESC, then R to reset, Enter/ESC to resume, Q to quit.

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
8. Confirm touch hold consumes water only while the barrier is active.
9. Confirm REFILL/CHARGE/CHECK taps do not start world movement from the same touch.
10. Confirm refill chip and focus camera do not shift touch coordinates after closing.
11. Confirm ACTION changes to BUBBLE near the abnormal urchin and to ZAP only after capture.
12. Confirm ACTION changes to GUARD near a normal urchin and holding it activates the barrier without starting world movement.
13. Confirm one tap fires the bubble and a separate later tap is required for discharge.
14. Confirm DONE closes an investigation chip and the same tap does not leak into movement.
15. Confirm small event particles and grass reactions appear without strong flashing or shaking.
16. Confirm debug culling counters are visible in landscape and do not cover touch controls.

## iPhone

Status: JWP002-JWP006 smoke passed by user; JWP007 needs another pass.

Expected checks:

- Safari tab in landscape.
- Home-screen standalone launch.
- Canvas aspect ratio and Safe Area in both landscape orientations.
- Touch drag, long hold, UI capture, and rotation/cancel behavior.
- Actual audible output after a user start action.
- Buddy readability, overview blend, focus demo, pan_demo, and tree occlusion outline.
- Normal urchin readability, barrier repel timing, WATER/ENERGY HUD readability, and refill/cancel behavior.
- Abnormal urchin windup/dash readability, bubble targeting, capture ring, and separate ZAP tap behavior.
- Investigation text readability, DONE tap behavior, first-read debug count, and small effect readability.
- Culling counter readability and actual frame feel with normal and overview camera movement.

## Local Culling Measurement

```sh
source .venv/bin/activate
python scripts/measure_culling.py --iterations 600
```

This measures Python-side candidate generation only. Do not treat it as an iPhone or browser FPS result.
