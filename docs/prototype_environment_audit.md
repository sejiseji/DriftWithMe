# Prototype Environment Audit

Date: 2026-09-11

Scope: JWP000 for the DriftWithMe repository.

## Repository

- Working directory: `/Users/toytoytoy330/Desktop/AllMyFiles/AICoding/DriftWithMe`
- Branch before implementation: `main...origin/main`
- Existing local instructions: no `AGENTS.md` found in this repository.
- Existing entry point: `main.py`
- Existing package: `drift_with_me`
- Existing project state before spec work: minimal Pyxel scaffold.

## Runtime

- Python used by the local venv: 3.14.2
- Project requirement: `>=3.11`
- Pyxel package version: 2.9.9
- Pyxel runtime version constant: 2.9.9
- Pyxel `init` supports `quit_key`; the app sets `quit_key=None` so Escape can be in-game pause.
- Pyxel `blt` supports uniform `scale` and `rotate`, not separate `scale_x` / `scale_y`.
- Pyxel CLI supports `package` and `app2html`. The project uses a custom deterministic `pyxapp` zip and a dedicated HTML host instead of invoking `app2html` directly.

## Specification Data

- Imported pack path: `docs/prototype_spec/`
- Game data path: `src/drift_with_me/data/`
- Data validator command: `.venv/bin/python docs/prototype_spec/tools/validate_spec_data.py --self-test`
- Validator result at import time: PASS, entity_count 21, solid_count 8, enemy_count 3, rejected_invalid_mutations 7.
- Tests compare the game JSON files against `docs/prototype_spec/data/*.json`.

## Implementation Boundary

Implemented in E0:

- 512 x 236 medium logical display profile.
- 1024 x 1024 square map from JSON.
- Player cube movement using screen direction converted through the camera projection Jacobian.
- Static AABB collision, outer bounds, and wall sliding.
- Shallow fixed camera projection and placeholder depth-sorted world drawing.
- Pointer ownership state machine for drag movement vs stationary hold barrier.
- Start screen, sound toggle, five explicit SE preview buttons.
- Action-denied placeholder for future bubble/electric action.
- Dedicated web host generator with Pyxel 2.9.9 and virtual gamepad disabled.

Not implemented in E0:

- Normal urchin AI, abnormal dash, bubble capture, discharge success, resources consumption, refill, investigate panels, buddy follow, area camera, focus camera, performance culling.

## Commands

- `.venv/bin/python docs/prototype_spec/tools/validate_spec_data.py --self-test`
- `.venv/bin/python -m pytest`
- `.venv/bin/python scripts/build_web.py`
- `.venv/bin/python scripts/check_all.py`

## Unconfirmed

- iPhone Safari canvas size and Safe Area behavior: NOT_RUN.
- Home-screen standalone mode: NOT_RUN.
- Physical audio audibility on iPhone: NOT_RUN.
- Real touch pointer events beyond Pyxel mouse-compatible input: NOT_RUN.

