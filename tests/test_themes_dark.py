"""Dark mode (registry revision 2): the data model, its validation, resolution and the derived palette.

Revision 1 stays frozen (tests/test_theme_frozen_r1.py); everything here is new surface that only revision 2
themes can use.
"""
import colorsys
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastlanelabs_sdk import theme_registry as registry
from fastlanelabs_sdk import themes
from fastlanelabs_sdk.theme_packs import create_theme_pack_v2, validate_theme_pack
from fastlanelabs_sdk.themes import (
    ThemeError, check_theme, contrast_report, default_theme_v2, derive_dark, effective_mode, offered_modes,
    project_v1, resolve_theme, validate_theme,
)

FIXTURES = Path(__file__).parent / 'fixtures/themes/v2'
SOURCES = {'website': 'https://example.com', 'retrieved_at': '2026-10-05',
           'observations': [{'url': 'https://example.com', 'kind': 'observed', 'note': 'Dark navy surfaces.'}], 'notes': []}


def auto():
    return default_theme_v2('client-acme', '1.0.0', 'Acme', scheme='auto')


def errors(value):
    return check_theme(value)['errors']


def error_paths(value):
    return [e['path'] for e in errors(value)]


def luminance(color):
    return themes._luminance(color)


# --- The data model ------------------------------------------------------------------------------

def test_the_registry_is_revision_2_and_adds_no_token():
    assert registry.REGISTRY_REVISION == 2 and registry.MODE_NAMES == ('dark',)
    assert registry.color_schemes(1) == ('light',) and registry.color_schemes(2) == ('light', 'dark', 'auto')
    assert all(token.since == 1 for token in registry.TOKENS)
    assert set(registry.MODE_EXTRA_TOKENS) <= set(registry.INDEX)
    assert len(registry.DARK_REQUIRED) == 6 * 11 + 2 and {'surface', 'on-primary'} <= set(registry.DARK_REQUIRED)


def test_overridable_tokens_are_colors_shadows_and_a_few_numbers_and_tones():
    assert {registry.INDEX[n].type for n in registry.MODE_TOKENS} == {'color', 'shadow', 'number', 'enum'}
    for forbidden in ('font-sans', 'radius', 'size-scale', 'space-md', 'weight-bold', 'button-radius', 'toast-position', 'card-variant'):
        assert forbidden not in registry.MODE_TOKENS
    assert {'ink-900', 'surface', 'on-primary', 'shadow-card', 'sidebar-tone', 'navbar-tone', 'modal-scrim-alpha'} <= set(registry.MODE_TOKENS)


def test_the_three_schemes_validate():
    for scheme in ('light', 'auto', 'dark'):
        value = default_theme_v2('client-acme', scheme=scheme)
        assert value['color_scheme'] == scheme and ('modes' in value) == (scheme == 'auto')
        assert errors(value) == [] and validate_theme(value) == value


def test_validation_returns_a_copy_that_includes_the_dark_block_untouched():
    value = auto()
    validated = validate_theme(value)
    assert validated == value and validated['modes'] is not value['modes']
    validated['modes']['dark']['semantic']['surface'] = '#000000'
    assert value['modes']['dark']['semantic']['surface'] != '#000000'


@pytest.mark.parametrize('scheme,has_modes,path', [
    ('light', True, 'modes'), ('dark', True, 'modes'), ('auto', False, 'modes'),
])
def test_modes_belong_to_auto_themes_only(scheme, has_modes, path):
    value = auto()
    value['color_scheme'] = scheme
    if not has_modes:
        del value['modes']
    assert path in error_paths(value)


@pytest.mark.parametrize('scheme', ['both', 'Dark', 'dark ', '', 'dаrk', 'auto\n', None, 1, True, ['dark'], {'dark': 1}, 'system'])
def test_unknown_or_hostile_schemes_are_rejected(scheme):
    value = default_theme_v2('client-acme')
    value['color_scheme'] = scheme
    assert error_paths(value) == ['color_scheme']
    with pytest.raises(ThemeError):
        validate_theme(value)


