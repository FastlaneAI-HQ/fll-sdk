"""Write the golden fixtures that keep the Python and TypeScript theme resolvers in step.

    python scripts/gen_theme_golden.py            # rewrite tests/golden/theme-resolve/*.json
    python scripts/gen_theme_golden.py --check    # exit 1 if a fixture is stale

Each fixture holds an input manifest (and optional v1 presentation) with the
expected resolve, upgrade, projection and contrast results; a theme with a dark
palette also holds the dark resolve and the derived dark block. pytest recomputes
them in Python and, where node and esbuild exist, runs frontend/theme-resolve.ts
over the same files (tests/golden/run_resolve.mjs).

tests/golden/frozen-r1 holds what SDK 1.3 produced for registry revision 1 and
tests/golden/frozen-r2 what SDK 1.4 produced for revision 2. They are never
regenerated: tests/test_theme_frozen_r1.py and test_theme_frozen_r2.py check that
today's code still produces every byte of them.
"""
from pathlib import Path
import argparse
import copy
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastlanelabs_sdk import themes  # noqa: E402
from fastlanelabs_sdk.theme_packs import validate_presentation  # noqa: E402

FIXTURES = ROOT / "tests/fixtures/themes"
# Revision 3 themes the theme builder produced for the two brands with the brightest dark accent tints (a neon green, a yellow):
# the dark text steps are solved against those tints (see tests/test_themes_r3.py).
R3_FIXTURES = ROOT / "tests/fixtures/themes-r3"
GOLDEN = ROOT / "tests/golden/theme-resolve"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def load_r3(name):
    return json.loads((R3_FIXTURES / name).read_text())


def inputs():
    default_pack = {"api_version": 1, "workspace": {"type": "column", "gap": "md", "children": [
        {"type": "slot", "name": "actions"},
        {"type": "row", "gap": "sm", "children": [
            {"type": "slot", "name": "content"}, {"type": "slot", "name": "navigation", "width": 240}]}]},
        "styles": {"navigation.sidebar": {"variant": "panel", "tone": "dark"}, "navigation.item": {"variant": "pill", "mode": "label"},
                   "control.button": {"variant": "outline", "radius": "square"}, "surface.card": {"variant": "raised"}}}
    top_navigation = {"api_version": 1, "workspace": {"type": "column", "gap": "lg", "children": [
        {"type": "slot", "name": "navigation"}, {"type": "slot", "name": "content"}, {"type": "slot", "name": "actions"}]},
        "styles": {"page.header": {"variant": "ruled"}, "control.input": {"variant": "filled"}}}
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
    # Registry revision 3: the optional roles set to something other than their fallback, and a dark palette derived from them.
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
        ("default-v2", themes.default_theme_v2(), None),
        ("fastlane-v1", load("fastlane-1.0.0.json"), None),
        ("precision-hose-1.0.0-v1", load("precision-hose-1.0.0.json"), None),
        ("precision-hose-1.1.0-v1", load("precision-hose-1.1.0.json"), None),
        ("pack-right-panel-v1", dict(load("precision-hose-1.1.0.json"), id="client-acme"), validate_presentation(default_pack)),
        ("pack-top-navigation-v1", dict(load("fastlane-1.0.0.json"), id="client-top"), validate_presentation(top_navigation)),
        ("custom-v2", custom, None),
        ("default-auto-v2", themes.default_theme_v2("fastlane", "2.1.0", "Fastlane", scheme="auto"), None),
        ("default-dark-v2", themes.default_theme_v2("fastlane-dark", "2.1.0", "Fastlane Dark", scheme="dark"), None),
        ("warm-auto-v2", warm_auto, None),
        ("custom-auto-v2", custom_auto, None),
        ("tuned-auto-v2", tuned, None),
        ("roles-auto-v2", roles_auto, None),
        ("warm-dark-v2", dark_only, None),
        ("green-auto-v2", load_r3("green-auto.json"), None),
        ("yellow-dark-auto-v2", load_r3("yellow-dark-auto.json"), None),
    ]


def compute(manifest, presentation):
    result = {"input": manifest, "presentation": presentation}
    if manifest["api_version"] == 1:
        report = themes.upgrade_v1_report(manifest, presentation)
        result["upgrade"] = report
        result["resolve_v1"] = themes.resolve_theme(manifest)
        v2 = report["theme"]
        result["project"] = themes.project_v1(v2)
    else:
        v2 = manifest
    result["resolve"] = themes.resolve_theme(v2)
    result["contrast"] = themes.contrast_report(v2)
    if v2.get("color_scheme", "light") != "light":
        result["resolve_dark"] = themes.resolve_theme(v2, "dark")
        result["check"] = themes.check_theme(v2)
        result["derive"] = themes.derive_dark(v2) if v2["color_scheme"] == "auto" else None
    return json.loads(json.dumps(result))


def outputs():
    return {GOLDEN / f"{name}.json": json.dumps(compute(copy.deepcopy(manifest), presentation), indent=2, sort_keys=True) + "\n"
            for name, manifest, presentation in inputs()}


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
