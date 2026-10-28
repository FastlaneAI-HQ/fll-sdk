"""Versioned, data-only theme manifests (theme API v2, registry revision 4).

A manifest is token layers plus layout variants, an optional layout tree and an optional brand, driven by
`theme_registry`. `validate_theme` accepts exactly the current API version and registry revision; nothing older is read.
"""
from __future__ import annotations

import base64
import copy
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from . import theme_registry as registry

THEME_API_VERSION = 2
REGISTRY_REVISION = registry.REGISTRY_REVISION
SHADES = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_FONT = re.compile(r"[a-zA-Z0-9 ,'-]{1,200}\Z")


class ThemeError(ValueError):
    """`errors` lists every problem as {path, message}; `path` is the first one's."""

    def __init__(self, message: str = "", path: Optional[str] = None, errors: Optional[List[dict]] = None):
        super().__init__(message)
        self.path = path
        self.errors = errors if errors is not None else [{"path": path or "theme", "message": message}]


# --- Tokens ----------------------------------------------------------------

_LENGTH = re.compile(r"(?:0|[0-9]+(?:\.[0-9]{1,2})?(?:px|rem))\Z")
_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]{1,3})?\Z")
_WEIGHT = re.compile(r"[1-9]00\Z")
_TRACKING = re.compile(r"(?:0|-?[0-9]{1,2}(?:\.[0-9]{1,3})?em)\Z")
_DURATION = re.compile(r"[0-9]{1,4}(?:\.[0-9]{1,2})?ms\Z")
# The 27 tokens flagged `v1` in the registry keep their original grammar: literal values only, and a radius of whole pixels.
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


def _is_current(value: Any) -> bool:
    """A manifest that declares the theme API this SDK reads (its registry revision is checked with the rest)."""
    return isinstance(value, dict) and type(value.get("api_version")) is int and value["api_version"] == THEME_API_VERSION


_UNSUPPORTED_API = f"Unsupported theme API version; only API v{THEME_API_VERSION} themes are supported"


def _check_header(value: dict, problems: _Problems) -> str:
    """Top-level fields; returns the color scheme."""
    keys = set(value) - set(registry.OPTIONAL_TOP_LEVEL_KEYS)
    if keys != set(registry.TOP_LEVEL_KEYS):
        problems.error("", "Theme must contain only " + ", ".join(registry.TOP_LEVEL_KEYS))
    revision = value.get("registry_revision")
    if not _is_int(revision) or revision < 1:
        problems.error("registry_revision", f"registry_revision must be {registry.REGISTRY_REVISION}")
    elif revision > registry.REGISTRY_REVISION:
        problems.error("registry_revision",
                       f"Theme targets registry revision {revision}; this workspace supports {registry.REGISTRY_REVISION}. Update the workspace")
    elif revision < registry.REGISTRY_REVISION:
        problems.error("registry_revision",
                       f"Theme targets registry revision {revision}, which is no longer supported; rebuild it at revision {registry.REGISTRY_REVISION}")
    if "id" in value and (not isinstance(value["id"], str) or not _ID.fullmatch(value["id"])):
        problems.error("id", "Invalid theme id")
    if "version" in value and (not isinstance(value["version"], str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value["version"])):
        problems.error("version", "Theme version must be major.minor.patch")
    if "label" in value and (not isinstance(value["label"], str) or not 1 <= len(value["label"]) <= 80):
        problems.error("label", "Theme label must be 1–80 characters")
    scheme = "light"
    if "color_scheme" in value:
        allowed = registry.COLOR_SCHEMES
        if not isinstance(value["color_scheme"], str) or value["color_scheme"] not in allowed:
            problems.error("color_scheme", "color_scheme must be " + ", ".join(allowed[:-1]) + " or " + allowed[-1])
        else:
            scheme = value["color_scheme"]
    return scheme


def _check_modes(value: dict, scheme: str, problems: _Problems) -> Optional[dict]:
    """Structure of `modes`; returns modes.dark when it is well formed."""
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
    known = registry.INDEX
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


def _check_dark_tokens(tokens: dict, dark: dict, problems: _Problems) -> Tuple[Dict[str, str], bool]:
    """The theme's tokens with modes.dark applied, validated by the same rules as the base."""
    merged = {key: dict(tokens[key], **dark[key]) for key in registry.LAYER_KEYS}
    sub = _Problems()
    resolved, valid = _check_tokens(merged, sub)
    for error in sub.errors:
        parts = error["path"].split(".", 2)
        if len(parts) == 3 and parts[0] == "tokens" and parts[2] in dark.get(parts[1], {}):
            problems.error(f"modes.dark.{parts[1]}.{parts[2]}", error["message"])
        else:
            problems.error(error["path"], "In dark mode, " + error["message"][:1].lower() + error["message"][1:])
    return resolved, valid


def _check_tokens(tokens: Any, problems: _Problems) -> Tuple[Dict[str, str], bool]:
    """Validate every layer; returns the resolved literal of each valid token and whether all were valid."""
    known = registry.INDEX
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
            if token.type == "font-stack":
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


# --- Layout tree ------------------------------------------------------------------------------------------------------
#
# docs/layout-tree.md is the specification. Every limit, enum, default and region option is read from the layout
# vocabulary (registry_data/layout-vocabulary.json, owned by the Themes app), so a newer vocabulary changes what is
# accepted without a code change. frontend/theme-resolve.ts (validateShell, normaliseShell, shellFromLayout) is the twin,
# step for step, including the order of the messages: tests/test_layout_tree_parity.py runs both over the same trees.
#
# Validation is two passes. The structure pass (keys, types, enums, ranges, limits) walks the tree depth first and visits
# the children of a node in order. When it finds nothing, the rule pass runs on the normalised tree (fill path, counts,
# fixed sizes, chrome, behavior, modules). A rule is never judged on a tree that is not well formed.

# size.min and size.max may be this large on the content path (the range of layout.content.max_width), because
# shell_from_layout turns content.max_width into the content region's size.max. A vocabulary may state its own bound
# as limits.content_path_px.max.
CONTENT_PATH_MAX_PX = registry.LAYOUT_SPEC["content"]["max_width"]["max"]
_SHELL_KINDS = ("container", "region", "spacer")
_SHELL_ROOT_KEYS = ("version", "root")
_SHELL_SIZE_KEYS = ("basis", "min", "max")


def _shell_vocab(vocabulary: Optional[dict]) -> dict:
    return registry.layout_vocabulary() if vocabulary is None else vocabulary


def _content_path_max(vocabulary: dict) -> int:
    return (vocabulary["limits"].get("content_path_px") or {}).get("max", CONTENT_PATH_MAX_PX)


