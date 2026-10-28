"""Write the golden fixtures that keep the Python and TypeScript theme resolvers in step.

    python scripts/gen_theme_golden.py            # rewrite tests/golden/theme-resolve/*.json
    python scripts/gen_theme_golden.py --check    # exit 1 if a fixture is stale

Each fixture holds an input manifest with the expected resolve and contrast results; a theme with a dark
palette also holds the dark resolve, the check and the derived dark block. pytest recomputes
them in Python and, where node and esbuild exist, runs frontend/theme-resolve.ts
over the same files (tests/golden/run_resolve.mjs).

tests/golden/theme-resolve holds themes without a layout tree or a brand: tokens, dark palettes and layout options.
tests/golden/brand holds themes that carry a brand (a logo with a mark and a tagline, a logo alone, a logo with a
logo_dark for dark backgrounds, and one whose brand is invalid): the resolved theme with its normalised `brand`, the check result and the brand's own validation.
tests/golden/layout-tree holds the default theme, the six vocabulary presets and a tree with a
`custom` region, with their resolved trees and validation results. tests/golden/shell-from-layout.json maps the layout options
of every theme-resolve golden (and the registry's and the release's default layouts) to the tree they describe.
"""
from pathlib import Path
import argparse
import base64
import copy
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastlanelabs_sdk import theme_registry as registry  # noqa: E402
from fastlanelabs_sdk import themes  # noqa: E402

# Themes the theme builder produced for the two brands with the brightest dark accent tints (a neon green, a yellow):
# the dark text steps are solved against those tints (see tests/test_themes_palette.py).
BRIGHT_FIXTURES = ROOT / "tests/fixtures/themes-bright"
GOLDEN = ROOT / "tests/golden/theme-resolve"
TREES = ROOT / "tests/golden/layout-tree"
FROM_LAYOUT = ROOT / "tests/golden/shell-from-layout.json"
BRANDS = ROOT / "tests/golden/brand"


def load_bright(name):
    return json.loads((BRIGHT_FIXTURES / name).read_text())