@pytest.mark.parametrize('modes', [
    [], 'dark', 5, None, {}, {'light': {}}, {'dark': None}, {'dark': []}, {'dark': {}}, {'Dark': {}},
    {'dark': {'primitives': {}, 'semantic': {}}}, {'dark': {'primitives': {}, 'semantic': {}, 'components': {}, 'extra': {}}},
    {'dark': {'primitives': [], 'semantic': {}, 'components': {}}}, {'dark': {'primitives': {}, 'semantic': 'x', 'components': {}}},
    {'dark': {'primitives': {}, 'semantic': {}, 'components': {}}, 'light': {}},
    {'__proto__': {}}, {'dark': {'__proto__': {}, 'primitives': {}, 'semantic': {}, 'components': {}}},
])
def test_a_malformed_modes_block_is_rejected_with_a_path(modes):
    value = auto()
    value['modes'] = modes
    assert error_paths(value) and all(p.startswith('modes') for p in error_paths(value)), errors(value)
    with pytest.raises(ThemeError):
        validate_theme(value)


def mutate_dark(layer, **tokens):
    value = auto()
    value['modes']['dark'][layer].update({k.replace('_', '-'): v for k, v in tokens.items()})
    return value


@pytest.mark.parametrize('layer,name,expected', [
    ('primitives', 'mystery', 'modes.dark.primitives.mystery'),
    ('primitives', 'font-sans', 'modes.dark.primitives.font-sans'),
    ('primitives', 'radius', 'modes.dark.primitives.radius'),
    ('primitives', 'size-scale', 'modes.dark.primitives.size-scale'),
    ('primitives', 'space-md', 'modes.dark.primitives.space-md'),
    ('primitives', 'weight-bold', 'modes.dark.primitives.weight-bold'),
    ('semantic', 'primary', 'modes.dark.semantic.primary'),  # a color: allowed, see below
    ('semantic', 'ink-900', 'modes.dark.semantic.ink-900'),  # in the wrong layer
    ('components', 'button-radius', 'modes.dark.components.button-radius'),
    ('components', 'toast-position', 'modes.dark.components.toast-position'),
    ('components', 'card-variant', 'modes.dark.components.card-variant'),
    ('components', 'button-glow', 'modes.dark.components.button-glow'),
    ('components', 'ink-900', 'modes.dark.components.ink-900'),
])
def test_a_mode_may_only_override_what_varies_with_the_palette(layer, name, expected):
    value = mutate_dark(layer, **{name: {'primary': '{accent-700}'}.get(name, '4px')})
    if name == 'primary':
        assert errors(value) == []
    else:
        assert expected in error_paths(value), errors(value)


def test_the_dark_palette_must_set_every_ramp_the_surface_and_the_text_on_primary():
    value = auto()
    for name in ('ink-900', 'danger-500', 'accent-50'):
        del value['modes']['dark']['primitives'][name]
    del value['modes']['dark']['semantic']['surface']
    del value['modes']['dark']['semantic']['on-primary']
    assert set(error_paths(value)) == {
        'modes.dark.primitives.ink-900', 'modes.dark.primitives.danger-500', 'modes.dark.primitives.accent-50',
        'modes.dark.semantic.surface', 'modes.dark.semantic.on-primary'}
    # Everything else is optional: a block with only the required colors is a complete dark palette.
    minimal = auto()
    required = set(registry.DARK_REQUIRED)
    for layer in registry.LAYER_KEYS:
        minimal['modes']['dark'][layer] = {k: v for k, v in minimal['modes']['dark'][layer].items() if k in required}
    assert errors(minimal) == [], errors(minimal)


