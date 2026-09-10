# DriftWithMe

DriftWithMe is a Pyxel prototype project for the Jack World P0 slice. The
current build implements JWP000-JWP003: a 1024 x 1024 square world, cube
placeholders for Jack and buddy, fixed-step movement, obstacle sliding, pointer
ownership for drag-vs-hold, a start screen, five explicit SE preview hooks,
basic depth-sorted world drawing, and camera demos for overview/focus/pan.

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
- Space or stationary pointer hold: barrier placeholder
- X or ACTION button: E0 action-denied placeholder
- M: sound on/off
- F1: debug HUD
- ESC: pause
- R while paused: reset scene
- Q while paused: quit desktop app

Debug-only camera checks:

- F: focus nearest inspectable object, then return
- P: play the pan_demo camera sequence
- Walk into the north overview zone around X/Z 640-896 to trigger AreaCamera

The action button and SE preview do not claim bubble capture or discharge
success yet. Those systems start in later waves.

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
