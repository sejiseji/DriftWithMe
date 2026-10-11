"""Approved sprite loops, displayed only in the temporary week-test session."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources

from drift_with_me.hex_assets import load_sprite_manifest, placement_for_upright_height_billboard
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

    def tick(self, now: float) -> None:
        if not self.paused:
            self.elapsed += max(0.0, now - self.previous_time)
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
        return (160.0, 240.0) if self.terrain == "water" else (512.0, 400.0)


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
    for kind, offset in (("normal", -28.0), ("abnormal", 28.0)):
        asset = library.get(f"electric_nudibranch_{kind}")
        placement = placement_for_upright_height_billboard(
            camera, asset.definition, Vec3(x + offset, 0.0, z)
        )
        if placement is None:
            continue
        frame = asset.frame(f"{state.direction_name}_{state.frame_index:02d}")
        commands.append(
            DrawCommand(
                depth=placement.depth,
                layer_bias=0,
                stable_id=f"nudibranch_preview:{kind}",
                draw=lambda asset=asset, placement=placement, frame=frame: (
                    renderer.draw_atmospheric_scaled_sprite(asset, placement, frame)
                ),
                atmosphere_strength=renderer.atmosphere_strength_config("enemy_strength", 1.0),
            )
        )
    return commands
