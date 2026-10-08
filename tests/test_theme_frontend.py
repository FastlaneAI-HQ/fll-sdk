"""The frontend contract files, the shared Tailwind preset and the published-release corpus."""
import json
import re
import subprocess
import sys
from pathlib import Path

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
    subprocess.run([sys.executable, str(ROOT / 'scripts/sync_theme_contract.py'), str(tmp_path)], check=True)
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
             'w-14', 'gap-3', 'text-[12px]', 'text-[13.5px]', 'rounded-full', 'font-normal', 'shadow',
             # Revision 3 adds roles beside these; what they resolve to does not move.
             'bg-ink-900', 'bg-ink-800', 'text-ink-400', 'text-ink-500', 'border-ink-300', 'text-accent-600', 'text-accent-700', 'bg-accent-50']
FOLLOW_THE_THEME = ['border', 'rounded', 'rounded-md', 'rounded-sm', 'shadow-sm', 'shadow-lg', 'shadow-xl', 'transition', 'text-xs', 'text-sm',
                    'text-base', 'text-lg', 'text-xl', 'text-2xl', 'font-medium', 'font-semibold', 'font-bold', 'bg-red-50', 'text-emerald-700',
                    'border-amber-200', 'bg-sky-50', 'bg-sky-100', 'ring-red-500/20']


# What the preset newly maps to a theme variable or a mode-following platform ramp: Tailwind's own value at defaults.
NEWLY_MAPPED = ['border-white', 'ring-white', 'ring-offset-white', 'divide-white', 'from-white', 'via-white', 'to-white', 'fill-white', 'stroke-white',
                'text-black', 'text-black/50', 'border-black', 'bg-slate-50', 'text-slate-700', 'border-violet-200', 'bg-violet-50', 'text-violet-700',
                'bg-rose-50', 'text-rose-700/50', 'bg-gray-100', 'text-gray-500', 'divide-gray-200', 'text-orange-600', 'ring-teal-500', 'bg-indigo-600',
                'from-blue-50', 'fill-zinc-400', 'placeholder-stone-400', 'border-pink-300', 'bg-yellow-50', 'text-lime-800', 'bg-cyan-100',
                'text-fuchsia-600', 'bg-purple-100', 'bg-green-50', 'bg-neutral-200']


def rules(css):
    return {m.group(1).strip(): ' '.join(m.group(2).split()) for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css)}


BARE_DEFAULTS = {'--fl-surface': '255 255 255', '--fl-on-primary': '255 255 255'}


def with_defaults(value):
    """Replace var(--fl-x, default) by default, then normalise equivalent spellings."""
    for name, default in BARE_DEFAULTS.items():
        value = value.replace(f'var({name})', default)
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
    value = re.sub(r'#([0-9a-f])([0-9a-f])([0-9a-f])\b', r'#\1\1\2\2\3\3', value)
    value = re.sub(r'#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})\b', lambda m: 'rgb(%d %d %d / 1)' % tuple(int(g, 16) for g in m.groups()), value)  # A solid colour, spelled either way.
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


def test_the_shared_preset_leaves_existing_classes_untouched(require_node):
    require_node('tailwindcss')
    old, new = compare(UNCHANGED)
    assert old == new and len(old) >= len(UNCHANGED) - 2


def test_classes_that_now_follow_the_theme_keep_their_default_rendering(require_node):
    require_node('tailwindcss')
    old, new = compare(FOLLOW_THE_THEME)
    assert set(old) == set(new) and len(old) >= len(FOLLOW_THE_THEME) - 1
    for selector in old:
        assert with_defaults(new[selector]) == with_defaults(old[selector]), selector
    # Every var() the preset adds carries its literal default.
    preset = (ROOT / 'frontend/tailwind-preset.mjs').read_text()
    bare = [m for m in re.findall(r'var\((--fl-[a-z0-9-]+)\)', preset)
            if not m.startswith(('--fl-ink-', '--fl-accent-', '--fl-surface', '--fl-on-primary'))]
    assert bare == []