def _js_json(value: Any) -> str:
    """Compact JSON the way JSON.stringify writes it, so the TypeScript twin measures the same number of bytes."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return "null"
        return str(int(value)) if value == int(value) and abs(value) < 1e21 else repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_js_json(item) for item in value) + "]"
    return "{" + ",".join(json.dumps(str(key), ensure_ascii=False) + ":" + _js_json(item) for key, item in value.items()) + "}"


def _enum_message(options: List[str]) -> str:
    return "Must be one of " + ", ".join(options)


def _range_message(low: int, high: int) -> str:
    return f"Must be a whole number {low}-{high}"


class _ShellCheck:
    """One run of the structure pass: the problems, the node budget and the vocabulary."""

    def __init__(self, vocabulary: dict, problems: "_Problems"):
        self.vocab = vocabulary
        self.limits = vocabulary["limits"]
        self.problems = problems
        self.nodes = 0
        self.stopped = False

    def node(self, node: Any, path: str, depth: int) -> None:
        limits = self.limits
        if self.stopped:
            return
        if depth > limits["max_depth"]:
            self.problems.error(path, f"A shell is at most {limits['max_depth']} levels deep")
            return
        self.nodes += 1
        if self.nodes > limits["max_nodes"]:
            self.problems.error(path, f"A shell has at most {limits['max_nodes']} nodes")
            self.stopped = True
            return
        if not isinstance(node, dict):
            self.problems.error(path, "A node must be an object")
            return
        kind = node.get("type")
        if depth == 1 and kind != "container":
            self.problems.error(path, "The root of a shell must be a container")
            return
        if not isinstance(kind, str) or kind not in _SHELL_KINDS:
            self.problems.error(f"{path}.type", "type must be " + ", ".join(_SHELL_KINDS[:-1]) + " or " + _SHELL_KINDS[-1])
            return
        if kind == "container":
            self.container(node, path, depth)
        elif kind == "region":
            self.region(node, path)
        else:
            self.unknown(node, path, ("type",))

    def unknown(self, node: dict, path: str, allowed: Tuple[str, ...]) -> None:
        for key in sorted(k for k in node if k not in allowed):
            self.problems.error(f"{path}.{key}", f"Unknown key {key}")

    def container(self, node: dict, path: str, depth: int) -> None:
        spec = self.vocab["container"]
        self.unknown(node, path, ("type", "size", "children") + tuple(spec))
        for name, field in spec.items():
            self.field(node, name, field, f"{path}.{name}")
        if "size" in node:
            self.size(node["size"], f"{path}.size")
        children = node.get("children")
        high = self.limits["max_children"]
        if not isinstance(children, list) or not 1 <= len(children) <= high:
            self.problems.error(f"{path}.children", f"A container has 1 to {high} children")
            return
        for index, child in enumerate(children):
            self.node(child, f"{path}.children[{index}]", depth + 1)

    def field(self, owner: dict, name: str, field: dict, path: str) -> None:
        """One container field, by the vocabulary's own description of it (enum, step or int)."""
        if name not in owner:
            if "default" not in field and not field.get("optional"):
                self.problems.error(path, "Required")
            return
        value = owner[name]
        if "enum" in field:
            if not isinstance(value, str) or value not in field["enum"]:
                self.problems.error(path, _enum_message(field["enum"]))
        elif field.get("step"):
            if not isinstance(value, str) or value not in self.vocab["steps"]:
                self.problems.error(path, _enum_message(self.vocab["steps"]))
        elif field.get("int"):
            bounds = self.limits[name]
            if not _is_int(value) or not bounds["min"] <= value <= bounds["max"]:
                self.problems.error(path, _range_message(bounds["min"], bounds["max"]))

    def size(self, size: Any, path: str) -> None:
        if not isinstance(size, dict):
            self.problems.error(path, "size must be an object")
            return
        self.unknown(size, path, _SHELL_SIZE_KEYS)
        px = self.limits["size_px"]
        bases = self.vocab["size"]["bases"]
        named = [base for base in bases if base != "px"]
        if "basis" not in size:
            self.problems.error(f"{path}.basis", "Required")
        else:
            basis = size["basis"]
            valid = (isinstance(basis, str) and basis in named) or (
                "px" in bases and _is_int(basis) and px["min"] <= basis <= px["max"])
            if not valid:
                self.problems.error(f"{path}.basis", "Must be " + ", ".join(named) + f" or a whole number of px {px['min']}-{px['max']}")
        high = _content_path_max(self.vocab)
        good = {}
        for key in ("min", "max"):
            if key in size:
                if _is_int(size[key]) and px["min"] <= size[key] <= high:
                    good[key] = size[key]
                else:
                    self.problems.error(f"{path}.{key}", _range_message(px["min"], high))
        if len(good) == 2 and good["min"] > good["max"]:
            self.problems.error(f"{path}.max", "max must be at least min")

    def region(self, node: dict, path: str) -> None:
        self.unknown(node, path, ("type", "region", "size", "options"))
        regions = self.vocab["regions"]
        name = node.get("region")
        known = isinstance(name, str) and name in regions
        if "region" not in node:
            self.problems.error(f"{path}.region", "Required")
        elif not known:
            names = list(regions)
            self.problems.error(f"{path}.region", "region must be " + ", ".join(names[:-1]) + " or " + names[-1])
        if "size" in node:
            self.size(node["size"], f"{path}.size")
        if not known:
            return
        spec = regions[name]["options"]
        given = node.get("options", {})
        if "options" in node and not isinstance(given, dict):
            self.problems.error(f"{path}.options", "options must be an object")
            return
        for key in sorted(k for k in given if k not in spec):
            self.problems.error(f"{path}.options.{key}", f"Unknown option {key}")
        for option, field in spec.items():
            self.option(given, option, field, f"{path}.options.{option}")

    def option(self, given: dict, name: str, field: dict, path: str) -> None:
        if name not in given:
            if "default" not in field and not field.get("optional"):
                self.problems.error(path, "Required")
            return
        value = given[name]
        if "enum" in field:
            if not isinstance(value, str) or value not in field["enum"]:
                self.problems.error(path, _enum_message(field["enum"]))
        elif "pattern" in field:
            if not isinstance(value, str) or not re.fullmatch(field["pattern"], value):
                self.problems.error(path, "Must match " + field["pattern"])
        elif field.get("json"):
            if not isinstance(value, dict):
                self.problems.error(path, "Must be a JSON object")
                return
            high = self.limits["custom_props_bytes"]
            try:
                size = len(_js_json(value).encode("utf-8", "surrogatepass"))
            except RecursionError:
                self.problems.error(path, "Is nested too deeply")
                return
            if size > high:
                self.problems.error(path, f"Must be at most {high} bytes of JSON")


