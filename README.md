# DriftWithMe

DriftWithMe is a Pyxel prototype project for the Jack World P0 slice. The
current build implements JWP000-JWP012B: a 1024 x 1024 square world, baked
pyxres Jack sprites with front/back direction selection, a cube placeholder for
buddy, fixed-step movement, obstacle sliding, pointer
ownership for drag-vs-hold, a start screen, five explicit SE preview hooks,
basic depth-sorted world drawing, camera demos for overview/focus/pan, slow
normal urchins, water barrier repel, contact knockback, and water/energy refill
interactions. The action button now fires a bubble at an abnormal urchin and,
after capture, uses buddy energy for manual discharge. Short investigation
chips now freeze the world, record read object IDs, and feed a separate
effect layer for small particles, actor marks, focus cues, and grass reactions.
Static rendering now uses visual chunk candidates, one-per-chunk deterministic
ground details, and active enemy hysteresis/pinning without changing model
results for the covered input comparisons. Jack art is loaded from
`src/drift_with_me/assets/jack_sprite.pyxres` with a runtime metadata JSON while
the game-specific anchor, world size, and direction mapping stay outside the image resource.

The prototype specification pack is stored in `docs/prototype_spec/`. The game
loads the copied JSON data from `src/drift_with_me/data/`; tests compare both
locations so the runnable data and the documented spec do not drift silently.

## Requirements

- Python 3.11 or newer
- Pyxel

## Setup

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Run

```sh
python main.py
```

or, after editable install:

```sh
drift-with-me
```

## Controls

- Arrow keys / WASD: move in screen direction
- Mouse or touch drag on the world: move
- Space, stationary pointer hold, or GUARD button near a normal urchin: water barrier; consumes water and stops Jack
- E or CHECK/REFILL/CHARGE button: interact with nearby stations or markers
- X or ACTION/BUBBLE/GUARD/ZAP button: guard near normal urchins, fire bubble at abnormal urchins, then manually discharge a captured abnormal urchin
- Enter or DONE while an interaction chip is open: complete and close the chip
- M: sound on/off
- F1: debug HUD
- ESC: pause
- While paused: tap RESUME, RESET, RES MAX, ZERO RES, CULL, or DEBUG
- R/F/Z/C/D while paused: reset, resource max, resource zero, culling toggle, debug HUD
- Q while paused: quit desktop app

Debug-only camera checks:

- F: focus nearest inspectable object, then return
- P: play the pan_demo camera sequence
- Walk into the north overview zone around X/Z 640-896 to trigger AreaCamera

The action button only targets abnormal urchins. Normal urchins are handled by
avoidance, contact knockback, and water barrier repel.

## Web Build

```sh
python scripts/build_web.py
python -m http.server 8000
```

Then open `http://127.0.0.1:8000/`. The generated host uses Pyxel
`2.9.9`, disables Pyxel's virtual gamepad, preserves the landscape aspect ratio,
and includes a portrait orientation overlay. iPhone Safari behavior still needs
real-device confirmation for each new wave.

GitHub Pages entry point:

```text
https://sejiseji.github.io/DriftWithMe/
```

## Validate

```sh
python scripts/check_all.py
```

This runs the specification data validator, pytest, ruff, compileall, web build,
and `git diff --check`.

## Culling Measurement

```sh
python scripts/measure_culling.py --iterations 600
```

This records Python-side static visibility and draw-command preparation only.
The latest local JWP007 numbers are in `docs/jwp007_culling_measurement.md`.
