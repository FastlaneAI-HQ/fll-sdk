"""Token registry for theme API v2: the single source of truth.

The validator, the resolver, the generated CSS/Tailwind/TypeScript and the
editor forms are produced from, or checked against, this module. Every token
names its layer (primitive, semantic or component), its value type, the value
that reproduces today's rendering, and the registry revision that introduced
it. A theme records the revision it targets; a revision never changes meaning
once released (new tokens are optional and their fallback reproduces the
previous rendering), so a stored release stays valid under every later
validator.

Defaults:
  primitive  a literal value. A theme supplies every primitive.
  semantic   a literal or a `{token}` reference. A theme supplies every role.
  component  a fallback only: `{token}`, `{token}*1.5` or `{token}+0.5px`
             (or a literal). A theme supplies only the ones it changes; an
             unset component token follows its fallback live.
"""
from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

REGISTRY_REVISION = 1
SHADES = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)
STATUSES = ("success", "warning", "danger", "info")
SIZE_STEPS = ("2xs", "xs", "sm", "md", "base", "lg", "xl", "2xl", "3xl")
SPACE_STEPS = ("xs", "sm", "md", "lg", "xl", "2xl")
STEPS = ("none",) + SPACE_STEPS[:-1]

REF = re.compile(r"\{([a-z][a-z0-9-]*)\}\Z")
# Fallbacks only: a reference, optionally scaled (`*1.5`) or offset (`+0.5px`).
FALLBACK_EXPR = re.compile(r"\{([a-z][a-z0-9-]*)\}(?:\*([0-9]+(?:\.[0-9]+)?)|\+([0-9]+(?:\.[0-9]+)?)px)?\Z")

# Value types; see theme_registry.GRAMMAR in the generated JSON for the rules.
TYPES = ("color", "length", "font-size", "number", "weight", "font-stack", "shadow",
         "ease", "duration", "tracking", "enum")

LAYERS = ("primitive", "semantic", "component")


class Token(NamedTuple):
    name: str
    layer: str
    type: str
    default: Any  # str, or {"dark": ..., "light": ...} when tone-dependent
    group: str
    label: str
    since: int = 1
    min: Optional[float] = None
    max: Optional[float] = None
    options: Tuple[str, ...] = ()
    component: Optional[str] = None
    tone: Optional[str] = None  # the enum token (e.g. sidebar-tone) selecting a default
    v1: bool = False  # one of the 27 v1 names: literal values in the v1 grammar only
    note: str = ""

    def as_dict(self) -> dict:
        data = {"name": self.name, "layer": self.layer, "type": self.type, "default": self.default,
                "group": self.group, "label": self.label, "since": self.since}
        if self.min is not None:
            data["min"] = self.min
        if self.max is not None:
            data["max"] = self.max
        if self.options:
            data["options"] = list(self.options)
        if self.component:
            data["component"] = self.component
        if self.tone:
            data["tone"] = self.tone
        if self.v1:
            data["v1"] = True
        if self.note:
            data["note"] = self.note
        return data


_TOKENS: List[Token] = []


def _add(*args, **kwargs) -> None:
    _TOKENS.append(Token(*args, **kwargs))


# --- Primitives -----------------------------------------------------------

_INK = ("#f7f7f8", "#ececee", "#d9dade", "#b8bac2", "#8f929e", "#6c6f7d", "#555764", "#454652", "#2b2c34", "#1a1b21", "#101117")
_ACCENT = ("#eef4ff", "#d9e6ff", "#bcd3ff", "#8eb5ff", "#598dff", "#3366f2", "#2148d8", "#1c39ae", "#1c3389", "#1c2f6c", "#152450")
# Tailwind 3.4 emerald, amber, red and sky: the classes core and the apps use for status today.
_STATUS = {
    "success": ("#ecfdf5", "#d1fae5", "#a7f3d0", "#6ee7b7", "#34d399", "#10b981", "#059669", "#047857", "#065f46", "#064e3b", "#022c22"),
    "warning": ("#fffbeb", "#fef3c7", "#fde68a", "#fcd34d", "#fbbf24", "#f59e0b", "#d97706", "#b45309", "#92400e", "#78350f", "#451a03"),
    "danger": ("#fef2f2", "#fee2e2", "#fecaca", "#fca5a5", "#f87171", "#ef4444", "#dc2626", "#b91c1c", "#991b1b", "#7f1d1d", "#450a0a"),
    "info": ("#f0f9ff", "#e0f2fe", "#bae6fd", "#7dd3fc", "#38bdf8", "#0ea5e9", "#0284c7", "#0369a1", "#075985", "#0c4a6e", "#082f49"),
}
_SIZES = {"2xs": 10, "xs": 11, "sm": 12, "md": 13, "base": 14, "lg": 15, "xl": 16, "2xl": 17, "3xl": 26}
_SPACES = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "2xl": 32}

for _palette, _values in (("ink", _INK), ("accent", _ACCENT)) + tuple(_STATUS.items()):
    for _shade, _value in zip(SHADES, _values):
        _add(f"{_palette}-{_shade}", "primitive", "color", _value, f"color.{_palette}",
             f"{_palette.capitalize()} {_shade}", v1=_palette in ("ink", "accent"))

