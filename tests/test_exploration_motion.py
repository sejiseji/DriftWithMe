"""Gameplay invariance, bounded display offsets, and silent environment contacts."""

from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

from drift_with_me.config import load_runtime_config
from drift_with_me.effects import EffectSystem
from drift_with_me.exploration_motion import ExplorationMotion
from drift_with_me.math3d import CameraState, Vec3
from drift_with_me.model import GameModel, InputIntent
from drift_with_me.save_state import snapshot
from drift_with_me.world import load_world_data
from test_save_state import payload


def setup():
    raw = load_runtime_config().raw
    m = GameModel(raw, load_world_data())
    m.enemies.clear()
    c = CameraState.from_config(raw, Vec3(200, 0, 240), 512, 236)
    return m, c, EffectSystem(raw)


def test_offsets_do_not_change_logic_collisions_events_or_saved_progress():
    a, _ = payload()
    b = deepcopy(a)
    motions = [ExplorationMotion(), ExplorationMotion()]
    motions[0].enabled = False
    effects = [EffectSystem(a.runtime.raw), EffectSystem(b.runtime.raw)]
    for app in (a, b):
        app.model.enemies.clear()
    for frame in range(600):
        direction = (1, 0, -1, 0, 0, 1)[frame // 20 % 6]
        intent = InputIntent(screen_x=direction, strength=abs(direction))
        events = []
        for app, motion, fx in zip((a, b), motions, effects, strict=True):
            events.append(app.model.step(intent, app.camera(), 1 / 60))
            fx.update(1 / 60, app.model)
            motion.update(1 / 60, app.model, app.camera(), fx)
        assert events[0] == events[1]
        assert asdict(a.model.player) == asdict(b.model.player)
        assert asdict(a.model.buddy) == asdict(b.model.buddy)
        assert a.model.world_tick == b.model.world_tick
        assert a.model.water == b.model.water and a.model.energy == b.model.energy
        for x, z in ((128, 192), (200, 240), (224, 352), (456, 568)):
            assert a.world.collides_player(x, z, 10, 10) == b.world.collides_player(x, z, 10, 10)
    assert snapshot(a) == snapshot(b)


def test_stops_reversals_cooldowns_and_buddy_offset_always_opposes_last_motion():
    m, c, fx = setup()
    motion = ExplorationMotion()
    motion.update(1 / 60, m, c, fx)
    had_stop = False
    contacts = 0
    for frame in range(600):
        dx = 1 if frame % 8 < 3 else -1 if frame % 8 < 6 else 0
        m.player.x += dx
        fx.contact_cues[:] = ["grass", "water"]
        motion.update(1 / 60, m, c, fx)
        for actor in ("player", "buddy"):
            offset = motion.offset(actor)
            assert abs(offset[0]) + abs(offset[1]) <= 1
        buddy = motion.offset("buddy")
        assert sum(a * b for a, b in zip(buddy, motion.direction, strict=True)) <= 0
        had_stop |= motion.offset("player") != (0, 0)
        contacts += motion.consume_contact() is not None
        assert motion.consume_contact() is None
    assert had_stop and contacts <= 12
    for _ in range(30):
        motion.update(1 / 60, m, c, fx)
    assert motion.offset("player") == motion.offset("buddy") == (0, 0)


def test_inactive_relocation_and_reset_clear_every_pending_reaction():
    m, c, fx = setup()
    motion = ExplorationMotion()
    for dx in (0, 1, 0):
        m.player.x += dx
        motion.update(1 / 60, m, c, fx)
    assert motion.offset("player") != (0, 0)
    motion.update(1 / 60, m, c, fx, active=False)
    assert motion.offset("player") == motion.offset("buddy") == (0, 0)
    assert motion.consume_contact() is None
    m.player.x += 40
    fx.contact_cues[:] = ["water"]
    motion.update(1 / 60, m, c, fx)
    assert motion.consume_contact() is None
    assert motion.offset("player") == (0, 0)


def test_water_reaction_accumulates_subthreshold_steps_at_60fps_only_in_real_area():
    m, c, fx = setup()
    m.player.x, m.player.z = 110, 240
    count = 0
    fx.update(1 / 60, m)
    for _ in range(70):
        m.player.x += 1.4  # actual configured 84 world units/sec at 60 Hz
        fx.update(1 / 60, m)
        count += "water" in fx.contact_cues
        assert len(fx.contact_cues) <= 2
        assert len(fx.rings) <= fx.max_particles
    assert count >= 3
    fx.reset()
    m.player.x, m.player.z = 600, 500
    fx.update(1 / 60, m)
    for _ in range(20):
        m.player.x += 1.4
        fx.update(1 / 60, m)
        assert "water" not in fx.contact_cues
    m.interaction = SimpleNamespace()
    fx.update(1 / 60, m)
    assert not fx.contact_cues


def test_zoom_and_pause_never_apply_an_old_screen_offset():
    from dataclasses import replace

    from drift_with_me.hex_assets import SpritePlacement

    m, c, fx = setup()
    motion = ExplorationMotion()
    for dx in (0, 1, 0):
        m.player.x += dx
        motion.update(1 / 60, m, c, fx)
    assert motion.offset("player") != (0, 0)
    placement = SpritePlacement(20, 20, 100, 1, False, 10, 10, 10, 10, 30, 30)
    before = deepcopy(m.player)
    assert motion.placement(placement, "player", m) != placement
    assert m.player == before
    m.interaction = SimpleNamespace()
    assert motion.placement(placement, "player", m) == placement
    m.interaction = None
    motion.update(1 / 60, m, replace(c, distance=c.distance + 1), fx)
    assert motion.offset("player") == motion.offset("buddy") == (0, 0)
    assert motion.consume_contact() is None


def test_lifecycle_reset_discards_only_new_presentation_state():
    from collections import namedtuple

    from drift_with_me.lifecycle import LifecycleMixin

    m, c, fx = setup()
    motion = ExplorationMotion()
    for dx in (0, 1, 0):
        m.player.x += dx
        motion.update(1 / 60, m, c, fx)
    assert motion.offset("player") != (0, 0)
    fx.contact_cues[:] = ["water"]
    pointer = namedtuple("Pointer", "down pressed x y")(False, False, 0, 0)
    stub = SimpleNamespace(
        _exploration_feedback=SimpleNamespace(motion=motion),
        effects=fx,
        model=m,
        pointer_snapshot=pointer,
        clear_world_input_latches=lambda: None,
    )
    LifecycleMixin.reset_lifecycle_input_and_clock(stub)
    assert motion.offset("player") == motion.offset("buddy") == (0, 0)
    assert not fx.contact_cues


def test_zoom_clears_offsets_while_contact_notifications_remain_bounded():
    m, c, fx = setup()
    motion = ExplorationMotion()
    motion.update(1 / 60, m, c, fx)
    count = 0
    for _ in range(120):
        m.player.x += 1
        fx.contact_cues[:] = ["water"]
        motion.update(1 / 60, m, c, fx, active=False, contacts_active=True)
        assert motion.offset("player") == motion.offset("buddy") == (0, 0)
        count += motion.consume_contact() is not None
    assert count == 3


def test_real_grass_and_shallow_water_contacts_never_play_audio():
    from drift_with_me.app import AppScreen
    from drift_with_me.audio import SOUND_SHAPES, AudioEngine
    from test_field_visit import make_visit

    app = make_visit()
    app.screen = AppScreen.PLAY
    app.presentation_time = 0.0
    app.effects = EffectSystem(app.runtime.raw)
    app.audio = AudioEngine(app.runtime.raw)
    calls = []
    app.audio._pyxel = SimpleNamespace(
        play=lambda *args: calls.append(args), play_pos=lambda channel: None
    )
    app.audio._sound_slots = {key: index for index, key in enumerate(SOUND_SHAPES)}
    app.audio.muted = False
    app.ui_trace_begin_frame = app.ui_trace_end_frame = lambda: None
    contacts = []

    def frame():
        app.presentation_time += 1 / 60
        app.model.player.x += 1.4
        app.effects.update(1 / 60, app.model)
        contacts.extend(app.effects.contact_cues)

    app.update_game_frame = frame
    for x, z in ((176, 352), (110, 240)):
        app.effects.reset()
        app.exploration_feedback.reset()
        app.model.player.x, app.model.player.z = x, z
        for _ in range(80):
            app.update()
    assert "grass" in contacts and "water" in contacts
    assert not calls
    assert "contact_grass" not in SOUND_SHAPES and "contact_water" not in SOUND_SHAPES


def test_accepted_three_se_shapes_are_preserved_exactly():
    from drift_with_me.audio import SOUND_SHAPES

    assert SOUND_SHAPES["explore_pickup"] == ("e4g4b4g4", "tttt", "2321", "nnvf", 7)
    assert SOUND_SHAPES["explore_water"] == ("c4e4b4g4", "ttpt", "1231", "ssnf", 5)
    assert SOUND_SHAPES["explore_energy"] == ("g4g4e4d4c4c4", "nntttt", "122211", "nnvvff", 7)
