from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from importlib import resources
from typing import Any

from drift_with_me.config import RuntimeConfig
from drift_with_me.pixel_font import draw_pixel_text, pixel_text_size


@dataclass(frozen=True)
class FontStyle:
    name: str
    font: Any | None
    size_px: int
    pixel_scale: int


class TextResources:
    def __init__(self, raw: dict[str, Any], locale: str) -> None:
        self.locale = locale
        self.locales = raw["locales"]
        self.display_token_mapping = raw.get("display_token_mapping", {})
        self.raw_text_mapping = raw.get("raw_text_mapping", {})

    @classmethod
    def load(cls, locale: str) -> TextResources:
        data = (
            resources.files("drift_with_me")
            .joinpath("assets/i18n/ui_text.json")
            .read_text(encoding="utf-8")
        )
        raw = json.loads(data)
        selected = locale if locale in raw["locales"] else raw["default_locale"]
        return cls(raw, selected)

    def text(self, key: str) -> str:
        values = self.locales.get(self.locale, {})
        fallback = self.locales.get("en", {})
        return str(values.get(key, fallback.get(key, key)))

    def token(self, token: str) -> str:
        key = self.display_token_mapping.get(token, token)
        return self.text(key)

    def raw_text(self, text: str) -> str:
        key = self.raw_text_mapping.get(text.upper())
        if key is None:
            return text
        return self.text(key)

    def reason(self, reason: str) -> str:
        return self.text(f"reason.{reason}") if reason else ""


class UITextRenderer:
    def __init__(self, resources_: TextResources, styles: dict[str, FontStyle]) -> None:
        self.resources = resources_
        self.styles = styles

    @property
    def font_loaded(self) -> bool:
        return any(style.font is not None for style in self.styles.values())

    def text_width(self, text: str, style_name: str = "label") -> int:
        style = self.styles[style_name]
        if style.font is not None:
            return int(style.font.text_width(text))
        return pixel_text_size(text, style.pixel_scale)[0]

    def text_height(self, style_name: str = "label") -> int:
        style = self.styles[style_name]
        if style.font is not None:
            return style.size_px
        return pixel_text_size("A", style.pixel_scale)[1]

    def draw(self, pyxel: Any, x: int, y: int, text: str, color: int, style_name: str) -> None:
        style = self.styles[style_name]
        if style.font is not None:
            pyxel.text(x, y, text, color, style.font)
            return
        draw_pixel_text(pyxel, x, y, text.upper(), color, scale=style.pixel_scale)

    def draw_centered(
        self,
        pyxel: Any,
        center_x: int,
        y: int,
        text: str,
        color: int,
        style_name: str,
    ) -> None:
        x = center_x - self.text_width(text, style_name) // 2
        self.draw(pyxel, x, y, text, color, style_name)

    def fit_text(self, text: str, max_width: int, style_name: str) -> str:
        if self.text_width(text, style_name) <= max_width:
            return text
        suffix = "..."
        while text and self.text_width(text + suffix, style_name) > max_width:
            text = text[:-1]
        return text + suffix if text else suffix


def load_ui_text_renderer(pyxel: Any, runtime: RuntimeConfig) -> UITextRenderer:
    ui_config = runtime.raw.get("ui", {})
    locale = str(ui_config.get("locale", "en"))
    text_resources = TextResources.load(locale)
    font_config = ui_config.get("font", {})
    profile_name = runtime.profile.name
    style_sizes = {
        "label": int(font_config.get("label_px", {}).get(profile_name, 16)),
        "body": int(font_config.get("body_px", {}).get(profile_name, 16)),
        "title": int(font_config.get("title_px", {}).get(profile_name, 18)),
        "hint": int(font_config.get("hint_px", {}).get(profile_name, 12)),
        "button": int(font_config.get("button_px", {}).get(profile_name, 16)),
        "resource": int(font_config.get("resource_px", {}).get(profile_name, 16)),
        "tooltip": int(font_config.get("tooltip_px", {}).get(profile_name, 16)),
        "numeric": int(font_config.get("numeric_px", {}).get(profile_name, 14)),
        "auxiliary": int(font_config.get("auxiliary_px", {}).get(profile_name, 12)),
    }
    font_path = str(font_config.get("path", ""))
    styles: dict[str, FontStyle] = {}
    for style_name, size_px in style_sizes.items():
        styles[style_name] = FontStyle(
            name=style_name,
            font=_load_font(pyxel, font_path, size_px),
            size_px=size_px,
            pixel_scale=max(1, round(size_px / 8)),
        )
    return UITextRenderer(text_resources, styles)


def _load_font(pyxel: Any, font_path: str, size_px: int) -> Any | None:
    if not font_path or not hasattr(pyxel, "Font"):
        return None
    try:
        traversable = resources.files("drift_with_me").joinpath(font_path)
        with resources.as_file(traversable) as path:
            return pyxel.Font(str(path), size_px)
    except Exception as exc:
        print(f"ui_font_error: {type(exc).__name__}: {exc}")
        return None


def normalize_ui_text(text: str) -> str:
    return unicodedata.normalize("NFC", text)