def _normalise_node(node: dict, vocabulary: dict) -> dict:
    kind = node["type"]
    if kind == "spacer":
        return {"type": "spacer"}
    size = copy.deepcopy(node["size"] if "size" in node else vocabulary["size"]["default"])
    if kind == "container":
        out: Dict[str, Any] = {"type": "container"}
        for name, field in vocabulary["container"].items():
            if name in node:
                out[name] = node[name]
            elif "default" in field:
                out[name] = field["default"]
        out["size"] = size
        out["children"] = [_normalise_node(child, vocabulary) for child in node["children"]]
        return out
    given = node.get("options", {})
    options: Dict[str, Any] = {}
    for name, field in vocabulary["regions"][node["region"]]["options"].items():
        if name in given:
            options[name] = copy.deepcopy(given[name])
        elif "default" in field:
            options[name] = field["default"]
    return {"type": "region", "region": node["region"], "size": size, "options": options}


def normalise_shell(shell: dict, vocabulary: Optional[dict] = None) -> dict:
    """A valid shell with every default filled in (the tree a host renders). The input is not changed.

    Every container carries direction, gap, padding, align, justify, chrome, surface, size, behavior and children
    (and collapse_below when it set one); every region carries size and the full set of its options (a `custom` region
    keeps `module`, and `props` only when it set it); a spacer is just its type. Behaviour for an invalid tree is undefined:
    run validate_shell first."""
    vocab = _shell_vocab(vocabulary)
    return {"version": shell["version"], "root": _normalise_node(shell["root"], vocab)}


def _shell_rules(tree: dict, path: str, vocabulary: dict, scroll: Optional[str], installed: Optional[Any],
                 problems: "_Problems") -> None:
    """The rule pass, on a normalised tree. `scroll` is layout.scroll when known; `installed` the module ids the host has
    installed, or None at the SDK level (a custom region is then always valid)."""
    limits, regions = vocabulary["limits"], vocabulary["regions"]
    px_max = limits["size_px"]["max"]
    root_path = f"{path}.root"
    counts: Dict[str, int] = {}
    chrome: Dict[str, int] = {}

    def walk(node: dict, node_path: str) -> None:
        if node["type"] == "container":
            if node["chrome"] != "none":
                chrome[node["chrome"]] = chrome.get(node["chrome"], 0) + 1
                if chrome[node["chrome"]] > limits["max_chrome_per_family"]:
                    problems.error(f"{node_path}.chrome",
                                   f"At most {limits['max_chrome_per_family']} container{'' if limits['max_chrome_per_family'] == 1 else 's'} "
                                   f"may have chrome {node['chrome']}")
            if node["behavior"] != "fixed" and scroll is not None and scroll != "page":
                problems.warn(f"{node_path}.behavior",
                              f"behavior {node['behavior']} has no visible effect while scroll is {scroll}; use scroll page or fixed")
            fills = 0
            for index, child in enumerate(node["children"]):
                if child["type"] != "spacer" and child["size"]["basis"] == "fill":
                    fills += 1
                    if fills > 1:
                        problems.error(f"{node_path}.children[{index}].size", "At most one child of a container may fill (basis fill)")
            for index, child in enumerate(node["children"]):
                walk(child, f"{node_path}.children[{index}]")
        elif node["type"] == "region":
            name = node["region"]
            counts[name] = counts.get(name, 0) + 1
            if counts[name] > regions[name]["max"]:
                problems.error(node_path, f"At most {regions[name]['max']} {name} region{'' if regions[name]['max'] == 1 else 's'}"
                                          + (" (a shell has exactly one)" if regions[name].get("required") else ""))
            module = node["options"].get("module")
            if name == "custom" and installed is not None and module is not None and module not in installed:
                problems.warn(f"{node_path}.options.module",
                              f"module not installed: {module}; the region renders nothing until the pack "
                              "that ships it is installed and approved")

    walk(tree["root"], root_path)
    needs = {"content": "A shell needs a content region (the page itself)",
             "navigation": "A shell needs a navigation region, so the user can always navigate"}
    for name, spec in regions.items():
        if spec.get("required") and not counts.get(name):
            problems.error(root_path, needs.get(name, f"A shell needs the {name} region"))

    # The content path: the first content region and every container above it.
    def find(node: dict, node_path: str) -> Optional[List[Tuple[dict, str]]]:
        if node["type"] == "region" and node["region"] == "content":
            return [(node, node_path)]
        if node["type"] == "container":
            for index, child in enumerate(node["children"]):
                found = find(child, f"{node_path}.children[{index}]")
                if found is not None:
                    return [(node, node_path)] + found
        return None

    trail = find(tree["root"], root_path)
    on_path = set()
    if trail is not None:
        parent = None
        for node, node_path in trail:
            on_path.add(node_path)
            if parent is not None and node["size"]["basis"] != "fill" and len(parent["children"]) != 1:
                problems.error(f"{node_path}.size", "The content region, and every container on the way to it, must fill "
                                                    "(basis fill) or be the only child, so the page is never squeezed away")
            if node["type"] == "container" and "collapse_below" in node:
                problems.error(f"{node_path}.collapse_below", "The container that holds the content cannot collapse into a drawer")
            parent = node

    def sizes(node: dict, node_path: str, horizontal: int, vertical: int, parent: Optional[dict]) -> None:
        if node["type"] == "spacer":
            return
        if parent is not None:
            size = node["size"]
            if isinstance(size["basis"], int):
                if parent["direction"] == "row":
                    horizontal += size["basis"]
                    over = horizontal > limits["max_fixed_path_px"] >= horizontal - size["basis"]
                else:
                    vertical += size["basis"]
                    over = vertical > limits["max_fixed_path_px"] >= vertical - size["basis"]
                if over:
                    problems.error(f"{node_path}.size", f"Fixed sizes on one root-to-leaf path add up to at most "
                                                        f"{limits['max_fixed_path_px']}px along the {'row' if parent['direction'] == 'row' else 'column'} axis")
            if node_path not in on_path:
                for key in ("min", "max"):
                    if key in size and size[key] > px_max:
                        problems.error(f"{node_path}.size.{key}", f"Off the content path a size is at most {px_max}px")
        if node["type"] == "container":
            for index, child in enumerate(node["children"]):
                sizes(child, f"{node_path}.children[{index}]", horizontal, vertical, node)

    sizes(tree["root"], root_path, 0, 0, None)


