"""Exercise the real app, map, encounter, battle and return without user saves.

PYTHONPATH=src python scripts/capture_swarm_field.py --scenario success --output /tmp/swarm
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("success", "retry", "retreat", "capture-water", "finish-water", "energy", "both"),
        default="success",
    )
    parser.add_argument("--individual", action="store_true")
    parser.add_argument("--guard-detail", action="store_true")
    parser.add_argument("--touch", action="store_true")
    parser.add_argument("--spam-wait", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)

    import pyxel

    from drift_with_me.app import DriftWithMeApp
    from drift_with_me.math3d import Vec3
    from drift_with_me.swarm_battle import PRESETS

    run = pyxel.run
    pyxel.run = lambda *_: None
    app = DriftWithMeApp(headless=True, swarm_field=True)
    pyxel.run = run
    assert not app.progress_store.enabled
    app.consume_elapsed = lambda: 1 / app.runtime.target_fps
    assert app.enter_swarm_test_field()
    app.model.water, app.model.energy = PRESETS.get(args.scenario, PRESETS["normal"])
    sprite_audit = {}
    scene_calls = {}
    continuity = {}
    common_ui = {"countdown": [], "timing_bar": [], "buttons": [], "cutin": []}
    float_frames = []
    zoom_audit = {}
    timing_rects = {}
    composition = {}
    water_stats = []
    original_bar = app.draw_combat_timing_bar

    def draw_bar(session=None):
        session = session or app.model.combat_session
        if session and session.phase in {"COMBAT_READY", "PARRY_TIMING", "PARRY_RESOLVE"}:
            common_ui["timing_bar"].append(phase())
            rect = app.combat_timing_bar_rect(session)
            timing_rects[phase()] = [rect.x, rect.y, rect.width, rect.height]
        return original_bar(session)

    app.draw_combat_timing_bar = draw_bar
    original_countdown = app.draw_combat_countdown_cue

    def draw_countdown(session):
        cue = app.combat_countdown_cue_text(session)
        if cue and cue not in common_ui["countdown"]:
            common_ui["countdown"].append(cue)
        return original_countdown(session)

    app.draw_combat_countdown_cue = draw_countdown
    original_button = app.draw_action_button

    def draw_button(rect, token, slot, enabled):
        if (phase(), token) not in common_ui["buttons"]:
            common_ui["buttons"].append((phase(), token))
        return original_button(rect, token, slot, enabled)

    app.draw_action_button = draw_button
    original_cutin = app.draw_combat_chance_cues

    def draw_cutin():
        if (
            any(c.kind == "combat_zap_chance" for c in app.effects.screen_cues)
            and phase() not in common_ui["cutin"]
        ):
            common_ui["cutin"].append(phase())
        return original_cutin()

    app.draw_combat_chance_cues = draw_cutin

    def phase():
        if args.individual:
            session = app.model.combat_session
            return session.phase if session else "field"
        b = app.model.swarm_field.battle
        return b.phase if b else "field"

    def remember(role, asset_id):
        values = sprite_audit.setdefault(phase(), {})
        values.setdefault(role, set()).add(asset_id)

    original_scene = app.renderer.draw_scene

    def draw_scene(model, camera, *args, **kwargs):
        assert model.world is app.world and model.player is app.model.player
        assert model.buddy is app.model.buddy
        scene_calls[phase()] = scene_calls.get(phase(), 0) + 1
        if app.last_combat_scene_camera is not None:
            zoom = app.camera_zoom(app.last_combat_scene_camera)
            values = zoom_audit.setdefault(phase(), [zoom, zoom])
            values[0], values[1] = min(values[0], zoom), max(values[1], zoom)
        return original_scene(model, camera, *args, **kwargs)

    app.renderer.draw_scene = draw_scene

    original_player = app.renderer.draw_player_sprite

    def draw_player(model, camera, time, *args, **kwargs):
        result = original_player(model, camera, time, *args, **kwargs)
        assert result, "production Jack sprite fell back to geometry"
        remember("jack", app.renderer.player_sprite_asset(model, camera, time).definition.asset_id)
        return result

    app.renderer.draw_player_sprite = draw_player

    original_buddy = app.renderer.draw_buddy_sprite

    def draw_buddy(model, camera, time, *args, **kwargs):
        result = original_buddy(model, camera, time, *args, **kwargs)
        assert result, "production Fuse sprite fell back to geometry"
        remember("fuse", app.renderer.buddy_sprite_asset(model, camera).definition.asset_id)
        return result

    app.renderer.draw_buddy_sprite = draw_buddy

    original_enemy = app.renderer.draw_enemy_sprite

    def draw_enemy(model, enemy, camera, *args, **kwargs):
        result = original_enemy(model, enemy, camera, *args, **kwargs)
        if enemy.id.startswith("swarm:"):
            assert result is not None, "production swarm sprite fell back to geometry"
            asset_id = (
                "electric_nudibranch_normal"
                if getattr(enemy, "species", None) == "electric_nudibranch"
                else "normal_urchin_idle_64"
            )
            remember(enemy.id, asset_id)
        return result

    app.renderer.draw_enemy_sprite = draw_enemy

    original_sprite = app.renderer.draw_atmospheric_scaled_sprite

    def draw_sprite(asset, *args, **kwargs):
        if asset.definition.asset_id == "jun_w4_fuji":
            remember("fuji", asset.definition.asset_id)
        return original_sprite(asset, *args, **kwargs)

    app.renderer.draw_atmospheric_scaled_sprite = draw_sprite

    original_event = app.process_swarm_event

    def actors():
        m = app.model
        return (m.player.x, m.player.z, m.buddy.x, m.buddy.y, m.buddy.z)

    def process_swarm_event(event):
        if event.kind == "swarm_started":
            continuity["entry_actors"] = actors()
        before, camera_before = actors(), app.camera()
        original_event(event)
        if event.kind == "swarm_restored":
            continuity["return_actors"] = actors()
            continuity["won"] = bool(event.payload.get("won"))
            if event.payload.get("won"):
                assert actors() == continuity["entry_actors"] == before
                assert app.camera() == camera_before
                continuity["victory_actors_and_camera_unchanged"] = True
            else:
                assert (app.model.player.x, app.model.player.z) == (
                    app.world.spawn_x,
                    app.world.spawn_z,
                )
                continuity["retreat_at_real_spawn"] = True

    app.process_swarm_event = process_swarm_event

    controls = {"pressed": set(), "held": set()}
    pyxel.btnp = lambda key, *_: key in controls["pressed"]
    pyxel.btn = lambda key: key in controls["held"]
    sent, saved = set(), set()
    frame = 0
    entered = False
    returned_at = None
    phases = []
    start_position = (app.model.player.x, app.model.player.z)
    if args.individual:
        app.swarm_field_enabled = False
        app.model.swarm_field.config["sites"] = {}
        app.model.player.x, app.model.player.z = 200, 800
        app.camera_controller.reset(Vec3(200, 0, 800))
        app.model.snap_buddy(app.camera())
        enemy = next(e for e in app.model.enemies if e.kind == "normal")
        enemy.x, enemy.z = 210, 800
        events = []
        app.model.start_contact_combat(enemy, events)
        app.process_events(events)

    def update():
        nonlocal frame, entered, returned_at
        frame += 1
        controls["pressed"].clear()
        controls["held"].clear()
        field = app.model.swarm_field
        b = field.battle
        if args.individual:
            session = app.model.combat_session
            if session:
                entered = True
                if session.phase == "PARRY_TIMING":
                    slider = app.model.combat_timing_slider_position(session)
                    for index, marker in enumerate(session.marker_positions):
                        token = (
                            session.successful_defense_count,
                            session.failed_round_count,
                            index,
                        )
                        if slider >= marker and token not in sent:
                            sent.add(token)
                            controls["held"].add(pyxel.KEY_SPACE)
                            break
                elif (
                    session.phase == "PERFECT_BUBBLE_WINDOW"
                    or session.phase == "PERFECT_ZAP_WINDOW"
                    and session.phase_elapsed_sec > 0.85
                ):
                    controls["pressed"].add(pyxel.KEY_X)
            elif entered and returned_at is None:
                returned_at = frame
            app.update()
            if frame > 2400:
                raise RuntimeError("individual comparison timed out")
            return
        if frame <= 12:
            controls["held"].add(pyxel.KEY_D)  # Real field movement before encounter.
        elif frame == 24:
            controls["pressed"].add(pyxel.KEY_F6)
        if b:
            entered = True
            token = (b.phase, b.failures)
            miss = (
                args.scenario == "retreat"
                or args.scenario == "retry"
                and b.phase == "approach"
                and b.failures == 0
            )
            target = 0.2 if miss else b.settings.target
            if b.phase == "approach" and token not in sent and b.progress >= target:
                sent.add(token)
                if args.touch:
                    rect = app.action_button_rect()
                    pyxel.mouse_x, pyxel.mouse_y = rect.x + rect.width / 2, rect.y + rect.height / 2
                    controls["pressed"].add(pyxel.MOUSE_BUTTON_LEFT)
                    controls["held"].add(pyxel.MOUSE_BUTTON_LEFT)
                else:
                    controls["pressed"].add(pyxel.KEY_SPACE)
                    controls["held"].add(pyxel.KEY_SPACE)
            if args.spam_wait and b.phase in {"bound", "finish_wait", "electric"}:
                controls["pressed"].add(pyxel.KEY_X)
        elif entered:
            if returned_at is None:
                returned_at = frame
            if frame - returned_at > 20:
                controls["held"].add(pyxel.KEY_D)  # Prove movement after restoration.
        app.update()
        if frame > 2400:
            raise RuntimeError("field capture timed out")

    def draw():
        app.draw()
        active_battle = app.model.swarm_field.battle
        if args.guard_detail and active_battle and active_battle.phase == "approach":
            guard_dir = out / "guard"
            guard_dir.mkdir(exist_ok=True)
            pyxel.screen.save(str(guard_dir / f"{frame:05d}.png"), 2)
        if active_battle and active_battle.phase in {"electric", "spear"}:
            phase_name = active_battle.phase
            tick = int(active_battle.elapsed / 0.06)
            key = f"{phase_name}-pose-{tick:02d}"
            if key not in saved:
                pyxel.screen.save(str(out / f"{key}.png"), 2)
                saved.add(key)
        field = app.model.swarm_field
        b = field.battle
        label = f"{b.phase}-{b.failures}" if b else ("field-return" if entered else "field-start")
        if args.individual and app.model.combat_session is not None:
            session = app.model.combat_session
            cue = app.combat_countdown_cue_text(session)
            label = "individual-" + (cue.replace("!", "") if cue else session.phase)
        if b and b.phase == "approach":
            label += f"-{int(b.progress * 3)}"
        if b and b.phase in {"ready", "approach"}:
            cue = app.combat_countdown_cue_text(field.presentation_session())
            if cue:
                label = "countdown-" + cue.replace("!", "")
        if b and app.swarm_view is not None:
            view = app.swarm_view
            placement = app.renderer.player_sprite_placement(
                view.model_view, view.camera, app.presentation_time
            )
            composition[b.phase] = {
                "jack_rect": placement.rect,
                "ground_y": view.camera.project(Vec3(app.model.player.x, 0, app.model.player.z)).y,
                "viewport_height": app.runtime.screen_height,
            }
        if b and b.phase == "spear":
            if hasattr(app.swarm_view, "water_stats"):
                water_stats.append(app.swarm_view.water_stats)
            label = f"spear-detail-{min(4, int(b.elapsed / 0.12))}"
        if b and b.captured and app.swarm_view is not None:
            float_frames.append(
                {
                    "phase": b.phase,
                    "time": b.capture_elapsed,
                    "enemies": [[e.x, e.z, e.capture_y] for e in app.swarm_view.enemies],
                }
            )
        if not phases or phases[-1] != label:
            phases.append(label)
        if b and b.phase == "electric" and b.elapsed > b.settings.electric * 0.65:
            label = "electric-mid"
        if b and b.phase == "bound" and b.elapsed > b.settings.bound_hold * 0.7:
            label = "bound-late"
        comparison_ready = (
            not args.individual
            or app.model.combat_session is None
            or app.model.combat_session.phase_elapsed_sec >= 0.15
        )
        if (
            label not in saved
            and comparison_ready
            and (not b or b.elapsed >= 0.2 or b.phase == "spear")
        ):
            pyxel.screen.save(str(out / f"{label}.png"), 2)
            saved.add(label)
        if returned_at and frame - returned_at >= 45:
            pyxel.screen.save(str(out / "field-movement-resumed.png"), 2)
            pyxel.screencast(str(out / "sequence.gif"), scale=2)
            from drift_with_me.save_state import decode, encode, snapshot

            restored = decode(encode(snapshot(app)))
            assert restored[2].swarm_progress == app.east_site_progress.swarm_progress
            assert restored[4] == {"water": app.model.water, "energy": app.model.energy}
            result = {
                "composition": composition,
                "water_stats": water_stats[:: max(1, len(water_stats) // 6)],
                "zoom_audit": zoom_audit,
                "timing_rects": timing_rects,
                "common_ui": {**common_ui, "timing_bar": sorted(set(common_ui["timing_bar"]))},
                "floating_samples": float_frames[:: max(1, len(float_frames) // 12)],
                "touch_button_input": args.touch,
                "spam_wait_input": args.spam_wait,
                "production_sprite_audit": {
                    phase: {role: sorted(ids) for role, ids in roles.items()}
                    for phase, roles in sprite_audit.items()
                },
                "renderer_scene_calls": scene_calls,
                "continuity": continuity,
                "checkpoint_roundtrip_valid": True,
                "scenario": "individual" if args.individual else args.scenario,
                "actual_app": True,
                "save_enabled": False,
                "phases": phases,
                "water": app.model.water,
                "energy": app.model.energy,
                "cleared": sorted(field.cleared),
                "start_position": start_position,
                "final_position": [app.model.player.x, app.model.player.z],
                "returned_to_map": field.battle is None,
                "ordinary_combat_active": app.model.combat_session is not None,
            }
            (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
            pyxel.quit()

    run(update, draw)


if __name__ == "__main__":
    main()