@pytest.mark.parametrize('layer,name,value,fragment', [
    ('primitives', 'ink-900', '#fff', 'color'),
    ('primitives', 'ink-900', '{ink-100}', 'literal'),
    ('primitives', 'accent-600', 'red', 'color'),
    ('primitives', 'accent-600', '#2b57db; background:url(x)', 'color'),
    ('primitives', 'accent-600', '#2b57dbff', 'color'),
    ('primitives', 'accent-600', 5, 'strings'),
    ('primitives', 'accent-600', None, 'strings'),
    ('primitives', 'accent-600', ['#ffffff'], 'strings'),
    ('primitives', 'shadow-card', 'url(https://x)', 'layers'),
    ('primitives', 'shadow-card', '0 1px 3px rgba(300,0,0,0.5)', 'rgba'),
    ('primitives', 'shadow-card', '0 1px 3px rgba(0,0,0,2)', 'rgba'),
    ('primitives', 'shadow-card', '0 100px 3px rgba(0,0,0,0.5)', '80px'),
    ('primitives', 'shadow-card', '0 1px 3px #000; x', 'layers'),
    ('primitives', 'shadow-card', 'x' * 500, 'at most'),
    ('semantic', 'surface', '{ink-100}', 'literal'),
    ('semantic', 'surface', 'transparent', 'color'),
    ('semantic', 'on-primary', 'rgb(0,0,0)', 'color'),
    ('semantic', 'scrim', '{missing}', 'Unknown token'),
    ('semantic', 'scrim', '{ink-900', 'reference'),
    ('semantic', 'scrim', '{radius}', 'cannot reference'),
    ('components', 'modal-scrim-alpha', '0.95', 'between'),
    ('components', 'modal-scrim-alpha', '{space-md}', 'cannot reference'),
    ('components', 'modal-scrim-alpha', '1e3', 'decimal'),
    ('components', 'sidebar-tone', 'medium', 'one of'),
    ('components', 'sidebar-tone', '{ink-900}', 'literal'),
    ('components', 'card-border', 'javascript:alert(1)', 'color'),
    ('components', 'card-shadow', '0 1px 3px #000, 0 1px 3px #000, 0 1px 3px #000, 0 1px 3px #000', 'layers'),
])
def test_dark_values_follow_the_same_closed_grammar(layer, name, value, fragment):
    theme = mutate_dark(layer, **{name.replace('-', '_'): value})
    found = errors(theme)
    assert found, 'expected an error'
    assert any(e['path'] == f'modes.dark.{layer}.{name}' for e in found), found
    assert any(fragment.lower() in e['message'].lower() for e in found if e['path'] == f'modes.dark.{layer}.{name}'), found
    with pytest.raises(ThemeError):
        validate_theme(theme)


def test_dark_references_may_point_at_base_tokens_but_never_loop_or_run_deep():
    value = mutate_dark('semantic', primary='{accent-700}', text_link='{primary}')
    assert errors(value) == []
    deep = auto()
    deep['modes']['dark']['semantic'].update({'surface-overlay': '{text-inverse}', 'text-inverse': '{surface-page}', 'surface-page': '{surface-sunken}'})
    deep['modes']['dark']['components'].update({'modal-bg': '{surface-overlay}'})
    assert any('deep' in e['message'] for e in errors(deep))
    loop = mutate_dark('semantic', text='{text-muted}', text_muted='{text}')
    assert any('cycle' in e['message'] for e in errors(loop))


def test_a_valid_base_with_an_invalid_dark_block_does_not_hide_base_errors_or_crash():
    value = auto()
    value['tokens']['primitives']['ink-900'] = 'nope'
    value['modes']['dark']['primitives']['ink-900'] = 'also nope'
    assert 'tokens.primitives.ink-900' in error_paths(value)
    value['modes'] = 'nope'
    assert 'modes' in error_paths(value)


# --- Contrast ------------------------------------------------------------------------------------