def validate_shell(shell: Any, vocabulary: Optional[dict] = None, path: str = "layout.shell", scroll: Optional[str] = None,
                   installed_modules: Optional[Any] = None) -> dict:
    """Check a `layout.shell` tree against the layout vocabulary: {"errors": [...], "warnings": [...]}, each {path, message}.

    `vocabulary` is the built-in one (registry.layout_vocabulary()) unless the host has a newer one from the Themes app.
    `path` is where the tree sits in the theme, and every problem names its node under it
    (`layout.shell.root.children[1].size`). `scroll` is layout.scroll: a container whose behavior is not `fixed` only
    warns when it is known not to be `page`. `installed_modules` is the set of reviewed module ids the HOST has installed;
    when given, a `custom` region that names another one produces a "module not installed" warning (a pack still imports).
    At the SDK level (None) every well-formed module id is valid. Every rule of docs/layout-tree.md is checked, in two
    passes: a tree that is not well formed is not judged against the rules."""
    vocab = _shell_vocab(vocabulary)
    problems = _Problems()
    if not isinstance(shell, dict):
        problems.error(path, "Shell must be an object with version and root")
        return {"errors": problems.errors, "warnings": problems.warnings}
    for key in sorted(k for k in shell if k not in _SHELL_ROOT_KEYS):
        problems.error(f"{path}.{key}", f"Unknown key {key}")
    if "version" not in shell:
        problems.error(f"{path}.version", "Required")
    elif not _is_int(shell["version"]) or shell["version"] != vocab["shell_version"]:
        problems.error(f"{path}.version", f"version must be {vocab['shell_version']}")
    if "root" not in shell:
        problems.error(f"{path}.root", "Required")
    else:
        _ShellCheck(vocab, problems).node(shell["root"], f"{path}.root", 1)
    if not problems.errors:
        _shell_rules(normalise_shell(shell, vocab), path, vocab, scroll, installed_modules, problems)
    return {"errors": problems.errors, "warnings": problems.warnings}


def shell_from_layout(layout: dict, vocabulary: Optional[dict] = None) -> dict:
    """The tree a theme's layout options describe (normalised): what a theme without `layout.shell` renders. See docs/layout-tree.md,
    "From the options to a tree".

    * Sidebar visible: a root row (gap and padding from content.gap and content.padding when the sidebar floats) holding the
      sidebar container and the main column, in the order of sidebar.side. The sidebar (chrome sidebar; surface, width,
      behavior and collapse_below from the layout; padding sm, gap xs) holds the brand, the navigation (icons for a rail,
      icons-labels for a panel) and, when there is no navbar, the actions. A rail centres its items and hides the name.
    * Navbar visible: a row container (chrome navbar, flush, height, behavior, padding md, gap md) above or below the
      content. It holds the brand (when show_brand and there is no sidebar: the sidebar carries the brand), the
      navigation (only when there is no sidebar), a spacer (navbar.align between) and the actions.
    * Both hidden: the content under a horizontal navigation region (the host's existing fallback; the validator
      rejects this layout, the mapping is still total).
    * content.max_width != 0: the content region sits in a row that centres (content.align center) or starts it, with
      size.max on the region. Without it the content region fills.
    """
    vocab = _shell_vocab(vocabulary)
    sidebar, navbar, content = layout["sidebar"], layout["navbar"], layout["content"]
    side_on, bar_on = sidebar["side"] != "hidden", navbar["position"] != "hidden"

    def region(name: str, options: Optional[dict] = None, size: Optional[dict] = None) -> dict:
        node: Dict[str, Any] = {"type": "region", "region": name}
        if size is not None:
            node["size"] = size
        if options is not None:
            node["options"] = options
        return node

    if content["max_width"]:
        page: dict = {"type": "container", "direction": "row", "justify": "center" if content["align"] == "center" else "start",
                      "size": {"basis": "fill"},
                      "children": [region("content", None, {"basis": "fill", "max": content["max_width"]})]}
    else:
        page = region("content", None, {"basis": "fill"})

    def sidebar_node() -> dict:
        rail = sidebar["style"] == "rail"
        children = [region("brand", {"name": "hide" if rail else "auto"}),
                    region("navigation", {"style": "icons" if rail else "icons-labels", "orientation": "vertical"}, {"basis": "fill"})]
        if not bar_on:
            children.append(region("actions", {"style": "icons" if rail else "labels", "orientation": "vertical"}))
        node: Dict[str, Any] = {
            "type": "container", "direction": "column", "chrome": "sidebar", "surface": sidebar["surface"],
            "size": {"basis": sidebar["width"]}, "behavior": sidebar["behavior"], "collapse_below": sidebar["collapse_below"],
            "padding": "sm", "gap": "xs", "children": children}
        if rail:
            node["align"] = "center"
        return node

    def navbar_node() -> dict:
        children = []
        if navbar["show_brand"] and not side_on:
            children.append(region("brand", {"name": "show"}))
        if not side_on:
            children.append(region("navigation", {"style": "icons-labels", "orientation": "horizontal", "overflow": "menu"}))
        if navbar["align"] == "between":
            children.append({"type": "spacer"})
        children.append(region("actions", {"style": "labels", "orientation": "horizontal"}))
        return {"type": "container", "direction": "row", "chrome": "navbar", "surface": "flush",
                "size": {"basis": navbar["height"]}, "behavior": navbar["behavior"], "align": "center",
                "justify": "center" if navbar["align"] == "center" else "start", "padding": "md", "gap": "md", "children": children}

    def column(first_bar: bool, size: Optional[dict]) -> dict:
        node: Dict[str, Any] = {"type": "container", "direction": "column",
                                "children": [navbar_node(), page] if first_bar else [page, navbar_node()]}
        if size is not None:
            node["size"] = size
        return node

    if side_on:
        main = column(navbar["position"] == "top", {"basis": "fill"}) if bar_on else page
        root: Dict[str, Any] = {"type": "container", "direction": "row",
                                "children": [sidebar_node(), main] if sidebar["side"] == "left" else [main, sidebar_node()]}
        if sidebar["surface"] == "floating":
            root.update({"padding": content["padding"], "gap": content["gap"]})
    elif bar_on:
        root = column(navbar["position"] == "top", None)
    else:
        root = {"type": "container", "direction": "column", "children": [
            region("navigation", {"style": "icons-labels", "orientation": "horizontal", "overflow": "menu"}), page]}
    return normalise_shell({"version": vocab["shell_version"], "root": root}, vocab)


def shell_tree_of(theme: Any, vocabulary: Optional[dict] = None) -> dict:
    """The normalised tree a host renders for a valid theme: its own `layout.shell` when it has one, otherwise the tree its
    layout options describe (`shell_from_layout`)."""
    layout = theme["layout"]
    if "shell" in layout:
        return normalise_shell(layout["shell"], vocabulary)
    return shell_from_layout(layout, vocabulary)


# --- The brand (logo) -------------------------------------------------------------------------------------------------
#
# docs/brand-logo.md is the specification; the limits (types, sizes, alt, height, tagline) come from the layout vocabulary's
# `brand.logo_limits`. The TypeScript twin (validateBrand, normaliseBrand in theme-resolve.ts) gives the same errors, with the same
# paths, messages and order: tests/test_brand.py runs both over the same cases. Everything below is written to behave the same in
# both languages: ASCII-only case folding, explicit whitespace classes, code point counts.

