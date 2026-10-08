"""Versioned, data-only theme manifests; reviewed JSX templates are separate bundles.

API v1 is frozen: `_validate_v1` below is the original validator and its output
is hashed into published releases, so it must never change. API v2 is a new
manifest shape (token layers plus layout variants) driven by `theme_registry`.
`validate_theme` accepts both; v1 manifests are only ever upgraded at read time.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

from . import theme_registry as registry

THEME_API_VERSION = 1
THEME_API_VERSION_V2 = 2
theme_contracts = (1, 2)
REGISTRY_REVISION = registry.REGISTRY_REVISION
SHADES = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)
TOKEN_NAMES = {"surface", "on-primary", "font-sans", "font-mono", "radius"} | {
    f"{palette}-{shade}" for palette in ("ink", "accent") for shade in SHADES
}
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_FONT = re.compile(r"[a-zA-Z0-9 ,'-]{1,200}\Z")


class ThemeError(ValueError):
    """`errors` lists every problem as {path, message}; `path` is the first one's."""

    def __init__(self, message: str = "", path: Optional[str] = None, errors: Optional[List[dict]] = None):
        super().__init__(message)
        self.path = path
        self.errors = errors if errors is not None else [{"path": path or "theme", "message": message}]


def _validate_v1(value: Any) -> dict:
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
    if layout["density"] not in ("comfortable", "compact") or layout["navigation"] not in ("rail", "sidebar"):
        raise ThemeError("Unsupported layout option")
    return dict(value, tokens=dict(tokens), layout=dict(layout))


# --- API v2 ----------------------------------------------------------------

_LENGTH = re.compile(r"(?:0|[0-9]+(?:\.[0-9]{1,2})?(?:px|rem))\Z")
_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]{1,3})?\Z")
_WEIGHT = re.compile(r"[1-9]00\Z")
_TRACKING = re.compile(r"(?:0|-?[0-9]{1,2}(?:\.[0-9]{1,3})?em)\Z")
_DURATION = re.compile(r"[0-9]{1,4}(?:\.[0-9]{1,2})?ms\Z")
_V1_RADIUS = re.compile(r"(?:0|[0-9]|1[0-6])px\Z")
_EASE = re.compile(r"(?:linear|ease|ease-in|ease-out|ease-in-out)\Z")
# Spaces are literal ` ` in both grammars below, never `\s`: that matches a
# newline, a no-break space and U+2028, which are harmless when a value is set
# with `style.setProperty` and an injection the day one is written into a
# stylesheet.
_BEZIER = re.compile(r"cubic-bezier\( *([0-9.]+) *, *([0-9.]+) *, *([0-9.]+) *, *([0-9.]+) *\)\Z")
_OFFSET = r"(-?(?:0|[0-9]+(?:\.[0-9]+)?)(?:px)?)"
_SHADOW_LAYER = re.compile(
    rf"{_OFFSET} {_OFFSET} {_OFFSET}(?: {_OFFSET})? "
    r"(#[0-9a-fA-F]{6}|rgba\( *([0-9]{1,3}) *, *([0-9]{1,3}) *, *([0-9]{1,3}) *, *([0-9]*\.?[0-9]+) *\))\Z")
# No shadow or easing needs more than this. Checked before any pattern runs:
# the old comma-splitting lookahead was quadratic, so 60 000 commas (a 2.5 KB
# pack) kept the validator busy for twelve seconds.
_MAX_EXPRESSION = 200


def _split_layers(text: str) -> List[str]:
    """Shadow layers: the commas that are not inside parentheses. One pass."""
    layers: List[str] = []
    depth = start = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            layers.append(text[start:i])
            start = i + 1
            if len(layers) > 3:
                break
    layers.append(text[start:])
    return layers
_TOP_SCALARS = ("api_version", "registry_revision", "id", "version", "label", "color_scheme")


def _is_int(value: Any) -> bool:
    return type(value) is int


def _length_px(text: str) -> float:
    if text == "0":
        return 0.0
    return float(text[:-3]) * 16 if text.endswith("rem") else float(text[:-2])


def _shadow_error(text: str) -> Optional[str]:
    if text == "none":
        return None
    if len(text) > _MAX_EXPRESSION:
        return "must be at most {0} characters".format(_MAX_EXPRESSION)
    layers = _split_layers(text)
    if not 1 <= len(layers) <= 3:
        return "must be none or 1-3 shadow layers"
    for layer in layers:
        match = _SHADOW_LAYER.fullmatch(layer.strip(" "))
        if not match:
            return "must be none or layers of `x y blur [spread] color`, e.g. 0 1px 3px rgba(0,0,0,0.1)"
        x, y, blur, spread = match.group(1), match.group(2), match.group(3), match.group(4)
        for part in (x, y, blur, spread):
            if part is not None and abs(float(part.replace("px", ""))) > 80:
                return "shadow offsets, blur and spread must be at most 80px"
        if float(blur.replace("px", "")) < 0:
            return "shadow blur cannot be negative"
        if match.group(6) is not None and (any(int(match.group(i)) > 255 for i in (6, 7, 8)) or float(match.group(9)) > 1):
            return "rgba channels must be 0-255 and alpha 0-1"
    return None


def _ease_error(text: str) -> Optional[str]:
    if _EASE.fullmatch(text):
        return None
    if len(text) > _MAX_EXPRESSION:
        return "must be at most {0} characters".format(_MAX_EXPRESSION)
    match = _BEZIER.fullmatch(text)
    try:
        if match and all(0 <= float(part) <= 1 for part in match.groups()):
            return None
    except ValueError:
        pass
    return "must be linear, ease, ease-in, ease-out, ease-in-out or cubic-bezier(a,b,c,d) with a-d in 0-1"


def _literal_error(token: "registry.Token", text: str) -> Optional[str]:
    """Why `text` is not a valid literal for this token's type, or None."""
    kind = token.type
    if token.v1:
        if kind == "color":
            return None if _COLOR.fullmatch(text) else "must be a #RRGGBB color"
        if kind == "font-stack":
            return None if _FONT.fullmatch(text) else "must be a font stack of letters, digits, spaces, commas, quotes and hyphens"
        return None if _V1_RADIUS.fullmatch(text) else "must be a whole number of pixels from 0px to 16px"
    if kind == "color":
        return None if _COLOR.fullmatch(text) else "must be a #RRGGBB color or a {token} reference"
    if kind in ("length", "font-size"):
        return None if _LENGTH.fullmatch(text) else "must be 0 or a number with px or rem (at most 2 decimals)"
    if kind == "number":
        return None if _NUMBER.fullmatch(text) else "must be a decimal number"
    if kind == "weight":
        return None if _WEIGHT.fullmatch(text) else "must be a weight from 100 to 900 in steps of 100"
    if kind == "font-stack":
        return None if _FONT.fullmatch(text) else "must be a font stack of letters, digits, spaces, commas, quotes and hyphens"
    if kind == "shadow":
        return _shadow_error(text)
    if kind == "ease":
        return _ease_error(text)
    if kind == "duration":
        return None if _DURATION.fullmatch(text) else "must be a number of milliseconds, e.g. 150ms"
    if kind == "tracking":
        return None if _TRACKING.fullmatch(text) else "must be 0 or a number of em, e.g. -0.01em"
    if kind == "enum":
        return None if text in token.options else "must be one of " + ", ".join(token.options)
    return "unsupported token type"