_add("font-sans", "primitive", "font-stack", "Inter, ui-sans-serif, system-ui, sans-serif", "font", "Sans-serif family", v1=True)
_add("font-mono", "primitive", "font-stack", "ui-monospace, SFMono-Regular, Menlo, monospace", "font", "Monospace family", v1=True)
_add("font-display", "primitive", "font-stack", "Inter, ui-sans-serif, system-ui, sans-serif", "font", "Display family",
     note="Headings, page titles and the brand name when a component selects the display family.")

_add("size-scale", "primitive", "number", "1", "type-scale", "Type scale", min=0.85, max=1.25,
     note="Multiplies every text size, including the standard Tailwind sizes.")
for _step, _px in _SIZES.items():
    _add(f"size-{_step}", "primitive", "font-size", f"{_px}px", "type-scale", f"Text size {_step}", min=8, max=64)

for _name, _value in (("regular", 400), ("medium", 500), ("semibold", 600), ("bold", 700)):
    _add(f"weight-{_name}", "primitive", "weight", str(_value), "weight", f"Weight {_name}")
for _name, _value in (("tight", "1.25"), ("normal", "1.5"), ("relaxed", "1.72")):
    _add(f"leading-{_name}", "primitive", "number", _value, "rhythm", f"Line height {_name}", min=1, max=2.2)
for _name, _value in (("tight", "-0.01em"), ("normal", "0"), ("wide", "0.04em")):
    _add(f"tracking-{_name}", "primitive", "tracking", _value, "rhythm", f"Letter spacing {_name}", min=-0.1, max=0.5)

for _step, _px in _SPACES.items():
    _add(f"space-{_step}", "primitive", "length", f"{_px}px", "spacing", f"Space {_step}", min=0, max=96)
_add("space-compact-factor", "primitive", "number", "0.8", "spacing", "Compact density factor", min=0.5, max=1,
     note="Scales component padding and the fl-* spacing keys in compact density; raw utilities such as p-3 do not change.")

_add("radius", "primitive", "length", "8px", "shape", "Corner radius", min=0, max=16, v1=True,
     note="Base for rounded-lg; rounded-xl is 1.5x and rounded-2xl 2x.")
_add("radius-default", "primitive", "length", "4px", "shape", "Small radius (bare rounded)", min=0, max=32)
_add("radius-sm", "primitive", "length", "2px", "shape", "Extra small radius", min=0, max=32)
_add("radius-md", "primitive", "length", "6px", "shape", "Medium radius", min=0, max=32)
_add("radius-pill", "primitive", "length", "9999px", "shape", "Pill radius", min=0, max=9999)
_add("border-width", "primitive", "length", "1px", "shape", "Border width", min=0, max=8)
_add("border-width-strong", "primitive", "length", "2px", "shape", "Strong border width", min=0, max=8)

_add("shadow-sm", "primitive", "shadow", "0 1px 2px 0 rgba(0,0,0,0.05)", "elevation", "Shadow small")
_add("shadow-lg", "primitive", "shadow", "0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -4px rgba(0,0,0,0.1)", "elevation", "Shadow large")
_add("shadow-xl", "primitive", "shadow", "0 20px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1)", "elevation", "Shadow extra large")
_add("shadow-card", "primitive", "shadow", "0 1px 3px 0 rgba(16,17,23,0.06)", "elevation", "Card shadow")
_add("shadow-popover", "primitive", "shadow", "0 8px 28px -14px rgba(16,17,23,0.28)", "elevation", "Popover shadow")
_add("shadow-modal", "primitive", "shadow", "0 24px 70px -20px rgba(16,17,23,0.45)", "elevation", "Modal shadow")

_add("duration-fast", "primitive", "duration", "120ms", "motion", "Fast transition", min=0, max=1000)
_add("duration-base", "primitive", "duration", "150ms", "motion", "Base transition", min=0, max=1000)
_add("ease-standard", "primitive", "ease", "cubic-bezier(0.4,0,0.2,1)", "motion", "Standard easing")
_add("focus-ring-width", "primitive", "length", "2px", "focus", "Focus ring width", min=2, max=8)
_add("focus-ring-offset", "primitive", "length", "2px", "focus", "Focus ring offset", min=0, max=8)

# --- Semantic roles -------------------------------------------------------

