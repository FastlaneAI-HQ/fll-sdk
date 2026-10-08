"""Registry revision 3 (SDK 1.5): an accessible default palette for new themes, the UI contrast pairs, four optional roles,
a dark palette whose text steps are solved rather than reversed, and quoted font stacks.

Revisions 1 and 2 are frozen (test_theme_frozen_r1.py, test_theme_frozen_r2.py): nothing here may reach a theme that
targets them.
"""
import json
from copy import deepcopy
from importlib.resources import files
from pathlib import Path

import pytest
from fastlanelabs_sdk import theme_registry as registry
from fastlanelabs_sdk import themes
from fastlanelabs_sdk.themes import check_theme, contrast_ratio, contrast_report, default_theme_v2, derive_dark, validate_theme

FIXTURES = Path(__file__).parent / 'fixtures/themes/v2'
ROLES = ('inverse', 'on-inverse', 'accent-text', 'accent-ui')
UI_IDS = [p.id for p in registry.CONTRAST_PAIRS if p.group == 'ui']


def resolved(theme, mode='light'):
    return themes._all_resolved(theme, mode)


def rows(theme, group='ui'):
    return [r for r in contrast_report(theme) if r.get('group') == group]


# --- The default palette for new themes ------------------------------------------------------------

def test_the_new_default_ink_ramp_reads_where_the_interface_uses_it():
    values = resolved(default_theme_v2())
    for step, minimum in (('ink-500', 4.5), ('ink-400', 4.5)):
        assert contrast_ratio(values[step], values['surface']) >= minimum, step
        assert contrast_ratio(values[step], values['ink-50']) >= minimum, step  # surface-page
    assert contrast_ratio(values['ink-300'], values['surface']) >= 3.0 and contrast_ratio(values['ink-300'], values['ink-50']) >= 3.0
    assert contrast_ratio(values['border-input'], values['surface']) >= 3.0
    # Monotone: every step is darker than the one before, so the ramp keeps its shape.
    ramp = [themes._luminance(values[f'ink-{shade}']) for shade in registry.SHADES]
    assert ramp == sorted(ramp, reverse=True) and len(set(ramp)) == 11


def test_the_new_default_status_600_steps_carry_text_and_white_text():
    values = resolved(default_theme_v2())
    for status in registry.STATUSES:
        fill = values[f'{status}-600']
        assert contrast_ratio(fill, values['surface']) >= 4.5 and contrast_ratio('#ffffff', fill) >= 4.5, status
        assert themes._luminance(fill) > themes._luminance(values[f'{status}-700']), status  # still lighter than the next step


@pytest.mark.parametrize('scheme', ['light', 'auto', 'dark'])
def test_the_new_default_has_no_error_warning_or_failing_pair(scheme):
    result = check_theme(default_theme_v2(scheme=scheme))
    assert result['errors'] == [] and result['warnings'] == []
    assert all(row['pass'] for row in result['contrast'])
    assert {row['id'] for row in result['contrast'] if row.get('group')} >= {'ink-400-on-surface', 'ink-500-on-surface-page', 'on-inverse-on-inverse'}


def test_earlier_revisions_still_start_from_the_old_palette():
    for revision in (1, 2):
        old = default_theme_v2(registry_revision=revision)
        assert old['tokens']['primitives']['ink-400'] == '#8f929e' and old['tokens']['semantic']['border-input'] == '{ink-200}'
        assert not set(ROLES) & set(old['tokens']['semantic'])
        assert old['tokens']['primitives']['success-600'] == '#059669'


def test_the_css_fallbacks_do_not_move_so_published_themes_render_as_before():
    assert registry.INDEX['ink-400'].default == '#8f929e' and registry.INDEX['border-input'].default == '{ink-200}'
    css = (Path(__file__).parents[1] / 'frontend/theme-defaults.css').read_text()
    assert '--fl-ink-400: 143 146 158;' in css and '--fl-success-600: 5 150 105;' in css


