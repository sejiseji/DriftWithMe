import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.app import DriftWithMeApp
from drift_with_me.august_patrol import BY_ID, W4_LARGE_DIALOGUE_PORTRAITS
from drift_with_me.config import load_runtime_config


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
@pytest.mark.parametrize("key", ["fuji", "yumesaki", "miyano"])
def test_fuji_detail_keeps_existing_large_portrait_size_and_center(profile, key):
    app = object.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config(profile)
    calls = []
    app.pyxel = SimpleNamespace(blt=lambda *a, **kw: calls.append((a, kw)))
    frame = SimpleNamespace(width=200, height=432, image="portrait", u=0, v=0)
    app.sprite_assets = SimpleNamespace(
        get=lambda _: SimpleNamespace(frame=lambda: frame, definition=SimpleNamespace(colkey=8))
    )
    app.draw_field_character_portrait(W4_LARGE_DIALOGUE_PORTRAITS[key])
    rect = app.office_rect(360, 6, 132, 196)
    args, kw = calls[0]
    assert kw["scale"] == min(rect.width / 200, rect.height / 432)
    assert math.isclose(kw["scale"] * 432, rect.height)
    assert args[:2] == (
        round(rect.x + (rect.width - 200) / 2),
        round(rect.y + (rect.height - 432) / 2),
    )
    assert kw["colkey"] == 8 and args[5:7] == (200, 432)


def test_fuji_alias_is_w4_only_static_and_keeps_old_source():
    assert {
        k: f"w4_{k}_dialogue_identity_normal" for k in ["fuji", "yumesaki", "miyano"]
    } == W4_LARGE_DIALOGUE_PORTRAITS
    assert BY_ID["aug_patrol_fuji"].portrait == "fuji_map_knees"
    manifest = json.loads(
        (Path(__file__).parents[1] / "src/drift_with_me/assets/jack_sprite.json").read_text()
    )
    assets = {a["id"]: a for a in manifest["source_assets"]}
    assert assets["fuji_map_knees"]["hex_width"] == 100
    assert (
        assets["fuji_map_knees"]["source_hash"]
        == "4dac8794ffa77097db33a946cbabda769d109d8c93b135132fafb50d8cf2cea6"
    )
    new = assets["w4_fuji_dialogue_identity_normal"]
    assert new["anchor_px"] == [100, 216]
    assert new["hex_width"] == 200 and new["hex_height"] == 432
    assert len(new["frames"]) == 1 and new["animation"] == "static"