_BRAND_KEYS = ("logo", "logo_dark", "mark", "tagline")
_IMAGE_KEYS = ("src", "alt")
_B64 = re.compile(r"[A-Za-z0-9+/]*={0,2}\Z")
_ALT_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
_TRIM = re.compile("^[ \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+|[ \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+\\Z")
_SVG_WS = " \t\r\n"
_SVG_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SVG_TAG = re.compile(r"<(?:[A-Za-z0-9_.-]+:)?(script|foreignobject|iframe|image|use)(?![A-Za-z0-9_:.-])", re.I | re.A)
_SVG_HREF = re.compile(r"(?:^|[^A-Za-z0-9_.:-])(?:[A-Za-z0-9_.-]+:)?href[ \t\r\n]*=[ \t\r\n]*(?:\"([^\"]*)\"|'([^']*)')", re.I | re.A)
_SVG_ATTR = re.compile(r"(?:^|[^A-Za-z0-9_.:-])((?:[A-Za-z0-9_.-]+:)?[A-Za-z_][A-Za-z0-9_.-]*)[ \t\r\n]*=[ \t\r\n]*(?:\"([^\"]*)(?=\")|'([^']*)(?='))", re.A)
_SVG_DOCTYPE_SUBSET = re.compile(r"<!doctype[^>\[]*\[", re.I | re.A)
_SVG_SCHEME = re.compile(r"(?:^|[^A-Za-z0-9+.-])(javascript|data|https?):", re.I | re.A)
_SVG_URL_FUNCTION = re.compile(r"url\([ \t\r\n]*[\"']?[ \t\r\n]*(javascript|data|https?)[ \t\r\n]*:", re.I | re.A)
_SVG_ENTITY = re.compile(r"&(?:#[xX]([0-9a-fA-F]{1,8})|#([0-9]{1,8})|(amp|lt|gt|quot|apos));")
_SVG_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}
_SVG_SIGNATURES = {"image/png": (b"\x89PNG\r\n\x1a\n", "PNG"), "image/jpeg": (b"\xff\xd8\xff", "JPEG")}
_SVG_FORBIDDEN_TAGS = ("script", "foreignObject", "iframe", "image")


def _logo_limits(vocabulary: Optional[dict]) -> dict:
    """The vocabulary's `brand.logo_limits`; a vocabulary that predates the brand falls back to the built-in one."""
    found = ((vocabulary or {}).get("brand") or {}).get("logo_limits")
    return found if found else registry.layout_vocabulary()["brand"]["logo_limits"]


def _size_text(count: int) -> str:
    return f"{count // 1024} KiB" if count % 1024 == 0 else f"{count} bytes"


def _decode_entities(text: str) -> str:
    def one(match):
        if match.group(3):
            return _SVG_NAMED[match.group(3)]
        point = int(match.group(1), 16) if match.group(1) else int(match.group(2))
        return "\ufffd" if point == 0 or point > 0x10FFFF or 0xD800 <= point <= 0xDFFF else chr(point)
    return _SVG_ENTITY.sub(one, text)


def _ascii_lower(text: str) -> str:
    return text.translate({code: code + 32 for code in range(65, 91)})


def _trim_text(text: str) -> str:
    return _TRIM.sub("", text)


def _svg_problems(text: str) -> List[str]:
    """Why this decoded SVG text is not acceptable (empty when it is). Order: structure, then each forbidden construct."""
    problems: List[str] = []
    if _SVG_CONTROL.search(text):
        problems.append("An SVG must be well-formed text, with no control characters")
    index, size = 0, len(text)
    while True:
        while index < size and text[index] in _SVG_WS:
            index += 1
        if text.startswith("<?", index):
            end = text.find("?>", index + 2)
            index = size + 1 if end < 0 else end + 2
        elif text.startswith("<!--", index):
            end = text.find("-->", index + 4)
            index = size + 1 if end < 0 else end + 3
        elif _ascii_lower(text[index:index + 9]) == "<!doctype":
            end, bracket = text.find(">", index), text.find("[", index)
            if 0 <= bracket < end or (bracket >= 0 and end < 0):
                bracket = text.find("]", bracket)
                end = -1 if bracket < 0 else text.find(">", bracket)
            index = size + 1 if end < 0 else end + 1
        else:
            break
    if index > size or not (text.startswith("<svg", index) and index + 4 < size and text[index + 4] in _SVG_WS + "/>"):
        problems.append("An SVG must start at <svg (an XML prolog and comments may come before it)")
    tail = text.rstrip(_SVG_WS)
    while tail.endswith("-->") and tail.rfind("<!--") >= 0:
        tail = tail[:tail.rfind("<!--")].rstrip(_SVG_WS)
    if not (tail.endswith("</svg>") or (tail.endswith("/>") and tail.find(">", index) == len(tail) - 1)):
        problems.append("An SVG must be well-formed: it must end with </svg>")
    text = _decode_entities(text)
    found = {match.group(1).lower() for match in _SVG_TAG.finditer(text)}
    for name in _SVG_FORBIDDEN_TAGS:
        if name.lower() in found:
            problems.append(f"An SVG must not contain <{name}>")
    external_use = False
    for match in _SVG_TAG.finditer(text):
        if match.group(1).lower() == "use":
            end = text.find(">", match.end())
            for href in _SVG_HREF.finditer(text[match.end():len(text) if end < 0 else end]):
                target = re.sub("[\x00-\x20]", "", href.group(1) if href.group(1) is not None else href.group(2))
                external_use = external_use or not target.startswith("#")
    if external_use:
        problems.append("An SVG <use> may only point at an element in the same file (an href starting with #)")
    if re.search(r"<!entity", text, re.I | re.A):
        problems.append("An SVG must not declare entities (<!ENTITY)")
    if _SVG_DOCTYPE_SUBSET.search(text):
        problems.append("An SVG must not have a DOCTYPE with an internal subset")
    if re.search(r"@import", text, re.I | re.A):
        problems.append("An SVG must not use @import")
    events = script = external = False
    for match in _SVG_ATTR.finditer(text):
        name = match.group(1)
        if name == "xmlns" or name.startswith("xmlns:"):
            continue
        if _ascii_lower(name.rsplit(":", 1)[-1]).startswith("on"):
            events = True
        value = re.sub("[\x00-\x20]", "", match.group(2) if match.group(2) is not None else match.group(3))
        for scheme in _SVG_SCHEME.finditer(value):
            if _ascii_lower(scheme.group(1)) == "javascript":
                script = True
            else:
                external = True
    for match in _SVG_URL_FUNCTION.finditer(text):
        if _ascii_lower(match.group(1)) == "javascript":
            script = True
        else:
            external = True
    if events:
        problems.append("An SVG must not have event attributes (on*=)")
    if script:
        problems.append("An SVG must not contain javascript: URLs")
    if external:
        problems.append("An SVG must not load external or data: URLs (http:, https: or data:)")
    return problems


