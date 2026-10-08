from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

from drift_with_me.app import (
    OFFICE_PORTRAIT_BLINK_OVERLAY_IDS,
    OFFICE_PORTRAIT_SMILE_BLINK_OVERLAY_IDS,
    OFFICE_PORTRAIT_SMILE_IDS,
    DriftWithMeApp,
)
from drift_with_me.config import load_runtime_config
from drift_with_me.input import Rect

ROOT = Path(__file__).resolve().parents[1]
EYES = {
    "succubus_green": ((21, 26, 9, 4, 1, 1), (35, 28, 7, 3, 1, 1)),
    "tired_gray_oldman": ((37, 47, 11, 6, 0, 0), (57, 47, 11, 5, 0, 0)),
    "smug_blond_hero": ((48, 42, 18, 7, 0, 0), (68, 50, 10, 7, 0, 0)),
    "nervous_elf_woodsman": ((39, 55, 13, 6, 0, 0), (62, 53, 12, 5, 0, 0)),
}
APPROVED_POSE_HASHES = {
    (
        "nervous_elf_woodsman",
        True,
        "closed",
    ): "8347fec1a718f68b1f98798998106dfc3cfaaf64b90acd17163c92a0d44fd9a2",
    (
        "nervous_elf_woodsman",
        True,
        "half",
    ): "8d637210238287951cccd71c2da7d84c7c8a2bdc5cd911ab2482c313c8f1a5ef",
    (
        "nervous_elf_woodsman",
        True,
        "open",
    ): "e16c64e16e4a062b0a04a3eaea80ba553752abdfad51aaa49d386a07215b469b",
    (
        "nervous_elf_woodsman",
        False,
        "closed",
    ): "48cfcd09e39120274f0b7318243dc4255284f3820fad3f38fa34b8d120f12bf7",
    (
        "nervous_elf_woodsman",
        False,
        "half",
    ): "acea91aa4c5a3f9f66978b9aa9a79d1b3fd432fbbd26c085da355ea04698fa50",
    (
        "nervous_elf_woodsman",
        False,
        "open",
    ): "6197d58204fac11c61845356c214018db23136edf3bf755695536c5396885159",
    (
        "succubus_green",
        False,
        "open",
    ): "f48b150e41b07e237357f3f4d6fe9d079548cb998ebda836a9dc6dd4464c1f8e",
    (
        "succubus_green",
        False,
        "half",
    ): "0268492396799c23a6a31cfdd05375ccb7d711a724efb2911540c4a796a5ad65",
    (
        "succubus_green",
        False,
        "closed",
    ): "077ebbda4d4acd21d63073e56bd7aa32dbed060a99a86ce68670da9a15610b64",
    (
        "succubus_green",
        True,
        "open",
    ): "2af3659d921f745ccf94c812a1dfa8bb9f185bdcf01ca95d7b5894cf3bfb4545",
    (
        "succubus_green",
        True,
        "half",
    ): "f28b3a157a0832c1025d913f5e66e754cbf6360e17d2b24d0d47620d4c37d8c4",
    (
        "succubus_green",
        True,
        "closed",
    ): "0254cc1baa08d5c3c41c6bc95cadae4200fff1487f85a54b5184141294576d87",
    (
        "tired_gray_oldman",
        False,
        "open",
    ): "5c22b1b9deebc78a3c64c92206c8df23974b8e1620ccde1ac739e6e180715332",
    (
        "tired_gray_oldman",
        False,
        "half",
    ): "023c7453d0cca07b472efe807f1a03e6a097672a6a42448e890fc6a0d4333736",
    (
        "tired_gray_oldman",
        False,
        "closed",
    ): "c57c4568befd04ea9eeb9919c564572bbfd39ad7334821003072a3ed6bf6bcb3",
    (
        "tired_gray_oldman",
        True,
        "open",
    ): "5c627939be1b389e590c1a75a741f51d8e209e12c3beb4b9f0c890684a4b6969",
    (
        "tired_gray_oldman",
        True,
        "half",
    ): "e193d101e222edd99f3b8da1111a4b73b6d89a9f3e9eefc12c2794f6a745c6fc",
    (
        "tired_gray_oldman",
        True,
        "closed",
    ): "611808965bda0cf2b3f4be9a6cb476286a87d74ed04aa2f17386423fd468b1bc",
    (
        "smug_blond_hero",
        False,
        "open",
    ): "463210229aff8772f0e1cb0757b6b89d0ab05fca12a441716edc4714df21f572",
    (
        "smug_blond_hero",
        False,
        "half",
    ): "7495dbadfd9c0396b94011201b81544840101916c3022404ab4b1760e71d8c14",
    (
        "smug_blond_hero",
        False,
        "closed",
    ): "a6fb24f8654c20a89deebee2c21511a90eb2b85d2641be9120af72138c263ce2",
    (
        "smug_blond_hero",
        True,
        "open",
    ): "f98d545bcbf5d6e309536037302dcb5eab6eab5a221f9a6e1a22d277f81f5f36",
    (
        "smug_blond_hero",
        True,
        "half",
    ): "9bf23e7012892f91ac45cf57f783f588f667a18b04bc7e9d90d9fef0d299ed49",
    (
        "smug_blond_hero",
        True,
        "closed",
    ): "cd87b35f1f928ef57a13ca274319e868b60587c0672255a0d780f4a9ab0c5145",
}


