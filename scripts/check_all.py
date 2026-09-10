from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_step(name: str, command: list[str], root: Path) -> int:
    print(f"==> {name}")
    completed = subprocess.run(command, cwd=root)
    if completed.returncode != 0:
        print(f"FAILED: {name} exited with {completed.returncode}")
    return completed.returncode


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    python = sys.executable
    steps = [
        ("pytest", [python, "-m", "pytest"]),
        ("ruff check", [python, "-m", "ruff", "check", "."]),
        ("ruff format check", [python, "-m", "ruff", "format", "--check", "."]),
        ("compileall", [python, "-m", "compileall", "src", "main.py", "scripts", "tests"]),
    ]

    failures = 0
    for name, command in steps:
        failures += run_step(name, command, root) != 0

    if failures:
        print(f"check_all: FAIL ({failures} failed step(s))")
        return 1

    print("check_all: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