def test_every_light_pair_is_judged_again_for_the_dark_palette_with_the_same_thresholds():
    rows = contrast_report(auto())
    light, dark = [r for r in rows if r['mode'] == 'light'], [r for r in rows if r['mode'] == 'dark']
    assert [(r['id'], r['min'], r['level']) for r in light] == [(r['id'], r['min'], r['level']) for r in dark]
    assert len(light) == len(dark) > 25
    assert all(r['pass'] for r in dark if r['level'] == 'error')
    assert {r['id'] for r in dark} >= {'legacy-ink-900-on-surface', 'text-on-surface', 'text-link-on-surface', 'on-primary-on-primary',
                                       'focus-ring-on-surface', 'nav-item-fg-on-sidebar-bg', 'success-text-on-soft'}


def test_light_only_themes_report_exactly_what_revision_1_reported():
    rows = contrast_report(default_theme_v2())
    assert rows and all('mode' not in row for row in rows)
    assert contrast_report(default_theme_v2(registry_revision=1)) == rows


@pytest.mark.parametrize('layer,name,value,pair', [
    ('semantic', 'text', '#3a3b44', 'text on surface'),
    ('primitives', 'ink-600', '#2b2c34', 'text-muted on surface'),
    ('semantic', 'text-link', '#2b2c88', 'text-link on surface'),
    ('semantic', 'on-primary', '#8eb5ff', 'on-primary on primary'),
    ('semantic', 'focus-ring', '#1a1b21', 'focus-ring on surface'),
    ('primitives', 'danger-700', '#7f1d1d', 'danger-text on danger-soft'),
])
def test_a_failing_dark_pair_is_an_error_that_points_into_modes_dark(layer, name, value, pair):
    theme = mutate_dark(layer, **{name.replace('-', '_'): value})
    found = [e for e in errors(theme) if pair in e['message']]
    assert found and all(e['path'].startswith('modes.dark.') and e['message'].startswith('In dark mode, ') for e in found), errors(theme)
    # The light palette is unaffected: the same pair passes there.
    assert not any(pair in e['message'] and not e['message'].startswith('In dark mode') for e in errors(theme))


def test_a_dark_palette_must_have_lighter_text_than_surface():
    value = auto()
    value['modes']['dark']['semantic']['surface'] = '#ffffff'
    value['modes']['dark']['semantic']['text'] = '#101117'
    found = errors(value)
    assert any('lighter than the surface' in e['message'] and e['path'] == 'modes.dark.semantic.text' for e in found)
    # The same inversion is fine as a light palette.
    assert errors(default_theme_v2('client-acme')) == []


def test_a_light_scrim_in_a_dark_palette_warns():
    value = mutate_dark('semantic', scrim='#ffffff')
    assert errors(value) == []
    assert any(w['path'] == 'modes.dark.semantic.scrim' for w in check_theme(value)['warnings'])
    assert not any(w['path'].endswith('scrim') for w in check_theme(auto())['warnings'])


def test_a_dark_only_theme_is_checked_in_place_and_must_be_dark():
    value = default_theme_v2('client-acme', scheme='dark')
    assert errors(value) == []
    assert {r['mode'] for r in contrast_report(value)} == {'dark'}
    light_tokens = default_theme_v2('client-acme')
    light_tokens['color_scheme'] = 'dark'
    found = errors(light_tokens)
    assert [e['path'] for e in found] == ['tokens.semantic.text'] and 'lighter than the surface' in found[0]['message']
    broken = default_theme_v2('client-acme', scheme='dark')
    broken['tokens']['primitives']['ink-600'] = '#2b2c34'
    assert 'tokens.semantic.text-muted' in error_paths(broken)
    assert not any(e['message'].startswith('In dark mode') for e in errors(broken))


