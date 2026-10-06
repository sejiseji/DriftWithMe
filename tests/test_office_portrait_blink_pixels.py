from __future__ import annotations

import hashlib
import json
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
    "tired_gray_oldman": ((19, 25, 7, 5, 3, 1), (29, 25, 7, 4, 3, 1)),
    "smug_blond_hero": ((24, 21, 9, 5, 1, 1), (36, 26, 5, 3, 1, 1)),
}
APPROVED_POSE_HASHES = {
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
    ): "f2fee518076a01b633898e66fe096a54eca43be150e067ec8a6d47b2ec7d8b61",
    (
        "tired_gray_oldman",
        False,
        "half",
    ): "b0ddf549f7f5a8d22a73a4b13267255562387f04925ecfac5ed950e0d50af93e",
    (
        "tired_gray_oldman",
        False,
        "closed",
    ): "06c5bfa42a230c88548d7d3add8aa34e589db798b5b9ab95ee84b1d58a3bf9c0",
    (
        "tired_gray_oldman",
        True,
        "open",
    ): "218b8e1de7f0f8f690084a3908102983cff7e0ecec90569fd4bb9c6f0ed34c41",
    (
        "tired_gray_oldman",
        True,
        "half",
    ): "a34f147440f004f3988ea18999ccfb95144244714d1a441cf186d0ff9eb7edfc",
    (
        "tired_gray_oldman",
        True,
        "closed",
    ): "ac41851ab735ec23760c08873f27cb5a0b3513ec2fdedbc1518b8f712e3f62cd",
    (
        "smug_blond_hero",
        False,
        "open",
    ): "5abb624393ecc542d2c03c723d54c9b40f10c50b2b2ff9e94e908ce714991e43",
    (
        "smug_blond_hero",
        False,
        "half",
    ): "0d97b5c676076089c747404f0d9860825917f0db1fad62de668ab9cf89825d02",
    (
        "smug_blond_hero",
        False,
        "closed",
    ): "709cd27fcdd0bc28be4139a29a9c95988f3645c509030644d22327f1385f1f03",
    (
        "smug_blond_hero",
        True,
        "open",
    ): "cd4e644c2886c45b0aa72ab19d3e9a2d41a3e86090373f4bceb5db53555328a6",
    (
        "smug_blond_hero",
        True,
        "half",
    ): "7e3e1a94554c4429b5d9aed22f577713c304f6205ac4efa1bcd81d617853c3eb",
    (
        "smug_blond_hero",
        True,
        "closed",
    ): "47f6c7d4088510f415df2ff2b9c7ea3e441c925ae9b8e75fe5fff15a1220bc11",
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
                overlay = pixels[mapping[pose]] if pose in mapping else bytes([8] * 4096)
                changed = {(i % 64, i // 64) for i, c in enumerate(overlay) if c != 8}
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
        def rect(*args):
            canvas[:] = [1] * 4096

        @staticmethod
        def rectb(*args):
            pass  # Border decoration is independent of portrait compositing.

        @staticmethod
        def blt(x, y, image, u, v, w, h, *, colkey, scale):
            assert (x, y, u, v, w, h, colkey, scale) == (0, 0, 0, 0, 64, 64, 8, 1)
            for i, c in enumerate(pixels[image]):
                if c != colkey:
                    canvas[i] = c

    assets = {
        name: SimpleNamespace(
            frame=lambda name=name: SimpleNamespace(image=name, u=0, v=0, width=64, height=64),
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
                app.draw_office_portrait(Rect(0, 0, 64, 64), name, smile=smile)
                assert bytes(canvas) == expected
