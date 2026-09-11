from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

from drift_with_me.math3d import CameraState, Vec3

SUPPORTED_SCHEMA_VERSION = 1
SUPPORTED_PALETTE_ID = "pyxel_default_16"
SUPPORTED_PROJECTION_MODE = "upright_height_billboard_v1"
SUPPORTED_FLIP_POLICY = "none"
SUPPORTED_ANIMATION = "static"
HEX_DIGITS = "0123456789ABCDEF"


class HexAssetError(ValueError):
    """An external HEX sprite source is invalid or cannot be loaded."""


@dataclass(frozen=True)
class HexFrameSource:
    frame_id: str
    path: str
    rows: tuple[str, ...]
    width: int
    height: int
    pixels: bytes
    source_hash: str


@dataclass(frozen=True)
class SpriteFrameDefinition:
    frame_id: str
    path: str
    source_hash: str | None = None


@dataclass(frozen=True)
class SpriteDefinition:
    asset_id: str
    palette_id: str
    hex_width: int
    hex_height: int
    colkey: int
    anchor_px: tuple[float, float]
    world_size: tuple[float, float]
    projection_mode: str
    flip_policy: str
    animation: str
    frames: tuple[SpriteFrameDefinition, ...]
    source_hash: str

    @property
    def default_frame_id(self) -> str:
        return self.frames[0].frame_id


@dataclass(frozen=True)
class LoadedSpriteFrame:
    frame_id: str
    image: Any
    source: HexFrameSource


@dataclass(frozen=True)
class LoadedSpriteAsset:
    definition: SpriteDefinition
    frames: dict[str, LoadedSpriteFrame]

    def frame(self, frame_id: str | None = None) -> LoadedSpriteFrame:
        selected = frame_id or self.definition.default_frame_id
        return self.frames[selected]


@dataclass(frozen=True)
class SpriteAssetLibrary:
    enabled: bool
    assets: dict[str, LoadedSpriteAsset]
    errors: tuple[str, ...] = ()

    @classmethod
    def empty(cls, enabled: bool = False, errors: tuple[str, ...] = ()) -> SpriteAssetLibrary:
        return cls(enabled=enabled, assets={}, errors=errors)

    def get(self, asset_id: str) -> LoadedSpriteAsset | None:
        return self.assets.get(asset_id)


@dataclass(frozen=True)
class SpritePlacement:
    anchor_x: float
    anchor_y: float
    depth: float
    scale: float
    blt_x: float
    blt_y: float
    left: float
    top: float
    right: float
    bottom: float

    @property
    def rect(self) -> tuple[int, int, int, int]:
        x0 = math.floor(self.left)
        y0 = math.floor(self.top)
        x1 = math.ceil(self.right)
        y1 = math.ceil(self.bottom)
        return (x0, y0, max(1, x1 - x0), max(1, y1 - y0))


def parse_hex_rows(text: str, width: int, height: int, source_label: str) -> tuple[str, ...]:
    if "\r" in text.replace("\r\n", ""):
        raise HexAssetError(f"{source_label}: lone CR line ending is not supported")
    normalized = text.replace("\r\n", "\n")
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    rows = tuple(normalized.split("\n")) if normalized else ()
    if len(rows) != height:
        raise HexAssetError(f"{source_label}: expected {height} rows, got {len(rows)}")
    for index, row in enumerate(rows, start=1):
        if len(row) != width:
            raise HexAssetError(f"{source_label}:{index}: expected {width} columns, got {len(row)}")
        for char in row:
            if char not in HEX_DIGITS:
                raise HexAssetError(f"{source_label}:{index}: invalid HEX color {char!r}")
    return rows


def hex_pixel_bytes(rows: tuple[str, ...]) -> bytes:
    return bytes(int(char, 16) for row in rows for char in row)


def source_hash_for_pixels(pixels: bytes) -> str:
    return hashlib.sha256(pixels).hexdigest()


def source_hash_for_rows(rows: tuple[str, ...]) -> str:
    return source_hash_for_pixels(hex_pixel_bytes(rows))