def _numeric(token: "registry.Token", text: str) -> Optional[float]:
    """The value a min/max range applies to, in px, ms, em or the plain number."""
    if token.type in ("length", "font-size"):
        return _length_px(text)
    if token.type == "number":
        return float(text)
    if token.type == "tracking":
        return 0.0 if text == "0" else float(text[:-2])
    if token.type == "duration":
        return float(text[:-2])
    return None


def _range_error(token: "registry.Token", text: str) -> Optional[str]:
    value = _numeric(token, text)
    if value is None or (token.min is None and token.max is None) or token.v1:
        return None
    unit = {"length": "px", "font-size": "px", "tracking": "em", "duration": "ms"}.get(token.type, "")
    if (token.min is not None and value < token.min) or (token.max is not None and value > token.max):
        low = "" if token.min is None else f"{token.min:g}{unit}"
        high = "" if token.max is None else f"{token.max:g}{unit}"
        return f"must be between {low} and {high}"
    return None


class _Problems:
    def __init__(self):
        self.errors: List[dict] = []
        self.warnings: List[dict] = []
        self.contrast: List[dict] = []

    def error(self, path: str, message: str):
        self.errors.append({"path": path, "message": message})

    def warn(self, path: str, message: str):
        self.warnings.append({"path": path, "message": message})

    def as_dict(self) -> dict:
        return {"errors": self.errors, "warnings": self.warnings, "contrast": self.contrast}


def _luminance(color: str) -> float:
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast_ratio(first: str, second: str) -> float:
    values = sorted((_luminance(first), _luminance(second)))
    return (values[1] + 0.05) / (values[0] + 0.05)


_LAYER_OF = {"primitives": "primitive", "semantic": "semantic", "components": "component"}
_SLOT_KINDS_WITH_REFS = ("color", "length", "font-size", "number", "weight", "font-stack", "shadow", "ease", "duration", "tracking")


def _is_v2(value: Any) -> bool:
    return isinstance(value, dict) and type(value.get("api_version")) is int and value["api_version"] == THEME_API_VERSION_V2


def _check_header(value: dict, problems: _Problems) -> Tuple[int, str]:
    """Top-level fields; returns the registry revision to check tokens against and the color scheme."""
    keys = set(value) - {"modes"}
    if keys != set(registry.TOP_LEVEL_KEYS):
        problems.error("", "Theme must contain only " + ", ".join(registry.TOP_LEVEL_KEYS))
    revision = value.get("registry_revision")
    if not _is_int(revision) or revision < 1:
        problems.error("registry_revision", "registry_revision must be a positive integer")
        revision = registry.REGISTRY_REVISION
    elif revision > registry.REGISTRY_REVISION:
        problems.error("registry_revision",
                       f"Theme targets registry revision {revision}; this workspace supports {registry.REGISTRY_REVISION}. Update the workspace")
        revision = registry.REGISTRY_REVISION
    if "id" in value and (not isinstance(value["id"], str) or not _ID.fullmatch(value["id"])):
        problems.error("id", "Invalid theme id")
    if "version" in value and (not isinstance(value["version"], str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value["version"])):
        problems.error("version", "Theme version must be major.minor.patch")
    if "label" in value and (not isinstance(value["label"], str) or not 1 <= len(value["label"]) <= 80):
        problems.error("label", "Theme label must be 1–80 characters")
    scheme = "light"
    if revision <= 1:
        # Registry revision 1: dark mode is reserved. These rules never change.
        if "modes" in value:
            problems.error("modes", "modes is reserved for a later registry revision and must be absent")
        if "color_scheme" in value and value["color_scheme"] != "light":
            problems.error("color_scheme", "color_scheme must be light; dark mode is reserved for a later registry revision")
    elif "color_scheme" in value:
        allowed = registry.color_schemes(revision)
        if not isinstance(value["color_scheme"], str) or value["color_scheme"] not in allowed:
            problems.error("color_scheme", "color_scheme must be " + ", ".join(allowed[:-1]) + " or " + allowed[-1])
        else:
            scheme = value["color_scheme"]
    return revision, scheme


def _check_modes(value: dict, revision: int, scheme: str, problems: _Problems) -> Optional[dict]:
    """Structure of `modes` (registry revision 2 and later); returns modes.dark when it is well formed."""
    if revision < 2:
        return None
    if scheme != "auto":
        if "modes" in value:
            problems.error("modes", "modes is only allowed with color_scheme auto")
        return None
    if "modes" not in value:
        problems.error("modes", "color_scheme auto requires modes.dark")
        return None
    modes = value["modes"]
    if not isinstance(modes, dict) or set(modes) != set(registry.MODE_NAMES):
        problems.error("modes", "modes must contain exactly " + ", ".join(registry.MODE_NAMES))
        return None
    dark = modes["dark"]
    if not isinstance(dark, dict) or set(dark) != set(registry.LAYER_KEYS):
        problems.error("modes.dark", "modes.dark must contain exactly primitives, semantic and components")
        return None
    known = registry.for_revision(revision)
    start = len(problems.errors)
    for layer_key, layer in _LAYER_OF.items():
        values, path = dark[layer_key], f"modes.dark.{layer_key}"
        if not isinstance(values, dict):
            problems.error(path, f"{layer_key} must be an object")
            continue
        for name, content in values.items():
            token = known.get(name)
            if token is None:
                problems.error(f"{path}.{name}", f"Unknown token {name}")
            elif token.layer != layer:
                problems.error(f"{path}.{name}", f"{name} belongs in {next(k for k, v in _LAYER_OF.items() if v == token.layer)}")
            elif name not in registry.MODE_TOKENS:
                problems.error(f"{path}.{name}", f"{name} cannot vary by mode; only colors, shadows, scrim opacities and bar tones can")
            elif not isinstance(content, str):
                problems.error(f"{path}.{name}", "Token values must be strings")
    if len(problems.errors) > start:
        return None
    for name in registry.DARK_REQUIRED:
        layer_key = _layer_key(known[name].layer)
        if name not in dark[layer_key]:
            problems.error(f"modes.dark.{layer_key}.{name}", f"Dark mode must set {name}; a dark palette supplies every color ramp and the surface")
    return dark if len(problems.errors) == start else None


def _check_dark_tokens(tokens: dict, dark: dict, revision: int, problems: _Problems) -> Tuple[Dict[str, str], bool]:
    """The theme's tokens with modes.dark applied, validated by the same rules as the base."""
    merged = {key: dict(tokens[key], **dark[key]) for key in registry.LAYER_KEYS}
    sub = _Problems()
    resolved, valid = _check_tokens(merged, revision, sub)
    for error in sub.errors:
        parts = error["path"].split(".", 2)
        if len(parts) == 3 and parts[0] == "tokens" and parts[2] in dark.get(parts[1], {}):
            problems.error(f"modes.dark.{parts[1]}.{parts[2]}", error["message"])
        else:
            problems.error(error["path"], "In dark mode, " + error["message"][:1].lower() + error["message"][1:])
    return resolved, valid