def test_nav_bar_contrast_follows_the_dark_tone():
    def row(theme):
        return next(r for r in contrast_report(theme) if r['mode'] == 'dark' and r['id'] == 'nav-item-fg-on-sidebar-bg')
    # On reversed ramps the `light` tone is the dark-looking bar, which is why the derived palette sets it.
    derived = row(auto())
    assert (derived['fg_value'], derived['bg_value']) == ('#d9dade', '#15161c') and derived['pass']
    flipped = row(mutate_dark('components', sidebar_tone='dark'))
    assert (flipped['fg_value'], flipped['bg_value']) == ('#454652', '#f7f7f8')
    # A bar painted by hand is still judged against its nav items.
    painted = mutate_dark('components', sidebar_bg='#d9dade')
    assert any('nav-item-fg on sidebar-bg' in e['message'] and e['message'].startswith('In dark mode') for e in errors(painted))


# --- Resolution ----------------------------------------------------------------------------------

def test_a_light_only_theme_resolves_without_any_dark_keys_whatever_mode_is_asked():
    value = default_theme_v2('client-acme')
    plain = resolve_theme(value)
    assert 'scheme' not in plain and 'data-fl-mode' not in plain['attrs']
    assert resolve_theme(value, 'dark') == plain == resolve_theme(value, 'light')


def test_an_auto_theme_resolves_light_by_default_and_dark_on_request():
    value = auto()
    light, dark = resolve_theme(value), resolve_theme(value, 'dark')
    assert light['scheme'] == {'offered': ['light', 'dark'], 'mode': 'light'} and light['attrs']['data-fl-mode'] == 'light'
    assert dark['scheme'] == {'offered': ['light', 'dark'], 'mode': 'dark'} and dark['attrs']['data-fl-mode'] == 'dark'
    assert light['vars']['--fl-surface'] == '255 255 255' and dark['vars']['--fl-surface'] == '21 22 28'
    assert dark['vars']['--fl-ink-50'] == '16 17 23' and dark['vars']['--fl-ink-950'] == '247 247 248'
    assert dark['vars']['--fl-on-primary'] == '16 17 23'
    # Everything that is not a color follows the base.
    assert {k: v for k, v in light['vars'].items() if k.startswith('--fl-size-')} == {k: v for k, v in dark['vars'].items() if k.startswith('--fl-size-')}
    assert dark['layout'] == light['layout'] and dark['shell'] == light['shell'] and dark['fonts'] == light['fonts']
    # A key only the dark block sets is present in dark and absent in light, so applyResolved removes it again.
    assert '--fl-sidebar-tone' not in light['vars'] and dark['vars']['--fl-sidebar-tone'] == 'light'
    assert dark['enums']['sidebar-tone'] == 'light' and light['enums']['sidebar-tone'] == 'dark'


@pytest.mark.parametrize('mode', [None, 'light', 'Dark', 'DARK', 5, '', 'system', ['dark']])
def test_anything_but_dark_resolves_an_auto_theme_light(mode):
    expected = 'dark' if mode == 'dark' else 'light'
    assert resolve_theme(auto(), mode)['scheme']['mode'] == expected


def test_a_dark_theme_is_always_dark_and_offers_nothing_else():
    value = default_theme_v2('client-acme', scheme='dark')
    for mode in (None, 'light', 'dark'):
        resolved = resolve_theme(value, mode)
        assert resolved['scheme'] == {'offered': ['dark'], 'mode': 'dark'} and resolved['attrs']['data-fl-mode'] == 'dark'
        assert resolved['vars']['--fl-surface'] == '21 22 28'


def test_offered_and_effective_modes():
    assert offered_modes(default_theme_v2('client-acme')) == ['light']
    assert offered_modes(auto()) == ['light', 'dark']
    assert offered_modes(default_theme_v2('client-acme', scheme='dark')) == ['dark']
    assert offered_modes({'api_version': 1}) == ['light'] and offered_modes('x') == ['light']
    light, both, dark = default_theme_v2('client-acme'), auto(), default_theme_v2('client-acme', scheme='dark')
    assert [effective_mode(light, p, True) for p in ('dark', 'system', None)] == ['light'] * 3
    assert [effective_mode(dark, p, False) for p in ('light', 'system', None)] == ['dark'] * 3
    assert effective_mode(both, 'dark', False) == 'dark' and effective_mode(both, 'light', True) == 'light'
    assert effective_mode(both, 'system', True) == 'dark' and effective_mode(both, None, False) == 'light'
    assert effective_mode(both, 'sepia', True) == 'dark'


