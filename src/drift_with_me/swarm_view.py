"""Legacy standalone experiment only. Main-game drawing lives in swarm_render."""

from __future__ import annotations

import json
import math
from pathlib import Path

from drift_with_me.swarm_battle import KINDS


class ImageSurface:
    def __init__(self, pyxel, image):
        self.pyxel, self.image = pyxel, image
        self.labels = []

    def text(self, *args):
        self.labels.append(args)

    def __getattr__(self, name):
        if name == "frame_count":
            return self.pyxel.frame_count
        return getattr(self.image, name)


class SwarmView:
    def __init__(self, pyxel, battle, *, integrated=False):
        self.pyxel = pyxel
        self.battle = battle
        self.integrated = integrated
        self.image = pyxel.Image(640, 360)
        self.p = ImageSurface(pyxel, self.image) if integrated else pyxel
        self.font = pyxel.Font(str(Path(__file__).parent / "assets/fonts/umplus_j12r_swarm.bdf"))
        self.capture_dir = None
        self.exported = set()

    def draw_scaled(self, width, height):
        self.p.labels.clear()
        self.draw()
        scale = min(width / 640, height / 360)
        offset_x, offset_y = (width - 640 * scale) / 2, (height - 360 * scale) / 2
        p, b = self.pyxel, self.battle
        p.cls(1)
        p.blt((width - 640) / 2, (height - 360) / 2, self.image, 0, 0, 640, 360, scale=scale)
        # Render text at native pixel size; downsampling BDF glyphs loses strokes.
        p.text(8, 4, "DriftWithMe / 群れバトル", 10, self.font)
        p.text(
            8, 19, f"水 {b.water:g}  電力 {b.energy:g}  援護 {b.assists}/1  {b.phase}", 7, self.font
        )
        for x, y, text, color, font in self.p.labels:
            if text and 50 < y < 255:
                p.text(offset_x + x * scale, offset_y + y * scale, text, color, font)
        if b.phase == "approach":
            p.text(
                64,
                offset_y + 258 * scale,
                "捕縛" if b.phase == "approach" else "トドメ",
                7,
                self.font,
            )
        p.rect(0, height - 48, width, 48, 0)
        message = "6体撃退！ フィールドへ戻る" if b.phase == "victory" else b.message
        lines, current = [], ""
        for char in message:
            if self.font.text_width(current + char) > width - 16:
                lines.append(current)
                current = ""
            current += char
        lines.append(current)
        for index, line in enumerate(lines[:2]):
            p.text(8, height - 46 + index * 13, line, 7, self.font)
        p.text(8, height - 15, "SPACE / X / クリック：入力   ESC：一時停止", 6, self.font)

    def text(self, x, y, text, color=7):
        self.p.text(x, y, text, color, self.font)

    def actor(self, x, y, kind):
        p = self.p
        p.elli(x - 16, y + 12, 32, 8, 1)
        if kind == "urchin":
            for i in range(12):
                a = i * math.tau / 12
                p.line(x, y, x + math.cos(a) * 18, y + math.sin(a) * 18, 2)
            p.circ(x, y, 11, 2)
            p.circ(x - 4, y - 2, 2, 8)
            p.circ(x + 4, y - 2, 2, 8)
        elif kind == "slug":
            p.elli(x - 16, y - 5, 32, 19, 14)
            p.line(x - 10, y, x - 12, y - 16, 14)
            p.line(x + 8, y, x + 12, y - 16, 14)
            for dx in (-8, 0, 8):
                p.circ(x + dx, y + 4, 3, 15)
        elif kind == "jack":
            p.rect(x - 9, y - 1, 18, 20, 12)
            p.circ(x, y - 8, 9, 15)
            p.line(x - 5, y + 19, x - 8, y + 24, 7)
            p.line(x + 5, y + 19, x + 8, y + 24, 7)
        elif kind == "fuse":
            p.circ(x, y, 10, 10)
            p.rect(x - 8, y - 4, 16, 6, 1)
            p.pset(x - 3, y - 2, 12)
            p.pset(x + 3, y - 2, 12)
            p.line(x, y - 10, x + 5, y - 17, 10)
        else:
            p.rect(x - 8, y, 16, 20, 3)
            p.circ(x, y - 8, 8, 4)
        self.text(
            x - 22, y + 26, {"jack": "ジャック", "fuse": "ヒューズ", "fuji": "フジ"}.get(kind, "")
        )

    def draw(self):
        p, b = self.p, self.battle
        p.cls(1)
        p.rect(0, 54, 640, 224, 3)
        for y in range(64, 278, 28):
            p.line(0, y, 640, y, 5)
        self.text(16, 8, "DriftWithMe / 群れバトル試作 / 混成6体・単独1戦", 10)
        self.text(
            16, 28, f"水 {b.water:g}   電力 {b.energy:g}   フジ援護 {b.assists}/1   {b.phase}"
        )
        p.camera(3 * math.sin(b.elapsed * 120) if b.phase == "shake" else 0, 0)
        if b.phase == "field":
            self.text(190, 100, "隔離フィールド：南西の初期位置", 10)
            self.text(190, 122, f"X={b.position[0]:g}  Z={b.position[1]:g}")
            self.actor(140, 230, "jack")
            self.actor(183, 210, "fuse")
        else:
            p.ellib(268, 153, 104, 75, 11)
            self.actor(320, 185, "jack")
            self.actor(359, 144 + math.sin(p.frame_count / 10) * 3, "fuse")
            if b.phase == "assist" or b.phase == "retreat_line" and b.failures > 1:
                self.actor(240, 191, "fuji")
            for i, kind in enumerate(KINDS):
                if i in b.defeated:
                    continue
                x, y = b.enemy_position(i)
                if b.phase == "shake":
                    x += math.sin(b.elapsed * 100 + i) * 5
                self.actor(x, y, kind)
                if b.captured:
                    p.ellib(x - 22, y - 23, 44, 47, 12)
                if b.phase == "electric" and kind == "urchin":
                    points = [(359, 144), (x + 20, y - 42), (x - 15, y - 24), (x, y)]
                    for a, c in zip(points, points[1:], strict=False):
                        p.line(*a, *c, 10 if p.frame_count % 4 < 2 else 7)
                if kind == "slug":
                    if b.phase in ("circle", "converge", "spear"):
                        p.ellib(x - 26, y + 6, 52, 17, 12)
                        p.ellib(x - 22, y + 8, 44, 13, 6)
                    if b.phase == "converge":
                        t = min(1, b.elapsed / b.settings.converge)
                        for a in range(8):
                            angle = a * math.tau / 8 + b.elapsed * 5
                            dx, dy = math.cos(angle), math.sin(angle)
                            r = 26 * (1 - t)
                            p.line(x + dx * r, y + 14 + dy * r / 3, x, y + 14, 12)
                    if b.phase == "spear":
                        height = min(92, b.elapsed / 0.16 * 92)
                        p.tri(x - 19, y + 15, x + 19, y + 15, x, y + 15 - height, 12)
                        p.tri(x - 6, y + 15, x + 6, y + 15, x, y + 15 - height, 7)
        p.camera()
        if b.phase == "approach":
            self.text(182, 260, "捕縛" if b.phase == "approach" else "トドメ（1回）")
            p.rect(220, 261, 220, 10, 1)
            p.rect(
                220 + (b.settings.target - b.settings.radius) * 220,
                261,
                b.settings.radius * 440,
                10,
                12,
            )
            p.rect(220 + b.progress * 220, 257, 3, 18, 10)
        p.rect(8, 282, 624, 42, 0)
        # Wrap Japanese in short lines without modifying the exact source dialogue.
        for line, start in enumerate(range(0, len(b.message), 46)):
            self.text(16, 287 + line * 16, b.message[start : start + 46])
        self.text(
            16,
            330,
            (
                "SPACE / X / クリック：入力   ESC：一時停止"
                if self.integrated
                else "1:通常 2:捕縛水不足 3:トドメ水不足 4:電力不足 5:両方不足 / R:再戦"
            ),
            6,
        )
        if b.phase == "fade":
            # Full-screen ordered fade after the complete dialogue hold.
            density = int(min(1, b.elapsed / b.settings.fade) * 16)
            for y in range(360):
                for x in range((y * 5) % 16, 640, 16):
                    p.rect(x, y, density, 1, 0)

        if self.capture_dir:
            token = f"{b.phase}-{b.failures}"
            # Export actual Pyxel framebuffer at a useful point within each effect.
            ready = b.elapsed >= (0.2 if b.phase in ("spear", "converge", "circle") else 0.05)
            if token not in self.exported and ready:
                p.screen.save(str(self.capture_dir / f"{token}.png"), 2)
                self.exported.add(token)
            if b.phase in ("field", "victory") and b.elapsed > 0.4:
                p.screencast(str(self.capture_dir / "sequence.gif"), scale=1)
                (self.capture_dir / "result.json").write_text(
                    json.dumps(
                        {
                            "phase": b.phase,
                            "water": b.water,
                            "energy": b.energy,
                            "defeated": sorted(b.defeated),
                            "events": b.events,
                            "position": b.position,
                            "message": b.message,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                p.quit()