def _check_tokens(tokens: Any, revision: int, problems: _Problems) -> Tuple[Dict[str, str], bool]:
    """Validate every layer; returns the resolved literal of each valid token and whether all were valid."""
    known = registry.for_revision(revision)
    if not isinstance(tokens, dict) or set(tokens) != set(registry.LAYER_KEYS):
        problems.error("tokens", "Tokens must contain exactly primitives, semantic and components")
        return {}, False
    raw: Dict[str, str] = {}
    start = len(problems.errors)
    for layer_key, layer in _LAYER_OF.items():
        values = tokens[layer_key]
        path = f"tokens.{layer_key}"
        if not isinstance(values, dict):
            problems.error(path, f"{layer_key} must be an object")
            continue
        expected = {n for n, t in known.items() if t.layer == layer and not t.optional}
        if layer != "component":
            for name in sorted(expected - set(values)):
                problems.error(f"{path}.{name}", f"Missing {layer} token {name}")
        for name, content in values.items():
            token = known.get(name)
            if token is None:
                problems.error(f"{path}.{name}", f"Unknown token {name}")
            elif token.layer != layer:
                problems.error(f"{path}.{name}", f"{name} belongs in {next(k for k, v in _LAYER_OF.items() if v == token.layer)}")
            elif not isinstance(content, str):
                problems.error(f"{path}.{name}", "Token values must be strings")
            else:
                raw[name] = content
    layer_of = {name: known[name].layer for name in raw}
    literals: Dict[str, str] = {}
    refs: Dict[str, str] = {}
    for name, content in raw.items():
        token, path = known[name], f"tokens.{_layer_key(known[name].layer)}.{name}"
        if content.startswith("{"):
            match = registry.REF.fullmatch(content)
            if token.layer == "primitive" or token.v1 or token.type not in _SLOT_KINDS_WITH_REFS:
                problems.error(path, "This token must be a literal value, not a reference")
            elif not match:
                problems.error(path, "Invalid reference; use {token-name}")
            else:
                target = known.get(match.group(1))
                if target is None:
                    problems.error(path, f"Unknown token {match.group(1)} in reference")
                elif target.layer == "component":
                    problems.error(path, "References may only point to primitive or semantic tokens")
                elif target.type != token.type:
                    problems.error(path, f"{token.type} tokens cannot reference {target.type} token {target.name}")
                else:
                    refs[name] = target.name
            continue
        message = _literal_error(token, content)
        if message:
            problems.error(path, "Invalid value: " + message)
        else:
            literals[name] = content
            if revision >= 3 and token.type == "font-stack":
                for family in _unquoted_digit_families(content):
                    problems.warn(path, f"Font family {family} must be quoted ('{family}'): CSS rejects an unquoted name with a "
                                        "word that starts with a digit, and the browser then drops the whole font stack")
    # References are followed downward: depth is capped and cycles are rejected.
    resolved: Dict[str, str] = dict(literals)
    memo: Dict[str, Optional[Tuple[str, int]]] = {}

    def walk(name: str, trail: List[str]) -> Optional[Tuple[str, int]]:
        """(literal, hops) for a token, following references downward."""
        if name in memo:
            return memo[name]
        if name not in refs:
            return (literals[name], 0) if name in literals else None  # Otherwise already reported.
        if name in trail:
            memo[name] = None
            problems.error(f"tokens.{_layer_key(layer_of[name])}.{name}", "Reference cycle: " + " -> ".join(trail[trail.index(name):] + [name]))
            return None
        target = walk(refs[name], trail + [name])
        memo[name] = (target[0], target[1] + 1) if target else None
        return memo[name]

    for name in refs:
        found = walk(name, [])
        if found is None:
            continue
        if found[1] > registry.SELF_REFERENCE_DEPTH:
            problems.error(f"tokens.{_layer_key(layer_of[name])}.{name}", f"References may be at most {registry.SELF_REFERENCE_DEPTH} deep")
        else:
            resolved[name] = found[0]
    for name in list(resolved):
        message = _range_error(known[name], resolved[name])
        if message:
            problems.error(f"tokens.{_layer_key(layer_of[name])}.{name}", "Invalid value: " + message)
            del resolved[name]
    return resolved, len(problems.errors) == start


def _layer_key(layer: str) -> str:
    return {"primitive": "primitives", "semantic": "semantic", "component": "components"}[layer]


def _check_layout(layout: Any, problems: _Problems) -> None:
    spec = registry.LAYOUT_SPEC
    if not isinstance(layout, dict) or set(layout) != set(spec):
        problems.error("layout", "Layout must supply exactly " + ", ".join(spec))
        return
    for key, field in spec.items():
        if "type" in field:
            _check_layout_field(layout[key], field, f"layout.{key}", problems)
            continue
        group = layout[key]
        if not isinstance(group, dict) or set(group) != set(field):
            problems.error(f"layout.{key}", f"layout.{key} must supply exactly " + ", ".join(field))
            continue
        for name, sub in field.items():
            _check_layout_field(group[name], sub, f"layout.{key}.{name}", problems)
    if problems.errors and any(e["path"].startswith("layout") for e in problems.errors):
        return
    sidebar, navbar = layout["sidebar"], layout["navbar"]
    if navbar["position"] == "hidden" and sidebar["side"] == "hidden":
        problems.error("layout", "At least one of the sidebar and the navbar must be visible")
    if layout["scroll"] == "panel":
        for bar, name in ((sidebar, "sidebar"), (navbar, "navbar")):
            if bar["behavior"] != "fixed":
                problems.warn(f"layout.{name}.behavior",
                              f"{name} behavior has no visible effect while scroll is panel; use scroll page or fixed")
    if sidebar["style"] == "rail" and sidebar["width"] > 120:
        problems.warn("layout.sidebar.width", "A rail wider than 120px is unusual; consider the panel style")
    if sidebar["style"] == "panel" and sidebar["width"] < 160:
        problems.warn("layout.sidebar.width", "A panel narrower than 160px truncates labels")


def _check_layout_field(value: Any, field: dict, path: str, problems: _Problems) -> None:
    kind = field["type"]
    if kind in ("enum", "step"):
        if not isinstance(value, str) or value not in field["options"]:
            problems.error(path, "Must be one of " + ", ".join(field["options"]))
    elif kind == "bool":
        if type(value) is not bool:
            problems.error(path, "Must be true or false")
    elif kind == "int":
        if not _is_int(value) or not (field["min"] <= value <= field["max"] or (field.get("zero") and value == 0)):
            low = "0 or " + str(field["min"]) if field.get("zero") else str(field["min"])
            problems.error(path, f"Must be a whole number {low}-{field['max']}")


class _Effective:
    """Resolve a token to its final literal, following fallbacks for unset components."""

    def __init__(self, resolved: Dict[str, str]):
        self.resolved = resolved

    def enum(self, name: str) -> str:
        return self.resolved.get(name) or registry.INDEX[name].default

    def get(self, name: str, tone: Optional[str] = None, depth: int = 0) -> Optional[str]:
        if name in self.resolved:
            return self.resolved[name]
        token = registry.INDEX.get(name)
        if token is None or depth > 8:
            return None
        default = token.default
        if isinstance(default, dict):
            default = default[tone or self.enum(token.tone)]
        match = registry.REF.fullmatch(default)
        return self.get(match.group(1), tone, depth + 1) if match else default


