from types import SimpleNamespace

import pytest

from drift_with_me.abnormal_urchin_arms import AbnormalUrchinArmSystem
from drift_with_me.render import Renderer


@pytest.mark.parametrize("scale", [0.75, 1.0, 2.0])
def test_pause_debug_arm_chains_draw_every_adjacent_segment(scale):
    lines, circles = [], []
    renderer = Renderer.__new__(Renderer)
    renderer.pyxel = SimpleNamespace(
        line=lambda *args: lines.append(args), circb=lambda *args: circles.append(args)
    )
    rig = AbnormalUrchinArmSystem().update_enemy("abnormal", "IDLE", 1, 0, 1 / 60)
    placement = SimpleNamespace(left=10, top=20, scale=scale)
    renderer.draw_abnormal_urchin_arm_debug(rig, placement)
    assert len(lines) == sum(len(arm.joints) for arm in rig.arms)
    assert len(circles) == sum(len(arm.joints) + 1 for arm in rig.arms)
    cursor = 0
    for arm in rig.arms:
        for i in range(len(arm.joints) - 1):
            start, end = arm.joints[i], arm.joints[i + 1]
            assert lines[cursor] == (
                round(10 + start[0] * scale),
                round(20 + start[1] * scale),
                round(10 + end[0] * scale),
                round(20 + end[1] * scale),
                5,
            )
            cursor += 1
        cursor += 1  # Existing hand-to-target guide.


@pytest.mark.parametrize("scale", [0.75, 1.0, 2.0])
def test_pause_fallback_arm_lines_draw_adjacent_points_without_length_error(scale):
    lines, points = [], []
    renderer = Renderer.__new__(Renderer)
    renderer.pyxel = SimpleNamespace(
        line=lambda *args: lines.append(args), pset=lambda *args: points.append(args)
    )
    placement = SimpleNamespace(left=10, top=20, scale=scale)
    renderer.draw_abnormal_urchin_arm_lines(placement, ((0, 0), (2, 1), (3, 4)), "front")
    assert lines == [
        (10, 20, round(10 + 2 * scale), round(20 + scale), 1),
        (
            round(10 + 2 * scale),
            round(20 + scale),
            round(10 + 3 * scale),
            round(20 + 4 * scale),
            14,
        ),
    ]
    assert points == [(round(10 + 3 * scale), round(20 + 4 * scale), 15)]