def test_the_platform_default_release_is_fastlane_2_0_0_and_current():
    data = json.loads(files('fastlanelabs_sdk.registry_data').joinpath('default-theme-v2.json').read_text())
    assert (data['id'], data['version'], data['api_version'], data['registry_revision']) == ('fastlane', '2.0.0', 2, 3)
    assert data == default_theme_v2('fastlane', '2.0.0', 'Fastlane') == validate_theme(data)
    # A client that asks for contract 1 gets the 27 tokens, with the accessible ramp.
    v1 = themes.project_v1(data)
    assert v1['tokens']['ink-400'] == '#6b6e7d' and len(v1['tokens']) == 27
    # fastlane 1.0.0 is a separate, untouched release.
    old = json.loads(files('fastlanelabs_sdk.registry_data').joinpath('default-theme.json').read_text())
    assert (old['id'], old['version'], old['tokens']['ink-400']) == ('fastlane', '1.0.0', '#8f929e')


# --- Optional roles ------------------------------------------------------------------------------

def test_the_four_roles_are_optional_in_revision_3_and_unknown_before():
    theme = default_theme_v2()
    for role in ROLES:
        assert registry.INDEX[role].optional and registry.INDEX[role].since == 3
        slim = deepcopy(theme)
        del slim['tokens']['semantic'][role]
        assert check_theme(slim)['errors'] == []
        assert validate_theme(slim) == slim  # nothing is defaulted into the manifest
    older = deepcopy(theme)
    older['registry_revision'] = 2
    assert any('Unknown token inverse' in e['message'] for e in check_theme(older)['errors'])
    assert registry.REF.fullmatch(registry.INDEX['on-inverse'].default)


def test_a_theme_that_leaves_the_roles_unset_renders_what_it_rendered_before():
    theme = default_theme_v2()
    for role in ROLES:
        del theme['tokens']['semantic'][role]
    vars_ = themes.resolve_theme(theme)['vars']
    assert not [name for name in vars_ if name in ('--fl-inverse', '--fl-on-inverse', '--fl-accent-text', '--fl-accent-ui')]
    effective = themes._Effective(resolved(theme))
    assert effective.get('inverse') == effective.get('ink-900') and effective.get('on-inverse') == effective.get('surface')
    assert effective.get('accent-text') == effective.get('accent-ui') == effective.get('accent-600')


def test_a_light_brand_gets_a_dark_inverse_fill_and_readable_brand_text_without_touching_on_primary():
    theme = default_theme_v2()
    theme['tokens']['primitives'].update({'accent-600': '#ffd400', 'accent-500': '#ffe14d', 'accent-700': '#8a6d00', 'accent-800': '#5c4900'})
    theme['tokens']['semantic'].update({'on-primary': '#101117', 'accent-text': '{accent-800}', 'accent-ui': '{accent-500}',
                                        'on-inverse': '#ffffff', 'text-link': '{accent-800}', 'focus-ring': '{accent-700}'})
    result = check_theme(theme)
    assert result['errors'] == []
    ids = {r['id'] for r in result['contrast']}
    # The roles take over from the raw steps: those legacy pairs are not judged for a theme that sets them.
    assert 'accent-600-on-surface' not in ids and 'on-primary-on-ink-900' not in ids
    assert {'accent-text-on-surface', 'on-inverse-on-inverse'} <= ids
    fails = {r['id'] for r in result['contrast'] if not r['pass'] and r.get('group') == 'ui'}
    assert fails == {'accent-ui-on-surface'}  # the pale yellow is not a 3:1 indicator; the pair is judged, not skipped


def test_legacy_pairs_are_judged_while_the_role_that_replaces_them_is_unset():
    theme = default_theme_v2()
    theme['tokens']['primitives'].update({'accent-600': '#ffd400'})
    theme['tokens']['semantic'].update({'on-primary': '#101117'})
    for role in ('accent-text', 'on-inverse'):
        del theme['tokens']['semantic'][role]
    fails = {r['id'] for r in check_theme(theme)['contrast'] if not r['pass']}
    assert {'accent-600-on-surface', 'accent-600-on-accent-50', 'on-primary-on-ink-900', 'on-primary-on-danger-600'} <= fails


# --- The UI pairs ----------------------------------------------------------------------------------

def test_ui_pairs_are_new_in_revision_3_warnings_except_the_inverse_pair():
    ui = [p for p in registry.CONTRAST_PAIRS if p.group == 'ui']
    assert len(ui) == 25 and all(p.since == 3 for p in ui)
    assert [p.id for p in ui if p.level == 'error'] == ['on-inverse-on-inverse']
    assert not [p for p in registry.CONTRAST_PAIRS if p.since < 3 and p.group]
    expected = {'ink-400-on-surface', 'ink-400-on-surface-page', 'ink-500-on-surface', 'ink-500-on-surface-page',
                'ink-400-on-accent-50', 'ink-500-on-accent-50', 'ink-500-on-accent-100',
                'accent-600-on-surface', 'accent-600-on-accent-50', 'accent-700-on-surface', 'accent-700-on-accent-50',
                'on-primary-on-ink-900', 'on-primary-on-ink-800', 'on-primary-on-danger-600', 'on-primary-on-success-600',
                'success-600-on-surface', 'warning-600-on-surface', 'danger-600-on-surface', 'info-600-on-surface'}
    assert expected <= set(UI_IDS)