def _check_contrast(resolved: Dict[str, str], layout: dict, problems: _Problems,
                    mode: Optional[str] = None, where: str = "tokens", prefix: str = "", revision: int = 1) -> None:
    """Judge every contrast pair. `mode` labels the rows of a theme that has a dark palette;
    `where` is the path root errors point at and `prefix` starts their message. With no mode
    (every light-only theme) the rows are exactly what registry revision 1 produced. A pair is judged
    only for a theme that targets the revision that introduced it (`revision`)."""
    effective = _Effective(resolved)

    def pair(key: str, fg_name: str, bg_name: str, minimum: Optional[float], level: str, tone: Optional[str] = None,
             group: str = ""):
        fg, bg = effective.get(fg_name, tone), effective.get(bg_name, tone)
        if not (fg and bg and _COLOR.fullmatch(fg) and _COLOR.fullmatch(bg)):
            return
        ratio = contrast_ratio(fg, bg)
        row = {"id": key, "fg": fg_name, "bg": bg_name, "fg_value": fg, "bg_value": bg,
               "ratio": round(ratio, 2), "min": minimum, "level": level,
               "pass": minimum is None or ratio >= minimum}
        if group:
            row["group"] = group
        if mode:
            row["mode"] = mode
        problems.contrast.append(row)
        if minimum is not None and ratio < minimum:
            message = f"{fg_name} on {bg_name} must meet {minimum:g}:1 contrast (got {ratio:.2f}:1)"
            if prefix:
                message = prefix + message
            path = f"{where}.{_layer_key(registry.INDEX[fg_name].layer)}.{fg_name}"
            if level == "error":
                problems.error(path, message)
            else:
                problems.warn(path, message)

    for item in registry.CONTRAST_PAIRS:
        if item.since <= revision and not (item.unless and item.unless in resolved):
            pair(item.id, item.fg, item.bg, item.min, item.level, group=item.group)
    bars = {"sidebar": layout["sidebar"]["side"] != "hidden", "navbar": layout["navbar"]["position"] != "hidden"}
    for bar, tone_name, bg_name in registry.NAV_BARS:
        if bars[bar]:
            pair(f"nav-item-fg-on-{bg_name}", "nav-item-fg", bg_name, 4.5, "error", effective.enum(tone_name))
    if bars["navbar"]:
        pair("navbar-fg-on-navbar-bg", "navbar-fg", "navbar-bg", 4.5, "warning", effective.enum("navbar-tone"))
    for key, fg, bg in registry.COMPONENT_CONTRAST_PAIRS:
        pair(key, fg, bg, 4.5, "warning")


def _check_dark_character(resolved: Dict[str, str], problems: _Problems, where: str, prefix: str) -> None:
    """A dark palette has light text on dark surfaces and a dark scrim. Contrast alone would accept the reverse."""
    effective = _Effective(resolved)
    text, surface, scrim = effective.get("text"), effective.get("surface"), effective.get("scrim")
    if text and surface and _COLOR.fullmatch(text) and _COLOR.fullmatch(surface) and _luminance(text) <= _luminance(surface):
        problems.error(f"{where}.semantic.text", prefix + "the text must be lighter than the surface in a dark palette")
    if scrim and surface and _COLOR.fullmatch(scrim) and _COLOR.fullmatch(surface) and _luminance(scrim) > _luminance(surface):
        problems.warn(f"{where}.semantic.scrim", prefix + "the scrim should be darker than the surface in a dark palette")


def _check_v2(value: Any) -> dict:
    problems = _Problems()
    if not isinstance(value, dict):
        problems.error("", "Theme must be an object")
        return problems.as_dict()
    revision, scheme = _check_header(value, problems)
    resolved, tokens_valid = {}, False
    if "tokens" in value:
        resolved, tokens_valid = _check_tokens(value["tokens"], revision, problems)
    else:
        problems.error("tokens", "Theme must contain tokens")
    if "layout" in value:
        _check_layout(value["layout"], problems)
    else:
        problems.error("layout", "Theme must contain layout")
    dark = _check_modes(value, revision, scheme, problems)
    dark_resolved, dark_valid = {}, False
    if dark is not None and tokens_valid:
        dark_resolved, dark_valid = _check_dark_tokens(value["tokens"], dark, revision, problems)
    if tokens_valid and not any(e["path"].startswith("layout") for e in problems.errors):
        if scheme == "light":
            _check_contrast(resolved, value["layout"], problems, revision=revision)
        elif scheme == "dark":
            _check_contrast(resolved, value["layout"], problems, mode="dark", revision=revision)
            _check_dark_character(resolved, problems, "tokens", "")
        else:
            _check_contrast(resolved, value["layout"], problems, mode="light", revision=revision)
            if dark_valid:
                _check_contrast(dark_resolved, value["layout"], problems, mode="dark", where="modes.dark",
                                prefix="In dark mode, ", revision=revision)
                _check_dark_character(dark_resolved, problems, "modes.dark", "In dark mode, ")
    return problems.as_dict()


def _first_error(problems: dict) -> ThemeError:
    first = problems["errors"][0]
    return ThemeError(first["message"], first["path"] or None, list(problems["errors"]))


def validate_theme(value: Any) -> dict:
    """Return a copy of a valid v1 or v2 manifest; raise ThemeError otherwise.

    Nothing is ever defaulted or rewritten: the output is the input, so a hash of
    it is stable across SDK releases. v1 follows its frozen rules; v2 rules are
    fixed per (api_version, registry_revision).
    """
    if _is_v2(value):
        problems = _check_v2(value)
        if problems["errors"]:
            raise _first_error(problems)
        return copy.deepcopy(value)
    if isinstance(value, dict) and "registry_revision" in value and value.get("api_version") != THEME_API_VERSION:
        raise ThemeError("Unsupported theme API version", "api_version")
    return _validate_v1(value)


def check_theme(value: Any) -> dict:
    """Never raises: {errors, warnings, contrast}, each error/warning {path, message}."""
    if _is_v2(value):
        return _check_v2(value)
    try:
        _validate_v1(value)
    except (ThemeError, TypeError) as exc:
        return {"errors": [{"path": "theme", "message": str(exc)}], "warnings": [], "contrast": []}
    return {"errors": [], "warnings": [], "contrast": []}


def contrast_report(theme: Any) -> List[dict]:
    """Every contrast pair judged for a v2 theme, with ratio, minimum, level and pass.

    A theme with a dark palette also reports it: its rows carry `mode` ("light" and "dark");
    a light-only theme's rows are what registry revision 1 produced, without the key.
    Returns an empty list when the theme has structural errors, since colors
    cannot be resolved; use `check_theme` for those.
    """
    return check_theme(theme)["contrast"] if _is_v2(theme) else []


