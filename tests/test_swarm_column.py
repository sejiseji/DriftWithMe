import hashlib
from pathlib import Path

from drift_with_me.render import Renderer
from drift_with_me.swarm_column import attack_view, column_frame


def test_exact_approved_clip_and_only_rotation_accelerated():
    assert [column_frame(t) for t in (0, 0.1, 0.2, 0.3)] == [0, 1, 2, 3]
    assert [column_frame(0.4 + t) for t in (0.001, 0.071, 0.131, 0.201)] == [4, 5, 6, 7]
    assert column_frame(0.671) == 4
    assert [column_frame(t) for t in (1.481, 1.581, 1.681, 1.781)] == [8, 9, 10, 11]
    assert column_frame(1.88) is None
    p = Path(__file__).parents[1] / "src/drift_with_me/assets/swarm_column"
    import json

    manifest = json.loads((p / "sprites.json").read_text())["assets"][0]
    for f in manifest["frames"]:
        raw = bytes(int(c, 16) for c in (p / f["path"]).read_text() if c.strip())
        assert hashlib.sha256(raw).hexdigest() == f["source_hash"]
    assert manifest["anchor_px"] == [24, 72] and manifest["colkey"] == 0


def test_single_turn_belongs_to_only_one_attacker_and_leaves_no_pose():
    views = Renderer.SPIN_DIRECTION_VIEWS
    for phase, actor, other in [("electric", "buddy", "player"), ("spear", "player", "buddy")]:
        assert attack_view(phase, 0, actor, views) == "front"
        samples = [attack_view(phase, 0.12 + (i + 0.5) * 0.48 / 8, actor, views) for i in range(8)]
        assert len(set(samples)) == 8
        assert all(attack_view(phase, t, other, views) is None for t in [0, 0.2, 0.4, 0.8])
        assert attack_view(phase, 0.6, actor, views) is None
        assert attack_view(phase, 1, actor, views) is None
        for interrupted in ["shake", "fade", "victory", "retreat_line", "field"]:
            assert attack_view(interrupted, 0.3, actor, views) is None


def test_attack_eyes_are_chevrons_without_touching_normal_or_rear_faces():
    import json

    root = Path(__file__).parents[1] / "src/drift_with_me/assets/swarm_column"
    assets = {a["id"]: a for a in json.loads((root / "sprites.json").read_text())["assets"]}
    for actor, left, right, y, color in [("jack", 8, 24, 20, "1"), ("fuse", 19, 28, 25, "A")]:
        rows = (
            (root / assets[f"{actor}_front_squint"]["frames"][0]["path"]).read_text().splitlines()
        )
        for dy, dx in enumerate([0, 1, 2, 1, 0]):
            assert rows[y - 2 + dy][left + dx] == color
            assert rows[y - 2 + dy][right - dx] == color
        assert not any(f"{actor}_back" in key for key in assets)
