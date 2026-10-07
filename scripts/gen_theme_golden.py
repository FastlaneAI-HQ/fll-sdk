"""Write the golden fixtures that keep the Python and TypeScript theme resolvers in step.

    python scripts/gen_theme_golden.py            # rewrite tests/golden/theme-resolve/*.json
    python scripts/gen_theme_golden.py --check    # exit 1 if a fixture is stale

Each fixture holds an input manifest (and optional v1 presentation) with the
expected resolve, upgrade, projection and contrast results. pytest recomputes
them in Python and, where node and esbuild exist, runs frontend/theme-resolve.ts
over the same files (tests/golden/run_resolve.mjs).
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
GOLDEN = ROOT / "tests/golden/theme-resolve"


def load(name):
    return json.loads((FIXTURES / name).read_text())


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
        "sidebar-tone": "light", "navbar-tone": "dark", "navbar-bg": "{ink-800}", "toast-position": "top-right",
        "card-shadow": "{shadow-card}", "modal-scrim-alpha": "0.6", "nav-item-active-bg": "{primary}",
    })
    custom["layout"].update({"scroll": "page", "density": "compact"})
    custom["layout"]["sidebar"].update({"side": "right", "style": "panel", "width": 240, "behavior": "sticky", "surface": "flush"})
    custom["layout"]["navbar"].update({"position": "top", "behavior": "sticky", "align": "center", "show_brand": False})
    custom["layout"]["content"].update({"max_width": 1200, "align": "center", "padding": "lg", "gap": "sm"})
    return [
        ("default-v2", themes.default_theme_v2(), None),
        ("fastlane-v1", load("fastlane-1.0.0.json"), None),
        ("precision-hose-1.0.0-v1", load("precision-hose-1.0.0.json"), None),
        ("precision-hose-1.1.0-v1", load("precision-hose-1.1.0.json"), None),
        ("pack-right-panel-v1", dict(load("precision-hose-1.1.0.json"), id="client-acme"), validate_presentation(default_pack)),
        ("pack-top-navigation-v1", dict(load("fastlane-1.0.0.json"), id="client-top"), validate_presentation(top_navigation)),
        ("custom-v2", custom, None),
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
