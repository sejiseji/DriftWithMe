"""Opt-in main-map encounters. Story/week advancement is intentionally unbound."""

from __future__ import annotations

import math
from dataclasses import replace
from types import SimpleNamespace

from drift_with_me.config import load_data_json
from drift_with_me.effects import COMBAT_CHANCE_CUE_SEC
from drift_with_me.swarm_battle import Settings, SwarmBattle

SITE_IDS = frozenset({"northwest", "northeast", "southeast"})
WEEK_KEYS = {f"{m}:{w}" for m in (6, 7) for w in range(1, 5)} | {"8:1", "8:2", "8:3"}


def validate_progress(raw):
    if not isinstance(raw, dict) or set(raw) - WEEK_KEYS:
        raise ValueError("invalid swarm weeks")
    result = {}
    for week, sites in raw.items():
        if (
            not isinstance(sites, list)
            or any(type(s) is not str for s in sites)
            or len(sites) != len(set(sites))
            or set(sites) - SITE_IDS
        ):
            raise ValueError("invalid swarm sites")
        result[week] = sorted(sites)
    return result


class SwarmField:
    def __init__(self, model, week_key, progress, config=None):
        self.model = model
        self.week_key = week_key
        self.progress = progress
        self.config = dict(config or load_data_json("swarm_config.json"))
        self.config["victory_hold"] = model.combat_victory_cue_sec()
        resource = model.config["resources"]
        self.settings = replace(
            Settings(),
            cutin=COMBAT_CHANCE_CUE_SEC,
            entry=model.combat_duration_sec(),
            ready=model.combat_ready_total_sec(),
            sweep=model.combat_parry_sweep_sec(),
            radius=model.combat_parry_hit_radius_normalized(enemy_kind="normal"),
            finish_wait=model.combat_zap_window_sec(),
            knockback=float(self.config.get("capture_knockback_world", 18)),
            float_height=float(self.config.get("capture_float_height_world", 8)),
            capture_water=(
                self.config["capture_water"]
                if self.config["capture_water"] is not None
                else float(resource["bubble_water_cost"])
            ),
            finish_water=float(self.config["finish_water"]),
            finish_energy=(
                self.config["finish_energy"]
                if self.config["finish_energy"] is not None
                else float(resource["discharge_energy_cost"])
            ),
        )
        self.battle = None
        self.site_id = None
        self.blocked_sites = set()
        self.cooldown = 0.0
        self.wait_release = False

    @property
    def action_mode(self):
        if self.battle is None:
            return "NONE"
        return {"approach": "GUARD", "finish_wait": "ZAP"}.get(self.battle.phase, "NONE")

    def presentation_session(self):
        b = self.battle
        phases = {
            "entry": "COMBAT_ENTRY",
            "ready": "COMBAT_READY",
            "approach": "PARRY_TIMING",
            "bound": "PERFECT_ZAP_WINDOW",
            "finish_wait": "PERFECT_ZAP_WINDOW",
            "shake": "PARRY_RESOLVE",
            "assist": "COMBAT_EXIT_DEFLECT",
            "victory": "VICTORY_CUE",
            "electric": "COMBAT_EXIT_COUNTER",
            "circle": "COMBAT_EXIT_COUNTER",
            "converge": "COMBAT_EXIT_COUNTER",
            "spear": "COMBAT_EXIT_COUNTER",
        }
        enemy_id = next((e.id for e in self.model.enemies if e.kind == "normal"), "")
        return SimpleNamespace(
            phase=phases.get(b.phase, "COMBAT_EXIT_DEFLECT"),
            elapsed_sec=b.total_elapsed,
            phase_elapsed_sec=(
                b.capture_elapsed
                if b.phase in {"bound", "finish_wait"}
                else b.finisher_elapsed
                if b.phase in {"electric", "circle", "converge", "spear"}
                else b.elapsed
            ),
            timing_elapsed_sec=b.elapsed if b.phase == "approach" else 0,
            enemy_id=enemy_id,
            marker_positions=(b.settings.target,),
            marker_judgements=(None,),
            result="failure" if b.phase == "shake" else None,
            outcome="defeat",
            zap_used=b.phase in {"electric", "circle", "converge", "spear", "victory"},
        )

    @property
    def cleared(self):
        return set(self.progress.get(self.week_key, []))

    @property
    def complete(self):
        return self.cleared == SITE_IDS

    def emit(self, events, kind, **payload):
        m = self.model
        events.append(
            m.event_queue.emit(
                world_tick=m.world_tick,
                kind=kind,
                actor_id="player",
                target_id=self.site_id,
                world_position=(m.player.x, 0, m.player.z),
                payload=payload,
            )
        )

    def start(self, site_id, camera, events):
        m = self.model
        if (
            self.battle is not None
            or m.combat_session is not None
            or m.world_paused
            or site_id in self.cleared
            or site_id in self.blocked_sites
            or self.cooldown > 0
            or site_id not in self.config["sites"]
            or m.action_lock_remaining > 0
            or m.player.stun_remaining > 0
        ):
            return False
        self.site_id = site_id
        self.battle = SwarmBattle(
            m.water,
            m.energy,
            self.settings,
            (m.world.spawn_x, m.world.spawn_z),
            self.config.get("compositions", {}).get(site_id),
        )
        m.cancel_auto_move()
        m.reset_manual_velocity()
        m.player.barrier_active = False
        m.bubble = None
        m.action_lock_remaining = 0
        self.wait_release = True
        self.emit(events, "swarm_started", week=self.week_key)
        return True

    def step(self, intent, camera, dt, events):
        m = self.model
        if self.battle is None:
            self.cooldown = max(0, self.cooldown - dt)
            for site, (x, z) in self.config["sites"].items():
                distance = math.hypot(m.player.x - x, m.player.z - z)
                if distance > self.config["release_radius"]:
                    self.blocked_sites.discard(site)
            if m.combat_session is None and not m.world_paused:
                for site, (x, z) in self.config["sites"].items():
                    if math.hypot(m.player.x - x, m.player.z - z) <= self.config[
                        "contact_radius"
                    ] and self.start(site, camera, events):
                        return True
            return False
        b = self.battle
        previous_phase = b.phase
        b.water, b.energy = m.water, m.energy
        if self.wait_release:
            # Entry input cannot also capture. The app also waits for physical release.
            self.wait_release = False
        elif intent.action_pressed:
            b.input()
        b.tick(dt)
        m.water, m.energy = b.water, b.energy
        if b.phase == "finish_wait" and previous_phase != "finish_wait":
            self.emit(
                events,
                "combat_zap_chance_started",
                window_sec=b.settings.finish_wait,
                energy_cost=b.settings.finish_energy if "urchin" in b.kinds else 0,
                swarm_kinds=list(b.kinds),
            )
        m.player.barrier_active = False
        if b.phase == "field" or (
            b.phase == "victory" and b.elapsed >= self.config["victory_hold"]
        ):
            won = b.phase == "victory"
            if won:
                self.progress[self.week_key] = sorted(self.cleared | {self.site_id})
                self.emit(events, "swarm_site_cleared", week=self.week_key)
                if self.complete:
                    self.emit(events, "swarm_week_completed", week=self.week_key)
            else:
                m.player.x, m.player.z = m.world.spawn_x, m.world.spawn_z
            self.blocked_sites.add(self.site_id)
            self.cooldown = self.config["reentry_cooldown"]
            m.cancel_auto_move()
            m.reset_manual_velocity()
            m.player.stun_remaining = 0
            m.player.invulnerable_remaining = max(1, m.player.invulnerable_remaining)
            m.barrier_blocked_until_release = True
            if not won:
                m.snap_buddy(camera)
            self.emit(events, "swarm_restored", won=won, week=self.week_key)
            self.battle = None
            self.site_id = None
        return True