_add("surface", "semantic", "color", "#ffffff", "surface", "Surface", v1=True, note="bg-white maps here.")
_add("surface-page", "semantic", "color", "{ink-50}", "surface", "Page background")
_add("surface-sunken", "semantic", "color", "{ink-100}", "surface", "Sunken surface")
_add("surface-overlay", "semantic", "color", "{surface}", "surface", "Overlay surface")
_add("surface-inverse", "semantic", "color", "{ink-950}", "surface", "Inverse surface")
_add("scrim", "semantic", "color", "{ink-950}", "surface", "Scrim")
_add("text", "semantic", "color", "{ink-900}", "text", "Text")
_add("text-muted", "semantic", "color", "{ink-600}", "text", "Muted text")
_add("text-subtle", "semantic", "color", "{ink-500}", "text", "Subtle text")
_add("text-inverse", "semantic", "color", "{surface}", "text", "Text on inverse surfaces")
_add("text-link", "semantic", "color", "{accent-600}", "text", "Link")
_add("on-primary", "semantic", "color", "#ffffff", "text", "Text on primary", v1=True, note="text-white maps here.")
_add("border", "semantic", "color", "{ink-200}", "line", "Border")
_add("border-strong", "semantic", "color", "{ink-300}", "line", "Strong border")
_add("border-input", "semantic", "color", "{ink-200}", "line", "Input border")
_add("focus-ring", "semantic", "color", "{accent-500}", "line", "Focus ring")
_add("primary", "semantic", "color", "{accent-600}", "brand", "Primary")
_add("primary-hover", "semantic", "color", "{accent-700}", "brand", "Primary hover")
_add("primary-soft", "semantic", "color", "{accent-50}", "brand", "Primary tint")
for _status in STATUSES:
    for _role, _shade in (("solid", 600), ("soft", 50), ("border", 200), ("text", 700), ("strong", 900)):
        _add(f"{_status}-{_role}", "semantic", "color", f"{{{_status}-{_shade}}}", "status",
             f"{_status.capitalize()} {_role}")

# --- Components -----------------------------------------------------------

COMPONENTS: Dict[str, str] = {}
_PROP_LABELS = {
    "bg": "Background", "fg": "Text", "border": "Border color", "border-width": "Border width",
    "radius": "Corner radius", "shadow": "Shadow", "pad-x": "Horizontal padding", "pad-y": "Vertical padding",
    "pad": "Padding", "gap": "Gap", "height": "Minimum height", "size": "Text size", "weight": "Font weight",
    "transform": "Text case", "variant": "Style", "hover-bg": "Hover background", "hover-fg": "Hover text",
    "active-bg": "Active background", "active-fg": "Active text", "disabled-bg": "Disabled background",
    "disabled-fg": "Disabled text", "font": "Font family", "tracking": "Letter spacing", "align": "Alignment",
    "leading": "Line height", "scrim-alpha": "Scrim opacity", "width": "Width", "position": "Position",
}
_COLOR_ENUM_NOTE = "Resolved from the sidebar tone unless set."
_TRANSFORMS = ("none", "uppercase", "capitalize")


def _c(component: str, prop: str, type_: str, default: Any, part: str = "", label: str = "",
       options: Tuple[str, ...] = (), min_: Optional[float] = None, max_: Optional[float] = None,
       tone: Optional[str] = None, note: str = "") -> None:
    name = "-".join(x for x in (component, part, prop) if x)
    if type_ == "font-size" and min_ is None:
        min_, max_ = 8, 64
    text = label or (" ".join(x for x in (part.capitalize().replace("-", " "), _PROP_LABELS.get(prop, prop)) if x))
    _add(name, "component", type_, default, "component." + component, text, min=min_, max=max_,
         options=options, component=component, tone=tone, note=note)


def _component(component: str, label: str) -> None:
    COMPONENTS[component] = label


def _variant(component: str, options: Tuple[str, ...], default: str) -> None:
    _c(component, "variant", "enum", default, options=options)


_component("button", "Button")
for _tone, _bg, _fg, _bd, _bw, _hover, _dbg, _dfg in (
    ("primary", "{primary}", "{on-primary}", "{primary}", "0px", "{primary-hover}", "{ink-300}", "{on-primary}"),
    ("secondary", "{surface}", "{ink-700}", "{border}", "{border-width}", "{surface-page}", "{surface}", "{ink-400}"),
    ("danger", "{surface}", "{danger-text}", "{danger-border}", "{border-width}", "{danger-soft}", "{surface}", "{ink-400}"),
):
    _c("button", "bg", "color", _bg, _tone)
    _c("button", "fg", "color", _fg, _tone)
    _c("button", "border", "color", _bd, _tone)
    _c("button", "border-width", "length", _bw, _tone, min_=0, max_=8)
    _c("button", "hover-bg", "color", _hover, _tone)
    _c("button", "disabled-bg", "color", _dbg, _tone)
    _c("button", "disabled-fg", "color", _dfg, _tone)
_c("button", "radius", "length", "{radius}", min_=0, max_=9999)
_c("button", "pad-x", "length", "14px", min_=0, max_=48)
_c("button", "pad-y", "length", "{space-sm}", min_=0, max_=32)
_c("button", "height", "length", "0px", min_=32, max_=96, note="Unset by default; an explicit height must be at least 32px.")
_c("button", "size", "font-size", "{size-md}")
_c("button", "weight", "weight", "{weight-medium}")
_c("button", "transform", "enum", "none", options=_TRANSFORMS)
_c("button", "shadow", "shadow", "none")
_variant("button", ("solid", "outline"), "solid")