def _image_source(src: Any, limits: dict) -> Tuple[List[str], int]:
    """(problems, decoded size): the problems of one `src` (at most the first failing step, or the SVG's list) and its size."""
    types = limits["types"]
    if not isinstance(src, str):
        return ["Must be a data: URI string"], 0
    if not src.startswith("data:"):
        return ["Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched"], 0
    comma = src.find(",")
    if comma < 0:
        return ["Malformed data URI: expected data:<type>;base64,<payload>"], 0
    header, payload = src[5:comma], src[comma + 1:]
    if not header.endswith(";base64"):
        return ["The data URI must be base64: data:<type>;base64,<payload>"], 0
    mime = header[:-7]
    if mime not in types:
        return ["Type must be one of " + ", ".join(types)], 0
    if len(payload) % 4 != 0 or not _B64.match(payload):
        return ["The payload is not valid base64"], 0
    size = len(payload) // 4 * 3 - (len(payload) - len(payload.rstrip("=")))
    if size == 0:
        return ["The image is empty"], 0
    if size > limits["max_image_bytes"]:
        return [f"The image is {size} bytes; at most {_size_text(limits['max_image_bytes'])}"], size
    data = base64.b64decode(payload, validate=True)
    if mime == "image/svg+xml":
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return ["An SVG must be UTF-8 text"], size
        return _svg_problems(text), size
    if mime == "image/webp":
        valid, label = len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP", "WebP"
    else:
        signature, label = _SVG_SIGNATURES[mime]
        valid = data.startswith(signature)
    if not valid:
        return [f"The data is not a {label} image (wrong file signature)"], size
    return [], size


def _text_problem(value: Any, limit: int) -> Optional[str]:
    if not isinstance(value, str):
        return "Must be text"
    if _ALT_CONTROL.search(value):
        return "Must not contain control characters"
    if not 1 <= len(_trim_text(value)) <= limit:
        return f"Must be 1 to {limit} characters"
    return None


def validate_brand(brand: Any, vocabulary: Optional[dict] = None, path: str = "brand") -> dict:
    """Check a theme's `brand`: {errors, warnings} with the path of every problem (`brand.logo.src`).

    Never raises. `vocabulary` is the layout vocabulary whose `brand.logo_limits` apply (the built-in one when omitted).
    Problems come in a fixed order: unknown keys (alphabetical), then `logo`, `logo_dark`, `mark`, `tagline`; inside an
    image its unknown keys, `src`, `alt`, `height`; last the size of all the images together. `logo_dark` (the logo drawn on
    dark backgrounds) follows the rules of `logo` and needs a `logo`."""
    errors: List[dict] = []
    warnings: List[dict] = []
    if not isinstance(brand, dict):
        return {"errors": [{"path": path, "message": "Brand must be an object with logo, mark and tagline"}], "warnings": warnings}
    limits = _logo_limits(vocabulary)
    height = limits["height"]

    def error(where: str, message: str) -> None:
        errors.append({"path": where, "message": message})

    for key in sorted(set(brand) - set(_BRAND_KEYS)):
        error(f"{path}.{key}", f"Unknown key {key}")
    if not brand:
        error(path, "Brand must set logo, mark or tagline")
    total = 0
    for key in ("logo", "logo_dark", "mark"):
        if key not in brand:
            continue
        image, where = brand[key], f"{path}.{key}"
        if key == "logo_dark" and "logo" not in brand:
            error(where, "logo_dark needs a logo")
        if not isinstance(image, dict):
            error(where, "Must be an object with src and alt")
            continue
        allowed = _IMAGE_KEYS + (("height",) if key != "mark" else ())
        for name in sorted(set(image) - set(allowed)):
            error(f"{where}.{name}", f"Unknown key {name}")
        if "src" not in image:
            error(f"{where}.src", "Required")
        else:
            problems, size = _image_source(image["src"], limits)
            for message in problems:
                error(f"{where}.src", message)
            total += size if not problems else 0
        if "alt" not in image:
            error(f"{where}.alt", "Required")
        else:
            message = _text_problem(image["alt"], limits["alt_max"])
            if message:
                error(f"{where}.alt", message)
        if key != "mark" and "height" in image and (not _is_int(image["height"]) or not height["min"] <= image["height"] <= height["max"]):
            error(f"{where}.height", _range_message(height["min"], height["max"]))
    if "tagline" in brand:
        message = _text_problem(brand["tagline"], limits["tagline_max"])
        if message:
            error(f"{path}.tagline", message)
    if total > limits["max_total_bytes"]:
        error(path, f"The images of a brand add up to {total} bytes; at most {_size_text(limits['max_total_bytes'])}")
    return {"errors": errors, "warnings": warnings}


def normalise_brand(brand: Any, vocabulary: Optional[dict] = None) -> Optional[dict]:
    """The brand a host draws: `{logo, logo_dark, mark, tagline}` with the defaults filled (`logo.height`; `logo_dark.height`
    follows the logo's height, else the vocabulary's default) and the text trimmed, an absent part `None`; `None` for a theme
    without a brand. Assumes a valid brand (see `validate_brand`)."""
    if brand is None:
        return None
    default = _logo_limits(vocabulary)["height"]["default"]
    logo, dark, mark = brand.get("logo"), brand.get("logo_dark"), brand.get("mark")
    tagline = brand.get("tagline")
    logo_height = default if logo is None else logo.get("height", default)
    return {
        "logo": None if logo is None else {"src": logo["src"], "alt": _trim_text(logo["alt"]), "height": logo_height},
        "logo_dark": None if dark is None else {"src": dark["src"], "alt": _trim_text(dark["alt"]), "height": dark.get("height", logo_height)},
        "mark": None if mark is None else {"src": mark["src"], "alt": _trim_text(mark["alt"])},
        "tagline": None if tagline is None else _trim_text(tagline),
    }


def brand_logo_for(brand: Optional[dict], on_dark: bool) -> Optional[dict]:
    """The logo to draw on a background: on a dark one (a dark header, a dark palette) `logo_dark` when the brand has one, else
    `logo`; on a light one `logo`. `brand` is a normalised brand (`resolve_theme(...)["brand"]`) or None. The result is
    `{src, alt, height}` or None when there is nothing to draw. Core calls it with the container's tone or the palette mode."""
    if brand is None:
        return None
    if on_dark and brand.get("logo_dark") is not None:
        return brand["logo_dark"]
    return brand.get("logo")


def brand_of(theme: Any, vocabulary: Optional[dict] = None) -> Optional[dict]:
    """The normalised brand of a valid theme, or None for a theme without one."""
    return normalise_brand(theme.get("brand"), vocabulary)


