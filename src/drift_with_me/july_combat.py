"""Finite July pest control, reusing approved sprites and the relay laser."""

from __future__ import annotations

import math

from drift_with_me.camera import camera_ground_axes
from drift_with_me.focus_laser import BURN_STEPS, FocusLaserAction, draw_focus_laser
from drift_with_me.hex_assets import draw_scaled_sprite, placement_for_upright_height_billboard
from drift_with_me.math3d import Vec3
from drift_with_me.nudibranch_preview import DIRECTIONS, preview_assets

JULY_ENEMY_IDS = tuple(
    f"july_nudibranch_{kind}_{i}" for kind in ("normal", "abnormal") for i in (1, 2)
)


def is_nudibranch(enemy):
    return getattr(enemy, "species", None) == "electric_nudibranch"


def configure_july_enemies(model, defeated_ids=()):
    from drift_with_me.model import EnemyState

    if not hasattr(model, "_pre_july_enemies"):
        model._pre_july_enemies = model.enemies
    # July patrol centers on the giant-tree area, not the old June spawn homes.
    homes = [(520.0, 480.0), (620.0, 448.0), (592.0, 608.0), (744.0, 544.0)]
    enemies = []
    for index, enemy_id in enumerate(JULY_ENEMY_IDS):
        x, z = homes[index]
        enemy = EnemyState(enemy_id, "normal" if index < 2 else "abnormal", x, z, x, z)
        enemy.species = "electric_nudibranch"
        enemy.focus_action = None
        enemy.zigzag_path = ()
        if enemy_id in defeated_ids:
            enemy.state = "DEFEATED"
        enemies.append(enemy)
    model.enemies = enemies
    model.bubble = None
    model.combat_session = None
    model.active_enemy_ids = {e.id for e in enemies}


def clear_july_enemies(model):
    if hasattr(model, "_pre_july_enemies"):
        model.enemies = model._pre_july_enemies
        del model._pre_july_enemies
    model.bubble = None
    model.combat_session = None


def defeated_july_ids(model):
    return {e.id for e in model.enemies if e.id in JULY_ENEMY_IDS and e.state == "DEFEATED"}


def freeze_zigzag(enemy, distance=56.0):
    # Target is snapshotted once. The same vertices are warned and traversed.
    dx, dz = enemy.dash_x, enemy.dash_z
    enemy.zigzag_path = tuple(
        (
            enemy.x + dx * distance * fraction - dz * offset,
            enemy.z + dz * distance * fraction + dx * offset,
        )
        for fraction, offset in ((0.0, 0.0), (0.25, 9.0), (0.5, -9.0), (0.75, 9.0), (1.0, 0.0))
    )
    enemy.zigzag_index = 1


def update_zigzag(model, enemy, dt):
    remaining = float(model.config["enemy"]["abnormal"]["dash_speed"]) * dt
    path = enemy.zigzag_path
    while remaining > 1e-6 and enemy.zigzag_index < len(path):
        x, z = path[enemy.zigzag_index]
        dx, dz = x - enemy.x, z - enemy.z
        length = math.hypot(dx, dz)
        if length < 1e-5:
            enemy.zigzag_index += 1
            continue
        step = min(remaining, length)
        moved = model.move_enemy(enemy, dx / length * step, dz / length * step)
        remaining -= step
        if moved < step * 0.5:
            enemy.zigzag_index = len(path)
            break
        if step >= length:
            enemy.zigzag_index += 1
    if enemy.zigzag_index >= len(path):
        enemy.state = "RECOVER"
        enemy.state_timer = float(model.config["enemy"]["abnormal"]["recover_sec"])


def start_focus(model, enemy, camera, events, session=None):
    if getattr(enemy, "focus_action", None) is not None:
        return
    right, _ = camera_ground_axes(camera)

    def ground(actor, fallback):
        anchor = model.combat_actor_anchor_ground(camera, actor) if session else None
        return fallback if anchor is None else Vec3(anchor[0], fallback.y, anchor[1])

    jack = ground("player", Vec3(model.player.x, 9.0, model.player.z))
    fuse = ground("buddy", Vec3(model.buddy.x, model.buddy.y, model.buddy.z))
    target = ground("enemy", Vec3(enemy.x, 9.0, enemy.z))
    enemy.focus_action = FocusLaserAction.create(jack, fuse, target, right, enemy.kind, "SE_00")
    enemy.state = "FOCUS"
    if session:
        session.outcome = "defeat"
        session.zap_used = True
        model.advance_combat_phase(session, "FOCUS_LASER", events)
    events.append(
        model.event_queue.emit(
            world_tick=model.world_tick,
            kind="focus_laser_started",
            actor_id="buddy",
            target_id=enemy.id,
            world_position=(enemy.x, 0.0, enemy.z),
            payload={"electric_immune": True},
        )
    )


