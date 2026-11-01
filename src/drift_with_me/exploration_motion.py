"""Tiny screen-only stop reactions; gameplay coordinates and sprite hit geometry stay intact."""

from __future__ import annotations

import math
from dataclasses import replace

from drift_with_me.math3d import Vec3


class ExplorationMotion:
    def __init__(self):
        self.enabled = True
        self.reset()

    def reset(self):
        self.contact_cooldown = 0.0
        self.pending_contact = None
        self.clear_offsets()

    def clear_offsets(self):
        self.active = False
        self.previous = None
        self.camera_signature = None
        self.direction = (0.0, 0.0)
        self.moving = False
        self.jack_age = self.buddy_age = 1.0
        self.jack_direction = (0.0, 0.0)
        self.cooldown = 0.0

    def update(self, dt, model, camera, effects=None, active=True, contacts_active=None):
        cues = getattr(effects, "contact_cues", [])
        contacts = tuple(cues)
        cues.clear()
        current = (model.player.x, model.player.z)
        if contacts_active is None:
            contacts_active = active
        if not self.enabled or not contacts_active or dt <= 0 or dt > 0.1:
            self.reset()
            self.previous = current
            return
        previous = self.previous
        distance = (
            math.hypot(current[0] - previous[0], current[1] - previous[1])
            if previous is not None
            else 0.0
        )
        if distance > 8:
            self.reset()
            self.previous = current
            return
        self.contact_cooldown = max(0.0, self.contact_cooldown - dt)
        self.pending_contact = None
        if distance > 0.001 and contacts and self.contact_cooldown == 0:
            self.pending_contact = "water" if "water" in contacts else "grass"
            self.contact_cooldown = 0.65 if self.pending_contact == "grass" else 0.85
        if not active:
            self.clear_offsets()
            self.previous = current
            return
        signature = tuple(
            getattr(camera, name, None)
            for name in (
                "distance",
                "zoom",
                "yaw_deg",
                "pitch_deg",
                "anchor_x",
                "anchor_y",
                "viewport_width",
                "viewport_height",
                "fx_offset_x",
                "fx_offset_y",
            )
        )
        if self.camera_signature is not None and signature != self.camera_signature:
            self.clear_offsets()
            self.previous = current
            self.camera_signature = signature
            return
        self.camera_signature = signature
        self.active = True
        self.jack_age += dt
        self.buddy_age += dt
        self.cooldown = max(0.0, self.cooldown - dt)
        self.previous = current
        if previous is None:
            return
        p = camera.project(Vec3(previous[0], 0, previous[1]))
        q = camera.project(Vec3(current[0], 0, current[1]))
        if p is None or q is None:
            self.reset()
            return
        dx, dy = q.x - p.x, q.y - p.y
        length = math.hypot(dx, dy)
        moving = distance > 0.001 and length > 0.01
        direction = (dx / length, dy / length) if moving else self.direction
        reverse = (
            moving
            and self.moving
            and sum(a * b for a, b in zip(direction, self.direction, strict=True)) < -0.25
        )
        stopped = self.moving and not moving
        if (stopped or reverse) and self.cooldown == 0:
            self.jack_age = 0.0
            self.jack_direction = self.direction
            self.cooldown = 0.18
        if stopped:
            self.buddy_age = 0.0
        elif moving:
            # Existing logical following already supplies motion lag. Only add
            # a one-pixel settling tail at a stop, never another following spring.
            self.buddy_age = 1.0
        self.direction = direction
        self.moving = moving

    def consume_contact(self):
        contact, self.pending_contact = self.pending_contact, None
        return contact

    def offset(self, actor):
        if not self.active or not self.enabled:
            return 0, 0
        if actor == "player":
            age, duration, direction = self.jack_age, 0.18, self.jack_direction
        else:
            age, duration = self.buddy_age, 0.32
            direction = (-self.direction[0], -self.direction[1])
        if age >= duration:
            return 0, 0
        strength = max(0.0, 1.0 - age / duration)
        # One logical display pixel maximum; idle hover and all world positions
        # remain untouched. Dominant axis avoids a sqrt(2)-pixel diagonal jump.
        axis = 0 if abs(direction[0]) >= abs(direction[1]) else 1
        value = round(math.copysign(strength, direction[axis])) if direction[axis] else 0
        return (value, 0) if axis == 0 else (0, value)

    def placement(self, placement, actor, model):
        if model.combat_session is not None or model.world_paused:
            return placement
        dx, dy = self.offset(actor)
        if dx == dy == 0:
            return placement
        return replace(
            placement,
            anchor_x=placement.anchor_x + dx,
            anchor_y=placement.anchor_y + dy,
            blt_x=placement.blt_x + dx,
            blt_y=placement.blt_y + dy,
            left=placement.left + dx,
            right=placement.right + dx,
            top=placement.top + dy,
            bottom=placement.bottom + dy,
        )
