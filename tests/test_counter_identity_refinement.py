from types import SimpleNamespace

import pytest

from drift_with_me.app import COUNTER_REFINED_PORTRAITS, DriftWithMeApp
from drift_with_me.config import load_runtime_config
from drift_with_me.yumesaki_portraits import YUMESAKI_PORTRAITS, yumesaki_office_portrait


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
@pytest.mark.parametrize("original,refined", list(COUNTER_REFINED_PORTRAITS.items()))
def test_counter_refinement_preserves_window_and_never_returns_to_old_frame(
    profile, original, refined
):
    app = object.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config(profile)
    calls, requests = [], []
    app.pyxel = SimpleNamespace(
        rect=lambda *a: None, rectb=lambda *a: None, blt=lambda *a, **kw: calls.append((a, kw))
    )
    frame = SimpleNamespace(width=232, height=232, image="portrait", u=0, v=0)

    def asset(ident):
        requests.append(ident)
        return SimpleNamespace(frame=lambda *_: frame, definition=SimpleNamespace(colkey=8))

    app.sprite_assets = SimpleNamespace(get=asset)
    rect = app.office_rect(10, 51, 116, 133)
    for tick in [0, 167, 169, 171, 999, 1182, 1400]:
        app.frame = tick
        app.draw_office_portrait(rect, original)
    assert requests == [refined] * 7
    assert all(a[5:7] == (232, 232) and kw["colkey"] == 8 for a, kw in calls)
    assert all(kw["scale"] == min(int(rect.width) / 232, int(rect.height) / 232) for a, kw in calls)


def test_authored_yumesaki_expression_selection_stays_original_and_complete():
    assert len(YUMESAKI_PORTRAITS) == 5
    for original in YUMESAKI_PORTRAITS.values():
        assert original in COUNTER_REFINED_PORTRAITS
    assert (
        yumesaki_office_portrait("げ、原因も、今は特定できていなくて……") == "yumesaki_bust_worried"
    )
    assert "fuji_map_knees" not in COUNTER_REFINED_PORTRAITS
    assert "miyano_map_knees" not in COUNTER_REFINED_PORTRAITS


@pytest.mark.parametrize(
    "original", ["nervous_elf_woodsman", "smug_blond_hero", "succubus_green", "tired_gray_oldman"]
)
@pytest.mark.parametrize("smile", [False, True])
def test_counter_full_blink_cycle_uses_only_matching_232_frames(original, smile):
    from drift_with_me.app import OFFICE_PORTRAIT_SMILE_IDS

    app = object.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config()
    loaded = []
    selected = []
    draws = []
    frame = SimpleNamespace(width=232, height=232, image="new", u=0, v=0)

    def get(ident):
        loaded.append(ident)

        def choose(pose=None):
            selected.append(pose)
            return frame

        return SimpleNamespace(frame=choose, definition=SimpleNamespace(colkey=8))

    app.sprite_assets = SimpleNamespace(get=get)
    app.pyxel = SimpleNamespace(
        rect=lambda *a: None, rectb=lambda *a: None, blt=lambda *a, **kw: draws.append(a)
    )
    intervals = tuple(app.runtime.raw["ui"]["office_portrait_blink_interval_frames"][original])
    for tick in range(2 * (sum(intervals) + 7 * len(intervals))):
        app.frame = tick
        pose = app.office_portrait_blink_pose(tick, original, intervals=intervals)
        expected = (
            {None: "open", "half": "half", "closed": "normal"}[pose]
            if smile
            else ("normal" if pose is None else pose)
        )
        app.draw_office_portrait(app.office_rect(10, 51, 116, 133), original, smile=smile)
        assert selected[-1] == expected
    expected_asset = COUNTER_REFINED_PORTRAITS[
        OFFICE_PORTRAIT_SMILE_IDS[original] if smile else original
    ]
    assert set(loaded) == {expected_asset}
    assert len(draws) == len(selected) == len(loaded)
    assert all(a[5:7] == (232, 232) for a in draws)