def test_a_failing_ui_pair_is_a_warning_not_an_error():
    theme = default_theme_v2()
    theme['tokens']['primitives']['ink-400'] = '#b8bac2'
    result = check_theme(theme)
    assert result['errors'] == []
    assert any(w['path'] == 'tokens.primitives.ink-400' and '4.5:1' in w['message'] for w in result['warnings'])
    assert not next(r for r in result['contrast'] if r['id'] == 'ink-400-on-surface')['pass']


def test_ui_pairs_never_reach_a_theme_that_targets_revision_1_or_2():
    for revision in (1, 2):
        theme = default_theme_v2(registry_revision=revision)
        assert not rows(theme) and all('group' not in r for r in contrast_report(theme))
        assert len(contrast_report(theme)) == 35 + (0 if revision == 1 else 0)
    published = [json.loads(p.read_text()) for p in sorted(FIXTURES.glob('*.json'))]
    assert published and all(not rows(t) for t in published)


def test_every_pair_is_judged_for_the_dark_palette_too():
    result = check_theme(default_theme_v2(scheme='auto'))
    light = [r['id'] for r in result['contrast'] if r['mode'] == 'light']
    dark = [r['id'] for r in result['contrast'] if r['mode'] == 'dark']
    assert light == dark and 'ink-400-on-surface' in dark


# --- Dark palette ----------------------------------------------------------------------------------

def test_the_dark_text_steps_are_solved_against_the_dark_surface_not_reversed():
    theme = default_theme_v2()
    dark = derive_dark(theme)['primitives']
    surface = derive_dark(theme)['semantic']['surface']
    page = dark['ink-50']
    for shade, minimum in themes.DARK_TEXT_STEPS:
        for background in (surface, page):
            assert contrast_ratio(dark[f'ink-{shade}'], background) >= minimum, (shade, background)
    light = resolved(theme)
    ratios = [contrast_ratio(dark[f'ink-{shade}'], surface) for shade in (400, 500, 600, 700)]
    assert ratios == sorted(ratios) and len(set(ratios)) == 4  # the hierarchy survives
    for shade in (400, 500, 600, 700):  # at least what the light palette gives the step on its own surface
        assert contrast_ratio(dark[f'ink-{shade}'], surface) >= contrast_ratio(light[f'ink-{shade}'], light['surface']) - 0.01
    # The ink steps that were already readable (800 and up) are the reversal.
    assert dark['ink-800'] == light['ink-200']


def test_revision_2_still_reverses_and_leaves_the_steps_at_2_5_to_3_6():
    theme = default_theme_v2(registry_revision=2)
    dark = derive_dark(theme)
    assert dark['primitives']['ink-400'] == theme['tokens']['primitives']['ink-600']
    assert contrast_ratio(dark['primitives']['ink-400'], dark['semantic']['surface']) < 3


def test_dark_accent_text_and_indicator_move_until_they_read():
    theme = default_theme_v2()
    theme['tokens']['semantic'].update({'accent-text': '{accent-700}', 'accent-ui': '{accent-500}'})
    block = derive_dark(theme)
    surface, accent_50 = block['semantic']['surface'], block['primitives']['accent-50']
    assert contrast_ratio(block['primitives']['accent-700'], surface) >= 4.5 and contrast_ratio(block['primitives']['accent-700'], accent_50) >= 4.5
    assert contrast_ratio(block['primitives']['accent-500'], surface) >= 3.0


# --- Text on the accent tints (a caption inside a selected row, a chip, a tile) -------------------------------

TINT_PAIRS = ('ink-400-on-accent-50', 'ink-500-on-accent-50', 'ink-500-on-accent-100')
BRIGHT_TINTS = sorted((Path(__file__).parent / 'fixtures/themes-r3').glob('*-auto.json'), key=lambda p: p.name)  # a neon green, a yellow


def brights():
    return [json.loads(p.read_text()) for p in BRIGHT_TINTS]


