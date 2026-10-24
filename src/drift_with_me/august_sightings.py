"""Non-colliding juvenile sightings using the normal sprite/depth renderer."""

from dataclasses import dataclass, replace

from drift_with_me.hex_assets import placement_for_upright_height_billboard
from drift_with_me.math3d import (
    AffineCameraState,
    Vec3,
    screen_to_ground_affine,
    screen_to_ground_point,
)
from drift_with_me.nudibranch_preview import DIRECTIONS, FPS, preview_assets

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
MAX_SIGHTING_ZOOM = 2.44
EXIT_COVERS = {"northwest": "tree_24", "northeast": "tree_11", "southeast": "solar_east"}


def crossing_path(model, camera, site):
    """Cache real ground endpoints so camera settling cannot drag the actors."""
    paths = getattr(model, "august_sighting_paths", None)
    if paths is None:
        paths = model.august_sighting_paths = {}
    if site not in paths:
        cover = model.world.object_by_id(EXIT_COVERS[site])
        if cover is None:
            raise RuntimeError("Missing authored juvenile exit cover")
        anchor = camera.project(Vec3(cover.x, 0, cover.z))
        if anchor is None:
            return None
        scale = camera.viewport_width / 512
        unproject = (
            screen_to_ground_affine
            if isinstance(camera, AffineCameraState)
            else screen_to_ground_point
        )
        # Feet end behind the existing opaque canopy/equipment body.
        world_height = cover.sprite_world_height or (48 if site == "southeast" else 64)
        top = camera.project(Vec3(cover.x, world_height, cover.z))
        if top is None:
            return None
        height = abs(top.y - anchor.y) * (0.13 if site == "southeast" else 0.368)
        a = unproject(camera, anchor.x - 128 * scale, anchor.y - height - 3 * scale)
        b = unproject(camera, anchor.x, anchor.y - height)
        if a is None or b is None:
            return None
        paths[site] = (Vec3(a.x, 0, a.y), Vec3(b.x, 0, b.y))
    return paths[site]


@dataclass
class JuvenileSighting:
    site: str
    elapsed: float

    def draw_commands(self, renderer, model, camera):
        from drift_with_me.render import DrawCommand

        library = getattr(renderer, "_nudibranch_preview_assets", None)
        if library is None:
            library = renderer._nudibranch_preview_assets = preview_assets(renderer.pyxel)
        path = crossing_path(model, camera, self.site)
        if path is None:
            return []
        start, end = path
        commands = []
        for i, kind in enumerate(SIGHTINGS[self.site]):
            t = (self.elapsed - i * 0.12) / 0.9
            if not 0 <= t <= 1:
                continue
            ground = Vec3(start.x + (end.x - start.x) * t, 0, start.z + (end.z - start.z) * t)
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
            placement = placement_for_upright_height_billboard(camera, definition, ground)
            if placement is None:
                continue
            frame = juvenile_frame(asset, kind, camera, start, end, self.elapsed - i * 0.12)
            point = camera.project(ground)
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


def reaction_amount(elapsed):
    def smooth(t):
        t = max(0.0, min(1.0, t))
        return t * t * (3 - 2 * t)

    if elapsed < 0.10:
        return smooth(elapsed / 0.10)
    if elapsed < 0.26:
        return 1.0
    return 1 - smooth((elapsed - 0.26) / 0.92)


def sighting_camera(model, camera, sighting):
    """Draw-only push: retain the input camera, yaw, pitch and world actors."""
    if sighting is None:
        return camera
    path = crossing_path(model, camera, sighting.site)
    amount = reaction_amount(sighting.elapsed)
    if path is None or amount <= 0:
        return camera
    cover = model.world.object_by_id(EXIT_COVERS[sighting.site])
    points = [
        *path,
        *(Vec3(p.x, 10, p.z) for p in path),
        Vec3(model.player.x, 0, model.player.z),
        Vec3(model.player.x, 24, model.player.z),
        Vec3(model.buddy.x, model.buddy.y, model.buddy.z),
        Vec3(model.buddy.x, model.buddy.y + 12, model.buddy.z),
        Vec3(cover.x, 0, cover.z),
    ]
    projected = [camera.project(p) for p in points]
    if any(p is None for p in projected):
        return camera
    left, right = min(p.x for p in projected), max(p.x for p in projected)
    top, bottom = min(p.y for p in projected) - 3, max(p.y for p in projected) + 3
    scale = camera.viewport_width / 512
    fit = min(
        (camera.viewport_width - 64 * scale) / max(1, right - left),
        (camera.viewport_height - 52 * scale) / max(1, bottom - top),
    )
    if fit < 1:
        return camera
    peak = max(1, min(MAX_SIGHTING_ZOOM, fit))
    dx, dy = (
        (left + right) / 2 - camera.viewport_width * 0.55,
        (top + bottom) / 2 - camera.viewport_height * 0.54,
    )
    anchor = camera.project(camera.target)
    unproject = (
        screen_to_ground_affine if isinstance(camera, AffineCameraState) else screen_to_ground_point
    )
    focus = unproject(camera, anchor.x + dx, anchor.y + dy)
    if focus is None:
        return camera
    target = Vec3(
        camera.target.x + (focus.x - camera.target.x) * amount,
        camera.target.y,
        camera.target.z + (focus.y - camera.target.z) * amount,
    )
    factor = 1 + (peak - 1) * amount
    if isinstance(camera, AffineCameraState):
        return replace(
            camera, target=target, zoom=camera.zoom * factor, distance=camera.distance / factor
        )
    return replace(camera, target=target, distance=camera.distance / factor)