def _check_layout(layout: Any, problems: _Problems, vocabulary: Optional[dict] = None, installed_modules: Optional[Any] = None) -> None:
    spec = registry.LAYOUT_SPEC
    if not isinstance(layout, dict) or set(layout) - {"shell"} != set(spec):
        problems.error("layout", "Layout must supply exactly " + ", ".join(spec) + " and may add shell")
        return
    start = len(problems.errors)
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
    scroll = layout["scroll"] if len(problems.errors) == start else None
    if "shell" in layout:
        found = validate_shell(layout["shell"], vocabulary, "layout.shell", scroll, installed_modules)
        problems.errors.extend(found["errors"])
        problems.warnings.extend(found["warnings"])
    if len(problems.errors) > start and any(e["path"].startswith("layout") and not e["path"].startswith("layout.shell")
                                            for e in problems.errors[start:]):
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
                    mode: Optional[str] = None, where: str = "tokens", prefix: str = "") -> None:
    """Judge every contrast pair. `mode` labels the rows of a theme that has a dark palette (a light-only theme's rows
    carry no mode); `where` is the path root errors point at and `prefix` starts their message."""
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
        if not (item.unless and item.unless in resolved):
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


def _check_v2(value: Any, vocabulary: Optional[dict] = None, installed_modules: Optional[Any] = None) -> dict:
    problems = _Problems()
    if not isinstance(value, dict):
        problems.error("", "Theme must be an object")
        return problems.as_dict()
    scheme = _check_header(value, problems)
    resolved, tokens_valid = {}, False
    if "tokens" in value:
        resolved, tokens_valid = _check_tokens(value["tokens"], problems)
    else:
        problems.error("tokens", "Theme must contain tokens")
    if "layout" in value:
        _check_layout(value["layout"], problems, vocabulary, installed_modules)
    else:
        problems.error("layout", "Theme must contain layout")
    if "brand" in value:
        found = validate_brand(value["brand"], vocabulary)
        problems.errors.extend(found["errors"])
        problems.warnings.extend(found["warnings"])
    dark = _check_modes(value, scheme, problems)
    dark_resolved, dark_valid = {}, False
    if dark is not None and tokens_valid:
        dark_resolved, dark_valid = _check_dark_tokens(value["tokens"], dark, problems)
    # A problem in layout.shell does not stop the contrast report: the colours do not depend on the tree.
    if tokens_valid and not any(e["path"].startswith("layout") and not e["path"].startswith("layout.shell") for e in problems.errors):
        if scheme == "light":
            _check_contrast(resolved, value["layout"], problems)
        elif scheme == "dark":
            _check_contrast(resolved, value["layout"], problems, mode="dark")
            _check_dark_character(resolved, problems, "tokens", "")
        else:
            _check_contrast(resolved, value["layout"], problems, mode="light")
            if dark_valid:
                _check_contrast(dark_resolved, value["layout"], problems, mode="dark", where="modes.dark",
                                prefix="In dark mode, ")
                _check_dark_character(dark_resolved, problems, "modes.dark", "In dark mode, ")
    return problems.as_dict()


def _first_error(problems: dict) -> ThemeError:
    first = problems["errors"][0]
    return ThemeError(first["message"], first["path"] or None, list(problems["errors"]))


def validate_theme(value: Any, vocabulary: Optional[dict] = None, installed_modules: Optional[Any] = None) -> dict:
    """Return a copy of a valid manifest; raise ThemeError otherwise.

    Nothing is ever defaulted or rewritten: the output is the input, so a hash of it is stable across SDK releases.
    A `layout.shell` is checked against `vocabulary` (the built-in layout vocabulary when omitted; a host passes the Themes
    app's newer one).
    """
    if not _is_current(value):
        raise ThemeError(_UNSUPPORTED_API, "api_version")
    problems = _check_v2(value, vocabulary, installed_modules)
    if problems["errors"]:
        raise _first_error(problems)
    return copy.deepcopy(value)


def check_theme(value: Any, vocabulary: Optional[dict] = None, installed_modules: Optional[Any] = None) -> dict:
    """Never raises: {errors, warnings, contrast}, each error/warning {path, message}.

    A `layout.shell` reports its errors and warnings with the path of the node (`layout.shell.root.children[1].size`).
    `installed_modules` is for a host: the module ids it has installed, so that a `custom` region naming another one warns
    ("module not installed"); the SDK itself (None) accepts every well-formed module id."""
    if not _is_current(value):
        return {"errors": [{"path": "api_version", "message": _UNSUPPORTED_API}], "warnings": [], "contrast": []}
    return _check_v2(value, vocabulary, installed_modules)


def contrast_report(theme: Any) -> List[dict]:
    """Every contrast pair judged for a theme, with ratio, minimum, level and pass.

    A theme with a dark palette also reports it: its rows carry `mode` ("light" and "dark");
    a light-only theme's rows have no `mode` key.
    Returns an empty list when the theme has structural errors, since colors
    cannot be resolved; use `check_theme` for those.
    """
    return check_theme(theme)["contrast"]


def default_theme_v2(theme_id: str = "fastlane", version: str = "2.0.0", label: str = "Fastlane", scheme: str = "light") -> dict:
    """The registry defaults as a complete manifest: the palette a new theme starts from (`registry.default_for`), every
    semantic role set, no component tokens and the registry's default layout (no `layout.shell`, no brand).

    `scheme` "auto" adds the derived default dark palette as `modes.dark`; "dark" makes the
    theme's own tokens that palette.
    """
    theme = {
        "api_version": THEME_API_VERSION, "registry_revision": REGISTRY_REVISION,
        "id": theme_id, "version": version, "label": label, "color_scheme": "light",
        "tokens": {
            "primitives": {t.name: registry.default_for(t) for t in registry.PRIMITIVES},
            "semantic": {t.name: registry.default_for(t) for t in registry.SEMANTIC},
            "components": {},
        },
        "layout": registry.default_layout("rail"),
    }
    if scheme != "light":
        if scheme not in registry.COLOR_SCHEMES:
            raise ThemeError("color_scheme must be light, dark or auto", "color_scheme")
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
    return _lighten_until_all(color, [(background, minimum) for background in backgrounds])