def test_resolving_does_not_mutate_the_theme():
    value = auto()
    snapshot = deepcopy(value)
    resolve_theme(value, 'dark')
    derive_dark(value)
    assert value == snapshot


# --- The derived palette -------------------------------------------------------------------------

def test_the_default_dark_palette_is_derived_not_inverted():
    dark = derive_dark(default_theme_v2())
    p, s = dark['primitives'], dark['semantic']
    light = {t.name: t.default for t in registry.PRIMITIVES}
    # Ramps are reversed, so every ink-*/accent-* class lands on a coherent dark value.
    for palette in registry.COLOR_RAMPS:
        values = [p[f'{palette}-{shade}'] for shade in registry.SHADES]
        assert values == [light[f'{palette}-{shade}'] for shade in reversed(registry.SHADES)]
    assert [luminance(p[f'ink-{shade}']) for shade in registry.SHADES] == sorted(luminance(p[f'ink-{shade}']) for shade in registry.SHADES)
    # Surfaces are dark, text is light, and the surface sits between the page and ink-100.
    assert luminance(p['ink-50']) < luminance(s['surface']) < luminance(p['ink-100'])
    assert luminance(s['surface']) < 0.02 and luminance(p['ink-900']) > 0.8
    # It is not a per-channel inversion: white would become pure black, the page #080807.
    assert s['surface'] != '#000000' and p['ink-50'] != '#080807'
    # The pieces a reversal gets wrong are set by hand.
    assert s['on-primary'] == p['ink-50'] and s['scrim'] == '#000000'
    assert dark['components']['sidebar-tone'] == dark['components']['navbar-tone'] == 'light'
    # Quiet raised fills, not the lightest colour on the page, where light used the strongest ink.
    assert dark['components']['nav-item-active-bg'] == dark['components']['chat-message-user-bg'] == '{ink-200}'
    assert dark['components']['nav-item-active-fg'] == dark['components']['chat-message-user-fg'] == '{text}'
    assert p['shadow-modal'].startswith('0 24px 70px -20px rgba(0,0,0,0.85)') and p['shadow-card'] == '0 1px 3px 0 rgba(0,0,0,0.15)'
    assert 'font-sans' not in p and 'radius' not in p


def test_derivation_is_deterministic_and_idempotent_on_the_light_tokens():
    value = default_theme_v2('client-acme')
    assert derive_dark(value) == derive_dark(deepcopy(value))
    with_modes = default_theme_v2('client-acme', scheme='auto')
    assert derive_dark(with_modes) == with_modes['modes']['dark']
    assert json.dumps(derive_dark(value), sort_keys=True) == json.dumps(derive_dark(with_modes), sort_keys=True)


def test_literal_colors_outside_the_ramps_are_mapped_or_reflected():
    value = default_theme_v2('client-acme')
    value['tokens']['semantic'].update({'text-link': '#1c39ae', 'border-strong': '#b08040'})  # accent-700, and a color on no ramp
    value['tokens']['components'].update({'card-border': '#d9dade', 'button-primary-bg': '#0f766e'})
    dark = derive_dark(value)
    assert dark['semantic']['text-link'] == derive_dark(default_theme_v2('x'))['primitives']['accent-700']  # the dark value of the same step
    assert dark['components']['card-border'] == dark['primitives']['ink-200']
    reflected = dark['semantic']['border-strong']
    assert reflected not in ('#b08040', '#4f7fbf') and luminance(reflected) > luminance('#b08040')  # lightness reflected, hue kept
    assert dark['components']['button-primary-bg'] != '#0f766e'
    themed = deepcopy(value)
    themed['color_scheme'], themed['modes'] = 'auto', {'dark': dark}
    assert errors(themed) == [], errors(themed)