def inputs():
    custom = themes.default_theme_v2("client-acme", "1.2.0", "Acme")
    custom["tokens"]["primitives"].update({"font-sans": "Roboto, Arial, sans-serif", "radius": "4px", "size-scale": "1.1"})
    custom["tokens"]["semantic"].update({"primary": "{accent-700}", "text-link": "#1c39ae", "surface-page": "{ink-100}"})
    custom["tokens"]["components"].update({
        "button-radius": "{radius-pill}", "button-transform": "uppercase", "button-height": "40px",
        "button-size": "{size-lg}", "page-header-title-size": "22px", "page-header-title-font": "display",
        "sidebar-tone": "light", "navbar-tone": "dark", "navbar-bg": "{ink-900}", "toast-position": "top-right",
        "card-shadow": "{shadow-card}", "modal-scrim-alpha": "0.6", "nav-item-active-bg": "{primary}",
    })
    custom["layout"].update({"scroll": "page", "density": "compact"})
    custom["layout"]["sidebar"].update({"side": "right", "style": "panel", "width": 240, "behavior": "sticky", "surface": "flush"})
    custom["layout"]["navbar"].update({"position": "top", "behavior": "sticky", "align": "center", "show_brand": False})
    custom["layout"]["content"].update({"max_width": 1200, "align": "center", "padding": "lg", "gap": "sm"})
    # A brand that sets literals outside its ramps, a custom shadow and an explicit navbar: the cases a
    # derived dark palette must map rather than reverse.
    warm = themes.default_theme_v2("client-warm", "1.0.0", "Warm")
    warm["tokens"]["primitives"].update({
        "accent-500": "#0d9488", "accent-600": "#0f766e", "accent-700": "#115e59", "shadow-card": "0 2px 8px 0 rgba(60,40,10,0.08)",
        "ink-50": "#faf8f5", "ink-100": "#f1ede6"})
    warm["tokens"]["semantic"].update({"surface": "#fffdf9", "text-link": "#b45309", "primary": "{accent-700}", "scrim": "#2a2118"})
    warm["tokens"]["components"].update({"button-secondary-border": "#c9bfae", "card-shadow": "0 1px 4px 0 rgba(0,0,0,0.12)",
                                         "sidebar-tone": "light", "navbar-bg": "{ink-900}", "toast-position": "top-center",
                                         "navbar-fg": "{text-inverse}", "nav-item-active-fg": "{text-inverse}", "chat-message-user-bg": "{accent-800}",
                                         "chat-message-user-fg": "{text-inverse}", "nav-item-hover-fg": "{text-inverse}"})
    warm["layout"]["navbar"].update({"position": "top"})
    warm_auto = copy.deepcopy(warm)
    warm_auto["color_scheme"], warm_auto["modes"] = "auto", {"dark": themes.derive_dark(warm)}
    custom_auto = copy.deepcopy(custom)
    custom_auto["color_scheme"], custom_auto["modes"] = "auto", {"dark": themes.derive_dark(custom)}
    # A hand-tuned dark palette: derived, then adjusted (the accent stays saturated, a warm surface).
    tuned = themes.default_theme_v2("client-tuned", "1.0.0", "Tuned", scheme="auto")
    tuned["modes"]["dark"]["primitives"].update({"accent-600": "#2b57db", "accent-500": "#4b74ee", "ink-50": "#0b0c10"})
    tuned["modes"]["dark"]["semantic"].update({"surface": "#14161d", "on-primary": "#ffffff", "text-link": "#8eb5ff"})
    tuned["modes"]["dark"]["components"].update({"button-primary-bg": "{accent-500}", "sidebar-bg": "#0b0c10"})
    # The optional roles set to something other than their fallback, and a dark palette derived from them.
    roles = themes.default_theme_v2("client-roles", "1.0.0", "Roles")
    roles["tokens"]["primitives"].update({"accent-600": "#b45309", "accent-500": "#d97706", "accent-700": "#92400e"})
    roles["tokens"]["semantic"].update({"accent-text": "{accent-700}", "accent-ui": "{accent-500}", "inverse": "{ink-800}",
                                        "on-inverse": "#ffffff"})
    roles_auto = copy.deepcopy(roles)
    roles_auto["color_scheme"], roles_auto["modes"] = "auto", {"dark": themes.derive_dark(roles)}
    dark_only = copy.deepcopy(warm_auto)
    dark_only["id"], dark_only["color_scheme"] = "client-warm-dark", "dark"
    dark_only["tokens"] = {key: dict(dark_only["tokens"][key], **dark_only["modes"]["dark"][key]) for key in ("primitives", "semantic", "components")}
    del dark_only["modes"]
    return [
        ("default-v2", themes.default_theme_v2()),
        ("custom-v2", custom),
        ("default-auto-v2", themes.default_theme_v2("fastlane", "2.1.0", "Fastlane", scheme="auto")),
        ("default-dark-v2", themes.default_theme_v2("fastlane-dark", "2.1.0", "Fastlane Dark", scheme="dark")),
        ("warm-auto-v2", warm_auto),
        ("custom-auto-v2", custom_auto),
        ("tuned-auto-v2", tuned),
        ("roles-auto-v2", roles_auto),
        ("warm-dark-v2", dark_only),
        ("green-auto-v2", load_bright("green-auto.json")),
        ("yellow-dark-auto-v2", load_bright("yellow-dark-auto.json")),
    ]


def compute(manifest):
    result = {"input": manifest}
    result["resolve"] = themes.resolve_theme(manifest)
    result["contrast"] = themes.contrast_report(manifest)
    if manifest.get("color_scheme", "light") != "light":
        result["resolve_dark"] = themes.resolve_theme(manifest, "dark")
        result["check"] = themes.check_theme(manifest)
        result["derive"] = themes.derive_dark(manifest) if manifest["color_scheme"] == "auto" else None
    return json.loads(json.dumps(result))


# --- The layout tree ----------------------------------------------------------------------------

def tree_theme(theme_id, label, preset=None, layout=None, shell=None):
    """A default theme whose layout options are what a host without the tree renderer falls back to, with `shell` set to a preset's
    tree (or to `shell`). The theme builder derives the options from the tree; here they are written out."""
    theme = themes.default_theme_v2(theme_id, "1.0.0", label)
    theme["layout"].update(layout or {})
    if preset is not None:
        shell = next(item["tree"] for item in registry.layout_vocabulary()["presets"] if item["id"] == preset)
    if shell is not None:
        theme["layout"]["shell"] = copy.deepcopy(shell)
    return theme