def _lighten_until_all(color: str, needs: List[Tuple[str, float]]) -> str:
    """`color` moved toward white in whole percents until it has each background's own minimum contrast."""
    if all(contrast_ratio(color, background) >= minimum for background, minimum in needs):
        return color
    start = _channels(color)
    for percent in range(1, 101):
        moved = _hex(*((a * (100 - percent) + 255 * percent + 50) // 100 for a in start))
        if all(contrast_ratio(moved, background) >= minimum for background, minimum in needs):
            return moved
    return "#ffffff"


# The ink steps the interface paints text and icons with (text-ink-400 ... 700) and borders (ink-300), and the
# least contrast each may have. Reversing a ramp leaves them at 2.5 to 3.6:1 on a dark surface.
DARK_TEXT_STEPS = ((300, 3.0), (400, 4.5), (500, 4.5), (600, 4.5), (700, 4.5))
# The dark accent tints the interface prints a text step on (a selected row, a chip, a tile): ink-400 is a caption on the
# faintest tint, and the steps from ink-500 up are printed on both.
DARK_TEXT_TINTS = {400: ("accent-50",), 500: ("accent-50", "accent-100"), 600: ("accent-50", "accent-100"), 700: ("accent-50", "accent-100")}
# How far a dark tint may be darkened to carry its text steps: its contrast against the dark surface stays at least this
# (a tint that is no longer a tint is a selected row nobody can see). The default palette's tints are 1.20 and 1.44.
DARK_TINT_FLOORS = {"accent-50": 1.15, "accent-100": 1.3}


def _darken(color: str, percent: int) -> str:
    """`color` moved toward black by `percent`: hue and saturation kept, every channel scaled."""
    return _hex(*((a * (100 - percent) + 50) // 100 for a in _channels(color)))


def _settle_tint(primitives: Dict[str, str], tint: str, surface: str, cap: Optional[str] = None) -> None:
    """Darken a dark accent tint, in place, until the text steps printed on it reach their minimum there, but no further
    than DARK_TINT_FLOORS from the surface (the remainder is the text's to lift) and, when `cap` is given, never as light as `cap`.

    The brand's bright tints (a saturated green or yellow reversed from its darkest ramp step is far from the surface) are the
    case: the text steps would otherwise all be pushed toward white until ink-400 and ink-700 are one colour."""
    steps = [shade for shade, tints in DARK_TEXT_TINTS.items() if tint in tints]
    start = primitives[tint]
    best = start
    for percent in range(0, 101):
        moved = _darken(start, percent) if percent else start
        if percent and contrast_ratio(moved, surface) < DARK_TINT_FLOORS[tint]:
            break
        best = moved
        if all(contrast_ratio(primitives[f"ink-{shade}"], moved) >= 4.5 for shade in steps):
            break
    if cap is not None and _luminance(best) >= _luminance(cap) * 0.93:
        # The ramp must keep its order: the fainter tint stays darker than the stronger one.
        for percent in range(0, 101):
            best = _darken(start, percent)
            if _luminance(best) < _luminance(cap) * 0.93:
                break
    primitives[tint] = best


def solve_dark_text(primitives: Dict[str, str], light_ratios: Dict[int, float], surface: str, page: str) -> None:
    """Re-solve the dark ramp's text steps, in place, against the dark surface, the page and the dark accent tints.

    Each step in DARK_TEXT_STEPS gets at least the contrast the light palette gives it on its own surface (so the
    three-step hierarchy survives) and never less than its minimum, on the surface and the page. The steps in
    DARK_TEXT_TINTS also reach their minimum on the accent tints they sit on (accent-50 and accent-100 of the dark ramp):
    a tint brighter than the text allows is first darkened (see _settle_tint), then whatever is still short is lifted.
    A step that already reads is left alone.
    """
    wanted = {shade: max(minimum, light_ratios.get(shade, minimum)) for shade, minimum in DARK_TEXT_STEPS}
    for shade, _ in DARK_TEXT_STEPS:
        name = f"ink-{shade}"
        primitives[name] = _lighten_until_all(primitives[name], [(surface, wanted[shade]), (page, wanted[shade])])
    _settle_tint(primitives, "accent-100", surface)
    _settle_tint(primitives, "accent-50", surface, cap=primitives["accent-100"])
    for shade, minimum in DARK_TEXT_STEPS:
        name = f"ink-{shade}"
        needs = [(surface, wanted[shade]), (page, wanted[shade])] + [(primitives[tint], minimum) for tint in DARK_TEXT_TINTS.get(shade, ())]
        primitives[name] = _lighten_until_all(primitives[name], needs)


def lift_accent_roles(primitives: Dict[str, str], semantic: Dict[str, str], surface: str) -> None:
    """The brand as text and as an indicator, in a dark palette, in place: the accent step `accent-text` and `accent-ui`
    point at moves toward white until it reads on the dark surface (3:1 for the indicator) and, for the text, on the
    dark tint behind a chip."""
    for role, minimum in (("accent-text", 4.5), ("accent-ui", 3.0)):
        match = registry.REF.fullmatch(semantic.get(role, ""))
        if match and match.group(1).startswith("accent-") and match.group(1) in primitives:
            backgrounds = [surface] + ([primitives["accent-50"]] if role == "accent-text" else [])
            primitives[match.group(1)] = _lighten_until(primitives[match.group(1)], backgrounds, minimum)


def derive_dark(theme: Any) -> dict:
    """The `modes.dark` block derived from a theme's own (light) tokens.

    Complete in color (every ramp and the surface), sparse elsewhere. The theme must be a
    valid manifest; its existing `modes` and `color_scheme` are ignored. Deterministic.
    The text steps are re-solved to read on the dark surfaces and tints (see solve_dark_text), and the steps
    accent-text and accent-ui point at are lifted (see lift_accent_roles).
    """
    tokens = theme["tokens"]
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
    """The modes a theme offers: ["light"], ["dark"] or ["light", "dark"]."""
    scheme = theme.get("color_scheme", "light") if isinstance(theme, dict) else "light"
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


def resolve_theme(value: Any, mode: Optional[str] = None, vocabulary: Optional[dict] = None) -> dict:
    """Flatten a theme into what the host applies; pure, with no DOM access.

    {api_version, vars, attrs, layout, shell, brand, fonts, enums}. `brand` is the normalised `brand` of the theme
    (`normalise_brand`: `{logo, logo_dark, mark, tagline}`, an absent part None, `logo.height` filled) and None for a theme without one.
    `shell` is {attrs, vars, tree}: `tree` is the normalised
    layout tree (see shell_tree_of): the theme's own `layout.shell`, otherwise the tree its
    layout options describe. `vars` holds every
    primitive and semantic token plus the component tokens the theme sets (the
    others follow their registry fallback in the generated defaults). `enums`
    is the effective value of every variant/tone/position token, for the
    data-* attributes components branch on. `shell` carries the data-*
    attributes and variables for the workspace frame.
    A theme with a dark palette (color_scheme dark or auto) resolves for `mode`
    ("light" or "dark"; an auto theme without one is light, a dark theme is always
    dark) and adds `scheme` {offered, mode} and the `data-fl-mode` attribute.
    """
    theme = validate_theme(value, vocabulary)
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
        "api_version": THEME_API_VERSION, "vars": variables, "attrs": attrs,
        "layout": copy.deepcopy(layout), "shell": {"attrs": shell_attrs, "vars": shell_vars, "tree": shell_tree_of(theme, vocabulary)},
        "brand": brand_of(theme, vocabulary), "fonts": fonts,
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
