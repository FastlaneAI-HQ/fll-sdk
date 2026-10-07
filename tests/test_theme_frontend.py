"""The frontend contract files, the shared Tailwind preset and the published-release corpus."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastlanelabs_sdk.theme_packs import STYLE_OPTIONS
from fastlanelabs_sdk.themes import check_theme, project_v1, validate_theme

ROOT = Path(__file__).resolve().parents[1]
CORPUS = Path(__file__).parent / 'fixtures/themes/v2'


def test_every_published_v2_release_stays_valid_under_the_current_validator():
    """Add each v2 manifest as it is published. Rules for a (api_version, registry_revision) never tighten."""
    releases = sorted(CORPUS.glob('*.json'))
    assert releases
    for path in releases:
        theme = json.loads(path.read_text())
        assert check_theme(theme)['errors'] == [], path.name
        assert validate_theme(theme) == theme
        assert validate_theme(project_v1(theme))['api_version'] == 1, path.name


def test_python_style_options_match_the_typescript_pack_contract():
    source = (ROOT / 'frontend/theme-pack-contract.ts').read_text()
    block = source[source.index('interface PresentationStyles'):source.index('export interface ThemePackPresentation')]
    declared = {}
    for name, body in re.findall(r"'([a-z.]+)'\?: \{([^}]*)\}", block):
        declared[name] = {key: tuple(re.findall(r"'([a-z]+)'", options)) for key, options in
                          (field.split(':') for field in body.split(';') if field.strip())}
    assert declared == {name: {key: tuple(values) for key, values in options.items()} for name, options in STYLE_OPTIONS.items()}


def test_typescript_layout_and_registry_types_follow_the_registry():
    from fastlanelabs_sdk import theme_registry as registry
    source = (ROOT / 'frontend/theme-contract.ts').read_text()
    block = source[source.index('export type LayoutStep'):source.index('export interface ThemeManifestV2')]
    for group, spec in registry.LAYOUT_SPEC.items():
        fields = spec.items() if 'type' not in spec else [(group, spec)]
        for name, field in fields:
            assert re.search(rf'\b{name}: ', block), name
            if field['type'] == 'enum':
                for option in field['options']:
                    assert f"'{option}'" in block, (name, option)
    assert [f"'{step}'" in source for step in registry.STEPS] == [True] * len(registry.STEPS)


def test_sync_script_copies_the_v2_runtime_files(tmp_path):
    subprocess.run(['python', str(ROOT / 'scripts/sync_theme_contract.py'), str(tmp_path)], check=True)
    generated = tmp_path / 'frontend/src/generated'
    assert sorted(path.name for path in generated.iterdir()) == [
        'tailwind-preset.mjs', 'theme-contract.ts', 'theme-defaults.css', 'theme-pack-contract.ts',
        'theme-registry.json', 'theme-resolve.ts']
    for path in generated.iterdir():
        assert path.read_bytes() == (ROOT / 'frontend' / path.name).read_bytes()


PARITY = r"""
import postcss from 'postcss'
import tailwindcss from 'tailwindcss'
import preset from '%s'
const shades=[50,100,200,300,400,500,600,700,800,900,950]
const palette = name => Object.fromEntries(shades.map(shade => [shade, `rgb(var(--fl-${name}-${shade}) / <alpha-value>)`]))
const classes = process.argv.slice(2).join(' ')
const content=[{raw:`<div class="${classes}"></div>`}]
const old = {content, corePlugins:{preflight:false}, theme:{extend:{
  colors:{ink:palette('ink'),accent:palette('accent')},
  backgroundColor:{white:'rgb(var(--fl-surface) / <alpha-value>)'}, textColor:{white:'rgb(var(--fl-on-primary) / <alpha-value>)'},
  borderRadius:{lg:'var(--fl-radius, 8px)',xl:'calc(var(--fl-radius, 8px) * 1.5)','2xl':'calc(var(--fl-radius, 8px) * 2)'},
  fontFamily:{sans:['var(--fl-font-sans, Inter)','ui-sans-serif','system-ui'],mono:['var(--fl-font-mono, ui-monospace)','monospace']}}}}