_component("input", "Input, select and textarea")
_c("input", "bg", "color", "{surface}")
_c("input", "fg", "color", "{text}")
_c("input", "placeholder", "color", "{ink-400}", label="Placeholder")
_c("input", "border", "color", "{border-input}")
_c("input", "border-width", "length", "{border-width}", min_=0, max_=8)
_c("input", "focus-border", "color", "{focus-ring}", label="Focus border")
_c("input", "focus-ring", "color", "{focus-ring}", label="Focus ring")
_c("input", "focus-ring-alpha", "number", "0.2", min_=0, max_=1, label="Focus ring opacity")
_c("input", "radius", "length", "{radius}", min_=0, max_=9999)
_c("input", "pad-x", "length", "{space-md}", min_=0, max_=48)
_c("input", "pad-y", "length", "{space-sm}", min_=0, max_=32)
_c("input", "height", "length", "0px", min_=32, max_=96, note="Unset by default; an explicit height must be at least 32px.")
_c("input", "size", "font-size", "{size-md}+0.5px")
_c("input", "disabled-bg", "color", "{surface-page}")
_c("input", "disabled-fg", "color", "{text-subtle}")
_variant("input", ("outline", "filled"), "outline")

_component("choice", "Checkbox, radio and range")
_c("choice", "accent", "color", "{primary}", label="Accent")
_c("choice", "track", "color", "{border}", label="Track")
_c("choice", "thumb", "color", "{surface}", label="Thumb")

_component("field", "Form field")
_c("field", "fg", "color", "{ink-700}", "label")
_c("field", "size", "font-size", "{size-sm}", "label")
_c("field", "weight", "weight", "{weight-medium}", "label")
_c("field", "fg", "color", "{text-subtle}", "hint")
_c("field", "size", "font-size", "{size-xs}+0.5px", "hint")
_c("field", "error-fg", "color", "{danger-text}", label="Error text")
_c("field", "gap", "length", "6px", min_=0, max_=32)
_variant("field", ("stacked", "inline"), "stacked")

_component("card", "Card")
_c("card", "bg", "color", "{surface}")
_c("card", "border", "color", "{border}")
_c("card", "border-width", "length", "{border-width}", min_=0, max_=8)
_c("card", "radius", "length", "{radius}*1.5", min_=0, max_=9999)
_c("card", "shadow", "shadow", "none")
_c("card", "pad", "length", "{space-lg}", min_=0, max_=64)
_c("card", "size", "font-size", "{size-base}", "title")
_c("card", "weight", "weight", "{weight-semibold}", "title")
_variant("card", ("bordered", "raised"), "bordered")

_component("page-header", "Page header")
_c("page-header", "size", "font-size", "20px", "title")
_c("page-header", "weight", "weight", "{weight-semibold}", "title")
_c("page-header", "fg", "color", "{text}", "title")
_c("page-header", "font", "enum", "sans", "title", options=("sans", "display"))
_c("page-header", "transform", "enum", "none", "title", options=_TRANSFORMS)
_c("page-header", "tracking", "tracking", "{tracking-normal}", "title")
_c("page-header", "fg", "color", "{text-muted}", "sub")
_c("page-header", "size", "font-size", "{size-base}", "sub")
_c("page-header", "gap", "length", "{space-lg}", min_=0, max_=64)
_c("page-header", "align", "enum", "start", options=("start", "center"))
_c("page-header", "rule-color", "color", "{border-strong}", label="Rule color")
_variant("page-header", ("plain", "ruled"), "plain")

_component("table", "Table")
_c("table", "bg", "color", "{surface-sunken}", "head")
_c("table", "fg", "color", "{text-muted}", "head")
_c("table", "size", "font-size", "{size-sm}", "head")
_c("table", "weight", "weight", "{weight-semibold}", "head")
_c("table", "transform", "enum", "none", "head", options=_TRANSFORMS)
_c("table", "bg", "color", "{surface}", "row")
_c("table", "stripe-bg", "color", "{surface-page}", label="Striped row background")
_c("table", "hover-bg", "color", "{surface-page}", "row")
_c("table", "border", "color", "{border}")
_c("table", "pad-x", "length", "{space-md}", "cell", min_=0, max_=48)
_c("table", "pad-y", "length", "{space-sm}", "cell", min_=0, max_=32)
_c("table", "size", "font-size", "{size-md}")
_c("table", "radius", "length", "{radius}", min_=0, max_=9999)

_component("tabs", "Tabs")
_c("tabs", "fg", "color", "{text-muted}")
_c("tabs", "active-fg", "color", "{text}")
_c("tabs", "active-indicator", "color", "{primary}", label="Active indicator")
_c("tabs", "hover-bg", "color", "{surface-page}")
_c("tabs", "border", "color", "{border}")
_c("tabs", "size", "font-size", "{size-md}")
_c("tabs", "weight", "weight", "{weight-medium}")
_c("tabs", "pad-x", "length", "{space-md}", min_=0, max_=48)
_c("tabs", "pad-y", "length", "{space-sm}", min_=0, max_=32)
_variant("tabs", ("underline", "pill", "boxed"), "underline")