def sources():
    path = ROOT / "src/drift_with_me/assets/jack_sprite.json"
    data = json.loads(path.read_text())
    return {
        item["id"]: bytes(
            int(c, 16)
            for c in "".join((path.parent / item["frames"][0]["path"]).read_text().splitlines())
        )
        for item in data["source_assets"]
        if item["id"] in OFFICE_PORTRAIT_SMILE_IDS
        or any(item["id"].startswith(n + "_") for n in OFFICE_PORTRAIT_SMILE_IDS)
    }


def composite(base, overlay):
    return bytes(a if b == 8 else b for a, b in zip(base, overlay, strict=True))


def test_approved_blink_poses_only_change_eye_pixels():
    pixels = sources()
    for name, eyes in EYES.items():
        for smile in (False, True):
            size = math.isqrt(len(pixels[name]))
            base = pixels[OFFICE_PORTRAIT_SMILE_IDS[name] if smile else name]
            mapping = (
                OFFICE_PORTRAIT_SMILE_BLINK_OVERLAY_IDS
                if smile
                else OFFICE_PORTRAIT_BLINK_OVERLAY_IDS
            )[name]
            allowed = {
                (x + (dx if smile else 0), y + (dy if smile else 0))
                for ox, oy, w, h, dx, dy in eyes
                for x in range(ox, ox + w)
                for y in range(oy, oy + h)
            }
            for pose in ("open", "half", "closed"):
                overlay = pixels[mapping[pose]] if pose in mapping else bytes([8] * len(base))
                changed = {(i % size, i // size) for i, c in enumerate(overlay) if c != 8}
                assert changed <= allowed
                target = composite(base, overlay)
                assert all((a == 8) == (b == 8) for a, b in zip(base, target, strict=True))
                assert (
                    hashlib.sha256(target).hexdigest() == APPROVED_POSE_HASHES[(name, smile, pose)]
                )


def test_every_person_expression_pose_transition_clears_previous_pixels():
    pixels = sources()
    canvas = [1] * 4096

    class PixelPyxel:
        @staticmethod
        def rect(x, y, width, height, color):
            canvas[:] = [color] * (width * height)

        @staticmethod
        def rectb(*args):
            pass  # Border decoration is independent of portrait compositing.

        @staticmethod
        def blt(x, y, image, u, v, w, h, *, colkey, scale):
            size = math.isqrt(len(pixels[image]))
            assert (x, y, u, v, w, h, colkey, scale) == (0, 0, 0, 0, size, size, 8, 1)
            for i, c in enumerate(pixels[image]):
                if c != colkey:
                    canvas[i] = c

    assets = {
        name: SimpleNamespace(
            frame=lambda name=name: SimpleNamespace(
                image=name,
                u=0,
                v=0,
                width=math.isqrt(len(pixels[name])),
                height=math.isqrt(len(pixels[name])),
            ),
            definition=SimpleNamespace(colkey=8),
        )
        for name in pixels
    }
    runtime = load_runtime_config()
    app = DriftWithMeApp.__new__(DriftWithMeApp)
    app.pyxel = PixelPyxel()
    app.sprite_assets = SimpleNamespace(get=assets.get)
    app.runtime = runtime
    targets = []
    for name in OFFICE_PORTRAIT_SMILE_IDS:
        intervals = tuple(runtime.raw["ui"]["office_portrait_blink_interval_frames"][name])
        for smile in (False, True):
            for pose in (None, "half", "closed"):
                frame = next(
                    f
                    for f in range(3000)
                    if app.office_portrait_blink_pose(f, name, intervals=intervals) == pose
                )
                base = pixels[OFFICE_PORTRAIT_SMILE_IDS[name] if smile else name]
                mapping = (
                    OFFICE_PORTRAIT_SMILE_BLINK_OVERLAY_IDS
                    if smile
                    else OFFICE_PORTRAIT_BLINK_OVERLAY_IDS
                )[name]
                overlay_id = mapping.get(pose or "open")
                expected = composite(base, pixels[overlay_id]) if overlay_id else base
                expected = bytes(1 if c == 8 else c for c in expected)
                targets.append((name, smile, frame, expected))
    for previous in targets:
        for current in targets:
            for name, smile, frame, expected in (previous, current):
                app.frame = frame
                size = math.isqrt(len(pixels[name]))
                app.draw_office_portrait(Rect(0, 0, size, size), name, smile=smile)
                assert bytes(canvas) == expected