def test_the_default_palette_reads_on_the_light_tints_too():
    result = check_theme(default_theme_v2())
    assert {r['id'] for r in result['contrast']} >= set(TINT_PAIRS)
    assert all(r['pass'] for r in result['contrast'] if r['id'] in TINT_PAIRS)
    # ink-400 was 4.46:1 on accent-50 (a selected row's caption); the registry's ink-400 moved one step so the pair holds
    values = resolved(default_theme_v2())
    assert contrast_ratio(values['ink-400'], values['accent-50']) >= 4.5 and contrast_ratio(values['ink-500'], values['accent-100']) >= 4.5


def test_the_pair_fixtures_are_the_audited_green_and_yellow_dark_brands():
    assert [p.name for p in BRIGHT_TINTS] == ['green-auto.json', 'yellow-dark-auto.json']
    assert [t['tokens']['primitives']['accent-600'] for t in brights()] == ['#00c853', '#ffd400']
    assert all(t['color_scheme'] == 'auto' and t['registry_revision'] == 3 for t in brights())


@pytest.mark.parametrize('theme', [default_theme_v2(scheme='auto')] + brights(), ids=lambda t: t['id'])
def test_every_ui_pair_holds_in_both_palettes_including_the_text_on_the_tints(theme):
    result = check_theme(theme)
    assert result['errors'] == [] and result['warnings'] == []
    rows_ = [r for r in result['contrast'] if r.get('group') == 'ui']
    assert {(r['id'], r['mode']) for r in rows_ if r['id'] in TINT_PAIRS} == {(i, m) for i in TINT_PAIRS for m in ('light', 'dark')}
    assert [(r['id'], r['mode']) for r in rows_ if not r['pass']] == []


@pytest.mark.parametrize('theme', [default_theme_v2()] + brights(), ids=lambda t: t['id'])
def test_the_dark_text_steps_reach_their_targets_on_the_surface_the_page_and_the_tints(theme):
    block = derive_dark(theme)
    dark, surface = block['primitives'], block['semantic']['surface']
    page = dark['ink-50']
    for shade, minimum in themes.DARK_TEXT_STEPS:
        for background in (surface, page):
            assert contrast_ratio(dark[f'ink-{shade}'], background) >= minimum, (shade, background)
        for tint in themes.DARK_TEXT_TINTS.get(shade, ()):
            assert contrast_ratio(dark[f'ink-{shade}'], dark[tint]) >= minimum, (shade, tint)


@pytest.mark.parametrize('theme', [default_theme_v2()] + brights(), ids=lambda t: t['id'])
def test_a_bright_tint_is_settled_not_answered_by_pushing_every_text_step_to_white(theme):
    """The dark accent tints of a saturated brand are far brighter than the surface; reaching 4.5:1 on them by lifting the text alone
    would make ink-400 to ink-700 one near-white. The tints are darkened first (and stay tints), so the hierarchy survives."""
    block = derive_dark(theme)
    dark, surface = block['primitives'], block['semantic']['surface']
    light = resolved(theme)
    ratios = [contrast_ratio(dark[f'ink-{shade}'], surface) for shade in (400, 500, 600, 700)]
    assert all(later - earlier >= 0.5 for earlier, later in zip(ratios, ratios[1:])), ratios
    assert ratios[0] <= 6.0 and ratios[1] <= 6.8  # ink-400 stays a caption (the light palette gives it 5.1), not a headline
    lumas = [themes._luminance(dark[f'accent-{shade}']) for shade in registry.SHADES]
    assert lumas == sorted(lumas) and len(set(lumas)) == 11, 'the dark accent ramp keeps its order'
    assert contrast_ratio(dark['accent-50'], surface) >= themes.DARK_TINT_FLOORS['accent-50'] - 1e-9
    assert contrast_ratio(dark['accent-100'], surface) >= themes.DARK_TINT_FLOORS['accent-100'] - 1e-9
    # it is still the brand's hue, scaled: a tint is darkened by scaling channels, never replaced
    reversed_tint = light['accent-950']
    assert all(a <= b for a, b in zip(themes._channels(dark['accent-50']), themes._channels(reversed_tint)))
    reversed_ink = light['ink-600']
    assert dark['ink-400'] != reversed_ink and dark['ink-500'] != light['ink-500']