_component("badge", "Badge")
_c("badge", "radius", "length", "{radius-pill}", min_=0, max_=9999)
_c("badge", "pad-x", "length", "{space-sm}", min_=0, max_=32)
_c("badge", "pad-y", "length", "2px", min_=0, max_=16)
_c("badge", "size", "font-size", "{size-xs}")
_c("badge", "weight", "weight", "{weight-medium}")
_c("badge", "transform", "enum", "none", options=_TRANSFORMS)

_component("modal", "Modal")
_c("modal", "bg", "color", "{surface-overlay}")
_c("modal", "border", "color", "{border}")
_c("modal", "border-width", "length", "{border-width}", min_=0, max_=8)
_c("modal", "radius", "length", "{radius}*2", min_=0, max_=9999)
_c("modal", "shadow", "shadow", "{shadow-modal}")
_c("modal", "pad", "length", "{space-xl}", min_=0, max_=64)
_c("modal", "size", "font-size", "{size-xl}", "title")
_c("modal", "weight", "weight", "{weight-semibold}", "title")
_c("modal", "scrim-alpha", "number", "0.45", min_=0, max_=0.8, label="Scrim opacity")

_component("drawer", "Drawer")
_c("drawer", "bg", "color", "{surface}")
_c("drawer", "border", "color", "{border}")
_c("drawer", "shadow", "shadow", "{shadow-xl}")
_c("drawer", "width", "length", "300px", min_=240, max_=480)
_c("drawer", "scrim-alpha", "number", "0.45", min_=0, max_=0.8, label="Scrim opacity")

_component("toast", "Toast")
for _tone, _border, _bg, _fg in (
    ("done", "{success-border}", "{success-soft}", "{success-strong}"),
    ("error", "{warning-border}", "{warning-soft}", "{warning-strong}"),
    ("notice", "{accent-200}", "{primary-soft}", "{accent-900}"),
    ("working", "{border}", "{surface}", "{ink-800}"),
):
    _c("toast", "border", "color", _border, _tone)
    _c("toast", "bg", "color", _bg, _tone)
    _c("toast", "fg", "color", _fg, _tone)
_c("toast", "radius", "length", "{radius}*1.5", min_=0, max_=9999)
_c("toast", "shadow", "shadow", "{shadow-lg}")
_c("toast", "size", "font-size", "{size-sm}+0.5px")
_c("toast", "position", "enum", "bottom-left",
   options=("bottom-left", "bottom-right", "top-left", "top-right", "top-center", "bottom-center"))

_component("notice", "Notice")
for _tone, _border, _bg, _fg in (
    ("bad", "{danger-border}", "{danger-soft}", "{danger-strong}"),
    ("good", "{success-border}", "{success-soft}", "{success-strong}"),
    ("info", "{ink-200}", "{ink-50}", "{ink-700}"),
):
    _c("notice", "border", "color", _border, _tone)
    _c("notice", "bg", "color", _bg, _tone)
    _c("notice", "fg", "color", _fg, _tone)
_c("notice", "radius", "length", "{radius}", min_=0, max_=9999)
_c("notice", "pad-x", "length", "{space-md}", min_=0, max_=48)
_c("notice", "pad-y", "length", "{space-sm}", min_=0, max_=32)
_c("notice", "border-width", "length", "{border-width}", min_=0, max_=8)
_c("notice", "size", "font-size", "{size-sm}+0.5px")
_variant("notice", ("soft", "outline", "solid"), "soft")

_component("sidebar", "Sidebar (navigation rail)")
_c("sidebar", "tone", "enum", "dark", options=("dark", "light"))
_c("sidebar", "bg", "color", {"dark": "{surface-inverse}", "light": "{surface}"}, tone="sidebar-tone", note=_COLOR_ENUM_NOTE)
_c("sidebar", "border", "color", "{border-strong}")
_c("sidebar", "border-width", "length", "0px", min_=0, max_=8,
   note="A flush sidebar draws a separator of at least the border-width primitive.")
_c("sidebar", "radius", "length", "{radius}*2", min_=0, max_=9999)
_c("sidebar", "shadow", "shadow", "none")
_c("sidebar", "pad-y", "length", "{space-md}", min_=0, max_=48)
_c("sidebar", "pad-x", "length", "0px", min_=0, max_=48)
_c("sidebar", "gap", "length", "{space-xs}", min_=0, max_=32)
_c("sidebar", "bg", "color", "{primary}", "brand")
_c("sidebar", "fg", "color", "{on-primary}", "brand")
_c("sidebar", "radius", "length", "{radius}", "brand", min_=0, max_=9999)