def sighting_facing(model, camera, sighting):
    path = crossing_path(model, camera, sighting.site)
    if path is None:
        return None
    a, b = path
    t = min(1, max(0, sighting.elapsed / 0.9))
    target = camera.project(Vec3(a.x + (b.x - a.x) * t, 0, a.z + (b.z - a.z) * t))
    actor = camera.project(Vec3(model.player.x, 0, model.player.z))
    return (target.x - actor.x, target.y - actor.y) if actor and target else None


def draw_notice(renderer, model, camera, time):
    import math

    sighting = getattr(model, "august_sighting_view", None)
    if sighting is None or not 0 <= sighting.elapsed < 0.62:
        return
    path = crossing_path(model, camera, sighting.site)
    if path is None:
        return
    a, b = (camera.project(v) for v in path)
    scale = max(1, round(camera.viewport_width / 512))
    # Keep marks outside the entire crossing corridor, not just this frame's babies.
    corridor = (
        min(a.x, b.x) - 16 * scale,
        min(a.y, b.y) - 22 * scale,
        max(a.x, b.x) + 16 * scale,
        max(a.y, b.y) + 4 * scale,
    )
    placements = [
        (
            renderer.player_sprite_asset(model, camera),
            Vec3(model.player.x, renderer.player_visual_y_offset(model, time), model.player.z),
        ),
        (
            renderer.buddy_sprite_asset(model, camera),
            Vec3(model.buddy.x, model.buddy.y + math.sin(time * math.tau / 1.3) * 2, model.buddy.z),
        ),
    ]
    for asset, anchor in placements:
        if asset is None:
            continue
        box = placement_for_upright_height_billboard(camera, asset.definition, anchor)
        if box is None:
            continue
        choices = (
            (box.right + 4 * scale, box.top + 2 * scale),
            (box.left - 10 * scale, box.top + 2 * scale),
            (box.right + 4 * scale, box.bottom - 5 * scale),
            (box.left - 10 * scale, box.bottom - 5 * scale),
        )
        for x, y in choices:
            if (
                x < 8
                or x + 7 * scale > camera.viewport_width - 8
                or y < 38 * scale
                or y + 13 * scale > camera.viewport_height - 35 * scale
            ):
                continue
            if (
                x < corridor[2]
                and x + 7 * scale > corridor[0]
                and y < corridor[3]
                and y + 13 * scale > corridor[1]
            ):
                continue
            draw_notice_glyph(renderer.pyxel, round(x), round(y), scale)
            break


def sighting_opacity(renderer, model, camera, command, sighting):
    """Use the battle's foreground fade style, never fade the juvenile exit cover."""
    if sighting is None or command.stable_id == EXIT_COVERS[sighting.site]:
        return 1.0
    obj = model.world.object_by_id(command.stable_id)
    if obj is None or not obj.occludes_player:
        return 1.0
    bounds = renderer.object_screen_bounds(obj, camera)
    for actor, y in ((model.player, 10), (model.buddy, model.buddy.y + 6)):
        foot = camera.project(Vec3(actor.x, 0, actor.z))
        head = camera.project(Vec3(actor.x, y, actor.z))
        if (
            foot
            and head
            and command.depth < foot.depth
            and bounds.x - 8 < head.x < bounds.x + bounds.width + 8
            and bounds.y - 8 < head.y < bounds.y + bounds.height + 8
        ):
            return 1 - 0.65 * reaction_amount(sighting.elapsed)
    return 1.0


def juvenile_frame(asset, kind, camera, start, end, elapsed):
    if kind == "urchin":
        return asset.frame()
    import math

    a, b = camera.project(start), camera.project(end)
    angle = math.atan2(b.x - a.x, -(b.y - a.y))
    direction = DIRECTIONS[int(round(angle / (math.pi / 4))) % 8]
    return asset.frame(f"{direction}_{int(max(0, elapsed) * FPS) % 4:02d}")


def draw_notice_glyph(p, x, y, scale):
    # Thick red pixels, white keyline and a dark outer edge: no panel or label.
    cells = [(x + col * 2 * scale, y + row * 2 * scale) for row in (0, 1, 2, 4) for col in (0, 1)]
    for radius, color in ((2 * scale, 0), (scale, 7), (0, 8)):
        for px, py in cells:
            p.rect(px - radius, py - radius, 2 * scale + radius * 2, 2 * scale + radius * 2, color)
