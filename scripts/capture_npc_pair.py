"""Native W4 map views at the authored idle-pose phases; synthetic storage only."""

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    sys.path.insert(0, str(root / "tests"))
    import pyxel

    from drift_with_me.app import DriftWithMeApp
    from drift_with_me.august_patrol import BY_ID, patrol_pose
    from drift_with_me.hex_assets import placement_for_upright_height_billboard
    from drift_with_me.math3d import Vec3
    from drift_with_me.save_state import ProgressStore, decode, encode, snapshot
    from test_august_patrol import patrol_app
    from test_august_wave1 import dispatch
    from test_save_state import Storage

    seed, _ = patrol_app()
    saved = snapshot(seed)
    run = pyxel.run
    pyxel.run = lambda *_: None
    app = DriftWithMeApp(headless=True)
    pyxel.run = run
    app.progress_store = ProgressStore(browser_storage=Storage())
    app.saved_progress = decode(encode(saved))
    app.start_game()
    dispatch(app)
    app.debug_enabled = False
    app.presentation_time = 0
    base = app.camera()
    app.camera = lambda: replace(base, target=Vec3(826, 0, 866))
    app.model.player.x, app.model.player.z = 780, 842
    app.model.snap_buddy(app.camera())
    app.draw()
    pyxel.screen.save(str(out / "Iwama_Merrill_Jack_Map.png"), 2)
    records = []
    for key in ("iwama", "merrill"):
        ident = "aug_patrol_" + key
        n = BY_ID[ident]
        app.camera = lambda n=n: replace(
            base, target=Vec3(n.position[0] - 8, 0, n.position[1] - 12)
        )
        app.model.player.x, app.model.player.z = n.position[0] - 23, n.position[1] - 18
        if key == "merrill":
            app.model.player.x, app.model.player.z = n.position[0] - 40, n.position[1] - 10
        app.model.player.last_move_x, app.model.player.last_move_z = 0, -1
        app.model.snap_buddy(app.camera())
        app.model.face_actor_toward(*n.position)
        seed = sum((i + 1) * ord(c) for i, c in enumerate(ident))
        app.model.patrol_talking = None
        root_position = (n.position[0], n.position[1])
        for pose, phase in [("normal", 1.0), ("look_left", 7.5), ("look_right", 15.5)]:
            app.model.world_tick = round(((phase - seed % 17) % 18) * 60)
            assert patrol_pose(app.model, ident) == pose
            app.draw()
            pyxel.screen.save(str(out / f"{key}_{pose}_Map.png"), 2)
            camera = app.scene_camera(app.camera())
            npc = app.world.object_by_id(ident)
            assert (npc.x, npc.z) == root_position
            asset = app.renderer.object_sprite_asset(app.model, npc)
            placement = placement_for_upright_height_billboard(
                camera, asset.definition, Vec3(npc.x, 0, npc.z)
            )
            frame = asset.frame(pose)
            records.append(
                dict(
                    npc=key,
                    pose=pose,
                    frame=frame.frame_id,
                    canvas=[frame.width, frame.height],
                    world_size=asset.definition.world_size,
                    anchor=asset.definition.anchor_px,
                    placement=asdict(placement),
                )
            )
        # Real interaction entry freezes the pose and preserves the conversation UI.
        events = []
        candidate = app.model.interaction_candidate(app.camera())
        for dx, dz in [(-12, -16), (0, 14), (-14, 0), (14, 0)]:
            app.model.player.x, app.model.player.z = n.position[0] + dx, n.position[1] + dz
            candidate = app.model.interaction_candidate(app.camera())
            if candidate and candidate.id == ident:
                break
        assert candidate and candidate.id == ident
        app.model.try_start_interaction(events, app.camera())
        app.process_events(events)
        assert app.model.patrol_talking == ident and app.model.world_paused
        app.draw()
        pyxel.screen.save(str(out / f"{key}_Conversation.png"), 2)
        app.patrol_wait_release = False
        app.key_pressed = lambda *_: True
        app.mouse_pressed_in = lambda *_: False
        app.update_patrol(1 / 60)
        assert not app.model.world_paused
    (out / "measurement.json").write_text(
        json.dumps(
            dict(
                records=records, synthetic_save=True, resources=[app.model.water, app.model.energy]
            ),
            indent=2,
        )
    )
    pyxel.quit()


if __name__ == "__main__":
    main()