_component("nav-item", "Navigation item")
_c("nav-item", "fg", "color", {"dark": "{ink-300}", "light": "{ink-800}"}, tone="sidebar-tone", note=_COLOR_ENUM_NOTE)
_c("nav-item", "hover-bg", "color", {"dark": "{ink-800}", "light": "{ink-100}"}, tone="sidebar-tone", note=_COLOR_ENUM_NOTE)
_c("nav-item", "hover-fg", "color", {"dark": "{on-primary}", "light": "{ink-900}"}, tone="sidebar-tone", note=_COLOR_ENUM_NOTE)
_c("nav-item", "active-bg", "color", "{ink-800}")
_c("nav-item", "active-fg", "color", "{on-primary}")
_c("nav-item", "focus", "color", "{primary}", label="Focus outline")
_c("nav-item", "radius", "length", "{radius}*1.5", min_=0, max_=9999)
_c("nav-item", "height", "length", "44px", min_=32, max_=96)
_c("nav-item", "pad-x", "length", "{space-md}", min_=0, max_=48)
_c("nav-item", "gap", "length", "{space-md}", min_=0, max_=48)
_c("nav-item", "size", "font-size", "{size-base}")
_c("nav-item", "weight", "weight", "{weight-medium}")
_c("nav-item", "transform", "enum", "none", options=_TRANSFORMS)
_variant("nav-item", ("square", "pill"), "square")

_component("navbar", "Navbar")
_c("navbar", "tone", "enum", "dark", options=("dark", "light"))
_c("navbar", "bg", "color", {"dark": "{surface-inverse}", "light": "{surface}"}, tone="navbar-tone", note="Resolved from the navbar tone unless set.")
_c("navbar", "fg", "color", {"dark": "{on-primary}", "light": "{text}"}, tone="navbar-tone", note="Resolved from the navbar tone unless set.")
_c("navbar", "border", "color", "{border-strong}")
_c("navbar", "border-width", "length", "{border-width}", min_=0, max_=8)
_c("navbar", "shadow", "shadow", "none")
_c("navbar", "pad-x", "length", "{space-lg}", min_=0, max_=64)
_c("navbar", "size", "font-size", "{size-base}", "brand")
_c("navbar", "weight", "weight", "{weight-semibold}", "brand")
_c("navbar", "font", "enum", "sans", "brand", options=("sans", "display"))

_component("workspace", "Workspace")
_c("workspace", "bg", "color", "{surface-page}")
_c("workspace", "bg", "color", "{surface}", "panel")
_c("workspace", "border", "color", "{border}", "panel")
_c("workspace", "radius", "length", "{radius}*2", "panel", min_=0, max_=9999)
_c("workspace", "shadow", "shadow", "{shadow-card}", "panel")

_component("conversation-list", "Conversation list")
_c("conversation-list", "bg", "color", "{surface}")
_c("conversation-list", "border", "color", "{border}")
_c("conversation-list", "fg", "color", "{ink-700}", "item")
_c("conversation-list", "hover-bg", "color", "{surface-page}", "item")
_c("conversation-list", "active-bg", "color", "{surface-sunken}", "item")
_c("conversation-list", "size", "font-size", "{size-md}", "item")

_component("chat-message", "Chat message")
_c("chat-message", "bg", "color", "{ink-900}", "user")
_c("chat-message", "fg", "color", "{on-primary}", "user")
_c("chat-message", "radius", "length", "{radius}*2", "user", min_=0, max_=9999)
_c("chat-message", "pad-x", "length", "{space-lg}", "user", min_=0, max_=48)
_c("chat-message", "pad-y", "length", "10px", "user", min_=0, max_=32)
_c("chat-message", "size", "font-size", "{size-base}+0.5px", "user")
_c("chat-message", "fg", "color", "{text}", "assistant")
_c("chat-message", "rule-color", "color", "{border-strong}", label="Rule color")
_c("chat-message", "leading", "number", "1.6", min_=1, max_=2.2)
_variant("chat-message", ("bubble", "ruled"), "bubble")

_component("composer", "Composer")
_c("composer", "bg", "color", "{surface}")
_c("composer", "border", "color", "{border-input}")
_c("composer", "border-width", "length", "{border-width}", min_=0, max_=8)
_c("composer", "radius", "length", "{radius}*1.5", min_=0, max_=9999)
_c("composer", "shadow", "shadow", "{shadow-card}")
_c("composer", "pad", "length", "{space-md}", min_=0, max_=48)
_variant("composer", ("panel", "plain"), "panel")

_component("prose", "Answer text")
_c("prose", "size", "font-size", "{size-lg}")
_c("prose", "leading", "number", "{leading-relaxed}", min_=1, max_=2.2)
_c("prose", "fg", "color", "{ink-800}")
_c("prose", "link-fg", "color", "{text-link}", label="Link")
_c("prose", "code-bg", "color", "{surface-sunken}", label="Code background")
_c("prose", "code-fg", "color", "{text}", label="Code text")
_c("prose", "heading-weight", "weight", "{weight-semibold}")
_c("prose", "table-head-bg", "color", "{surface-sunken}", label="Table header background")

_component("link", "Link")
_c("link", "fg", "color", "{text-link}")
_c("link", "hover-fg", "color", "{primary-hover}")
_c("link", "underline", "enum", "hover", options=("none", "hover", "always"))

_component("divider", "Divider")
_c("divider", "color", "color", "{border}", label="Color")
_c("divider", "width", "length", "{border-width}", min_=0, max_=8)