def tick_focus(model, enemy, dt, events):
    action = enemy.focus_action
    if action.complete:
        return True
    action.elapsed += max(0.0, dt)
    if action.complete:
        enemy.state = "DEFEATED"
        enemy.state_timer = 0.0
        events.append(
            model.event_queue.emit(
                world_tick=model.world_tick,
                kind="enemy_defeated",
                actor_id="buddy",
                target_id=enemy.id,
                world_position=(enemy.x, 0.0, enemy.z),
                payload={"finish": "focus_laser"},
            )
        )
        return True
    return False


def draw_sprite(renderer, model, enemy, camera, x, z, y):
    library = getattr(renderer, "_nudibranch_preview_assets", None)
    if library is None:
        library = renderer._nudibranch_preview_assets = preview_assets(renderer.pyxel)
    asset = library.get(f"electric_nudibranch_{enemy.kind}")
    placement = placement_for_upright_height_billboard(camera, asset.definition, Vec3(x, y, z))
    if placement is None:
        return None
    hx, hz = getattr(enemy, "sprite_heading", (enemy.dash_x, enemy.dash_z))
    direction = Vec3(enemy.x + hx, 0.0, enemy.z + hz)
    origin, toward = camera.project(Vec3(enemy.x, 0.0, enemy.z)), camera.project(direction)
    angle = math.atan2(toward.x - origin.x, -(toward.y - origin.y)) if origin and toward else 0.0
    name = DIRECTIONS[int(round(angle / (math.pi / 4))) % 8]
    action = getattr(enemy, "focus_action", None)
    frame = asset.frame(
        action.frame_id if action else f"{name}_{int(model.world_tick / 30 * 6) % 4:02d}"
    )
    if action and action.burn_progress > 0:
        frame = action.ensure_burn_frames(renderer.pyxel, frame, asset.definition.colkey)[
            int(action.burn_progress * BURN_STEPS)
        ]
    if frame.source is None:
        draw_scaled_sprite(renderer.pyxel, frame, asset.definition, placement)
    else:
        renderer.draw_atmospheric_scaled_sprite(asset, placement, frame)
    return placement


def focus_draw_commands(renderer, model, camera):
    from drift_with_me.render import DrawCommand

    commands = []
    for enemy in model.enemies:
        action = getattr(enemy, "focus_action", None)
        if not action or action.complete:
            continue
        point = camera.project(action.target)
        if point is not None:
            commands.append(
                DrawCommand(
                    point.depth,
                    1,
                    f"july_focus:{enemy.id}",
                    lambda action=action: draw_focus_laser(renderer, action, camera, (), True),
                    0.0,
                )
            )
        projected = action.ensure_projection(camera)
        for i, bit in enumerate(projected["bits"]):
            if bit is not None:
                commands.append(
                    DrawCommand(
                        bit.depth,
                        1,
                        f"july_focus_bit:{enemy.id}:{i}",
                        lambda action=action, i=i: draw_focus_laser(
                            renderer, action, camera, (i,), False
                        ),
                        0.0,
                    )
                )
    return commands


def prepare_combat_zigzag(model, enemy, session, camera):
    if not is_nudibranch(enemy) or enemy.kind != "abnormal":
        return
    if getattr(session, "july_charge_path", None):
        return
    start = model.combat_actor_anchor_ground(camera, "enemy")
    target = model.combat_actor_anchor_ground(camera, "player")
    if start is None or target is None:
        return
    dx, dz = target[0] - start[0], target[1] - start[1]
    distance = math.hypot(dx, dz)
    if distance < 1e-6:
        return
    ux, uz = dx / distance, dz / distance
    travel = max(0.0, distance - model.combat_charge_closest_approach_world())
    session.july_charge_path = tuple(
        (
            start[0] + ux * travel * fraction - uz * offset,
            start[1] + uz * travel * fraction + ux * offset,
        )
        for fraction, offset in ((0.0, 0.0), (0.25, 9.0), (0.5, -9.0), (0.75, 9.0), (1.0, 0.0))
    )


def combat_zigzag_position(session, progress):
    path = getattr(session, "july_charge_path", ())
    if not path:
        return None
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:], strict=False)]
    distance = max(0.0, min(1.0, progress)) * sum(lengths)
    for a, b, length in zip(path, path[1:], lengths, strict=False):
        if distance <= length:
            t = distance / length if length else 0.0
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        distance -= length
    return path[-1]


def focus_attack_direction(model):
    return (
        "front_right"
        if any(
            getattr(e, "focus_action", None) is not None and not e.focus_action.complete
            for e in model.enemies
        )
        else None
    )
