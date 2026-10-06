from types import SimpleNamespace

import pytest

from drift_with_me.app import OFFICE_PORTRAIT_SMILE_IDS
from drift_with_me.office import OfficePrototype
from test_office_supervisor import app_for, finish


@pytest.mark.parametrize("profile,scale", [("low", 95 / 64), ("medium", 116 / 64), ("high", 2.0)])
def test_every_visitor_expression_and_blink_stays_inside_large_name_only_layout(profile, scale):
    office = OfficePrototype.load()
    office.begin_current_case()
    finish(office)
    app = app_for(office, profile)
    rect = app.office_visitor_portrait_rect()
    name = app.office_visitor_info_rect()
    assert rect.y + rect.height + 4 == name.y
    assert name.y + name.height < app.office_visitor_rect().y + app.office_visitor_rect().height
    for case in office.cases:
        assert app.office_visitor_info_lines(case) == (case.visitor.name,)
        assert app.ui_text.text_width(case.visitor.name, "office_japanese") <= name.width
        for smile in (False, True):
            for pose in ("open", "half", "closed"):
                calls = []
                loaded = []

                def asset(asset_id, loaded=loaded):
                    loaded.append(asset_id)
                    frame = SimpleNamespace(width=64, height=64, image=asset_id, u=0, v=0)
                    return SimpleNamespace(
                        frame=lambda: frame, definition=SimpleNamespace(colkey=8)
                    )

                app.sprite_assets = SimpleNamespace(get=asset)
                app.pyxel = SimpleNamespace(
                    rect=lambda *args: None,
                    rectb=lambda *args: None,
                    blt=lambda *args, calls=calls, **kw: calls.append((args, kw)),
                )
                app.office_portrait_blink_pose = lambda *args, pose=pose, **kw: (
                    None if pose == "open" else pose
                )
                app.draw_office_portrait(rect, case.visitor.portrait_id, smile=smile)
                expected = (
                    OFFICE_PORTRAIT_SMILE_IDS[case.visitor.portrait_id]
                    if smile
                    else case.visitor.portrait_id
                )
                assert loaded[0] == expected
                for args, kw in calls:
                    assert kw["scale"] == scale
                    x = args[0] + 64 * (1 - scale) / 2
                    y = args[1] + 64 * (1 - scale) / 2
                    assert (
                        rect.x - 0.500001 <= x and x + 64 * scale <= rect.x + rect.width + 0.500001
                    )
                    assert (
                        rect.y - 0.500001 <= y and y + 64 * scale <= rect.y + rect.height + 0.500001
                    )
                assert all(
                    (args[:2], kw["scale"]) == (calls[0][0][:2], scale) for args, kw in calls
                )