_component("progress", "Progress")
_c("progress", "track", "color", "{surface-sunken}", label="Track")
_c("progress", "bar", "color", "{primary}", label="Bar")

_component("citation", "Citation")
_c("citation", "bg", "color", "{primary-soft}")
_c("citation", "fg", "color", "{accent-700}")
_c("citation", "active-bg", "color", "{accent-100}")
_c("citation", "radius", "length", "{radius-md}", min_=0, max_=9999)

_component("splitter", "Splitter")
_c("splitter", "handle", "color", "{border}", label="Handle")
_c("splitter", "hover", "color", "{accent-400}", label="Handle hover")

_component("gate", "Sign-in card")
_c("gate", "bg", "color", "{surface}")
_c("gate", "border", "color", "{border}")
_c("gate", "radius", "length", "{radius}*2", min_=0, max_=9999)
_c("gate", "max-width", "length", "416px", min_=320, max_=640)
_c("gate", "size", "font-size", "{size-2xl}", "title")
_c("gate", "bg", "color", "{surface-page}", "page")

_component("scrollbar", "Scrollbar")
_c("scrollbar", "thumb", "color", "{ink-200}", label="Thumb")
_c("scrollbar", "track", "color", "{surface}", label="Track")
_c("scrollbar", "width", "length", "8px", min_=4, max_=16)

_component("skeleton", "Loading skeleton")
_c("skeleton", "base", "color", "{ink-100}", label="Base")
_c("skeleton", "highlight", "color", "{ink-50}", label="Highlight")

TOKENS: Tuple[Token, ...] = tuple(_TOKENS)
INDEX: Dict[str, Token] = {token.name: token for token in TOKENS}
assert len(INDEX) == len(TOKENS), "duplicate token names"

PRIMITIVES = tuple(t for t in TOKENS if t.layer == "primitive")
SEMANTIC = tuple(t for t in TOKENS if t.layer == "semantic")
COMPONENT_TOKENS = tuple(t for t in TOKENS if t.layer == "component")
V1_TOKEN_NAMES = frozenset(t.name for t in TOKENS if t.v1)

# --- Layout ---------------------------------------------------------------

# Each entry: type "enum" (options), "int" (min/max, optional zero), "bool", "step".
LAYOUT_SPEC: Dict[str, Any] = {
    "density": {"type": "enum", "options": ["comfortable", "compact"], "default": "comfortable"},
    "scroll": {"type": "enum", "options": ["panel", "page"], "default": "panel"},
    "sidebar": {
        "side": {"type": "enum", "options": ["left", "right", "hidden"], "default": "left"},
        "style": {"type": "enum", "options": ["rail", "panel"], "default": "rail"},
        "surface": {"type": "enum", "options": ["floating", "flush"], "default": "floating"},
        "width": {"type": "int", "min": 56, "max": 320, "default": 56,
                  "note": "56 for rail, 224 for panel. Warns when a rail is wider than 120 or a panel narrower than 160."},
        "behavior": {"type": "enum", "options": ["fixed", "sticky", "static"], "default": "fixed"},
        "collapse_below": {"type": "int", "min": 480, "max": 1280, "default": 760},
    },
    "navbar": {
        "position": {"type": "enum", "options": ["hidden", "top", "bottom"], "default": "hidden"},
        "behavior": {"type": "enum", "options": ["fixed", "sticky", "static"], "default": "fixed"},
        "height": {"type": "int", "min": 40, "max": 96, "default": 56},
        "align": {"type": "enum", "options": ["start", "center", "between"], "default": "between"},
        "show_brand": {"type": "bool", "default": True},
    },
    "content": {
        "max_width": {"type": "int", "min": 640, "max": 1920, "zero": True, "default": 0,
                      "note": "0 means no limit. Applies to page-scroll routes only."},
        "align": {"type": "enum", "options": ["start", "center"], "default": "start"},
        "padding": {"type": "step", "options": list(STEPS), "default": "md"},
        "gap": {"type": "step", "options": list(STEPS), "default": "md"},
    },
}
# Panel-style sidebars default wider.
PANEL_SIDEBAR_WIDTH = 224


def default_layout(style: str = "rail") -> dict:
    layout: Dict[str, Any] = {}
    for key, spec in LAYOUT_SPEC.items():
        layout[key] = ({name: field["default"] for name, field in spec.items()} if "type" not in spec else spec["default"])
    layout["sidebar"]["style"] = style
    layout["sidebar"]["width"] = PANEL_SIDEBAR_WIDTH if style == "panel" else 56
    return layout


# --- Contrast -------------------------------------------------------------