def test_what_a_theme_sets_itself_is_not_overridden_by_the_derived_fills():
    value = default_theme_v2('client-acme')
    value['tokens']['components'].update({'nav-item-active-bg': '{primary}', 'chat-message-user-bg': '{accent-700}', 'input-placeholder': '{ink-300}'})
    dark = derive_dark(value)
    for name in ('nav-item-active-bg', 'chat-message-user-bg', 'input-placeholder'):
        assert name not in dark['components']
    assert dark['components']['nav-item-active-fg'] == '{text}'


def test_text_set_as_text_inverse_becomes_plain_text_where_the_fill_under_it_is_derived():
    value = default_theme_v2('client-acme')
    value['tokens']['components'].update({'navbar-fg': '{text-inverse}', 'nav-item-hover-fg': '{text-inverse}',
                                          'nav-item-active-fg': '{text-inverse}', 'chat-message-user-fg': '{text-inverse}'})
    dark = derive_dark(value)
    assert [dark['components'][n] for n in ('navbar-fg', 'nav-item-hover-fg', 'nav-item-active-fg', 'chat-message-user-fg')] == ['{text}'] * 4
    # Where the theme also set the fill, the fill stays its own and so does the text on it.
    value['tokens']['components'].update({'nav-item-active-bg': '{accent-800}', 'chat-message-user-bg': '{accent-800}'})
    kept = derive_dark(value)['components']
    assert kept['navbar-fg'] == '{text}'
    assert 'nav-item-active-fg' not in kept and 'chat-message-user-fg' not in kept
    assert 'nav-item-active-bg' not in kept and 'chat-message-user-bg' not in kept


def test_a_bar_painted_by_hand_falls_back_to_the_surface_in_dark():
    value = default_theme_v2('client-acme')
    value['tokens']['components'].update({'navbar-bg': '{ink-800}', 'sidebar-bg': '#112233'})
    value['layout']['navbar']['position'] = 'top'
    dark = derive_dark(value)
    assert dark['components']['navbar-bg'] == dark['components']['sidebar-bg'] == '{surface}'
    themed = dict(deepcopy(value), color_scheme='auto', modes={'dark': dark})
    assert errors(themed) == []


def test_derived_dark_passes_every_error_level_pair_for_many_brands():
    """Rotate the default ramps through 24 hues and a few saturations: a derived palette must validate."""
    def rotate(color, degrees, saturation):
        r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        r, g, b = colorsys.hls_to_rgb((h + degrees / 360) % 1, l, min(1, s * saturation))
        return '#%02x%02x%02x' % (round(r * 255), round(g * 255), round(b * 255))

    failures = []
    for degrees in range(0, 360, 15):
        for saturation in (0.35, 1.0, 1.4):
            value = default_theme_v2('client-brand')
            for shade in registry.SHADES:
                for palette in ('accent', 'ink'):
                    name = f'{palette}-{shade}'
                    value['tokens']['primitives'][name] = rotate(value['tokens']['primitives'][name], degrees, saturation if palette == 'accent' else saturation * 0.3)
            if errors(value):
                continue  # a base that is not itself valid is not the derivation's problem
            value['color_scheme'], value['modes'] = 'auto', {'dark': derive_dark(value)}
            found = errors(value)
            if found:
                failures.append((degrees, saturation, found[0]['message']))
    assert failures == []


# --- v1 projection, packs and the published corpus --------------------------------------------

def test_old_clients_get_the_light_palette_of_an_auto_theme():
    value = auto()
    projected = project_v1(value)
    assert projected == project_v1(default_theme_v2('client-acme', '1.0.0', 'Acme'))
    assert projected['tokens']['surface'] == '#ffffff' and validate_theme(projected) == projected


def test_a_dark_only_theme_projects_its_own_palette_and_stays_a_valid_v1_manifest():
    projected = project_v1(default_theme_v2('client-acme', scheme='dark'))
    assert projected['tokens']['surface'] == '#15161c' and projected['tokens']['ink-900'] == '#ececee'
    assert validate_theme(projected) == projected


