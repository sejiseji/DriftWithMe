"""Pilot wind linkage. Pure presentation samples; no new wind, particles or simulation RNG."""

from __future__ import annotations

import math

from drift_with_me.grass_sway import bend_angle

TREE_IDS = frozenset({"tree_01", "tree_02", "tree_04"})
SHORE_RECT = (336.0, 320.0, 480.0, 336.0)
MAX_SHORE_BLADES = 24


def normal_context(app):
    from drift_with_me.screen_flow import resolve_state

    state = resolve_state(app)
    if state.screen != "PLAY" or state.modal is not None or state.transition is not None:
        return False
    if state.week == (7, 1):
        progress = getattr(getattr(app, "office", None), "july_progress", None)
        if getattr(progress, "stage", None) != "patrol":
            return False
    if getattr(getattr(app.model, "swarm_field", None), "battle", None) is not None:
        return False
    return (
        not app.model.world_paused
        and app.model.combat_session is None
        and getattr(app, "hitstop_remaining", 0.0) <= 0
        and not any(
            getattr(app, name, None)
            for name in (
                "field_conversation",
                "first_sight_conversation",
                "patrol_dialogue",
                "combat_camera_restore",
                "august_crossing",
                "august_sighting_dialogue",
            )
        )
    )


def allowed(renderer, model, camera):
    return (
        getattr(renderer, "wind_life_enabled", True)
        and getattr(renderer, "wind_life_context", False)
        and renderer.camera_is_affine(camera)
        and model.config.get("simulation", {}).get("day_phase") == "day"
        and not getattr(model, "august_rain", False)
        and not model.world_paused
        and model.combat_session is None
        and getattr(model, "swarm_presentation", None) is None
        and getattr(model, "august_sighting_view", None) is None
    )


def leaf_phase_shift(obj, seconds, config, gust):
    if obj.id not in TREE_IDS or not config.get("enabled", False):
        return 0
    seed = sum((i + 1) * ord(c) for i, c in enumerate(obj.id))
    delay = (seed % 7) / 24
    angle = bend_angle(obj.x, obj.z, seconds - delay, 0.5, config, gust)
    normal = math.radians(48) * max(0.001, float(config.get("strength", 0.7)))
    return round(8 * min(1.0, angle / normal))


def shore_candidate(area_id, cell_x, cell_z, blade_index, x, z, world):
    # Six world-anchored cells, four existing blade indices each. Camera changes
    # cannot select a different first-N cohort; total is at most 24 everywhere.
    if (
        area_id != "spawn_grassland_micro"
        or cell_z != 13
        or not 14 <= cell_x <= 19
        or blade_index >= 4
    ):
        return False
    x0, z0, x1, z1 = SHORE_RECT
    if not (x0 <= x <= x1 and z0 <= z < z1):
        return False
    for area in world.shallow_water_areas:
        r = area.rect
        if r.contains_point(x, z):
            return False
    return any(
        math.hypot(
            max(a.rect.min_x - x, 0, x - a.rect.max_x), max(a.rect.min_z - z, 0, z - a.rect.max_z)
        )
        <= 16
        for a in world.shallow_water_areas
    )


def shore_angle(x, z, seconds, variation, config, gust, height):
    extended = dict(config, rect_xz=(304, 288, 512, 384), strength=0.24)
    angle = bend_angle(x, z, seconds, variation, extended, gust)
    return min(angle, math.atan(0.9 / max(1, height)))
