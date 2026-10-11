"""Presentation-only relay finish. No damage, rewards, enemies or save writes."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

from drift_with_me.hex_assets import LoadedSpriteFrame
from drift_with_me.math3d import Vec3

BIT_COUNT = 6
CURVE_SAMPLES = 33
BUBBLE_BEGIN = 0.52
BUBBLE_STAGGER = 0.055
BUBBLE_FLIGHT = 0.50
BEAM_BEGIN = 1.38
BEAM_STAGGER = 0.105
CURVE_FLIGHT = 0.75
CONTACT_HOLD = 0.09
DIRECT_FLIGHT = 0.14
FIRST_IMPACT = BEAM_BEGIN + CURVE_FLIGHT + CONTACT_HOLD + DIRECT_FLIGHT
BURN_BEGIN = FIRST_IMPACT + 0.12
BURN_DURATION = 0.95
RAY_FADE_BEGIN = BURN_BEGIN + BURN_DURATION + 0.05
RAY_FADE_END = RAY_FADE_BEGIN + 0.20
BIT_FADE_END = RAY_FADE_END + 0.20
DURATION = BIT_FADE_END + 0.18
BURN_STEPS = 24


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def quadratic_path(start: Vec3, control: Vec3, end: Vec3) -> tuple[Vec3, ...]:
    return tuple(
        start * ((1 - t) ** 2) + control * (2 * (1 - t) * t) + end * (t * t)
        for t in (i / (CURVE_SAMPLES - 1) for i in range(CURVE_SAMPLES))
    )


@dataclass(frozen=True)
class Relay:
    index: int
    bit: Vec3
    spawn_path: tuple[Vec3, ...]
    laser_path: tuple[Vec3, ...]

    @property
    def arrival(self) -> float:
        return BEAM_BEGIN + self.index * BEAM_STAGGER + CURVE_FLIGHT

    @property
    def straight_start(self) -> float:
        return self.arrival + CONTACT_HOLD

    @property
    def impact(self) -> float:
        return self.straight_start + DIRECT_FLIGHT


@dataclass
class FocusLaserAction:
    jack: Vec3
    fuse: Vec3
    target: Vec3
    kind: str
    frame_id: str
    relays: tuple[Relay, ...]
    elapsed: float = 0.0
    projected_camera: object = None
    projected: dict = field(default_factory=dict)
    burn_frames: tuple[LoadedSpriteFrame, ...] = ()
    geometry_projection_count: int = 0
    burn_preparation_count: int = 0

    @classmethod
    def create(cls, jack: Vec3, fuse: Vec3, target: Vec3, right, kind, frame_id):
        relays = []
        # A loose upper semicircle centered on the target, never on Fuse.
        for i in range(BIT_COUNT):
            angle = math.radians(18 + i * 144 / (BIT_COUNT - 1))
            lateral = math.cos(angle) * 29
            height = 18 + math.sin(angle) * 25
            bit = Vec3(target.x + right.x * lateral, height, target.z + right.y * lateral)
            spawn_control = (jack + bit) * 0.5 + Vec3(0, 10 + i, 0)
            laser_control = (fuse + bit) * 0.5 + Vec3(
                right.x * (i - 2.5) * 3, 16 + i * 1.1, right.y * (i - 2.5) * 3
            )
            relays.append(
                Relay(
                    i,
                    bit,
                    quadratic_path(jack, spawn_control, bit),
                    quadratic_path(fuse, laser_control, bit),
                )
            )
        return cls(jack, fuse, target, kind, frame_id, tuple(relays))

    @property
    def burn_progress(self) -> float:
        return clamp01((self.elapsed - BURN_BEGIN) / BURN_DURATION)

    @property
    def complete(self) -> bool:
        return self.elapsed >= DURATION

    @property
    def phase(self) -> str:
        if self.complete:
            return "DONE"
        if self.elapsed < BUBBLE_BEGIN:
            return "FUSE: SUPPRESS"
        if self.elapsed < BEAM_BEGIN:
            return "JACK: DEPLOY 6 BITS"
        if self.elapsed < FIRST_IMPACT:
            return "CURVE > BIT > STRAIGHT"
        if self.elapsed < BURN_BEGIN:
            return "FOCUS IMPACT"
        if self.elapsed < RAY_FADE_END:
            return "PIXEL BURN"
        return "CLEAR"

    def ensure_projection(self, camera) -> dict:
        if self.projected_camera != camera:
            self.projected_camera = camera
            self.projected = {
                "jack": camera.project(self.jack),
                "fuse": camera.project(self.fuse),
                "target": camera.project(self.target),
                "bits": tuple(camera.project(r.bit) for r in self.relays),
                "spawn": tuple(tuple(camera.project(p) for p in r.spawn_path) for r in self.relays),
                "laser": tuple(tuple(camera.project(p) for p in r.laser_path) for r in self.relays),
            }
            self.geometry_projection_count += 1
        return self.projected

    def ensure_burn_frames(self, pyxel, frame, colkey: int) -> tuple[LoadedSpriteFrame, ...]:
        if not self.burn_frames:
            source = frame.source.pixels
            thresholds = burn_thresholds(frame.width, frame.height)
            frames = []
            for stage in range(BURN_STEPS + 1):
                pixels = burn_pixels(source, thresholds, stage / BURN_STEPS, colkey)
                image = pyxel.Image(frame.width, frame.height)
                rows = [
                    "".join(format(c, "X") for c in pixels[y * frame.width : (y + 1) * frame.width])
                    for y in range(frame.height)
                ]
                image.set(0, 0, rows)
                frames.append(
                    LoadedSpriteFrame(
                        frame_id=f"{frame.frame_id}_burn_{stage}",
                        image=image,
                        source=None,
                        u=0,
                        v=0,
                        width=frame.width,
                        height=frame.height,
                        source_hash=hashlib.sha256(pixels).hexdigest(),
                    )
                )
            self.burn_frames = tuple(frames)
            self.burn_preparation_count += 1
        return self.burn_frames


def burn_thresholds(width: int, height: int) -> tuple[float, ...]:
    result = []
    for y in range(height):
        for x in range(width):
            noise = ((x * 73856093) ^ (y * 19349663) ^ (x * y * 83492791)) & 1023
            radius = min(1.0, math.hypot(x - width / 2, y - height * 0.60) / (width * 0.7))
            result.append(0.025 + 0.94 * (0.67 * noise / 1023 + 0.33 * radius))
    return tuple(result)


def burn_pixels(source: bytes, thresholds, progress: float, colkey: int) -> bytes:
    if progress <= 0:
        return source
    if progress >= 1:
        return bytes([colkey]) * len(source)
    return bytes(
        colkey if color == colkey or rank <= progress else 10 if rank - progress < 0.04 else color
        for color, rank in zip(source, thresholds, strict=True)
    )


def point_on_path(path, amount):
    value = clamp01(amount) * (len(path) - 1)
    i = min(len(path) - 2, int(value))
    a, b = path[i], path[i + 1]
    if a is None or b is None:
        return None
    t = value - i
    return (a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)


def draw_path_tail(pyxel, path, progress, color=12):
    start = max(0.0, progress - 0.23)
    points = [point_on_path(path, start)]
    points.extend(
        (p.x, p.y) if p is not None else None
        for i, p in enumerate(path)
        if start < i / (len(path) - 1) < progress
    )
    points.append(point_on_path(path, progress))
    for a, b in zip(points, points[1:], strict=False):
        if a is not None and b is not None:
            pyxel.line(round(a[0]), round(a[1]), round(b[0]), round(b[1]), color)
    if points[-1] is not None:
        pyxel.pset(round(points[-1][0]), round(points[-1][1]), 7)


def draw_focus_laser(renderer, action, camera, relay_indices=None, shared=True) -> None:
    if action.complete:
        return
    pyxel = renderer.pyxel
    p = action.ensure_projection(camera)
    target, fuse, jack = p["target"], p["fuse"], p["jack"]
    if target is None or fuse is None or jack is None:
        return
    time = action.elapsed
    if shared and time < 0.48:
        # Reuse only the existing restraint range, excluding its final large zap.
        renderer.draw_combat_homing_zaps(fuse, target, 0.26 + time / 0.48 * 0.40)
    if shared and time < BURN_BEGIN:
        pyxel.ellib(round(target.x - 10), round(target.y - 9), 20, 18, 12)
    for relay in action.relays:
        i = relay.index
        if relay_indices is not None and i not in relay_indices:
            continue
        spawn = (time - BUBBLE_BEGIN - i * BUBBLE_STAGGER) / BUBBLE_FLIGHT
        if spawn < 0 or time >= BIT_FADE_END:
            continue
        if spawn < 1:
            bit_xy = point_on_path(p["spawn"][i], spawn)
        else:
            bit = p["bits"][i]
            bit_xy = None if bit is None else (bit.x, bit.y)
        if bit_xy is None:
            continue
        bx, by = map(round, bit_xy)
        if time < RAY_FADE_END:
            pyxel.circb(bx, by, 3, 12)
            pyxel.pset(bx - 1, by - 1, 7)
        else:
            pyxel.circb(bx, by, 1, 5)
        curve = (time - BEAM_BEGIN - i * BEAM_STAGGER) / CURVE_FLIGHT
        if 0 <= curve < 1:
            draw_path_tail(pyxel, p["laser"][i], curve)
        elif relay.arrival <= time < relay.straight_start:
            # Local contact light makes the change in trajectory readable.
            pyxel.circ(bx, by, 2, 7)
            pyxel.circb(bx, by, 4, 10)
        if relay.straight_start <= time < RAY_FADE_END:
            travel = clamp01((time - relay.straight_start) / DIRECT_FLIGHT) ** 2
            ex = bx + (target.x - bx) * travel
            ey = by + (target.y - by) * travel
            color = 7 if time < RAY_FADE_BEGIN else 10
            pyxel.line(bx, by, round(ex), round(ey), color)
            if time < RAY_FADE_BEGIN:
                pyxel.line(bx + 1, by, round(ex + 1), round(ey), 10)
    if shared and FIRST_IMPACT <= time < RAY_FADE_END:
        pyxel.circ(round(target.x), round(target.y), 2, 10)
        pyxel.pset(round(target.x), round(target.y), 7)
    if shared and BURN_BEGIN <= time < BIT_FADE_END:
        # Bounded embers, driven by time; never added to the persistent effect pool.
        for i in range(8):
            age = time - BURN_BEGIN - i * 0.085
            if 0 <= age < 0.55:
                px = target.x + (i % 4 - 1.5) * (3 + age * 3)
                py = target.y - age * 16 - (i // 4) * 3
                pyxel.pset(round(px), round(py), 10 if age < 0.24 else 9)
