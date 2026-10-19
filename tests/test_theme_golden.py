"""Golden fixtures keep the Python and TypeScript resolvers in step (see scripts/gen_theme_golden.py)."""
import importlib.util
import json
import subprocess
from pathlib import Path

from conftest import without_tree
from fastlanelabs_sdk import theme_registry, themes


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests/golden/theme-resolve'
FROZEN = ROOT / 'tests/golden/frozen-r1'
FROZEN_R2 = ROOT / 'tests/golden/frozen-r2'
TREES = ROOT / 'tests/golden/layout-tree'
BRANDS = ROOT / 'tests/golden/brand'
FROM_LAYOUT = ROOT / 'tests/golden/shell-from-layout.json'


def generator():
    spec = importlib.util.spec_from_file_location('gen_theme_golden', ROOT / 'scripts/gen_theme_golden.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_python_results_match_the_golden_files():
    stale = [path.name for path, content in generator().outputs().items() if not path.exists() or path.read_text() != content]
    assert stale == [], 'run scripts/gen_theme_golden.py'
    assert len(list(GOLDEN.glob('*.json'))) == 16
    assert len(list(TREES.glob('*.json'))) == 8
    assert len(list(BRANDS.glob('*.json'))) == 5


def close(expected, actual):
    """Equal, allowing the 2-decimal contrast ratio to differ by one rounding step across languages."""
    if isinstance(expected, dict):
        return expected.keys() == actual.keys() and all(
            (abs(expected[k] - actual[k]) <= 0.011 if k == 'ratio' else close(expected[k], actual[k])) for k in expected)
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(close(a, b) for a, b in zip(expected, actual))
    return expected == actual


def typescript(set_name, require_node):
    require_node('esbuild')  # fails in CI, skips locally -- see conftest
    run = subprocess.run(['node', str(ROOT / 'tests/golden/run_resolve.mjs'), set_name], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


KEYS = ('upgrade', 'resolve_v1', 'project', 'resolve', 'contrast', 'resolve_dark', 'derive')
RESOLVES = ('resolve_v1', 'resolve', 'resolve_dark')


def produced_without_tree(produced):
    """TypeScript results for a revision 1 to 3 golden: those files were written before `shell.tree` and never gain it."""
    return {key: (without_tree(value) if key in RESOLVES else value) for key, value in produced.items()}


def test_typescript_resolver_agrees_with_python(require_node):
    produced = typescript('theme-resolve', require_node)
    for path in sorted(GOLDEN.glob('*.json')):
        golden = json.loads(path.read_text())
        result = produced_without_tree(produced[path.name])
        for key in KEYS:
            if key in golden:
                assert close(golden[key], result[key]), f'{path.name}: {key} differs between Python and TypeScript'


def test_typescript_resolver_still_produces_every_frozen_revision_1_result(require_node):
    produced = typescript('frozen-r1', require_node)
    assert len(produced) == 7
    for path in sorted(FROZEN.glob('*.json')):
        golden = json.loads(path.read_text())
        result = produced_without_tree(produced[path.name])
        for key in ('upgrade', 'resolve_v1', 'project', 'resolve', 'contrast'):
            if key in golden:
                assert close(golden[key], result[key]), f'{path.name}: {key} changed'
        assert 'resolve_dark' not in produced[path.name]


def test_typescript_resolver_still_produces_every_frozen_revision_2_result(require_node):
    produced = typescript('frozen-r2', require_node)
    assert len(produced) == 13
    for path in sorted(FROZEN_R2.glob('*.json')):
        golden = json.loads(path.read_text())
        result = produced_without_tree(produced[path.name])
        for key in ('upgrade', 'resolve_v1', 'project', 'resolve', 'contrast', 'resolve_dark', 'derive'):
            if key in golden:
                assert close(golden[key], result[key]), f'{path.name}: {key} changed'


# --- Registry revision 4: the layout tree ----------------------------------------------------------------------------

def test_the_revision_3_goldens_still_describe_revision_3_themes():
    for path in GOLDEN.glob('*.json'):
        golden = json.loads(path.read_text())
        for key in RESOLVES:
            assert 'tree' not in golden.get(key, {'shell': {}})['shell'], path.name
        manifest = golden['input']
        assert manifest['api_version'] == 1 or manifest['registry_revision'] == 3, path.name
        if 'upgrade' in golden:
            assert golden['upgrade']['theme']['registry_revision'] == 3, path.name


def test_the_trees_of_revision_1_to_3_themes_are_pinned():
    golden = json.loads(FROM_LAYOUT.read_text())
    assert len(golden) == 19
    for name, item in golden.items():
        assert themes.shell_from_layout(item['layout']) == item['tree'], name
        assert themes.validate_shell(item['tree'])['errors'] == [], name
    # The registry's default layout is the `rail` preset, the platform release's is `panel-flush` (spec: "the default theme's tree").
    presets = {item['id']: themes.normalise_shell(item['tree']) for item in theme_registry.layout_vocabulary()['presets']}
    assert golden['registry-default-rail']['tree'] == presets['rail']
    assert golden['default-release']['tree'] == presets['panel-flush']


def test_typescript_trees_of_revision_1_to_3_themes_agree_with_python(require_node):
    produced = typescript('shell-from-layout', require_node)
    golden = json.loads(FROM_LAYOUT.read_text())
    assert produced == {name: item['tree'] for name, item in golden.items()}


def test_typescript_resolves_every_theme_to_the_same_tree_as_python(require_node):
    for name, directory in (('theme-resolve', GOLDEN), ('frozen-r1', FROZEN), ('frozen-r2', FROZEN_R2)):
        produced = typescript(name, require_node)
        for path in sorted(directory.glob('*.json')):
            manifest = json.loads(path.read_text())['input']
            theme = themes.upgrade_v1(manifest, json.loads(path.read_text())['presentation'], registry_revision=
                                      {'frozen-r1': 1, 'frozen-r2': 2}.get(name, 3)) if manifest['api_version'] == 1 else manifest
            assert produced[path.name]['tree'] == themes.shell_tree_of(theme), f'{name}/{path.name}'
            assert produced[path.name]['resolve']['shell']['tree'] == themes.shell_tree_of(theme), f'{name}/{path.name}'
            if manifest['api_version'] == 1:
                assert produced[path.name]['resolve_v1']['shell']['tree'] == themes.shell_tree_of(manifest), f'{name}/{path.name}'


def test_revision_4_results_match_the_golden_files_in_both_languages(require_node):
    produced = typescript('layout-tree', require_node)
    assert len(produced) == 8
    for path in sorted(TREES.glob('*.json')):
        golden = json.loads(path.read_text())
        manifest = golden['input']
        assert json.loads(json.dumps(themes.resolve_theme(manifest))) == golden['resolve']
        assert json.loads(json.dumps(themes.project_v1(manifest))) == golden['project']
        assert golden['resolve']['shell']['tree'] == golden['tree']
        for key in ('resolve', 'contrast', 'project', 'tree', 'validate'):
            assert close(golden[key], produced[path.name][key]), f'{path.name}: {key} differs between Python and TypeScript'


def test_the_revision_4_default_resolves_like_revision_3_except_for_the_revision():
    old = themes.default_theme_v2(registry_revision=3)
    new = themes.default_theme_v2()
    assert new['registry_revision'] == 4 and old['registry_revision'] == 3
    assert dict(new, registry_revision=3) == old
    assert themes.resolve_theme(new) == themes.resolve_theme(old)
    assert themes.resolve_theme(new, 'dark') == themes.resolve_theme(old, 'dark')
    assert json.loads((TREES / 'default-v4.json').read_text())['tree'] == json.loads(FROM_LAYOUT.read_text())['registry-default-rail']['tree']


# --- Registry revision 4: the brand ---------------------------------------------------------------------------------------

def test_the_brand_goldens_hold_a_full_a_logo_only_and_an_invalid_brand():
    full, logo_only, invalid = (json.loads((BRANDS / f'{name}.json').read_text()) for name in ('brand-full-v4', 'brand-logo-only-v4', 'brand-invalid-v4'))
    for golden in (full, logo_only, invalid):
        assert golden['input']['registry_revision'] == 4
    assert full['validate'] == {'errors': [], 'warnings': []} and full['check'] == {'errors': [], 'warnings': []}
    brand = full['resolve']['brand']
    assert brand['logo']['height'] == 40 and brand['mark']['alt'] == 'Precision Hose mark' and brand['tagline'] == 'Hose & expansion joints'
    assert logo_only['resolve']['brand'] == {'logo': {'src': logo_only['input']['brand']['logo']['src'], 'alt': 'Precision Hose', 'height': 32},
                                             'logo_dark': None, 'mark': None, 'tagline': None}
    assert [(e['path']) for e in invalid['check']['errors']] == ['brand.colour', 'brand.logo.src', 'brand.logo.alt', 'brand.logo.height',
                                                                  'brand.mark.src', 'brand.tagline']
    assert invalid['check']['errors'] == invalid['validate']['errors'] and 'resolve' not in invalid


def test_the_logo_dark_goldens_hold_a_resolved_logo_for_dark_backgrounds_and_the_error_without_a_logo():
    dark = json.loads((BRANDS / 'brand-logo-dark-v4.json').read_text())
    brand = dark['resolve']['brand']
    assert dark['check'] == {'errors': [], 'warnings': []} and brand['logo']['height'] == 40
    assert brand['logo_dark']['height'] == 40 and brand['logo_dark']['alt'] == 'Precision Hose on dark'  # trimmed, the logo's height
    assert themes.brand_logo_for(brand, True) == brand['logo_dark'] and themes.brand_logo_for(brand, False) == brand['logo']
    bad = json.loads((BRANDS / 'brand-logo-dark-invalid-v4.json').read_text())
    assert [(e['path'], e['message']) for e in bad['check']['errors']] == [('brand.logo_dark', 'logo_dark needs a logo')] and 'resolve' not in bad


def test_the_launcher_header_golden_is_the_preset_with_a_launcher_navigation_and_a_slim_fallback_bar():
    golden = json.loads((TREES / 'preset-launcher-header-v4.json').read_text())
    assert golden['check'] == {'errors': [], 'warnings': []} and golden['validate'] == {'errors': [], 'warnings': []}
    nav = golden['tree']['root']['children'][0]['children'][0]
    assert nav['region'] == 'navigation' and nav['options']['style'] == 'launcher'
    layout = golden['input']['layout']
    assert (layout['sidebar']['side'], layout['navbar']['position'], layout['navbar']['height']) == ('hidden', 'top', 56)


def test_typescript_validates_and_resolves_the_brand_goldens_like_python(require_node):
    produced = typescript('brand', require_node)
    assert len(produced) == 5
    for path in sorted(BRANDS.glob('*.json')):
        golden = json.loads(path.read_text())
        result = produced[path.name]
        assert result['validate'] == golden['validate'], path.name
        for key in ('resolve', 'contrast', 'project'):
            if key in golden:
                assert close(golden[key], result[key]), f'{path.name}: {key} differs between Python and TypeScript'
            else:
                assert key not in result