# (id, foreground, background, minimum ratio, level). Hard errors apply to v2
# manifests only; v1 manifests are never re-judged against them. The two
# "legacy" pairs are the v1 validator's own, so project_v1() always passes it.
CONTRAST_PAIRS: Tuple[Tuple[str, str, str, float, str], ...] = (
    ("legacy-ink-900-on-surface", "ink-900", "surface", 4.5, "error"),
    ("legacy-on-primary-on-accent-600", "on-primary", "accent-600", 4.5, "error"),
    ("text-on-surface", "text", "surface", 4.5, "error"),
    ("text-on-surface-page", "text", "surface-page", 4.5, "error"),
    ("text-on-surface-sunken", "text", "surface-sunken", 4.5, "error"),
    ("text-muted-on-surface", "text-muted", "surface", 4.5, "error"),
    ("text-muted-on-surface-page", "text-muted", "surface-page", 4.5, "error"),
    ("text-inverse-on-surface-inverse", "text-inverse", "surface-inverse", 4.5, "error"),
    ("text-link-on-surface", "text-link", "surface", 4.5, "error"),
    ("on-primary-on-primary", "on-primary", "primary", 4.5, "error"),
    ("success-text-on-soft", "success-text", "success-soft", 4.5, "error"),
    ("warning-text-on-soft", "warning-text", "warning-soft", 4.5, "error"),
    ("danger-text-on-soft", "danger-text", "danger-soft", 4.5, "error"),
    ("info-text-on-soft", "info-text", "info-soft", 4.5, "error"),
    ("focus-ring-on-surface", "focus-ring", "surface", 3.0, "error"),
    # The default input border (ink-200) is about 1.4:1, so this can only warn.
    ("border-input-on-surface", "border-input", "surface", 3.0, "warning"),
)
# Component pairs checked as warnings: (id, fg token, bg token).
COMPONENT_CONTRAST_PAIRS: Tuple[Tuple[str, str, str], ...] = (
    ("button-primary", "button-primary-fg", "button-primary-bg"),
    ("button-secondary", "button-secondary-fg", "button-secondary-bg"),
    ("button-danger", "button-danger-fg", "button-danger-bg"),
    ("input", "input-fg", "input-bg"),
    ("input-placeholder", "input-placeholder", "input-bg"),
    ("input-disabled", "input-disabled-fg", "input-disabled-bg"),
    ("table-head", "table-head-fg", "table-head-bg"),
    ("tabs-active", "tabs-active-fg", "surface"),
    ("badge-text", "text", "surface"),
    ("toast-done", "toast-done-fg", "toast-done-bg"),
    ("toast-error", "toast-error-fg", "toast-error-bg"),
    ("toast-notice", "toast-notice-fg", "toast-notice-bg"),
    ("toast-working", "toast-working-fg", "toast-working-bg"),
    ("notice-bad", "notice-bad-fg", "notice-bad-bg"),
    ("notice-good", "notice-good-fg", "notice-good-bg"),
    ("notice-info", "notice-info-fg", "notice-info-bg"),
    ("nav-item-active", "nav-item-active-fg", "nav-item-active-bg"),
    ("chat-message-user", "chat-message-user-fg", "chat-message-user-bg"),
)
# Bars whose nav-item colours are judged against the bar background (errors).
NAV_BARS = (("sidebar", "sidebar-tone", "sidebar-bg"), ("navbar", "navbar-tone", "navbar-bg"))

SELF_REFERENCE_DEPTH = 3
TOP_LEVEL_KEYS = ("api_version", "registry_revision", "id", "version", "label", "color_scheme", "tokens", "layout")
LAYER_KEYS = ("primitives", "semantic", "components")


def for_revision(revision: int) -> Dict[str, Token]:
    """The tokens a theme targeting `revision` may use."""
    return {name: token for name, token in INDEX.items() if token.since <= revision}


def webfonts() -> List[dict]:
    """The reviewed allow-list of webfont families the host may load (registry_data/fonts.json)."""
    return json.loads(files("fastlanelabs_sdk.registry_data").joinpath("fonts.json").read_text())["fonts"]


def registry_json() -> dict:
    """The registry as JSON-ready data (generated into registry_data and frontend)."""
    return {
        "registry_revision": REGISTRY_REVISION,
        "layers": list(LAYERS),
        "types": list(TYPES),
        "shades": list(SHADES),
        "size_steps": list(SIZE_STEPS),
        "space_steps": list(SPACE_STEPS),
        "steps": list(STEPS),
        "v1_tokens": sorted(V1_TOKEN_NAMES),
        "components": [{"id": key, "label": label} for key, label in COMPONENTS.items()],
        "tokens": [token.as_dict() for token in TOKENS],
        "layout": LAYOUT_SPEC,
        "layout_defaults": default_layout("rail"),
        "panel_sidebar_width": PANEL_SIDEBAR_WIDTH,
        "contrast_pairs": [{"id": i, "fg": f, "bg": b, "min": m, "level": l} for i, f, b, m, l in CONTRAST_PAIRS],
        "component_contrast_pairs": [{"id": i, "fg": f, "bg": b} for i, f, b in COMPONENT_CONTRAST_PAIRS],
        "nav_bars": [{"bar": a, "tone": b, "bg": c} for a, b, c in NAV_BARS],
        "reference_depth": SELF_REFERENCE_DEPTH,
        "top_level_keys": list(TOP_LEVEL_KEYS),
        "webfonts": webfonts(),
    }