@pytest.mark.parametrize('theme', brights(), ids=lambda t: t['id'])
def test_the_stored_dark_ramps_of_the_builder_fixtures_are_what_derive_dark_gives(theme):
    """The builder adds a few dark roles of its own (the input border, the placeholder); the ramps and the surface are derive_dark's."""
    plain = deepcopy(theme)
    plain['color_scheme'] = 'light'
    del plain['modes']
    block = derive_dark(plain)
    stored = theme['modes']['dark']
    assert block['primitives'] == stored['primitives']
    assert {name: block['semantic'][name] for name in ('surface', 'on-primary')} == {name: stored['semantic'][name] for name in ('surface', 'on-primary')}


@pytest.mark.parametrize('theme', brights(), ids=lambda t: t['id'])
def test_the_audits_d3_caption_on_a_selected_tile_failed_before_and_reads_now(theme):
    """D3: with the text steps solved against the surface and the page only (what 1.5.0-dev did), ink-500 on the dark accent-50 was
    about 4.0:1 for a neon green and a yellow (Admin > Apps, 9 nodes each)."""
    plain = deepcopy(theme)
    plain['color_scheme'] = 'light'
    del plain['modes']
    reversed_ramps = derive_dark({**plain, 'registry_revision': 2})  # registry 2 derives by reversal alone
    surface, primitives = reversed_ramps['semantic']['surface'], dict(reversed_ramps['primitives'])
    light = resolved(plain)
    for shade, minimum in themes.DARK_TEXT_STEPS:
        primitives[f'ink-{shade}'] = themes._lighten_until(
            primitives[f'ink-{shade}'], [surface, primitives['ink-50']],
            max(minimum, contrast_ratio(light[f'ink-{shade}'], light['surface'])))
    assert contrast_ratio(primitives['ink-500'], primitives['accent-50']) < 4.5
    assert contrast_ratio(primitives['ink-400'], primitives['accent-50']) < 4.5
    now = derive_dark(plain)['primitives']
    assert contrast_ratio(now['ink-500'], now['accent-50']) >= 4.5 and contrast_ratio(now['ink-400'], now['accent-50']) >= 4.5


def test_a_revision_2_theme_still_reverses_and_ignores_the_tints():
    two = default_theme_v2(registry_revision=2)
    block = derive_dark(two)
    assert block['primitives']['accent-50'] == two['tokens']['primitives']['accent-950']
    assert block['primitives']['ink-400'] == two['tokens']['primitives']['ink-600']


def test_derive_dark_is_deterministic_and_the_result_validates():
    theme = default_theme_v2()
    assert derive_dark(theme) == derive_dark(deepcopy(theme))
    auto = default_theme_v2(scheme='auto')
    assert check_theme(auto)['errors'] == [] and auto['modes']['dark'] == derive_dark(theme)


# --- Fonts -----------------------------------------------------------------------------------------

@pytest.mark.parametrize('font', registry.webfonts(), ids=lambda f: f['family'])
def test_a_quoted_stack_of_every_allow_listed_family_validates_and_resolves(font):
    stack = f"'{font['family']}', ui-sans-serif, system-ui, sans-serif"
    theme = default_theme_v2()
    theme['tokens']['primitives']['font-sans'] = stack
    result = check_theme(theme)
    assert result['errors'] == [] and not [w for w in result['warnings'] if 'font-sans' in w['path']]
    resolved_theme = themes.resolve_theme(theme)
    assert resolved_theme['vars']['--fl-font-sans'] == stack
    assert [f['family'] for f in resolved_theme['fonts']][0] == font['family']


def test_an_unquoted_family_with_a_digit_warns_at_revision_3_and_not_before():
    stack = 'Source Sans 3, ui-sans-serif, system-ui, sans-serif'
    theme = default_theme_v2()
    theme['tokens']['primitives']['font-sans'] = stack
    result = check_theme(theme)
    assert result['errors'] == []
    assert [w['path'] for w in result['warnings'] if 'must be quoted' in w['message']] == ['tokens.primitives.font-sans']
    older = default_theme_v2(registry_revision=2)
    older['tokens']['primitives']['font-sans'] = stack
    assert [w for w in check_theme(older)['warnings'] if 'quoted' in w['message']] == [] and check_theme(older)['errors'] == []
    quoted = default_theme_v2()
    quoted['tokens']['primitives']['font-sans'] = "Open Sans, 'Source Serif 4', serif"
    assert [w for w in check_theme(quoted)['warnings'] if 'quoted' in w['message']] == []
