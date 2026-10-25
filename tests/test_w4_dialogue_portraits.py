import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from drift_with_me.app import DriftWithMeApp
from drift_with_me.august_patrol import BY_ID, W4_DIALOGUE_PORTRAITS
from drift_with_me.config import load_runtime_config

ROOT = Path(__file__).parents[1] / "src/drift_with_me/assets"


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
@pytest.mark.parametrize(
    "key",
    [
        "iwama",
        "merrill",
        "morris",
        "ruby",
        "ramel",
        "hero",
        "mina",
        "grow",
        "takanashi",
        "yoake",
        "sagan",
        "ura",
    ],
)
def test_w4_detail_uses_same_window_and_common_centered_scaling(profile, key):
    app = object.__new__(DriftWithMeApp)
    app.runtime = load_runtime_config(profile)
    calls = []
    app.pyxel = SimpleNamespace(
        rect=lambda *a: None, rectb=lambda *a: None, blt=lambda *a, **kw: calls.append((a, kw))
    )
    frame = SimpleNamespace(width=232, height=232, image="portrait", u=0, v=0)
    app.sprite_assets = SimpleNamespace(
        get=lambda ident: SimpleNamespace(frame=lambda: frame, definition=SimpleNamespace(colkey=8))
    )
    rect = app.office_rect(44, 52, 66, 66)
    app.draw_office_portrait(rect, W4_DIALOGUE_PORTRAITS[key])
    args, kw = calls[0]
    width, height = int(rect.width), int(rect.height)
    assert kw["scale"] == min(width, height) / 232
    assert args[:2] == (
        math.floor(int(rect.x) + (width - 232) / 2),
        math.floor(int(rect.y) + (height - 232) / 2),
    )
    assert args[5:7] == (232, 232) and kw["colkey"] == 8


def test_w4_aliases_preserve_original_counter_portraits_and_expressions():
    assert BY_ID["aug_patrol_iwama"].portrait == "iwama_bust_normal"
    assert BY_ID["aug_patrol_merrill"].portrait == "merrill_matte"
    assert BY_ID["aug_patrol_morris"].portrait == "morris_matte"
    assert BY_ID["aug_patrol_ruby"].portrait == "ruby_matte"
    assert BY_ID["aug_patrol_ramel"].portrait == "nervous_elf_woodsman"
    assert BY_ID["aug_patrol_hero"].portrait == "smug_blond_hero"
    assert set(W4_DIALOGUE_PORTRAITS) == {
        "iwama",
        "merrill",
        "morris",
        "ruby",
        "ramel",
        "hero",
        "mina",
        "grow",
        "takanashi",
        "yoake",
        "sagan",
        "ura",
    }
    original = {
        "Iwama_bust_normal_116.hex": (
            "543277523653880db566f3b72b6c5e93a82b006671946ceb11c89dfb2f9457fe"
        ),
        "Iwama_bust_smug_116.hex": (
            "4c17f7b532e4a139adab88eff67ed02ed1bf1653146dbbe0f4775ba84a109a01"
        ),
        "Merrill_116_normal.hex": (
            "5dfbc2f2f4a739b649843d72b77e4ea022ded5bfdf43aeec72548036b0edcd2c"
        ),
    }
    original.update(
        {
            "Morris_116_normal.hex": (
                "7676c36e5e88f5c7c08dba52fbbbc08e4e2fcaef4306ed5a36a859ffb05c23a4"
            ),
            "Ruby_116_normal.hex": (
                "eefe839711e6fac41cb6a36a7377f4baa9ca8f384a9fb1823820e22c21662cba"
            ),
        }
    )
    original.update(
        {
            "Ramel_116_normal.hex": (
                "6197d58204fac11c61845356c214018db23136edf3bf755695536c5396885159"
            ),
            "Hero_116_normal.hex": (
                "463210229aff8772f0e1cb0757b6b89d0ab05fca12a441716edc4714df21f572"
            ),
            "Ramel_116_smile_closed.hex": (
                "8347fec1a718f68b1f98798998106dfc3cfaaf64b90acd17163c92a0d44fd9a2"
            ),
            "Hero_116_smile_closed.hex": (
                "cd87b35f1f928ef57a13ca274319e868b60587c0672255a0d780f4a9ab0c5145"
            ),
        }
    )
    for name, expected in original.items():
        data = bytes(int(c, 16) for c in "".join((ROOT / name).read_text().split()))
        assert hashlib.sha256(data).hexdigest() == expected


def test_w4_iwama_expressions_are_separate_with_fixed_shirt_and_valid_palette():
    assets = {
        a["id"]: a for a in json.loads((ROOT / "jack_sprite.json").read_text())["source_assets"]
    }
    rows = []
    for ident in [
        "w4_iwama_dialogue_normal",
        "w4_iwama_dialogue_smug",
        "w4_merrill_dialogue_normal",
        "w4_morris_dialogue_normal",
        "w4_ruby_dialogue_normal",
        "w4_ramel_dialogue_normal",
        "w4_ramel_dialogue_smile",
        "w4_hero_dialogue_normal",
        "w4_hero_dialogue_smile",
        "w4_mina_dialogue_normal",
        "w4_mina_dialogue_smile",
        "w4_grow_dialogue_normal",
        "w4_grow_dialogue_smile",
        "w4_takanashi_dialogue_normal",
        "w4_yoake_dialogue_normal",
        "w4_sagan_dialogue_normal",
        "w4_ura_dialogue_normal",
    ]:
        a = assets[ident]
        assert a["hex_width"] == a["hex_height"] == 232
        assert a["anchor_px"] == [116, 116] and a["colkey"] == 8
        r = (ROOT / a["frames"][0]["path"]).read_text().splitlines()
        assert len(r) == 232 and all(len(line) == 232 for line in r)
        assert set("".join(r)) <= set("0123456789ABCDEF")
        rows.append(r)
    assert rows[0][:156] != rows[1][:156]
    assert rows[0][156:] == rows[1][156:]


@pytest.mark.parametrize("key", ["ramel", "hero"])
def test_river_closed_smile_uses_separate_asset_and_preserves_shirt(key):
    from drift_with_me.app import OFFICE_PORTRAIT_SMILE_IDS

    normal = W4_DIALOGUE_PORTRAITS[key]
    from drift_with_me.august_patrol import W4_DIALOGUE_SMILE_PORTRAITS

    assert normal not in OFFICE_PORTRAIT_SMILE_IDS
    smile = W4_DIALOGUE_SMILE_PORTRAITS[key]
    assert smile == f"w4_{key}_dialogue_smile"
    assets = {
        a["id"]: a for a in json.loads((ROOT / "jack_sprite.json").read_text())["source_assets"]
    }
    rows = [
        (ROOT / assets[ident]["frames"][0]["path"]).read_text().splitlines()
        for ident in [normal, smile]
    ]
    assert rows[0][:156] != rows[1][:156]
    assert rows[0][156:] == rows[1][156:]
