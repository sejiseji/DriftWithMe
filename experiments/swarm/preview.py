"""Developer-only launcher: python -m experiments.swarm.preview.

Primitive actors deliberately keep the experiment independent of production
rendering. Real Japanese font and world spawn are read, but never written.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from drift_with_me.swarm_battle import PRESETS, SwarmBattle
from drift_with_me.swarm_view import SwarmView


class Preview(SwarmView):
    def __init__(self, preset="normal", demo=None, capture_dir=None):
        import pyxel

        self.p = pyxel
        self.integrated = False
        self.preset = preset
        self.demo = demo
        self.demo_done = set()
        self.capture_dir = Path(capture_dir).resolve() if capture_dir else None
        self.exported = set()
        if self.capture_dir:
            self.capture_dir.mkdir(parents=True, exist_ok=True)
        root = Path(__file__).resolve().parents[2] / "src/drift_with_me"
        world = json.loads((root / "data/prototype_world.json").read_text())
        spawn = world["spawn"]["player"]
        self.spawn = (spawn[0], spawn[2])
        self.battle = SwarmBattle(*PRESETS[preset], spawn=self.spawn)
        pyxel.init(640, 360, title="DriftWithMe / Swarm Lab - LOCAL ONLY", fps=60)
        pyxel.mouse(True)
        self.font = pyxel.Font(str(root / "assets/fonts/umplus_j12r_swarm.bdf"))
        pyxel.run(self.update, self.draw)

    def update(self):
        p, b = self.p, self.battle
        # Inputs are edge-triggered. No second input can spend during animation.
        if p.btnp(p.KEY_R):
            b.rematch()
            self.demo_done.clear()
        if b.phase in ("field", "victory", "approach"):
            for key, preset in zip(
                (p.KEY_1, p.KEY_2, p.KEY_3, p.KEY_4, p.KEY_5), PRESETS, strict=True
            ):
                if p.btnp(key):
                    self.preset = preset
                    self.battle = SwarmBattle(*PRESETS[preset], spawn=self.spawn)
                    self.demo_done.clear()
                    return
        if self.demo and b.phase == "approach":
            token = (b.phase, b.failures)
            should_miss = (
                self.demo == "retry"
                and b.phase == "approach"
                and b.failures == 0
                or self.demo == "retreat"
            )
            target = 0.2 if should_miss else b.settings.target
            if token not in self.demo_done and b.progress >= target:
                self.demo_done.add(token)
                b.input()
        elif p.btnp(p.KEY_SPACE) or p.btnp(p.MOUSE_BUTTON_LEFT):
            b.input()
        b.tick(1 / 60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=PRESETS, default="normal")
    parser.add_argument("--demo", choices=("success", "retry", "retreat"))
    parser.add_argument("--capture-dir", help="Export local renderer evidence and exit after demo")
    args = parser.parse_args()
    if args.capture_dir and not args.demo:
        parser.error("--capture-dir requires --demo")
    Preview(args.preset, args.demo, args.capture_dir)


if __name__ == "__main__":
    main()