def load_sprite_manifest_path(pyxel_module: Any, manifest_path: Path) -> SpriteAssetLibrary:
    base_dir = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    def read_text(relative_path: str) -> str:
        path = base_dir / relative_asset_path(relative_path)
        if not path.is_file():
            raise HexAssetError(f"{relative_path}: referenced HEX file does not exist")
        return path.read_text(encoding="utf-8")

    return load_sprite_manifest(pyxel_module, manifest, read_text, enabled=True)


def load_runtime_sprite_library(
    pyxel_module: Any, raw_config: dict[str, Any]
) -> SpriteAssetLibrary:
    asset_config = raw_config.get("assets", {})
    enabled = bool(asset_config.get("sprite_rendering_enabled", False))
    if not enabled:
        return SpriteAssetLibrary.empty(enabled=False)

    manifest_name = str(asset_config.get("manifest", "assets/sprites.json"))
    try:
        root = resources.files("drift_with_me")
        manifest_path = join_traversable(root, manifest_name)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        def read_text(relative_path: str) -> str:
            return join_traversable(manifest_path.parent, relative_path).read_text(encoding="utf-8")

        return load_sprite_manifest(pyxel_module, manifest, read_text, enabled=True)
    except Exception as exc:
        return SpriteAssetLibrary.empty(enabled=True, errors=(f"{manifest_name}: {exc}",))


def load_sprite_manifest(
    pyxel_module: Any,
    manifest: dict[str, Any],
    read_text: Callable[[str], str],
    *,
    enabled: bool,
) -> SpriteAssetLibrary:
    require_dict(manifest, "manifest")
    require_int(manifest.get("schema_version"), "manifest.schema_version")
    if manifest["schema_version"] != SUPPORTED_SCHEMA_VERSION:
        raise HexAssetError("manifest.schema_version: unsupported value")
    assets_raw = manifest.get("assets")
    if not isinstance(assets_raw, list):
        raise HexAssetError("manifest.assets: expected list")

    assets: dict[str, LoadedSpriteAsset] = {}
    for index, raw_asset in enumerate(assets_raw):
        asset = load_sprite_asset(pyxel_module, raw_asset, read_text, f"manifest.assets[{index}]")
        asset_id = asset.definition.asset_id
        if asset_id in assets:
            raise HexAssetError(f"{asset_id}: duplicate asset id")
        assets[asset_id] = asset
    return SpriteAssetLibrary(enabled=enabled, assets=assets)


def load_sprite_asset(
    pyxel_module: Any,
    raw_asset: Any,
    read_text: Callable[[str], str],
    path: str,
) -> LoadedSpriteAsset:
    definition = parse_sprite_definition(raw_asset, path)
    loaded_frames: dict[str, LoadedSpriteFrame] = {}
    frame_sources: list[HexFrameSource] = []
    for frame_definition in definition.frames:
        text = read_text(frame_definition.path)
        rows = parse_hex_rows(
            text,
            definition.hex_width,
            definition.hex_height,
            f"{definition.asset_id}:{frame_definition.path}",
        )
        pixels = hex_pixel_bytes(rows)
        frame_hash = source_hash_for_pixels(pixels)
        if frame_definition.source_hash is not None and frame_definition.source_hash != frame_hash:
            raise HexAssetError(
                f"{definition.asset_id}:{frame_definition.frame_id}: source_hash mismatch"
            )
        source = HexFrameSource(
            frame_id=frame_definition.frame_id,
            path=frame_definition.path,
            rows=rows,
            width=definition.hex_width,
            height=definition.hex_height,
            pixels=pixels,
            source_hash=frame_hash,
        )
        image = build_pyxel_image(pyxel_module, source)
        loaded_frames[source.frame_id] = LoadedSpriteFrame(
            frame_id=source.frame_id,
            image=image,
            source=source,
        )
        frame_sources.append(source)

    combined_hash = source_hash_for_pixels(b"".join(source.pixels for source in frame_sources))
    if definition.source_hash != combined_hash:
        raise HexAssetError(f"{definition.asset_id}: source_hash mismatch")
    return LoadedSpriteAsset(definition=definition, frames=loaded_frames)


