"""Native renderer evidence, synthetic in-memory save; never touches user storage."""

import argparse
import json
import sys
from dataclasses import replace
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

    from drift_with_me.app import AppScreen, DriftWithMeApp
    from drift_with_me.august_patrol import BY_ID
    from drift_with_me.math3d import Vec3
    from drift_with_me.save_state import ProgressStore, decode, encode, snapshot
    from test_august_patrol import patrol_app
    from test_august_wave1 import dispatch
    from test_save_state import Storage

    seed, _ = patrol_app()
    payload = snapshot(seed)
    run = pyxel.run
    pyxel.run = lambda *_: None
    app = DriftWithMeApp(headless=True)
    pyxel.run = run
    app.progress_store = ProgressStore(browser_storage=Storage())
    app.saved_progress = decode(encode(payload))
    app.start_game()
    dispatch(app)
    app.field_transition = None
    app.screen = AppScreen.PLAY
    app.debug_enabled = False
    app.presentation_time = 0
    app.draw()
    base = app.camera
    files = []

    def save(name):
        app.draw()
        path = out / (name + ".png")
        pyxel.screen.save(str(path), 2)
        files.append(path.name)

    # All-map view is a real world-camera shot, not an explanatory UI/map mockup.
    scene_base = app.scene_camera
    app.scene_camera = lambda c: replace(scene_base(c), zoom=0.24)
    app.camera = lambda: replace(base(), target=Vec3(510, 0, 510))
    save("W4_Overview")
    app.scene_camera = scene_base
    for label, x, z in (
        ("NW_Researchers", 94, 636),
        ("NE_Park", 848, 888),
        ("Garden_Fuji", 210, 400),
        ("Entrance", 180, 200),
        ("Waterway", 920, 170),
        ("North_Shallow", 470, 280),
        ("East_Canal", 936, 274),
        ("Branches", 300, 400),
    ):
        app.camera = lambda x=x, z=z: replace(
            base(), target=Vec3(x, 0, z), distance=base().distance / 1.2
        )
        app.model.player.x, app.model.player.z = x - 60, z - 60
        app.model.snap_buddy(app.camera())
        save("W4_" + label)
    records = []
    for ident, n in BY_ID.items():
        app.camera = lambda n=n: replace(
            base(), target=Vec3(n.position[0], 0, n.position[1]), distance=base().distance / 1.2
        )
        app.model.player.x, app.model.player.z = n.position[0] - 12, n.position[1] - 16
        app.model.snap_buddy(app.camera())
        app.model.face_actor_toward(*n.position)
        # Normal interaction entry and event dispatch, not direct dialogue assignment.
        candidate = None
        for dx, dz in ((-12, -16), (0, 14), (-14, 0), (14, 0), (0, -14)):
            app.model.player.x, app.model.player.z = n.position[0] + dx, n.position[1] + dz
            if app.world.collides_player(app.model.player.x, app.model.player.z, 4, 4):
                continue
            candidate = app.model.interaction_candidate(app.camera())
            if candidate and candidate.id == ident:
                break
        assert candidate and candidate.id == ident, (ident, candidate)
        app.model.snap_buddy(app.camera())
        events = []
        app.model.try_start_interaction(events, app.camera())
        app.process_events(events)
        assert app.patrol_dialogue and app.patrol_dialogue.target_id == ident
        assert app.model.world_paused and app.model.combat_session is None
        save("W4_Talk_" + n.key)
        app.patrol_wait_release = False
        app.key_pressed = lambda *_: True
        app.mouse_pressed_in = lambda *_: False
        app.update_patrol(1 / 60)
        assert not app.model.world_paused and app.patrol_dialogue is None
        records.append(dict(npc=n.key, asset=n.map_asset, portrait=n.portrait, large=n.large))
    app.camera = base
    assert app.return_august()
    app.field_transition = None
    app.screen = AppScreen.OFFICE
    save("W4_Return_Choice")
    assert app.office.august_progress.sites == []
    (out / "result.json").write_text(
        json.dumps(
            dict(
                files=files,
                npcs=records,
                enemy_count=len(app.model.enemies),
                resources=[app.model.water, app.model.energy],
                save_isolated=True,
                dialogue_preview_text=True,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    pyxel.quit()


if __name__ == "__main__":
    main()