const run = async cfg => (await postcss([tailwindcss(cfg)]).process('@tailwind utilities;',{from:undefined})).css
console.log(JSON.stringify({old: await run(old), new: await run({...old, theme:{}, presets:[preset]})}))
"""
UNCHANGED = ['bg-ink-50', 'text-ink-900/60', 'border-ink-200', 'bg-accent-600', 'hover:bg-accent-700', 'bg-white', 'text-white',
             'rounded-lg', 'rounded-xl', 'rounded-2xl', 'font-sans', 'font-mono', 'leading-relaxed', 'tracking-tight', 'p-4', 'h-9',
             'w-14', 'gap-3', 'text-[12px]', 'text-[13.5px]', 'rounded-full', 'font-normal', 'shadow']
FOLLOW_THE_THEME = ['border', 'rounded', 'rounded-md', 'rounded-sm', 'shadow-sm', 'shadow-lg', 'shadow-xl', 'transition', 'text-xs', 'text-sm',
                    'text-base', 'text-lg', 'text-xl', 'text-2xl', 'font-medium', 'font-semibold', 'font-bold', 'bg-red-50', 'text-emerald-700',
                    'border-amber-200', 'bg-sky-50', 'bg-sky-100', 'ring-red-500/20']


def rules(css):
    return {m.group(1).strip(): ' '.join(m.group(2).split()) for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css)}


def with_defaults(value):
    """Replace var(--fl-x, default) by default, then normalise equivalent spellings."""
    while True:
        start = value.find('var(--fl-')
        if start < 0:
            break
        depth, end, comma = 0, start + 3, None
        for index in range(start + 3, len(value)):
            char = value[index]
            depth += char == '('
            depth -= char == ')'
            if char == ',' and depth == 1 and comma is None:
                comma = index
            if depth == 0:
                end = index
                break
        value = value[:start] + (value[comma + 1:end].strip() if comma else '') + value[end + 1:]
    value = re.sub(r'calc\(([0-9.]+rem) \* 1\)', r'\1', value)
    value = re.sub(r'([0-9.]+)rem', lambda m: f'{float(m.group(1)) * 16:g}px', value)  # Tailwind spells 4px as 0.25rem.
    value = re.sub(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\)', r'rgb(\1 \2 \3 / \4)', value)
    value = re.sub(r'--tw-shadow-colored: [^;]*; ', '', value)  # Colored shadows cannot be derived from a var().
    return re.sub(r'\s*,\s*', ', ', value)


def compare(classes):
    script = ROOT / 'tests/_preset_parity.mjs'
    script.write_text(PARITY % (ROOT / 'frontend/tailwind-preset.mjs'))
    try:
        run = subprocess.run(['node', str(script), *classes], capture_output=True, text=True, cwd=ROOT, timeout=120)
    finally:
        script.unlink()
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    return rules(result['old']), rules(result['new'])


def test_the_shared_preset_leaves_existing_classes_untouched():
    if not shutil.which('node') or not (ROOT / 'node_modules/tailwindcss').exists():
        pytest.skip('node and the SDK dev dependencies (npm install) are required')
    old, new = compare(UNCHANGED)
    assert old == new and len(old) >= len(UNCHANGED) - 2


def test_classes_that_now_follow_the_theme_keep_their_default_rendering():
    if not shutil.which('node') or not (ROOT / 'node_modules/tailwindcss').exists():
        pytest.skip('node and the SDK dev dependencies (npm install) are required')
    old, new = compare(FOLLOW_THE_THEME)
    assert set(old) == set(new) and len(old) >= len(FOLLOW_THE_THEME) - 1
    for selector in old:
        assert with_defaults(new[selector]) == with_defaults(old[selector]), selector
    # Every var() the preset adds carries its literal default.
    preset = (ROOT / 'frontend/tailwind-preset.mjs').read_text()
    bare = [m for m in re.findall(r'var\((--fl-[a-z0-9-]+)\)', preset)
            if not m.startswith(('--fl-ink-', '--fl-accent-', '--fl-surface', '--fl-on-primary'))]
    assert bare == []