def default_theme_v2(theme_id: str = "fastlane", version: str = "2.0.0", label: str = "Fastlane",
                     scheme: str = "light", registry_revision: Optional[int] = None) -> dict:
    """The registry defaults as a complete v2 manifest (what a fresh v1 `fastlane` upgrades to).

    `scheme` "auto" adds the derived default dark palette as `modes.dark`; "dark" makes the
    theme's own tokens that palette. Both need registry revision 2 (the default).
    `registry_revision=1` reproduces what SDK 1.3 produced and `2` what SDK 1.4 produced; revision 3 (SDK 1.5)
    starts from the accessible palette (registry.REVISION_DEFAULTS) and sets the four optional roles.
    """
    revision = REGISTRY_REVISION if registry_revision is None else registry_revision
    theme = {
        "api_version": THEME_API_VERSION_V2, "registry_revision": revision,
        "id": theme_id, "version": version, "label": label, "color_scheme": "light",
        "tokens": {
            "primitives": {t.name: registry.default_for(t, revision) for t in registry.PRIMITIVES if t.since <= revision},
            "semantic": {t.name: registry.default_for(t, revision) for t in registry.SEMANTIC if t.since <= revision},
            "components": {},
        },
        "layout": registry.default_layout("rail"),
    }
    if scheme != "light":
        if revision < 2 or scheme not in registry.COLOR_SCHEMES:
            raise ThemeError("Dark mode needs registry revision 2 and a color scheme of light, dark or auto", "color_scheme")
        dark = derive_dark(theme)
        theme["color_scheme"] = scheme
        if scheme == "auto":
            theme["modes"] = {"dark": dark}
        else:
            for key in registry.LAYER_KEYS:
                theme["tokens"][key].update(dark[key])
    return theme


webfonts = registry.webfonts


def _unquoted_digit_families(stack: str) -> List[str]:
    """The families of a font stack that are not quoted but have a word starting with a digit (invalid CSS)."""
    found = []
    for part in stack.split(","):
        family = part.strip()
        if family and not family.startswith("'") and any(word[:1].isdigit() for word in family.split(" ")):
            found.append(family)
    return found


def _first_family(stack: str) -> str:
    return stack.split(",")[0].strip().strip("'\"")


# --- Resolution --------------------------------------------------------------

def _triplet(color: str) -> str:
    return " ".join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))


def _var_value(token: "registry.Token", literal: str, raw: str) -> str:
    """The CSS value a token is applied as (colors become `r g b` channels)."""
    if token.type == "color":
        return _triplet(literal)
    if token.type == "font-size" and token.layer == "component":
        match = registry.REF.fullmatch(raw)
        if match:
            return f"var(--fl-fs-{match.group(1)[len('size-'):]})"
        return f"calc({literal} * var(--fl-size-scale, 1))"
    return literal


# --- Dark palette derivation ---------------------------------------------------------------------
#
# A dark palette is derived, not a naive inversion. Each color ramp is reversed (ink-50, the page,
# becomes the darkest step and ink-950 the lightest), so every existing `bg-ink-50`, `text-ink-900`,
# `border-ink-200` or `bg-accent-600` class lands on a coherent dark value without a new class.
# The pieces that a reversal would get wrong are then set by hand: the surface sits between the
# page and ink-100, `on-primary` is whichever of the palette's two ends reads on the primary colour,
# the scrim stays dark, shadows get stronger, the active nav item and the user's message become quiet
# raised fills instead of the lightest colour on the page, and both bars use the `light` tone (which, on reversed
# ramps, is the dark-looking one). Literal colours a theme sets outside its ramps are mapped to the
# ramp step they equal, or have their lightness reflected; a bar painted by hand falls back to the
# surface (a derived palette cannot know which dark colour the brand wants there). The same arithmetic, step for step, is
# frontend/theme-resolve.ts `deriveDark`; tests/golden checks they agree.

_RGBA = re.compile(r"rgba\( *([0-9]{1,3}) *, *([0-9]{1,3}) *, *([0-9]{1,3}) *, *([0-9]*\.?[0-9]+) *\)")
_SHADOW_BOOST = 2.5
_SHADOW_ALPHA_CAP = 0.85


def _channels(color: str) -> Tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _hex(r: int, g: int, b: int) -> str:
    return "#%02x%02x%02x" % (r, g, b)


