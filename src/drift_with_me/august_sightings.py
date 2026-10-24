"""Non-colliding juvenile sightings using the normal sprite/depth renderer."""

from dataclasses import dataclass, replace

from drift_with_me.hex_assets import placement_for_upright_height_billboard
from drift_with_me.math3d import (
    AffineCameraState,
    Vec3,
    screen_to_ground_affine,
    screen_to_ground_point,
)
from drift_with_me.nudibranch_preview import preview_assets

SIGHTINGS = {
    "northwest": ("urchin", "urchin"),
    "northeast": ("slug", "slug"),
    "southeast": ("urchin", "slug", "urchin", "slug"),
}
LINES = {
    "northwest": (
        ("ジャック", "小さなウニが横切った。いつものウニよりずっと小さいね"),
        ("ヒューズ", "ここでも幼体が育っているのね。見かけた場所を記録しましょう"),
    ),
    "northeast": (
        ("ジャック", "今のは小さなウミウシだね。あっという間に通り過ぎた"),
        ("ヒューズ", "幼体がここにもいるわ。姿と場所を記録しておきましょう"),
    ),
    "southeast": (
        ("ジャック", "小さなウニもウミウシもいたね"),
        ("ヒューズ", "同じ場所で両方を見かけたわ。どこで何を見たか、そのまま伝えましょう"),
    ),
}
DURATION = 1.3


@dataclass
class JuvenileSighting:
    site: str
    elapsed: float

    def draw_commands(self, renderer, model, camera):
        from drift_with_me.render import DrawCommand

        library = getattr(renderer, "_nudibranch_preview_assets", None)
        if library is None:
            library = renderer._nudibranch_preview_assets = preview_assets(renderer.pyxel)
        anchor = camera.project(Vec3(model.player.x, 0, model.player.z))
        commands = []
        for i, kind in enumerate(SIGHTINGS[self.site]):
            t = (self.elapsed - i * 0.12) / 0.9
            if not 0 <= t <= 1:
                continue
            scale = camera.viewport_width / 512
            sx = anchor.x + (-64 + 128 * t) * scale
            sy = anchor.y - (36 + (i % 2) * 8) * scale
            ground = (
                screen_to_ground_affine(camera, sx, sy)
                if isinstance(camera, AffineCameraState)
                else screen_to_ground_point(camera, sx, sy)
            )
            if ground is None:
                continue
            asset = (
                renderer.configured_sprite_asset(model, "normal_urchin_idle_asset")
                if kind == "urchin"
                else library.get("electric_nudibranch_normal")
            )
            if asset is None:
                raise RuntimeError("Missing juvenile production sprite")
            definition = replace(
                asset.definition, world_size=tuple(v * 0.38 for v in asset.definition.world_size)
            )
            placement = placement_for_upright_height_billboard(
                camera, definition, Vec3(ground.x, 0, ground.y)
            )
            if placement is None:
                continue
            frame = asset.frame()
            point = camera.project(Vec3(ground.x, 0, ground.y))
            commands.append(
                DrawCommand(
                    depth=point.depth,
                    layer_bias=0,
                    stable_id=f"august_baby:{i}",
                    draw=lambda a=asset, p=placement, f=frame: (
                        renderer.draw_atmospheric_scaled_sprite(a, p, f)
                    ),
                    atmosphere_strength=0.0,
                )
            )
        return commands
