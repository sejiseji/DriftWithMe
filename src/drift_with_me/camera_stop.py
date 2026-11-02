"""Finite affine follow settling; shared by rendering and existing picking paths.

Interpolate zoom and zoom-weighted target together. Every fixed world point then
moves along a monotone screen segment, including while source proximity zooms.
No pixel rounding, separate render camera, or input-coordinate conversion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from drift_with_me.math3d import Vec3


@dataclass
class StopSettle:
    origin: tuple[float, float, float]
    target: tuple[float, float, float]
    elapsed: float = 0.0
    duration: float = 0.65
    latched: bool = False

    def sample(self, dt: float, mode: str, screen_error: float) -> tuple[float, float, float]:
        self.elapsed = min(self.duration, self.elapsed + max(0.0, dt))
        if mode == "threshold":
            self.latched = self.latched or screen_error <= 0.75
            return self.target if self.latched else ()
        t = self.elapsed / self.duration
        # Ease out, exact finite endpoint. The same progress applies to every
        # affine screen point, avoiding differing translation/zoom tail rates.
        u = 1.0 - (1.0 - t) ** 3
        x0, z0, q0 = self.origin
        x1, z1, q1 = self.target
        q = q0 + (q1 - q0) * u
        return ((x0 * q0 + (x1 * q1 - x0 * q0) * u) / q, (z0 * q0 + (z1 * q1 - z0 * q0) * u) / q, q)


def apply_stop_settle(controller, dt: float, player_x: float, player_z: float, enabled: bool):
    """Called after base resolution, before publishing the common camera state."""
    c = controller
    eligible = (
        enabled
        and c.has_player_moved
        and not c.player_moving
        and c.mode_name == "FOLLOW"
        and c.base_blend is None
        and c.camera_config.get("lookahead_enabled", False)
    )
    if not eligible:
        c.stop_settle = None
        return
    direction = c.last_moving_direction
    offset = c.directional_lookahead_offset(*direction)
    final_x = c.world.camera_target_rect.clamp_x(player_x + offset.x)
    final_z = c.world.camera_target_rect.clamp_z(player_z + offset.y)
    final_zoom = c.target_water_source_zoom_multiplier(player_x, player_z)
    target = (final_x, final_z, final_zoom)
    if c.stop_settle is None or c.stop_settle.target != target:
        c.stop_settle = StopSettle(
            (c.follow_target.x, c.follow_target.z, c.water_source_zoom_multiplier), target
        )
    s = c.stop_settle
    # Bound screen residual using viewport corners, not just player root.
    scale = c.affine_profile.viewport_scale(c.viewport_width)
    q = c.water_source_zoom_multiplier
    dx, dz = (
        final_x * final_zoom - c.follow_target.x * q,
        final_z * final_zoom - c.follow_target.z * q,
    )
    bx, bz = c.affine_profile.basis_x, c.affine_profile.basis_z
    translation = math.hypot((bx.x * dx + bz.x * dz) * scale, (bx.y * dx + bz.y * dz) * scale)
    zoom_error = abs(final_zoom - q) * max(c.viewport_width, c.viewport_height) / max(q, 1e-9)
    value = s.sample(dt, c.stop_settle_mode, translation + zoom_error)
    if value:
        x, z, q = value
        c.follow_target = Vec3(x, 0.0, z)
        c.water_source_zoom_multiplier = q
        c.lookahead_offset = offset
        c.current = c.to_camera_state(c.follow_shot())