def _midpoint(first: str, second: str) -> str:
    return _hex(*((a + b + 1) // 2 for a, b in zip(_channels(first), _channels(second))))


def _reflect_lightness(color: str) -> str:
    """The same hue and saturation with lightness 1 - L (HSL)."""
    r, g, b = (c / 255 for c in _channels(color))
    high, low = max(r, g, b), min(r, g, b)
    lightness = (high + low) / 2
    if high == low:
        hue = saturation = 0.0
    else:
        delta = high - low
        saturation = delta / (2 - high - low) if lightness > 0.5 else delta / (high + low)
        if high == r:
            hue = ((g - b) / delta + (6 if g < b else 0)) / 6
        elif high == g:
            hue = ((b - r) / delta + 2) / 6
        else:
            hue = ((r - g) / delta + 4) / 6
    lightness = 1 - lightness

    def channel(p: float, q: float, t: float) -> float:
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    if saturation == 0:
        values = (lightness, lightness, lightness)
    else:
        q = lightness * (1 + saturation) if lightness < 0.5 else lightness + saturation - lightness * saturation
        p = 2 * lightness - q
        values = (channel(p, q, hue + 1 / 3), channel(p, q, hue), channel(p, q, hue - 1 / 3))
    return _hex(*(int(v * 255 + 0.5) for v in values))


def _percent(hundredths: int) -> str:
    whole, part = divmod(hundredths, 100)
    return str(whole) if not part else f"{whole}.{part:02d}".rstrip("0")


def _boost_shadow(text: str) -> str:
    """Stronger, black shadows: a shadow that reads on white vanishes on a dark surface."""
    def boost(match):
        hundredths = min(int(float(match.group(4)) * _SHADOW_BOOST * 100 + 0.5), int(_SHADOW_ALPHA_CAP * 100))
        return f"rgba(0,0,0,{_percent(hundredths)})"
    return _RGBA.sub(boost, text)


def _move_until(color: str, target: str, against: str, minimum: float) -> str:
    """`color` moved toward `target` in tenths until it reaches `minimum`:1 against `against` (or is `target`)."""
    if contrast_ratio(color, against) >= minimum:
        return color
    start, end = _channels(color), _channels(target)
    for tenth in range(1, 11):
        moved = _hex(*((a * (10 - tenth) + b * tenth + 5) // 10 for a, b in zip(start, end)))
        if contrast_ratio(moved, against) >= minimum:
            return moved
    return target


def _lighten_until(color: str, backgrounds: List[str], minimum: float) -> str:
    """`color` moved toward white in whole percents until it reaches `minimum`:1 against every background."""
    if all(contrast_ratio(color, background) >= minimum for background in backgrounds):
        return color
    start = _channels(color)
    for percent in range(1, 101):
        moved = _hex(*((a * (100 - percent) + 255 * percent + 50) // 100 for a in start))
        if all(contrast_ratio(moved, background) >= minimum for background in backgrounds):
            return moved
    return "#ffffff"


# The ink steps the interface paints text and icons with (text-ink-400 ... 700) and borders (ink-300), and the
# least contrast each may have. Reversing a ramp leaves them at 2.5 to 3.6:1 on a dark surface.
DARK_TEXT_STEPS = ((300, 3.0), (400, 4.5), (500, 4.5), (600, 4.5), (700, 4.5))


def solve_dark_text(primitives: Dict[str, str], light_ratios: Dict[int, float], surface: str, page: str) -> None:
    """Re-solve the dark ramp's text steps against the dark surface and page, in place.

    Each step in DARK_TEXT_STEPS gets at least the contrast the light palette gives it on its own surface (so the
    three-step hierarchy survives) and never less than its minimum; a step that already reads is left alone.
    Registry revision 3 and later; registry 1 and 2 derive by reversal alone.
    """
    for shade, minimum in DARK_TEXT_STEPS:
        name = f"ink-{shade}"
        primitives[name] = _lighten_until(primitives[name], [surface, page], max(minimum, light_ratios.get(shade, minimum)))


def lift_accent_roles(primitives: Dict[str, str], semantic: Dict[str, str], surface: str) -> None:
    """The brand as text and as an indicator, in a dark palette, in place: the accent step `accent-text` and `accent-ui`
    point at moves toward white until it reads on the dark surface (3:1 for the indicator) and, for the text, on the
    dark tint behind a chip. Registry revision 3 and later."""
    for role, minimum in (("accent-text", 4.5), ("accent-ui", 3.0)):
        match = registry.REF.fullmatch(semantic.get(role, ""))
        if match and match.group(1).startswith("accent-") and match.group(1) in primitives:
            backgrounds = [surface] + ([primitives["accent-50"]] if role == "accent-text" else [])
            primitives[match.group(1)] = _lighten_until(primitives[match.group(1)], backgrounds, minimum)


def derive_dark(theme: Any) -> dict:
    """The `modes.dark` block derived from a v2 theme's own (light) tokens.

    Complete in color (every ramp and the surface), sparse elsewhere. The theme must be a
    valid v2 manifest; its existing `modes` and `color_scheme` are ignored. Deterministic.
    A theme that targets registry revision 3 or later also gets readable text steps (see
    solve_dark_text) and dark accent-text and accent-ui steps; earlier revisions derive as SDK 1.4 did.
    """
    tokens = theme["tokens"]
    revision = theme["registry_revision"] if _is_int(theme.get("registry_revision")) else 1
    primitives: Dict[str, str] = {}
    ramp_step: Dict[str, str] = {}  # a light ramp color -> the name of the step it occupies
    dark_of: Dict[str, str] = {}  # that step's name -> the dark value at the same name
    for palette in registry.COLOR_RAMPS:
        light = [tokens["primitives"][f"{palette}-{shade}"] for shade in registry.SHADES]
        for shade, color in zip(registry.SHADES, reversed(light)):
            primitives[f"{palette}-{shade}"] = color
        for shade, color in zip(registry.SHADES, light):
            ramp_step.setdefault(color.lower(), f"{palette}-{shade}")
    for name, token in registry.INDEX.items():
        if token.layer == "primitive" and token.type == "shadow" and name in tokens["primitives"]:
            primitives[name] = _boost_shadow(tokens["primitives"][name])

    def mapped(color: str) -> str:
        step = ramp_step.get(color.lower())
        return primitives[step] if step else _reflect_lightness(color)

    semantic: Dict[str, str] = {}
    semantic["surface"] = _midpoint(primitives["ink-50"], primitives["ink-100"])
    semantic["scrim"] = "#000000"
    components: Dict[str, str] = {"sidebar-tone": "light", "navbar-tone": "light",
                                  "modal-scrim-alpha": "0.6", "drawer-scrim-alpha": "0.6"}
    for layer, out in (("semantic", semantic), ("components", components)):
        for name, value in tokens[layer].items():
            token = registry.INDEX[name]
            if name in registry.MODE_TOKENS and token.type == "color" and _COLOR.fullmatch(value) and name not in ("surface", "on-primary", "scrim"):
                out[name] = mapped(value)
            elif token.type == "shadow" and not registry.REF.fullmatch(value) and value != "none":
                out[name] = _boost_shadow(value)
    # Where the light palette fills with the strongest ink (the active nav item, the user's message), reversal
    # would fill with the lightest colour on the page: a quiet raised fill with plain text is what a dark UI uses.
    for name, value in (("nav-item-active-bg", "{ink-200}"), ("nav-item-active-fg", "{text}"),
                        ("chat-message-user-bg", "{ink-200}"), ("chat-message-user-fg", "{text}"),
                        ("input-placeholder", "{ink-500}")):  # the ramp's own placeholder step reads at 2.5:1
        if name not in tokens["components"]:
            components[name] = value
    # Text a theme set as `{text-inverse}` (white on a dark bar, when its primary needs dark text) sits on a fill that is
    # now a quiet dark one, so it becomes the plain text colour. The fills it sat on are the ones set just above.
    for name, fill in (("navbar-fg", None), ("nav-item-hover-fg", None), ("nav-item-active-fg", "nav-item-active-bg"),
                       ("chat-message-user-fg", "chat-message-user-bg")):
        if tokens["components"].get(name) == "{text-inverse}" and (fill is None or fill not in tokens["components"]):
            components[name] = "{text}"
    for bar in ("sidebar", "navbar"):
        if f"{bar}-bg" in tokens["components"]:
            # A bar the theme painted by hand has no dark counterpart to reverse to: it falls back to the surface,
            # and the theme can colour it in modes.dark.
            components[f"{bar}-bg"] = "{surface}"
    # A reversed accent can land mid-way, too dark to read as a link or too light for white text. The steps the
    # theme's own roles point at are moved toward white or black, in tenths, until the pairs the validator
    # judges hold. Each step is only ever moved by this function, never by the theme's other tokens.
    surface = semantic["surface"]
    steps = {}
    for role in ("text-link", "focus-ring", "primary"):
        match = registry.REF.fullmatch(tokens["semantic"].get(role, ""))
        if match and match.group(1) in primitives and registry.INDEX[match.group(1)].type == "color":
            steps[role] = match.group(1)
    for role, minimum in (("text-link", 4.5), ("focus-ring", 3.0)):
        if role in steps:
            primitives[steps[role]] = _move_until(primitives[steps[role]], "#ffffff", surface, minimum)
    if revision >= 3:
        page = primitives["ink-50"]
        light_surface = _flatten({name: content for layer in registry.LAYER_KEYS for name, content in tokens[layer].items()})["surface"]
        solve_dark_text(primitives, {shade: contrast_ratio(tokens["primitives"][f"ink-{shade}"], light_surface)
                                     for shade, _ in DARK_TEXT_STEPS}, surface, page)
        lift_accent_roles(primitives, tokens["semantic"], surface)
    # Text on the primary color: the darker or the lighter end of the dark ramp, whichever reads better.
    merged = {name: content for layer in registry.LAYER_KEYS for name, content in tokens[layer].items()}
    merged.update(primitives)
    merged.update(semantic)
    merged.update(components)
    ends = (primitives["ink-50"], primitives["ink-950"])
    primary = _flatten(merged)["primary"]
    end = max(ends, key=lambda candidate: (contrast_ratio(candidate, primary), candidate == ends[0]))
    toward = "#ffffff" if end == ends[0] else "#000000"
    for name in sorted({"accent-600"} | ({steps["primary"]} if "primary" in steps else set())):
        primitives[name] = _move_until(primitives[name], toward, end, 4.5)
    semantic["on-primary"] = end
    return {"primitives": primitives, "semantic": semantic, "components": components}


def offered_modes(theme: Any) -> List[str]:
    """The modes a theme offers: ["light"], ["dark"] or ["light", "dark"] (a v1 theme offers light)."""
    scheme = theme.get("color_scheme", "light") if _is_v2(theme) else "light"
    return {"light": ["light"], "dark": ["dark"], "auto": ["light", "dark"]}.get(scheme, ["light"])


def effective_mode(theme: Any, preference: Optional[str] = None, system_dark: bool = False) -> str:
    """The mode to show: the only one a theme offers, else the user's choice ("light", "dark" or
    "system"/None, which follows the operating system)."""
    offered = offered_modes(theme)
    if len(offered) == 1:
        return offered[0]
    if preference in offered:
        return preference
    return "dark" if system_dark else "light"


def _raw_tokens(theme: dict, mode: str) -> Dict[str, str]:
    """Every token the theme sets, with modes.dark applied when the dark palette of an auto theme is wanted."""
    raw = {name: content for layer in registry.LAYER_KEYS for name, content in theme["tokens"][layer].items()}
    if mode == "dark" and theme.get("color_scheme") == "auto":
        for layer in registry.LAYER_KEYS:
            raw.update(theme["modes"]["dark"][layer])
    return raw


def resolve_theme(value: Any, mode: Optional[str] = None) -> dict:
    """Flatten a theme into what the host applies; pure, with no DOM access.

    v2: {api_version, vars, attrs, layout, shell, fonts, enums}. `vars` holds every
    primitive and semantic token plus the component tokens the theme sets (the
    others follow their registry fallback in the generated defaults). `enums`
    is the effective value of every variant/tone/position token, for the
    data-* attributes components branch on. `shell` carries the data-*
    attributes and variables for the workspace frame.
    A theme with a dark palette (color_scheme dark or auto) resolves for `mode`
    ("light" or "dark"; an auto theme without one is light, a dark theme is always
    dark) and adds `scheme` {offered, mode} and the `data-fl-mode` attribute. A
    light-only theme resolves to exactly what registry revision 1 produced.
    v1: exactly what the v1 applier sets (27 variables, density and theme).
    """
    theme = validate_theme(value)
    if theme["api_version"] == THEME_API_VERSION:
        return {
            "api_version": 1,
            "vars": {f"--fl-{name}": (_triplet(content) if _COLOR.fullmatch(content) else content)
                     for name, content in theme["tokens"].items()},
            "attrs": {"data-density": theme["layout"]["density"], "data-theme": theme["id"]},
            "layout": dict(theme["layout"]), "shell": {"attrs": {}, "vars": {}}, "fonts": [], "enums": {},
        }
    scheme = theme.get("color_scheme", "light")
    chosen = effective_mode(theme, mode)
    raw = _raw_tokens(theme, chosen)
    resolved = _flatten(raw)
    variables: Dict[str, str] = {}
    for name, content in raw.items():
        variables[f"--fl-{name}"] = _var_value(registry.INDEX[name], resolved[name], content)
    layout = theme["layout"]
    sidebar, navbar, content = layout["sidebar"], layout["navbar"], layout["content"]
    step = lambda name: "0px" if name == "none" else f"var(--fl-space-{name})"
    shell_attrs = {
        "data-fl-sidebar-side": sidebar["side"], "data-fl-sidebar-style": sidebar["style"],
        "data-fl-sidebar-surface": sidebar["surface"], "data-fl-sidebar-behavior": sidebar["behavior"],
        "data-fl-navbar": navbar["position"], "data-fl-navbar-behavior": navbar["behavior"],
        "data-fl-navbar-align": navbar["align"], "data-fl-navbar-brand": "true" if navbar["show_brand"] else "false",
        "data-fl-scroll": layout["scroll"], "data-fl-content-align": content["align"],
    }
    shell_vars = {
        "--fl-sidebar-w": f"{sidebar['width']}px", "--fl-sidebar-collapse-below": f"{sidebar['collapse_below']}px",
        "--fl-navbar-h": f"{navbar['height']}px",
        "--fl-content-max-w": "none" if content["max_width"] == 0 else f"{content['max_width']}px",
        "--fl-content-pad": step(content["padding"]), "--fl-content-gap": step(content["gap"]),
    }
    allow = {item["family"].lower(): item for item in webfonts()}
    fonts: List[dict] = []
    for name in ("font-sans", "font-mono", "font-display"):
        family = _first_family(resolved[name])
        item = allow.get(family.lower())
        if item and item["family"] not in [f["family"] for f in fonts]:
            fonts.append({"family": item["family"], "weights": list(item["weights"])})
    attrs = {"data-density": layout["density"], "data-theme": theme["id"], "data-fl-contract": "2"}
    result = {
        "api_version": 2, "vars": variables, "attrs": attrs,
        "layout": copy.deepcopy(layout), "shell": {"attrs": shell_attrs, "vars": shell_vars}, "fonts": fonts,
        "enums": {t.name: resolved.get(t.name, t.default) for t in registry.COMPONENT_TOKENS if t.type == "enum"},
    }
    if scheme != "light":
        attrs["data-fl-mode"] = chosen
        result["scheme"] = {"offered": offered_modes(theme), "mode": chosen}
    return result


def _flatten(raw: Dict[str, str]) -> Dict[str, str]:
    """Resolved literal of every token in `raw` (already validated), following references."""
    out: Dict[str, str] = {}

    def follow(name: str) -> str:
        if name not in out:
            match = registry.REF.fullmatch(raw[name])
            out[name] = follow(match.group(1)) if match else raw[name]
        return out[name]

    for name in raw:
        follow(name)
    return out


def _all_resolved(theme: dict, mode: str = "light") -> Dict[str, str]:
    """Resolved literal of every token the (already valid) theme sets, in `mode`."""
    return _flatten(_raw_tokens(theme, mode))


# --- v1 <-> v2 -----------------------------------------------------------------

_V1_COLOR_TOKENS = tuple(f"{palette}-{shade}" for palette in ("ink", "accent") for shade in registry.SHADES)
_STYLE_TOKENS = {
    "page.header": "page-header-variant", "surface.card": "card-variant", "control.button": "button-variant",
    "control.input": "input-variant", "control.field": "field-variant", "chat.message": "chat-message-variant",
    "chat.composer": "composer-variant",
}


def _slot_order(workspace: dict) -> Tuple[Dict[str, list], Dict[int, str]]:
    """Slot name -> trail of (node id, child index), and node id -> constructor type."""
    trails: Dict[str, list] = {}
    kinds: Dict[int, str] = {}

    def walk(node: dict, trail: list):
        if node.get("type") == "slot":
            trails[node["name"]] = trail
            return
        kinds[id(node)] = node["type"]
        for index, child in enumerate(node["children"]):
            walk(child, trail + [(id(node), index)])

    walk(workspace, [])
    return trails, kinds


def _relation(trails: Dict[str, list], kinds: Dict[int, str], first: str, second: str) -> Tuple[str, bool]:
    """(constructor type at the common ancestor, whether `first` comes before `second`)."""
    a, b = trails[first], trails[second]
    for (node_a, index_a), (node_b, index_b) in zip(a, b):
        if node_a == node_b and index_a != index_b:
            return kinds[node_a], index_a < index_b
    return "column", True


def upgrade_v1_report(theme: Any, presentation: Optional[dict] = None, registry_revision: Optional[int] = None) -> dict:
    """Read-time view of a v1 theme as a v2 manifest: {"theme", "notes"}.

    Used for the editor, forking and export, never to render v1. A fork is an
    approximation: reviewed JSX templates are hand-written and the data-pack
    compiler adds 44px controls, strong borders and its own focus outline.
    `presentation` is a validated v1 presentation.json, or None. The result targets the
    current registry revision unless `registry_revision` pins an older one.
    """
    source = _validate_v1(theme)
    notes: List[str] = ["A v2 fork approximates the v1 original; compare them before publishing."]
    v1 = source["tokens"]
    result = default_theme_v2(source["id"], source["version"], source["label"], registry_revision=registry_revision)
    primitives, semantic, components = result["tokens"]["primitives"], result["tokens"]["semantic"], result["tokens"]["components"]
    for name in _V1_COLOR_TOKENS + ("font-sans", "font-mono", "radius"):
        primitives[name] = v1[name]
    primitives["font-display"] = v1["font-sans"]
    semantic["surface"], semantic["on-primary"] = v1["surface"], v1["on-primary"]
    style = "panel" if source["layout"]["navigation"] == "sidebar" else "rail"
    layout = registry.default_layout(style)
    layout["density"] = source["layout"]["density"]
    result["layout"] = layout
    if presentation:
        _upgrade_presentation(presentation, layout, components, notes)
    return {"theme": result, "notes": notes}


def _upgrade_presentation(presentation: dict, layout: dict, components: dict, notes: List[str]) -> None:
    styles = presentation.get("styles", {})
    workspace = presentation["workspace"]
    trails, kinds = _slot_order(workspace)
    sidebar, navbar, content = layout["sidebar"], layout["navbar"], layout["content"]
    # The data-pack compiler draws flush, bordered, square bars that default to the light tone.
    sidebar["surface"] = "flush"
    components["sidebar-radius"] = "0px"
    components["sidebar-border-width"] = "{border-width}"
    components["sidebar-brand-radius"] = "{radius-sm}"
    nav_style = styles.get("navigation.sidebar")
    if nav_style:
        sidebar["style"] = nav_style["variant"]
        sidebar["width"] = registry.PANEL_SIDEBAR_WIDTH if nav_style["variant"] == "panel" else 56
    components["sidebar-tone"] = nav_style["tone"] if nav_style else "light"
    topbar = styles.get("navigation.topbar")
    components["navbar-tone"] = topbar["tone"] if topbar else "light"
    # nav-item-fg is shared by both bars, so it is only pinned when they agree.
    if components["sidebar-tone"] == "dark" and components["navbar-tone"] == "dark":
        components["nav-item-fg"] = "{ink-200}"
    kind, before = _relation(trails, kinds, "navigation", "content")
    if kind == "row":
        sidebar["side"] = "left" if before else "right"
        slot = _find_slot(workspace, "navigation")
        if slot and "width" in slot:
            sidebar["width"] = slot["width"]
        kind, before = _relation(trails, kinds, "actions", "content")
        navbar["position"] = "top" if before else "bottom"
        if kind == "row":
            notes.append("The actions slot sits beside the content; it was mapped to a navbar at the top.")
    else:
        # The navbar carries the navigation items, so it follows where the navigation sat.
        sidebar["side"] = "hidden"
        navbar["position"] = "top" if before else "bottom"
        notes.append("Navigation sits above or below the content, so it was mapped to a navbar that carries the navigation items and actions.")
    if workspace.get("gap") in ("none", "sm", "md", "lg"):
        content["gap"] = workspace["gap"]
        if workspace["gap"] == "lg":
            notes.append("Workspace gap lg (20px) was approximated by the lg step (16px).")
    item = styles.get("navigation.item")
    if item:
        components["nav-item-radius"] = "{radius-pill}" if item["variant"] == "pill" else "{radius-sm}"
        components["nav-item-variant"] = item["variant"]
    for key, token in _STYLE_TOKENS.items():
        if key in styles:
            components[token] = styles[key]["variant"]
    button = styles.get("control.button")
    if button:
        components.update({"button-height": "44px", "button-weight": "{weight-semibold}", "button-pad-x": "16px",
                           "button-size": "{size-base}",
                           "button-radius": "{radius-sm}" if button["radius"] == "square" else "{radius}",
                           "button-secondary-border": "{border-strong}", "button-secondary-fg": "{ink-800}",
                           "button-secondary-hover-bg": "{ink-100}", "button-danger-border": "{danger-700}",
                           "button-danger-fg": "{danger-800}"})
    if "control.input" in styles:
        components.update({"input-height": "44px", "input-border": "{ink-400}", "input-placeholder": "{ink-500}",
                           "input-size": "{size-base}"})
    if "control.field" in styles:
        components.update({"field-label-fg": "{ink-800}", "field-label-size": "{size-base}",
                           "field-label-weight": "{weight-semibold}", "field-hint-fg": "{ink-600}", "field-hint-size": "{size-sm}"})
    if "surface.card" in styles:
        components.update({"card-border": "{border-strong}", "card-radius": "{radius}", "card-title-size": "{size-base}"})
        if styles["surface.card"]["variant"] == "raised":
            components["card-shadow"] = "{shadow-sm}"
    if "page.header" in styles:
        components["page-header-rule-color"] = "{border-strong}"
    if "chat.message" in styles:
        components.update({"chat-message-user-bg": "{primary}", "chat-message-user-radius": "{radius}"})
    notes.append("Layout, tones and component variants were mapped from presentation.json; unmapped details use registry defaults.")


def _find_slot(node: dict, name: str) -> Optional[dict]:
    if node.get("type") == "slot":
        return node if node["name"] == name else None
    for child in node["children"]:
        found = _find_slot(child, name)
        if found:
            return found
    return None


def upgrade_v1(theme: Any, presentation: Optional[dict] = None, registry_revision: Optional[int] = None) -> dict:
    """A v2 manifest equivalent in tokens and layout to the v1 theme (see upgrade_v1_report)."""
    return upgrade_v1_report(theme, presentation, registry_revision)["theme"]


def project_v1(theme: Any) -> dict:
    """The v1 manifest an old client can apply: 27 literal tokens, density and navigation.

    Total for every valid v2 theme: the v1-named tokens are literal v1 values and
    v2 enforces the two contrast pairs the v1 validator checks.
    """
    source = validate_theme(theme)
    if source["api_version"] == THEME_API_VERSION:
        return source
    tokens = {}
    for name in sorted(registry.V1_TOKEN_NAMES):
        group = "semantic" if registry.INDEX[name].layer == "semantic" else "primitives"
        tokens[name] = source["tokens"][group][name]
    layout = {"density": source["layout"]["density"],
              "navigation": "sidebar" if source["layout"]["sidebar"]["style"] == "panel" else "rail"}
    return _validate_v1({"api_version": THEME_API_VERSION, "id": source["id"], "version": source["version"],
                         "label": source["label"], "tokens": tokens, "layout": layout})
