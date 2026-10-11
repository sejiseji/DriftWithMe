"""Approved sprite loops, displayed only in the temporary week-test session."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources

from drift_with_me.focus_laser import BURN_STEPS, FocusLaserAction, draw_focus_laser
from drift_with_me.hex_assets import (
    draw_scaled_sprite,
    load_sprite_manifest,
    placement_for_upright_height_billboard,
)
from drift_with_me.math3d import Vec3

DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
FPS = 6


@dataclass
class NudibranchPreview:
    elapsed: float = 0.0
    previous_time: float = 0.0
    direction: int = 0
    automatic: bool = True
    paused: bool = False
    terrain: str = "water"
    mode: str = "sprites"
    target_kind: str = "abnormal"
    target_anchor: tuple[float, float] | None = None
    focus_action: FocusLaserAction | None = None

    def tick(self, now: float) -> None:
        if not self.paused:
            delta = max(0.0, now - self.previous_time)
            self.elapsed += delta
            if self.focus_action is not None:
                self.focus_action.elapsed += delta
        self.previous_time = now

    @property
    def frame_index(self) -> int:
        return int(self.elapsed * FPS + 1e-9) % 4

    @property
    def direction_name(self) -> str:
        return DIRECTIONS[int(self.elapsed // 2) % 8 if self.automatic else self.direction]

    def freeze_direction(self) -> None:
        self.direction = DIRECTIONS.index(self.direction_name)
        self.automatic = False

    @property
    def center(self) -> tuple[float, float]:
        return (256.0, 104.0) if self.terrain == "water" else (512.0, 400.0)


def preview_attack_direction(model) -> str | None:
    state = getattr(model, "nudibranch_preview", None)
    if (
        state is not None
        and state.mode == "laser"
        and state.focus_action is not None
        and not state.focus_action.complete
    ):
        # Existing screen-space SE sprites; do not write ordinary facing caches.
        return "front_right"
    return None


def preview_assets(pyxel):
    root = resources.files("drift_with_me").joinpath("assets", "electric_nudibranch")
    manifest = json.loads(root.joinpath("sprites.json").read_text(encoding="utf-8"))
    return load_sprite_manifest(
        pyxel, manifest, lambda path: root.joinpath(path).read_text(encoding="utf-8"), enabled=True
    )


def preview_draw_commands(renderer, model, camera):
    state = getattr(model, "nudibranch_preview", None)
    if state is None:
        return []
    from drift_with_me.render import DrawCommand

    library = getattr(renderer, "_nudibranch_preview_assets", None)
    if library is None:
        library = renderer._nudibranch_preview_assets = preview_assets(renderer.pyxel)
    commands = []
    x, z = state.center
    samples = (("normal", -28.0), ("abnormal", 28.0))
    if state.mode == "laser":
        x, z = state.target_anchor
        samples = ((state.target_kind, 0.0),)
    for kind, offset in samples:
        asset = library.get(f"electric_nudibranch_{kind}")
        placement = placement_for_upright_height_billboard(
            camera, asset.definition, Vec3(x + offset, 0.0, z)
        )
        if placement is None:
            continue
        action = state.focus_action
        if action is not None and action.burn_progress >= 1:
            continue
        frame = asset.frame(
            action.frame_id
            if action is not None
            else f"{state.direction_name}_{state.frame_index:02d}"
        )
        if action is not None and action.burn_progress > 0:
            frames = action.ensure_burn_frames(renderer.pyxel, frame, asset.definition.colkey)
            frame = frames[int(action.burn_progress * BURN_STEPS)]
        commands.append(
            DrawCommand(
                depth=placement.depth,
                layer_bias=0,
                stable_id=f"nudibranch_preview:{kind}",
                draw=lambda asset=asset, placement=placement, frame=frame: (
                    draw_scaled_sprite(renderer.pyxel, frame, asset.definition, placement)
                    if frame.source is None
                    else renderer.draw_atmospheric_scaled_sprite(asset, placement, frame)
                ),
                atmosphere_strength=renderer.atmosphere_strength_config("enemy_strength", 1.0),
            )
        )
    if state.focus_action is not None:
        action = state.focus_action
        point = camera.project(action.target)
        if point is not None and not action.complete:
            commands.append(
                DrawCommand(
                    depth=point.depth,
                    layer_bias=1,
                    stable_id="focus_laser_preview",
                    draw=lambda: draw_focus_laser(renderer, action, camera, (), True),
                    atmosphere_strength=0.0,
                )
            )
            projected = action.ensure_projection(camera)
            for i, bit in enumerate(projected["bits"]):
                if bit is not None:
                    commands.append(
                        DrawCommand(
                            depth=bit.depth,
                            layer_bias=1,
                            stable_id=f"focus_laser_bit:{i}",
                            draw=lambda i=i: draw_focus_laser(
                                renderer, action, camera, (i,), False
                            ),
                            atmosphere_strength=0.0,
                        )
                    )
    return commands