@pytest.mark.parametrize('scheme', ['auto', 'dark'])
def test_packs_carry_dark_themes_and_round_trip(scheme):
    value = default_theme_v2('client-acme', '1.0.0', 'Acme', scheme=scheme)
    data = create_theme_pack_v2(value, SOURCES)
    assert create_theme_pack_v2(value, SOURCES) == data, 'deterministic'
    assert validate_theme_pack(data)['theme'] == value


def test_a_pack_with_a_malformed_dark_block_cannot_be_created():
    value = auto()
    value['modes']['dark']['primitives']['ink-50'] = 'url(x)'
    with pytest.raises(Exception):
        create_theme_pack_v2(value, SOURCES)


RELEASE_HASHES = {
    'client-dusk-1.0.0': '21ccb4d44aa5e75fecde98c0531639479b1310c2e08cde9b39fe287e7fdd2170',
    'client-night-1.0.0': '9a6759c82ac1e7d2bec65fda27f18c75a0b0705de5888d06d109e748dffd1877',
}


@pytest.mark.parametrize('name', sorted(RELEASE_HASHES))
def test_published_dark_releases_hash_exactly_as_published(name):
    """Registry revision 2 is frozen from here on: these bytes must keep validating and hashing the same."""
    theme = json.loads((FIXTURES / f'{name}.json').read_text())
    assert theme['registry_revision'] == 2
    assert hashlib.sha256((json.dumps(validate_theme(theme), sort_keys=True, indent=2) + '\n').encode()).hexdigest() == RELEASE_HASHES[name]
    assert errors(theme) == []


def test_the_published_corpus_covers_every_scheme():
    schemes = {json.loads(p.read_text()).get('color_scheme') for p in FIXTURES.glob('*.json')}
    assert schemes == {'light', 'auto', 'dark'}


# --- Registry data for the frontend ---------------------------------------------------------------

def test_the_registry_json_carries_what_the_typescript_twin_needs():
    data = registry.registry_json()
    assert data['registry_revision'] == 2 and data['color_schemes'] == {'1': ['light'], '2': ['light', 'dark', 'auto']}
    assert data['modes']['required'] == list(registry.DARK_REQUIRED) and data['modes']['ramps'] == list(registry.COLOR_RAMPS)
    assert set(data['modes']['overridable']) == set(registry.MODE_TOKENS)
    assert 'rose' in data['hues'] and len(data['hues']['rose']) == 11 and data['black'] == {'light': '#000000', 'dark': '#f7f7f8'}


# --- Hostile input at scale ----------------------------------------------------------------------

def test_a_huge_dark_block_is_judged_in_linear_time():
    import time
    value = auto()
    value['modes']['dark']['components'].update({f'mystery-{i}': '#ffffff' for i in range(30000)})
    start = time.time()
    found = errors(value)
    assert time.time() - start < 3 and len(found) == 30000 and all(e['path'].startswith('modes.dark.components.mystery-') for e in found)


def test_deeply_nested_or_non_string_values_in_the_dark_block_are_errors_not_crashes():
    value = auto()
    nested = {}
    cursor = nested
    for _ in range(500):
        cursor['a'] = {}
        cursor = cursor['a']
    value['modes']['dark']['primitives']['ink-900'] = nested
    value['modes']['dark']['semantic']['scrim'] = float('nan')
    value['modes']['dark']['components']['sidebar-tone'] = {'x': [1, 2]}
    assert set(error_paths(value)) == {'modes.dark.primitives.ink-900', 'modes.dark.semantic.scrim', 'modes.dark.components.sidebar-tone'}


def test_every_layer_of_a_dark_theme_is_checked_even_when_the_base_is_broken():
    value = auto()
    value['tokens']['semantic'].pop('primary')
    found = error_paths(value)
    assert found == ['tokens.semantic.primary']