def tree_inputs():
    panel = registry.default_layout("panel")["sidebar"]
    flush = {"sidebar": dict(panel, surface="flush")}
    right = {"sidebar": dict(panel, side="right")}
    top = {"sidebar": dict(registry.default_layout()["sidebar"], side="hidden"),
           "navbar": dict(registry.default_layout()["navbar"], position="top", height=64)}
    # What a host without the renderer falls back to for launcher-header: the same slim top bar (56px), no sidebar.
    launcher = {"sidebar": dict(registry.default_layout()["sidebar"], side="hidden"),
                "navbar": dict(registry.default_layout()["navbar"], position="top", height=56)}
    console = {"sidebar": dict(panel, surface="flush", width=240), "navbar": dict(registry.default_layout()["navbar"], position="top")}
    # A tree no preset draws: a sticky header band with a custom module, a title and a spacer, a content column capped at
    # 1200px with a custom footer, and the navigation in a floating panel on the right that collapses below 900px.
    # scroll page, so the sticky container has an effect.
    custom = {"version": 1, "root": {"type": "container", "direction": "column", "children": [
        {"type": "container", "direction": "row", "chrome": "navbar", "surface": "flush", "size": {"basis": 72}, "behavior": "sticky",
         "align": "center", "padding": "md", "gap": "md", "justify": "start", "children": [
             {"type": "region", "region": "brand", "options": {"name": "show"}},
             {"type": "region", "region": "custom", "options": {"module": "client-acme/header@1", "props": {"tagline": "Since 1952", "accent": True, "weight": 2}}},
             {"type": "spacer"},
             {"type": "region", "region": "title", "options": {"size": "lg"}},
             {"type": "region", "region": "actions", "options": {"style": "icons", "orientation": "horizontal"}}]},
        {"type": "container", "direction": "row", "size": {"basis": "fill"}, "gap": "lg", "padding": "lg", "children": [
            {"type": "container", "direction": "column", "size": {"basis": "fill", "max": 1200}, "justify": "start", "children": [
                {"type": "region", "region": "content", "size": {"basis": "fill"}},
                {"type": "region", "region": "custom", "options": {"module": "client-acme/footer@2"}}]},
            {"type": "container", "direction": "column", "chrome": "sidebar", "surface": "floating", "size": {"basis": 240, "min": 200},
             "collapse_below": 900, "padding": "sm", "gap": "xs", "children": [
                {"type": "region", "region": "navigation", "size": {"basis": "fill"},
                 "options": {"style": "labels", "groups": "primary", "overflow": "wrap"}}]}]}]}}
    custom_layout = {"scroll": "page", "sidebar": dict(panel, side="right", behavior="sticky"),
                     "navbar": dict(registry.default_layout()["navbar"], position="top", behavior="sticky", height=72)}
    return [
        ("default-v4", themes.default_theme_v2()),
        ("preset-panel-flush-v4", tree_theme("client-panel-flush", "Panel flush", "panel-flush", flush)),
        ("preset-rail-v4", tree_theme("client-rail", "Rail", "rail")),
        ("preset-top-bar-v4", tree_theme("client-top-bar", "Top bar", "top-bar", top)),
        ("preset-console-v4", tree_theme("client-console", "Console", "console", console)),
        ("preset-right-sidebar-v4", tree_theme("client-right", "Right sidebar", "right-sidebar", right)),
        ("preset-launcher-header-v4", tree_theme("client-launcher", "Launcher header", "launcher-header", launcher)),
        ("custom-region-v4", tree_theme("client-custom", "Custom regions", None, custom_layout, custom)),
    ]


def compute_tree(manifest):
    """The layout-tree golden: the resolved theme (with its tree), the check's errors and warnings."""
    layout = manifest["layout"]
    result = {"input": manifest}
    result["resolve"] = themes.resolve_theme(manifest)
    result["contrast"] = themes.contrast_report(manifest)
    check = themes.check_theme(manifest)
    result["check"] = {"errors": check["errors"], "warnings": check["warnings"]}
    result["tree"] = themes.shell_tree_of(manifest)
    result["validate"] = (themes.validate_shell(layout["shell"], None, "layout.shell", layout["scroll"]) if "shell" in layout else None)
    return json.loads(json.dumps(result))


# --- The brand ----------------------------------------------------------------------------------------

