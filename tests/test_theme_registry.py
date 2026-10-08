"""The registry is the source of truth; these checks keep it, its generated files and the validator honest."""
import importlib.util
import json
import re
import subprocess
from collections import Counter
from importlib.resources import files
from pathlib import Path

from fastlanelabs_sdk import theme_registry as registry
from fastlanelabs_sdk import themes

ROOT = Path(__file__).resolve().parents[1]


def generator():
    spec = importlib.util.spec_from_file_location('gen_theme_registry', ROOT / 'scripts/gen_theme_registry.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_files_are_current():
    stale = [str(path.relative_to(ROOT)) for path, content in generator().outputs().items()
             if not path.exists() or path.read_text() != content]
    assert stale == [], 'run scripts/gen_theme_registry.py'


def test_registry_json_in_the_package_and_frontend_match_python():
    packaged = json.loads(files('fastlanelabs_sdk.registry_data').joinpath('theme-registry-v2.json').read_text())
    assert packaged == registry.registry_json()
    assert (ROOT / 'frontend/theme-registry.json').read_bytes() == files('fastlanelabs_sdk.registry_data').joinpath('theme-registry-v2.json').read_bytes()


def test_the_27_v1_tokens_are_unchanged():
    expected = {'surface', 'on-primary', 'font-sans', 'font-mono', 'radius'} | {
        f'{palette}-{shade}' for palette in ('ink', 'accent') for shade in themes.SHADES}
    assert registry.V1_TOKEN_NAMES == expected == set(themes.TOKEN_NAMES)
    assert len(registry.V1_TOKEN_NAMES) == 27


def test_names_are_unique_kebab_case_and_layered():
    names = [token.name for token in registry.TOKENS]
    assert not [n for n, count in Counter(names).items() if count > 1]
    for token in registry.TOKENS:
        assert re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', token.name), token.name
        assert token.layer in registry.LAYERS and token.type in registry.TYPES
        assert token.since in (1, 3) and (token.since == 1 or token.optional)
        if token.layer == 'component':
            assert token.name.startswith(token.component + '-'), token.name
            assert token.component in registry.COMPONENTS
    assert {t.layer for t in registry.TOKENS} == set(registry.LAYERS)
    assert registry.REGISTRY_REVISION == 3 == themes.REGISTRY_REVISION


def test_token_counts_are_what_the_contract_documents():
    assert (len(registry.PRIMITIVES), len(registry.SEMANTIC), len(registry.COMPONENT_TOKENS)) == (114, 43, 248)


def defaults_of(token):
    return list(token.default.values()) if isinstance(token.default, dict) else [token.default]


def test_every_default_is_valid_for_its_slot():
    for token in registry.TOKENS:
        for default in defaults_of(token):
            match = registry.FALLBACK_EXPR.fullmatch(default)
            if match:
                target = registry.INDEX[match.group(1)]
                assert token.layer != 'primitive', token.name
                assert target.layer in ('primitive', 'semantic'), f'{token.name} falls back to a component token'
                assert target.type == token.type, f'{token.name} -> {target.name}: {token.type} vs {target.type}'
                assert token.type in ('length', 'font-size') or (match.group(2) is None and match.group(3) is None), token.name
                assert not isinstance(target.default, dict), f'{token.name} chains through a tone-dependent token'
            else:
                assert themes._literal_error(token, default) is None, (token.name, default)
        if token.type == 'enum':
            assert all(d in token.options for d in defaults_of(token)), token.name
        if token.min is not None and token.max is not None:
            assert token.min <= token.max
        if isinstance(token.default, dict):
            assert set(token.default) == {'dark', 'light'}
            assert registry.INDEX[token.tone].type == 'enum' and token.tone.endswith('-tone')


def test_semantic_defaults_form_an_acyclic_graph_within_the_depth_limit():
    def depth(name, seen=()):
        assert name not in seen, f'cycle through {name}'
        match = registry.REF.fullmatch(registry.INDEX[name].default)
        return 0 if not match else 1 + depth(match.group(1), seen + (name,))
    assert max(depth(t.name) for t in registry.SEMANTIC) <= registry.SELF_REFERENCE_DEPTH


def test_ref_defaults_of_ranged_slots_resolve_in_range():
    # A literal default such as button-height 0px means "unset" and is exempt; refs must satisfy the slot.
    resolved = themes._all_resolved(themes.default_theme_v2())
    for token in registry.COMPONENT_TOKENS:
        match = registry.FALLBACK_EXPR.fullmatch(token.default) if isinstance(token.default, str) else None
        if match and not (match.group(2) or match.group(3)) and token.type != 'font-size':
            assert themes._range_error(token, resolved[match.group(1)]) is None, token.name


def test_contrast_tables_name_real_tokens_and_the_default_theme_passes_them():
    for pair in registry.CONTRAST_PAIRS:
        assert pair.fg in registry.INDEX and pair.bg in registry.INDEX
        assert pair.unless == '' or registry.INDEX[pair.unless].optional
    for _, fg, bg in registry.COMPONENT_CONTRAST_PAIRS:
        assert fg in registry.INDEX and bg in registry.INDEX
    for _, tone, bg in registry.NAV_BARS:
        assert tone in registry.INDEX and bg in registry.INDEX
    result = themes.check_theme(themes.default_theme_v2())
    assert result['errors'] == []
    assert all(row['pass'] for row in result['contrast'] if row['level'] == 'error')
    assert {row['id'] for row in result['contrast']} >= {'legacy-ink-900-on-surface', 'text-on-surface', 'nav-item-fg-on-sidebar-bg'}


def test_layout_defaults_validate_and_cover_every_field():
    layout = registry.default_layout()
    theme = themes.default_theme_v2()
    assert theme['layout'] == layout
    assert layout['sidebar'] == {'side': 'left', 'style': 'rail', 'surface': 'floating', 'width': 56, 'behavior': 'fixed', 'collapse_below': 760}
    assert layout['navbar'] == {'position': 'hidden', 'behavior': 'fixed', 'height': 56, 'align': 'between', 'show_brand': True}
    assert layout['content'] == {'max_width': 0, 'align': 'start', 'padding': 'md', 'gap': 'md'}
    assert (layout['density'], layout['scroll']) == ('comfortable', 'panel')
    assert registry.default_layout('panel')['sidebar']['width'] == 224
    assert themes.check_theme(dict(theme, layout=registry.default_layout('panel')))['errors'] == []


def test_status_ramps_are_tailwind_3_colors(require_node):
    require_node('tailwindcss')
    colors = ROOT / 'node_modules/tailwindcss/colors.js'
    script = "const c=require(process.argv[1]);console.log(JSON.stringify({success:c.emerald,warning:c.amber,danger:c.red,info:c.sky}))"
    palettes = json.loads(subprocess.run(['node', '-e', script, str(colors)], capture_output=True, text=True, check=True).stdout)
    for status, ramp in palettes.items():
        assert {f'{status}-{shade}': ramp[str(shade)] for shade in registry.SHADES} == {
            f'{status}-{shade}': registry.INDEX[f'{status}-{shade}'].default for shade in registry.SHADES}


def test_webfont_allow_list_is_reviewed_data():
    fonts = registry.webfonts()
    assert {f['family'] for f in fonts} >= {'Inter', 'Roboto', 'JetBrains Mono'}
    for font in fonts:
        assert re.fullmatch(r"[A-Za-z0-9 ]+", font['family']) and font['weights'] and all(100 <= w <= 900 for w in font['weights'])


def test_default_css_declares_every_primitive_semantic_and_untoned_component_token():
    css = (ROOT / 'frontend/theme-defaults.css').read_text()
    declared = set(re.findall(r'^\s+--fl-([a-z0-9-]+):', css, re.M))
    for token in registry.TOKENS:
        if not isinstance(token.default, dict):
            assert token.name in declared, token.name
    assert 'tone-nav-item-fg' in declared and 'fs-md' in declared
    assert ":root, [data-fl-theme-root]" in css
