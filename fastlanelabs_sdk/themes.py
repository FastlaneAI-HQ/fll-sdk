"""Versioned, data-only tenant theme contract. Themes cannot execute code."""
from __future__ import annotations

import re
from typing import Any

THEME_API_VERSION = 1
SHADES = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)
TOKEN_NAMES = {"surface", "on-primary", "font-sans", "font-mono", "radius"} | {
    f"{palette}-{shade}" for palette in ("ink", "accent") for shade in SHADES
}
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_FONT = re.compile(r"[a-zA-Z0-9 ,'-]{1,200}\Z")


class ThemeError(ValueError):
    pass


def validate_theme(value: Any) -> dict:
    """Return a normalized manifest or reject unsupported/unsafe values.

    Every theme supplies all tokens. Partial inheritance is deliberately not
    supported: installing a theme must never depend on the previous theme.
    Layout slots and application components belong to the platform; themes
    select supported values and do not replace authentication or app logic.
    """
    if not isinstance(value, dict) or set(value) != {
        "api_version", "id", "version", "label", "tokens", "layout"
    }:
        raise ThemeError("Theme must contain only api_version, id, version, label, tokens and layout")
    if type(value["api_version"]) is not int or value["api_version"] != THEME_API_VERSION:
        raise ThemeError("Unsupported theme API version")
    if not isinstance(value["id"], str) or not _ID.fullmatch(value["id"]):
        raise ThemeError("Invalid theme id")
    if not isinstance(value["version"], str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value["version"]):
        raise ThemeError("Theme version must be major.minor.patch")
    if not isinstance(value["label"], str) or not 1 <= len(value["label"]) <= 80:
        raise ThemeError("Theme label must be 1–80 characters")
    tokens = value["tokens"]
    if not isinstance(tokens, dict) or set(tokens) != TOKEN_NAMES:
        raise ThemeError("Theme must supply exactly the supported tokens")
    for name, content in tokens.items():
        if not isinstance(content, str):
            raise ThemeError(f"Invalid token {name}")
        if name.startswith("font-"):
            valid = _FONT.fullmatch(content)
        elif name == "radius":
            valid = re.fullmatch(r"(?:0|[0-9]|1[0-6])px", content)
        else:
            valid = _COLOR.fullmatch(content)
        if not valid:
            raise ThemeError(f"Invalid token {name}")
    # Shared text and primary controls must remain readable in every theme.
    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    for foreground, background in (("ink-900", "surface"), ("on-primary", "accent-600")):
        values = sorted((luminance(tokens[foreground]), luminance(tokens[background])))
        if (values[1] + 0.05) / (values[0] + 0.05) < 4.5:
            raise ThemeError(f"{foreground} on {background} must meet 4.5:1 contrast")
    layout = value["layout"]
    if not isinstance(layout, dict) or set(layout) != {"density", "navigation"}:
        raise ThemeError("Layout must supply density and navigation")
    if layout["density"] not in ("comfortable", "compact") or layout["navigation"] != "rail":
        raise ThemeError("Unsupported layout option")
    return dict(value, tokens=dict(tokens), layout=dict(layout))
