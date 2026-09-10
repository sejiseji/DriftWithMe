# DriftWithMe

DriftWithMe is a new Pyxel game project scaffold. The prototype specification
will be added later; for now this repository contains a small runnable Pyxel app,
basic project packaging, and lightweight verification.

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

- Left and Right: steer
- Up: accelerate
- Down: brake
- Z: boost
- R: reset
- ESC: quit

## Validate

```sh
python scripts/check_all.py
```

The scaffold intentionally keeps gameplay minimal until the prototype
specification is available.

