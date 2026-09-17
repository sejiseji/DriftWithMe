from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from drift_with_me.hex_assets import HexAssetError, join_traversable, parse_hex_rows
from drift_with_me.input import Rect


@dataclass(frozen=True)
class UISkinAsset:
    asset_id: str
    width: int
    height: int
    colkey: int
    rows: tuple[str, ...]
    image: Any


@dataclass(frozen=True)
class UISkinLibrary:
    enabled: bool
    assets: dict[str, UISkinAsset]
    errors: tuple[str, ...] = ()
    _scaled_cache: dict[tuple[str, int, int], Any] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def get(self, asset_id: str) -> UISkinAsset | None:
        return self.assets.get(asset_id)

    def draw(self, pyxel_module: Any, asset_id: str, rect: Rect) -> bool:
        asset = self.get(asset_id)
        if asset is None:
            return False
        width = max(1, int(round(rect.width)))
        height = max(1, int(round(rect.height)))
        image = self.scaled_image(pyxel_module, asset, width, height)
        pyxel_module.blt(int(rect.x), int(rect.y), image, 0, 0, width, height, colkey=asset.colkey)
        return True

    def scaled_image(self, pyxel_module: Any, asset: UISkinAsset, width: int, height: int) -> Any:
        if width == asset.width and height == asset.height:
            return asset.image
        key = (asset.asset_id, width, height)
        cached = self._scaled_cache.get(key)
        if cached is not None:
            return cached
        rows = scale_hex_rows(asset.rows, width, height)
        image = build_ui_image(pyxel_module, rows, width, height)
        self._scaled_cache[key] = image
        return image

    @classmethod
    def empty(cls, errors: tuple[str, ...] = ()) -> UISkinLibrary:
        return cls(enabled=False, assets={}, errors=errors)


def load_ui_skin_library(
    pyxel_module: Any, manifest_name: str = "assets/ui/manifest.json"
) -> UISkinLibrary:
    try:
        root = resources.files("drift_with_me")
        manifest_path = join_traversable(root, manifest_name)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assets_raw = manifest.get("assets")
        if not isinstance(assets_raw, dict):
            raise HexAssetError("ui manifest.assets: expected object")
        assets: dict[str, UISkinAsset] = {}
        for asset_id, raw_asset in assets_raw.items():
            if not isinstance(raw_asset, dict):
                raise HexAssetError(f"{asset_id}: expected object")
            source_file = raw_asset.get("source_file")
            if not isinstance(source_file, str):
                raise HexAssetError(f"{asset_id}.source_file: expected string")
            size = raw_asset.get("sprite_size")
            if not isinstance(size, list | tuple) or len(size) != 2:
                raise HexAssetError(f"{asset_id}.sprite_size: expected pair")
            width, height = int(size[0]), int(size[1])
            colkey = int(str(raw_asset.get("colkey", manifest.get("colkey", "8"))), 16)
            source_path = join_traversable(manifest_path.parent, source_file)
            rows = parse_hex_rows(
                source_path.read_text(encoding="utf-8"),
                width,
                height,
                f"ui:{asset_id}",
            )
            assets[asset_id] = UISkinAsset(
                asset_id=asset_id,
                width=width,
                height=height,
                colkey=colkey,
                rows=rows,
                image=build_ui_image(pyxel_module, rows, width, height),
            )
        return UISkinLibrary(enabled=True, assets=assets)
    except Exception as exc:
        return UISkinLibrary.empty(errors=(f"{manifest_name}: {exc}",))


def build_ui_image(pyxel_module: Any, rows: tuple[str, ...], width: int, height: int) -> Any:
    image = pyxel_module.Image(width, height)
    image.set(0, 0, list(rows))
    return image


def scale_hex_rows(rows: tuple[str, ...], width: int, height: int) -> tuple[str, ...]:
    source_height = len(rows)
    source_width = len(rows[0]) if rows else 0
    if source_width <= 0 or source_height <= 0:
        raise HexAssetError("ui asset: cannot scale empty source")
    scaled: list[str] = []
    for y in range(height):
        source_y = 0 if height == 1 else round(y * (source_height - 1) / (height - 1))
        source_row = rows[source_y]
        chars = [
            source_row[0 if width == 1 else round(x * (source_width - 1) / (width - 1))]
            for x in range(width)
        ]
        scaled.append("".join(chars))
    return tuple(scaled)