def test_newly_mapped_classes_render_as_tailwind_does_at_defaults(require_node):
    """White also paints borders, rings and glyphs now; the remaining hues and black text follow the colour mode."""
    require_node('tailwindcss')
    old, new = compare(NEWLY_MAPPED)
    assert set(old) == set(new) and len(old) >= len(NEWLY_MAPPED) - 3
    for selector in old:
        assert with_defaults(new[selector]) == with_defaults(old[selector]), selector
    assert 'var(--fl-hue-rose-700' in new[next(s for s in new if 'text-rose-700' in s)]


def test_every_hue_var_the_preset_reads_is_declared_for_both_modes():
    css = (ROOT / 'frontend/theme-defaults.css').read_text()
    light, dark = css.split("[data-fl-mode='dark'] {")
    preset = (ROOT / 'frontend/tailwind-preset.mjs').read_text()
    wanted = set(re.findall(r'var\((--fl-(?:hue-[a-z]+-[0-9]+|black))', preset))
    from fastlanelabs_sdk import theme_registry as registry
    assert len(wanted) == len(registry.HUE_RAMPS) * 11 + 1
    for name in wanted:
        assert f'{name}:' in light and f'{name}:' in dark, name
    assert 'color-scheme: dark' in dark and "[data-fl-theme-root]:not([data-fl-mode='dark']) { color-scheme: light; }" in light


def test_platform_hues_are_tailwind_3_colors_and_reverse_in_dark(require_node):
    from fastlanelabs_sdk import theme_registry as registry
    require_node('tailwindcss')
    colors = ROOT / 'node_modules/tailwindcss/colors.js'
    script = "const c=require(process.argv[1]);console.log(JSON.stringify(Object.fromEntries(process.argv.slice(2).map(h=>[h,c[h]]))))"
    hues = list(registry.HUE_RAMPS)
    palettes = json.loads(subprocess.run(['node', '-e', script, str(colors), *hues], capture_output=True, text=True, check=True).stdout)
    for hue, ramp in registry.HUE_RAMPS.items():
        assert list(ramp) == [palettes[hue][str(shade)] for shade in registry.SHADES], hue
    css = (ROOT / 'frontend/theme-defaults.css').read_text().split("[data-fl-mode='dark'] {")[1]
    rose = registry.HUE_RAMPS['rose']
    assert f"--fl-hue-rose-50: {' '.join(str(int(rose[10][i:i + 2], 16)) for i in (1, 3, 5))};" in css


def test_revision_3_roles_get_tailwind_keys_with_the_fallback_that_reproduces_todays_rendering(require_node):
    require_node('tailwindcss')
    _, new = compare(['bg-inverse', 'text-on-inverse', 'text-accent-text', 'bg-accent-ui', 'border-accent-ui', 'ring-focus',
                      'bg-surface-inverse', 'text-accent-text/50'])
    text = ' '.join(new.values())
    for variable, fallback in (('--fl-inverse', '26 27 33'), ('--fl-on-inverse', '255 255 255'), ('--fl-accent-text', '33 72 216'),
                               ('--fl-accent-ui', '33 72 216'), ('--fl-focus-ring', '51 102 242'), ('--fl-surface-inverse', '16 17 23')):
        assert f'var({variable}, {fallback})' in text, variable
    # The fallbacks are the literals bg-ink-900 and text-accent-600 already render (ink-900 26 27 33, accent-600 33 72 216).


def test_the_generated_css_declares_the_roles_with_the_same_fallbacks():
    css = (ROOT / 'frontend/theme-defaults.css').read_text()
    for line in ('--fl-inverse: var(--fl-ink-900);', '--fl-on-inverse: var(--fl-surface);',
                 '--fl-accent-text: var(--fl-accent-600);', '--fl-accent-ui: var(--fl-accent-600);'):
        assert line in css