# A 1x1 PNG and a small SVG: real images, small enough to read in a golden file.
PIXEL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkqPn/HwAEhgJ/mPsmewAAAABJRU5ErkJggg=="
WORDMARK = ('<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 32">'
            '<rect width="120" height="32" rx="6" fill="#0b5fa5"/><text x="12" y="21" font-size="14" fill="#fff">Precision Hose</text></svg>')

WORDMARK_DARK = ('<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 32">'
                 '<rect width="120" height="32" rx="6" fill="#ffffff"/><text x="12" y="21" font-size="14" fill="#0b5fa5">Precision Hose</text></svg>')


def svg_uri(text):
    return "data:image/svg+xml;base64," + base64.b64encode(text.encode("utf-8")).decode("ascii")


def brand_theme(theme_id, label, brand):
    theme = themes.default_theme_v2(theme_id, "1.0.0", label)
    theme["brand"] = brand
    return theme


def brand_inputs():
    full = {"logo": {"src": svg_uri(WORDMARK), "alt": "Precision Hose", "height": 40},
            "mark": {"src": PIXEL, "alt": "Precision Hose mark"}, "tagline": "Hose & expansion joints"}
    logo_only = {"logo": {"src": PIXEL, "alt": "  Precision Hose  "}}
    with_dark = {"logo": {"src": PIXEL, "alt": "Precision Hose", "height": 40},
                 "logo_dark": {"src": svg_uri(WORDMARK_DARK), "alt": "  Precision Hose on dark  "}, "tagline": "Hose & expansion joints"}
    invalid = {"logo": {"src": svg_uri('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'), "alt": "", "height": 70},
               "mark": {"src": "https://example.com/mark.png", "alt": "Mark"}, "tagline": "x" * 81, "colour": "red"}
    dark_without_logo = {"logo_dark": {"src": PIXEL, "alt": "On dark"}, "tagline": "Hose"}
    return [("brand-full-v4", brand_theme("client-precision", "Precision Hose", full)),
            ("brand-logo-only-v4", brand_theme("client-logo-only", "Logo only", logo_only)),
            ("brand-logo-dark-v4", brand_theme("client-logo-dark", "Logo for dark backgrounds", with_dark)),
            ("brand-logo-dark-invalid-v4", brand_theme("client-logo-dark-invalid", "Logo dark without a logo", dark_without_logo)),
            ("brand-invalid-v4", brand_theme("client-invalid-brand", "Invalid brand", invalid))]


def compute_brand(manifest):
    """The brand golden: the brand's validation, the check of the whole theme and, for a valid theme, the resolved
    theme (with its normalised `brand`) and the contrast report."""
    result = {"input": manifest, "validate": themes.validate_brand(manifest["brand"])}
    check = themes.check_theme(manifest)
    result["check"] = {"errors": check["errors"], "warnings": check["warnings"]}
    if not check["errors"]:
        result["resolve"] = themes.resolve_theme(manifest)
        result["contrast"] = themes.contrast_report(manifest)
    return json.loads(json.dumps(result))


def from_layout():
    """The tree every theme-resolve golden's layout describes, and the registry's and the release's default layouts."""
    layouts = {"registry-default-rail": registry.default_layout("rail"), "registry-default-panel": registry.default_layout("panel")}
    release = json.loads((ROOT / "fastlanelabs_sdk/registry_data/default-theme.json").read_text())
    layouts["default-release"] = release["layout"]
    for name, manifest in inputs():
        layouts[name] = manifest["layout"]
    return {name: {"layout": layout, "tree": themes.shell_from_layout(layout)} for name, layout in sorted(layouts.items())}


def outputs():
    files = {GOLDEN / f"{name}.json": json.dumps(compute(copy.deepcopy(manifest)), indent=2, sort_keys=True) + "\n"
             for name, manifest in inputs()}
    files.update({TREES / f"{name}.json": json.dumps(compute_tree(manifest), indent=2, sort_keys=True) + "\n"
                  for name, manifest in tree_inputs()})
    files.update({BRANDS / f"{name}.json": json.dumps(compute_brand(manifest), indent=2, sort_keys=True) + "\n"
                  for name, manifest in brand_inputs()})
    files[FROM_LAYOUT] = json.dumps(json.loads(json.dumps(from_layout())), indent=2, sort_keys=True) + "\n"
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, content in outputs().items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(path.name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    if stale:
        print("Out of date; run scripts/gen_theme_golden.py:", *stale, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