def parse_sprite_definition(raw_asset: Any, path: str) -> SpriteDefinition:
    require_dict(raw_asset, path)
    schema_version = require_int(raw_asset.get("schema_version"), f"{path}.schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise HexAssetError(f"{path}.schema_version: unsupported value")

    asset_id = require_nonempty_str(raw_asset.get("id"), f"{path}.id")
    palette_id = require_nonempty_str(raw_asset.get("palette_id"), f"{path}.palette_id")
    if palette_id != SUPPORTED_PALETTE_ID:
        raise HexAssetError(f"{asset_id}.palette_id: unsupported value {palette_id!r}")

    hex_width = require_int(raw_asset.get("hex_width"), f"{asset_id}.hex_width")
    hex_height = require_int(raw_asset.get("hex_height"), f"{asset_id}.hex_height")
    if hex_width <= 0 or hex_height <= 0:
        raise HexAssetError(f"{asset_id}: hex dimensions must be positive")

    colkey = require_int(raw_asset.get("colkey"), f"{asset_id}.colkey")
    if not 0 <= colkey <= 15:
        raise HexAssetError(f"{asset_id}.colkey: expected 0..15")

    anchor_px = require_float_pair(raw_asset.get("anchor_px"), f"{asset_id}.anchor_px")
    if not (0.0 <= anchor_px[0] <= hex_width and 0.0 <= anchor_px[1] <= hex_height):
        raise HexAssetError(f"{asset_id}.anchor_px: outside image boundary coordinates")

    world_size = require_float_pair(raw_asset.get("world_size"), f"{asset_id}.world_size")
    if world_size[0] <= 0.0 or world_size[1] <= 0.0:
        raise HexAssetError(f"{asset_id}.world_size: dimensions must be positive")
    if not math.isclose(
        world_size[0] / world_size[1], hex_width / hex_height, rel_tol=1e-6, abs_tol=1e-9
    ):
        raise HexAssetError(f"{asset_id}.world_size: aspect ratio must match HEX dimensions")

    projection_mode = require_nonempty_str(
        raw_asset.get("projection_mode"), f"{asset_id}.projection_mode"
    )
    if projection_mode != SUPPORTED_PROJECTION_MODE:
        raise HexAssetError(f"{asset_id}.projection_mode: unsupported value {projection_mode!r}")

    flip_policy = require_nonempty_str(raw_asset.get("flip_policy"), f"{asset_id}.flip_policy")
    if flip_policy != SUPPORTED_FLIP_POLICY:
        raise HexAssetError(f"{asset_id}.flip_policy: unsupported value {flip_policy!r}")

    animation = require_nonempty_str(raw_asset.get("animation"), f"{asset_id}.animation")
    if animation != SUPPORTED_ANIMATION:
        raise HexAssetError(f"{asset_id}.animation: unsupported value {animation!r}")

    frames_raw = raw_asset.get("frames")
    if not isinstance(frames_raw, list) or not frames_raw:
        raise HexAssetError(f"{asset_id}.frames: expected non-empty list")
    if animation == SUPPORTED_ANIMATION and len(frames_raw) != 1:
        raise HexAssetError(f"{asset_id}.frames: static assets must have exactly one frame")

    frames: list[SpriteFrameDefinition] = []
    seen_frame_ids: set[str] = set()
    for index, frame_raw in enumerate(frames_raw):
        require_dict(frame_raw, f"{asset_id}.frames[{index}]")
        frame_id = require_nonempty_str(frame_raw.get("id"), f"{asset_id}.frames[{index}].id")
        if frame_id in seen_frame_ids:
            raise HexAssetError(f"{asset_id}.{frame_id}: duplicate frame id")
        seen_frame_ids.add(frame_id)
        frame_path = str(
            relative_asset_path(
                require_nonempty_str(frame_raw.get("path"), f"{asset_id}.frames[{index}].path")
            )
        )
        frame_hash = frame_raw.get("source_hash")
        if frame_hash is not None:
            frame_hash = require_sha256(frame_hash, f"{asset_id}.frames[{index}].source_hash")
        frames.append(
            SpriteFrameDefinition(
                frame_id=frame_id,
                path=frame_path,
                source_hash=frame_hash,
            )
        )

    source_hash = require_sha256(raw_asset.get("source_hash"), f"{asset_id}.source_hash")
    return SpriteDefinition(
        asset_id=asset_id,
        palette_id=palette_id,
        hex_width=hex_width,
        hex_height=hex_height,
        colkey=colkey,
        anchor_px=anchor_px,
        world_size=world_size,
        projection_mode=projection_mode,
        flip_policy=flip_policy,
        animation=animation,
        frames=tuple(frames),
        source_hash=source_hash,
    )


def build_pyxel_image(pyxel_module: Any, source: HexFrameSource) -> Any:
    image = pyxel_module.Image(source.width, source.height)
    image.set(0, 0, list(source.rows))
    for y, row in enumerate(source.rows):
        for x, char in enumerate(row):
            actual = image.pget(x, y)
            expected = int(char, 16)
            if actual != expected:
                raise HexAssetError(
                    f"{source.path}: pixel mismatch at ({x},{y}); expected {expected}, got {actual}"
                )
    return image


def placement_for_upright_height_billboard(
    camera: CameraState,
    definition: SpriteDefinition,
    anchor: Vec3,
) -> SpritePlacement | None:
    if definition.projection_mode != SUPPORTED_PROJECTION_MODE:
        return None
    root = camera.project(anchor)
    top = camera.project(Vec3(anchor.x, anchor.y + definition.world_size[1], anchor.z))
    if root is None or top is None:
        return None
    height_px = abs(top.y - root.y)
    scale = height_px / definition.hex_height
    if not math.isfinite(scale) or scale <= 0.0:
        return None

    source_center_x = definition.hex_width / 2.0
    source_center_y = definition.hex_height / 2.0
    anchor_x, anchor_y = definition.anchor_px
    left = root.x - anchor_x * scale
    top_y = root.y - anchor_y * scale
    right = left + definition.hex_width * scale
    bottom = top_y + definition.hex_height * scale
    blt_x = root.x - source_center_x - scale * (anchor_x - source_center_x)
    blt_y = root.y - source_center_y - scale * (anchor_y - source_center_y)
    return SpritePlacement(
        anchor_x=root.x,
        anchor_y=root.y,
        depth=root.depth,
        scale=scale,
        blt_x=blt_x,
        blt_y=blt_y,
        left=left,
        top=top_y,
        right=right,
        bottom=bottom,
    )


def draw_scaled_sprite(
    pyxel_module: Any,
    image: Any,
    definition: SpriteDefinition,
    placement: SpritePlacement,
) -> None:
    pyxel_module.blt(
        placement.blt_x,
        placement.blt_y,
        image,
        0,
        0,
        definition.hex_width,
        definition.hex_height,
        colkey=definition.colkey,
        scale=placement.scale,
    )


def relative_asset_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HexAssetError(f"{value}: expected normalized relative path")
    return path


def join_traversable(root: Any, relative_path: str) -> Any:
    current = root
    for part in relative_asset_path(relative_path).parts:
        current = current.joinpath(part)
    return current


def require_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HexAssetError(f"{path}: expected object")
    return value


def require_nonempty_str(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise HexAssetError(f"{path}: expected non-empty string")
    return value


def require_int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise HexAssetError(f"{path}: expected integer")
    return value


def require_float_pair(value: Any, path: str) -> tuple[float, float]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise HexAssetError(f"{path}: expected pair")
    first, second = value
    if (
        not isinstance(first, int | float)
        or isinstance(first, bool)
        or not math.isfinite(first)
        or not isinstance(second, int | float)
        or isinstance(second, bool)
        or not math.isfinite(second)
    ):
        raise HexAssetError(f"{path}: expected finite numeric pair")
    return (float(first), float(second))


def require_sha256(value: Any, path: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise HexAssetError(f"{path}: expected SHA-256 hex string")
    if any(char not in "0123456789abcdef" for char in value):
        raise HexAssetError(f"{path}: expected lowercase SHA-256 hex string")
    return value
