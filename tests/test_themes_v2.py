import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastlanelabs_sdk import theme_registry as registry
from fastlanelabs_sdk import themes
from fastlanelabs_sdk.themes import (
    ThemeError, check_theme, contrast_report, default_theme_v2, project_v1, resolve_theme,
    upgrade_v1, upgrade_v1_report, validate_theme,
)

FIXTURES = Path(__file__).parent / 'fixtures/themes'
V1_FIXTURES = ['fastlane-1.0.0', 'precision-hose-1.0.0', 'precision-hose-1.1.0']


def v1(name):
    return json.loads((FIXTURES / f'{name}.json').read_text())


def theme(**changes):
    value = default_theme_v2('client-acme', '1.0.0', 'Acme')
    value.update(changes)
    return value


def mutate(change):
    value = theme()
    change(value)
    return value


def prim(**tokens):
    return lambda t: t['tokens']['primitives'].update({k.replace('_', '-'): v for k, v in tokens.items()})


def sem(**tokens):
    return lambda t: t['tokens']['semantic'].update({k.replace('_', '-'): v for k, v in tokens.items()})


def comp(**tokens):
    return lambda t: t['tokens']['components'].update({k.replace('_', '-'): v for k, v in tokens.items()})


def paths(value):
    return [e['path'] for e in check_theme(value)['errors']]


def test_the_default_theme_is_complete_valid_and_unchanged_by_validation():
    value = default_theme_v2()
    validated = validate_theme(value)
    assert validated == value and validated is not value
    validated['tokens']['primitives']['ink-900'] = '#000000'
    validated['layout']['sidebar']['side'] = 'right'
    assert value['tokens']['primitives']['ink-900'] == '#1a1b21'
    assert value['layout']['sidebar']['side'] == 'left'


def test_validation_never_injects_defaults_so_hashes_are_stable():
    value = theme()
    value['tokens']['components'] = {'button-radius': '{radius-pill}'}
    first = json.dumps(validate_theme(value), sort_keys=True, indent=2)
    assert first == json.dumps(value, sort_keys=True, indent=2)
    del value['tokens']['semantic']['primary']
    with pytest.raises(ThemeError):
        validate_theme(value)


def test_validate_theme_dispatches_on_api_version():
    assert validate_theme(v1('fastlane-1.0.0'))['api_version'] == 1
    assert validate_theme(theme())['api_version'] == 2
    with pytest.raises(ThemeError, match='Unsupported theme API version'):
        validate_theme(dict(theme(), api_version=3))
    assert themes.theme_contracts == (1, 2)


@pytest.mark.parametrize('change,path', [
    (lambda t: t.update(script='x'), ''),
    (lambda t: t.pop('registry_revision'), ''),
    (lambda t: t.update(registry_revision=0), 'registry_revision'),
    (lambda t: t.update(registry_revision=True), 'registry_revision'),
    (lambda t: t.update(registry_revision='1'), 'registry_revision'),
    (lambda t: t.update(registry_revision=3), 'registry_revision'),
    (lambda t: t.update(id='../escape'), 'id'),
    (lambda t: t.update(id='Acme'), 'id'),
    (lambda t: t.update(version='1.0'), 'version'),
    (lambda t: t.update(label=''), 'label'),
    (lambda t: t.update(label='x' * 81), 'label'),
    (lambda t: t.update(registry_revision=1, color_scheme='dark'), 'color_scheme'),
    (lambda t: t.update(registry_revision=1, color_scheme='auto'), 'color_scheme'),
    (lambda t: t.update(color_scheme='both'), 'color_scheme'),
    (lambda t: t.update(modes={'dark': {}}), 'modes'),
    (lambda t: t['tokens'].pop('components'), 'tokens'),
    (lambda t: t['tokens'].update(extra={}), 'tokens'),
    (lambda t: t.update(tokens=[]), 'tokens'),
    (lambda t: t['tokens']['primitives'].pop('ink-900'), 'tokens.primitives.ink-900'),
    (lambda t: t['tokens']['semantic'].pop('primary'), 'tokens.semantic.primary'),
    (lambda t: t['tokens']['primitives'].update({'mystery': '#ffffff'}), 'tokens.primitives.mystery'),
    (lambda t: t['tokens']['components'].update({'button-glow': '#ffffff'}), 'tokens.components.button-glow'),
    (lambda t: t['tokens']['primitives'].update({'primary': '#ffffff'}), 'tokens.primitives.primary'),
    (lambda t: t['tokens']['components'].update({'radius': '4px'}), 'tokens.components.radius'),
    (lambda t: t['tokens']['semantic'].update({'primary': 5}), 'tokens.semantic.primary'),
    (lambda t: t['tokens']['semantic'].update({'primary': None}), 'tokens.semantic.primary'),
    (lambda t: t['tokens'].update(semantic=[]), 'tokens.semantic'),
])
def test_structure_errors_carry_a_path(change, path):
    result = check_theme(mutate(change))
    assert result['errors'] and path in [e['path'] for e in result['errors']], result['errors']
    with pytest.raises(ThemeError) as failure:
        validate_theme(mutate(change))
    assert failure.value.errors == result['errors']


@pytest.mark.parametrize('change', [
    prim(**{'ink_900': '#fff'}), prim(**{'ink_900': '#1a1b21ff'}), prim(**{'ink_900': 'red'}), prim(**{'ink_900': 'rgb(0,0,0)'}),
    prim(**{'ink_900': '#fff;display:none'}), prim(**{'ink_900': 'url(https://x)'}),
    prim(**{'font_sans': 'url(https://example.com/font)'}), prim(**{'font_display': 'x;y'}), prim(font_mono=''),
    prim(radius='17px'), prim(radius='1.5px'), prim(radius='0.5rem'), prim(radius='-1px'), prim(radius='8'),
    prim(radius_pill='20000px'), prim(radius_sm='33px'),
    prim(size_scale='0.5'), prim(size_scale='1.5'), prim(size_scale='abc'), prim(size_scale='1.2345'),
    prim(size_md='5px'), prim(size_md='100px'), prim(size_md='13'), prim(size_md='1em'),
    prim(weight_medium='450'), prim(weight_medium='1000'), prim(weight_medium='bold'),
    prim(leading_normal='3'), prim(leading_normal='0.5'), prim(tracking_tight='-1em'), prim(tracking_tight='0.1'),
    prim(space_md='-4px'), prim(space_md='100px'), prim(space_md='1.234px'), prim(space_md='12em'),
    prim(space_compact_factor='1.5'), prim(space_compact_factor='0.2'),
    prim(border_width='9px'), prim(focus_ring_width='1px'), prim(focus_ring_width='9px'),
    prim(duration_fast='2s'), prim(duration_fast='1001ms'), prim(duration_fast='fast'),
    prim(ease_standard='bounce'), prim(ease_standard='cubic-bezier(0.4,0,0.2,2)'), prim(ease_standard='cubic-bezier(0.4,0,0.2)'),
    prim(shadow_card='url(x)'), prim(shadow_card='0 1px 3px'), prim(shadow_card='0 1px 3px red'),
    prim(shadow_card='0 100px 3px rgba(0,0,0,0.1)'), prim(shadow_card='0 1px -3px rgba(0,0,0,0.1)'),
    prim(shadow_card='0 1px 3px rgba(0,0,0,2)'), prim(shadow_card='0 1px 3px rgba(300,0,0,0.5)'),
    prim(shadow_card='0 1px 3px #fff'), prim(shadow_card='0 1px 3px 0 2px #000000'),
    prim(shadow_card='0 1px 1px #000000, 0 1px 1px #000000, 0 1px 1px #000000, 0 1px 1px #000000'),
    prim(shadow_card='inset 0 1px 3px #000000'), prim(shadow_card='0 1px 3px #000000; x'),
    sem(text='not-a-color'), sem(text='{missing}'), sem(text='{ink-900'), sem(text='{}'), sem(text='{INK-900}'),
    sem(text='{radius}'), sem(text='{font-sans}'), sem(text='{size-md}'), sem(text='{button-radius}'),
    comp(button_variant='ghost'), comp(button_transform='shout'), comp(toast_position='middle'),
    comp(button_height='20px'), comp(button_height='{space-md}'), comp(input_height='31px'),
    comp(button_radius='#ffffff'), comp(button_radius='{ink-900}'), comp(button_radius='{size-md}'),
    comp(button_size='{radius}'), comp(button_size='4px'), comp(button_size='{space-md}'),
    comp(button_weight='{radius}'), comp(button_primary_bg='10px'), comp(button_primary_bg='{space-md}'),
    comp(button_pad_x='{ink-900}'), comp(button_pad_x='200px'), comp(modal_scrim_alpha='0.9'),
    comp(modal_scrim_alpha='{space-md}'), comp(button_variant='{radius}'),
    comp(button_primary_bg='{button-primary-fg}'), comp(button_shadow='{ink-900}'), comp(button_shadow='{shadow-card} 1px'),
    comp(drawer_width='100px'), comp(gate_max_width='1000px'), comp(scrollbar_width='1px'),
    comp(page_header_title_tracking='{radius}'), comp(page_header_title_font='serif'),
])
def test_bad_values_are_rejected(change):
    value = mutate(change)
    assert check_theme(value)['errors'], 'expected an error'
    with pytest.raises(ThemeError):
        validate_theme(value)


def test_v1_named_tokens_are_literal_only():
    for name in ('ink-900', 'accent-600', 'surface', 'on-primary', 'font-sans', 'font-mono', 'radius'):
        group = 'semantic' if name in ('surface', 'on-primary') else 'primitives'
        value = theme()
        value['tokens'][group][name] = '{ink-800}' if name != 'font-sans' else '{font-mono}'
        assert paths(value) == [f'tokens.{group}.{name}'], name


def test_references_cannot_cycle_or_run_too_deep():
    cycle = mutate(lambda t: t['tokens']['semantic'].update({'text': '{text-muted}', 'text-muted': '{text}'}))
    assert any('cycle' in e['message'] for e in check_theme(cycle)['errors'])
    chain = mutate(lambda t: (t['tokens']['semantic'].update({
        'surface-overlay': '{text-inverse}', 'text-inverse': '{surface-page}', 'surface-page': '{surface-sunken}'}),
        t['tokens']['components'].update({'modal-bg': '{surface-overlay}'})))
    assert any('deep' in e['message'] for e in check_theme(chain)['errors'])
    ok = mutate(lambda t: (t['tokens']['semantic'].update({'surface-overlay': '{surface-sunken}'}),
                           t['tokens']['components'].update({'modal-bg': '{surface-overlay}'})))
    assert check_theme(ok)['errors'] == []


def test_valid_references_literals_and_every_value_type_are_accepted():
    value = mutate(lambda t: (
        t['tokens']['primitives'].update({
            'ink-900': '#1A1B21', 'radius': '4px', 'font-sans': "'Open Sans', Arial, sans-serif",
            'size-scale': '1.1', 'shadow-card': '0 1px 3px 0 rgba(16,17,23,0.06), 0 8px 28px -14px #101117',
            'space-md': '0.75rem', 'tracking-tight': '-0.02em', 'ease-standard': 'ease-in-out', 'duration-base': '200ms',
            'weight-bold': '800'}),
        t['tokens']['semantic'].update({'primary': '#c0392b', 'text-link': '{primary}', 'danger-soft': '#ffeeee'}),
        t['tokens']['components'].update({
            'button-radius': '{radius-pill}', 'button-pad-x': '{space-lg}', 'button-size': '{size-lg}',
            'button-weight': '{weight-bold}', 'button-shadow': '{shadow-card}', 'button-transform': 'uppercase',
            'button-height': '40px', 'button-primary-bg': '{danger-solid}', 'page-header-title-size': '22px',
            'page-header-title-tracking': '{tracking-wide}', 'card-shadow': '0 2px 4px #000000', 'nav-item-active-bg': '#112233',
            'toast-position': 'top-center', 'modal-scrim-alpha': '0.8', 'chat-message-leading': '{leading-tight}'})))
    assert check_theme(value)['errors'] == []
    assert validate_theme(value) == value


def test_every_error_is_reported_not_only_the_first():
    value = mutate(lambda t: (t.update(id='X'), t['tokens']['primitives'].update({'radius': '99px'}),
                              t['layout']['sidebar'].update({'width': 5})))
    assert {e['path'] for e in check_theme(value)['errors']} == {'id', 'tokens.primitives.radius', 'layout.sidebar.width'}


@pytest.mark.parametrize('bad', [None, [], 'theme', 7])
def test_non_objects_are_rejected_without_crashing(bad):
    with pytest.raises(ThemeError):
        validate_theme(bad)
    assert check_theme(bad)['errors']


@pytest.mark.parametrize('section,key,value', [
    ('', 'density', 'tight'), ('', 'scroll', 'both'),
    ('sidebar', 'side', 'middle'), ('sidebar', 'style', 'drawer'), ('sidebar', 'surface', 'glass'),
    ('sidebar', 'width', 55), ('sidebar', 'width', 321), ('sidebar', 'width', '56'), ('sidebar', 'width', True),
    ('sidebar', 'behavior', 'absolute'), ('sidebar', 'collapse_below', 479), ('sidebar', 'collapse_below', 1281),
    ('navbar', 'position', 'left'), ('navbar', 'behavior', 'floating'), ('navbar', 'height', 39), ('navbar', 'height', 97),
    ('navbar', 'align', 'end'), ('navbar', 'show_brand', 1), ('navbar', 'show_brand', 'yes'),
    ('content', 'max_width', 100), ('content', 'max_width', 639), ('content', 'max_width', 1921), ('content', 'max_width', -1),
    ('content', 'align', 'end'), ('content', 'padding', '2xl'), ('content', 'padding', '12px'), ('content', 'gap', 'huge'),
])
def test_bad_layout_options_are_rejected(section, key, value):
    layout = default_theme_v2()['layout']
    (layout[section] if section else layout)[key] = value
    result = check_theme(theme(layout=layout))
    assert any(e['path'].startswith('layout') for e in result['errors'])


@pytest.mark.parametrize('shape', ['missing-group', 'extra-group', 'extra-key', 'missing-key', 'not-object'])
def test_layout_shape_is_exact(shape):
    layout = default_theme_v2()['layout']
    if shape == 'missing-group':
        del layout['navbar']
    elif shape == 'extra-group':
        layout['footer'] = {}
    elif shape == 'extra-key':
        layout['sidebar']['color'] = 'red'
    elif shape == 'missing-key':
        del layout['sidebar']['width']
    else:
        layout['content'] = 'wide'
    assert any(e['path'].startswith('layout') for e in check_theme(theme(layout=layout))['errors'])
    assert check_theme(theme(layout=layout))['errors']


def test_layout_cross_rules_and_warnings():
    layout = default_theme_v2()['layout']
    layout['sidebar']['side'] = 'hidden'
    assert check_theme(theme(layout=layout))['errors'][0]['message'].startswith('At least one of the sidebar')
    layout['navbar']['position'] = 'top'
    assert check_theme(theme(layout=layout))['errors'] == []
    warned = default_theme_v2()['layout']
    warned['sidebar'].update(behavior='sticky')
    warned['navbar'].update(position='bottom', behavior='static')
    messages = [w['path'] for w in check_theme(theme(layout=warned))['warnings']]
    assert 'layout.sidebar.behavior' in messages and 'layout.navbar.behavior' in messages
    warned['scroll'] = 'page'
    assert not [w for w in check_theme(theme(layout=warned))['warnings'] if w['path'].endswith('behavior')]
    wide = default_theme_v2()['layout']
    wide['sidebar']['width'] = 200
    assert 'layout.sidebar.width' in [w['path'] for w in check_theme(theme(layout=wide))['warnings']]
    narrow = registry.default_layout('panel')
    narrow['sidebar']['width'] = 100
    assert 'layout.sidebar.width' in [w['path'] for w in check_theme(theme(layout=narrow))['warnings']]


def test_contrast_hard_errors_apply_to_v2_only():
    low = '#c8c8c8'
    for change, text in [
        (prim(ink_900=low), 'ink-900 on surface'),
        (sem(text='{ink-300}'), 'text on surface'),
        (sem(text_muted='{ink-200}'), 'text-muted on surface'),
        (sem(on_primary='#cccccc'), 'on-primary on'),
        (sem(text_link='{ink-200}'), 'text-link on surface'),
        (sem(text_inverse='{ink-900}'), 'text-inverse on surface-inverse'),
        (sem(success_text='{success-300}'), 'success-text on success-soft'),
        (sem(warning_text='{warning-400}'), 'warning-text on warning-soft'),
        (sem(danger_text='{danger-300}'), 'danger-text on danger-soft'),
        (sem(info_text='{info-300}'), 'info-text on info-soft'),
        (sem(focus_ring='{ink-100}'), 'focus-ring on surface'),
        (comp(nav_item_fg='{ink-900}'), 'nav-item-fg on sidebar-bg'),
    ]:
        errors = check_theme(mutate(change))['errors']
        assert any(text in e['message'] for e in errors), (text, errors)
    # v1 manifests are never re-judged: a legacy-passing v1 theme that fails v2's text-muted still validates.
    legacy = v1('fastlane-1.0.0')
    legacy['tokens']['ink-600'] = '#dddddd'
    assert validate_theme(legacy)['tokens']['ink-600'] == '#dddddd'
    assert any('text-muted' in e['message'] for e in check_theme(upgrade_v1(legacy))['errors'])


def test_nav_contrast_follows_the_bar_tone_and_visibility():
    light = mutate(comp(sidebar_tone='light', nav_item_fg='{ink-100}'))
    assert any('nav-item-fg on sidebar-bg' in e['message'] for e in check_theme(light)['errors'])
    fine = mutate(comp(sidebar_tone='light'))
    assert check_theme(fine)['errors'] == []
    # The navbar shares nav-item-fg: dark text on a dark navbar fails, but only while the navbar is shown.
    shared = mutate(comp(navbar_tone='light', nav_item_fg='{ink-300}'))
    shared['layout']['navbar']['position'] = 'top'
    assert any('nav-item-fg on navbar-bg' in e['message'] for e in check_theme(shared)['errors'])
    shared['layout']['navbar']['position'] = 'hidden'
    assert not any('navbar-bg' in e['message'] for e in check_theme(shared)['errors'])
    hidden_sidebar = mutate(comp(nav_item_fg='{ink-900}'))
    hidden_sidebar['layout']['sidebar']['side'] = 'hidden'
    hidden_sidebar['layout']['navbar']['position'] = 'top'
    assert any('navbar-bg' in e['message'] for e in check_theme(hidden_sidebar)['errors'])
    assert not any('sidebar-bg' in e['message'] for e in check_theme(hidden_sidebar)['errors'])


def test_component_contrast_only_warns_and_a_report_lists_every_pair():
    value = mutate(comp(button_primary_bg='{accent-200}'))
    result = check_theme(value)
    assert result['errors'] == []
    assert any('button-primary-fg on button-primary-bg' in w['message'] for w in result['warnings'])
    report = contrast_report(value)
    row = next(r for r in report if r['id'] == 'button-primary')
    assert row['pass'] is False and row['level'] == 'warning' and row['ratio'] < 4.5
    assert contrast_report(v1('fastlane-1.0.0')) == [] and contrast_report(mutate(lambda t: t.pop('layout'))) == []
    legacy = next(r for r in contrast_report(theme()) if r['id'] == 'legacy-ink-900-on-surface')
    assert legacy['min'] == 4.5 and legacy['pass'] is True and legacy['fg_value'] == '#1a1b21'


def test_a_theme_from_a_newer_registry_asks_for_a_workspace_update():
    errors = check_theme(theme(registry_revision=3))['errors']
    assert 'Update the workspace' in errors[0]['message']


def test_project_v1_is_always_a_valid_v1_manifest():
    value = mutate(lambda t: (t['layout']['sidebar'].update(style='panel', width=224),
                              t['tokens']['primitives'].update({'accent-600': '#aa0000'}),
                              t['tokens']['components'].update({'button-radius': '{radius-pill}'})))
    projected = project_v1(value)
    assert projected['api_version'] == 1 and projected['layout'] == {'density': 'comfortable', 'navigation': 'sidebar'}
    assert set(projected['tokens']) == registry.V1_TOKEN_NAMES
    assert projected['tokens']['accent-600'] == '#aa0000'
    assert validate_theme(projected) == projected
    assert project_v1(projected) == projected


@pytest.mark.parametrize('name', V1_FIXTURES)
def test_v1_upgrades_to_v2_with_identical_tokens_and_layout(name):
    original = v1(name)
    snapshot = deepcopy(original)
    upgraded = upgrade_v1(original)
    assert original == snapshot, 'upgrade must not mutate its input'
    assert check_theme(upgraded)['errors'] == []
    assert validate_theme(upgraded) == upgraded
    assert (upgraded['id'], upgraded['version'], upgraded['label']) == (original['id'], original['version'], original['label'])
    # Round trip: identical manifest, identical published hash.
    assert project_v1(upgraded) == validate_theme(original)
    assert hashlib.sha256(json.dumps(project_v1(upgraded), sort_keys=True, indent=2).encode()).hexdigest() == \
        hashlib.sha256(json.dumps(validate_theme(original), sort_keys=True, indent=2).encode()).hexdigest()
    # The 27 v1 variables resolve to exactly what the v1 applier sets.
    legacy = resolve_theme(original)['vars']
    modern = resolve_theme(upgraded)['vars']
    assert len(legacy) == 27 and all(modern[key] == value for key, value in legacy.items())
    assert resolve_theme(upgraded)['attrs']['data-density'] == original['layout']['density']
    expected_style = 'panel' if original['layout']['navigation'] == 'sidebar' else 'rail'
    assert upgraded['layout']['sidebar']['style'] == expected_style
    assert upgraded['tokens']['components'] == {}
    assert upgraded['tokens']['primitives']['font-display'] == original['tokens']['font-sans']


def test_the_fastlane_upgrade_is_exactly_the_registry_default():
    upgraded = upgrade_v1(v1('fastlane-1.0.0'))
    default = default_theme_v2('fastlane', '1.0.0', 'Fastlane')
    assert upgraded == default
    assert resolve_theme(upgraded)['vars'] == resolve_theme(default)['vars']


def test_v1_resolution_matches_what_the_v1_applier_sets():
    resolved = resolve_theme(v1('precision-hose-1.1.0'))
    assert resolved['api_version'] == 1
    assert resolved['vars']['--fl-accent-600'] == '179 38 30'
    assert resolved['vars']['--fl-radius'] == '2px' and resolved['vars']['--fl-font-sans'] == 'Arial, Helvetica, sans-serif'
    assert resolved['attrs'] == {'data-density': 'comfortable', 'data-theme': 'precision-hose'}
    assert 'data-fl-contract' not in resolved['attrs']
    assert resolved['shell'] == {'attrs': {}, 'vars': {}}


def test_upgrade_notes_say_a_fork_is_an_approximation():
    report = upgrade_v1_report(v1('fastlane-1.0.0'))
    assert 'approximates' in report['notes'][0] and report['theme'] == upgrade_v1(v1('fastlane-1.0.0'))


def presentation(workspace, **styles):
    from fastlanelabs_sdk.theme_packs import validate_presentation
    return validate_presentation({'api_version': 1, 'workspace': workspace, 'styles': styles})


def slot(name, **extra):
    return dict({'type': 'slot', 'name': name}, **extra)


@pytest.mark.parametrize('nav_first,side', [(True, 'left'), (False, 'right')])
@pytest.mark.parametrize('actions_first,position', [(True, 'top'), (False, 'bottom')])
def test_pack_layouts_map_onto_sidebar_side_and_navbar_position(nav_first, side, actions_first, position):
    row = {'type': 'row', 'gap': 'sm', 'children': [slot('navigation', width=240), slot('content')] if nav_first
           else [slot('content'), slot('navigation', width=240)]}
    children = [slot('actions'), row] if actions_first else [row, slot('actions')]
    upgraded = upgrade_v1(v1('fastlane-1.0.0'), presentation({'type': 'column', 'gap': 'lg', 'children': children}))
    layout = upgraded['layout']
    assert (layout['sidebar']['side'], layout['navbar']['position']) == (side, position)
    assert layout['sidebar']['width'] == 240 and layout['sidebar']['surface'] == 'flush'
    assert layout['content']['gap'] == 'lg'
    assert check_theme(upgraded)['errors'] == []


def test_pack_styles_become_component_tokens():
    pack = presentation(
        {'type': 'row', 'gap': 'md', 'children': [slot('navigation'), {'type': 'column', 'gap': 'none', 'children': [slot('actions'), slot('content')]}]},
        **{'navigation.sidebar': {'variant': 'panel', 'tone': 'dark'}, 'navigation.topbar': {'tone': 'dark'},
           'navigation.item': {'variant': 'pill', 'mode': 'label'}, 'control.button': {'variant': 'outline', 'radius': 'square'},
           'surface.card': {'variant': 'raised'}, 'page.header': {'variant': 'ruled'}, 'chat.message': {'variant': 'ruled'},
           'control.input': {'variant': 'filled'}, 'control.field': {'variant': 'inline'}, 'chat.composer': {'variant': 'plain'}})
    upgraded = upgrade_v1(v1('fastlane-1.0.0'), pack)
    tokens = upgraded['tokens']['components']
    assert upgraded['layout']['sidebar']['style'] == 'panel' and upgraded['layout']['sidebar']['width'] == 224
    assert tokens['sidebar-tone'] == 'dark' and tokens['navbar-tone'] == 'dark' and tokens['nav-item-fg'] == '{ink-200}'
    assert tokens['nav-item-radius'] == '{radius-pill}' and tokens['nav-item-variant'] == 'pill'
    assert tokens['button-variant'] == 'outline' and tokens['button-radius'] == '{radius-sm}' and tokens['button-height'] == '44px'
    assert tokens['card-variant'] == 'raised' and tokens['card-shadow'] == '{shadow-sm}'
    assert tokens['page-header-variant'] == 'ruled' and tokens['chat-message-variant'] == 'ruled'
    assert tokens['input-variant'] == 'filled' and tokens['field-variant'] == 'inline' and tokens['composer-variant'] == 'plain'
    assert check_theme(upgraded)['errors'] == []
    assert resolve_theme(upgraded)['enums']['button-variant'] == 'outline'


def test_a_pack_without_styles_defaults_to_the_compilers_light_bars():
    pack = presentation({'type': 'row', 'gap': 'md', 'children': [slot('navigation'), {'type': 'column', 'gap': 'md', 'children': [slot('actions'), slot('content')]}]})
    tokens = upgrade_v1(v1('fastlane-1.0.0'), pack)['tokens']['components']
    assert (tokens['sidebar-tone'], tokens['navbar-tone']) == ('light', 'light') and 'nav-item-fg' not in tokens


def test_navigation_above_content_becomes_a_navbar_that_carries_the_items():
    pack = presentation({'type': 'column', 'gap': 'md', 'children': [slot('navigation'), slot('content'), slot('actions')]})
    report = upgrade_v1_report(v1('fastlane-1.0.0'), pack)
    layout = report['theme']['layout']
    assert (layout['sidebar']['side'], layout['navbar']['position']) == ('hidden', 'top')
    assert any('navbar that carries the navigation items' in note for note in report['notes'])
    assert check_theme(report['theme'])['errors'] == []


def test_resolution_flattens_references_and_tags_font_sizes():
    value = mutate(lambda t: (t['tokens']['semantic'].update({'primary': '{accent-700}'}),
                              t['tokens']['components'].update({
                                  'button-primary-bg': '{primary}', 'button-radius': '{radius-pill}', 'button-size': '{size-lg}',
                                  'page-header-title-size': '22px', 'button-transform': 'uppercase', 'card-shadow': '{shadow-card}'})))
    resolved = resolve_theme(value)
    vars_ = resolved['vars']
    assert vars_['--fl-primary'] == '28 57 174'
    assert vars_['--fl-button-primary-bg'] == '28 57 174'
    assert vars_['--fl-button-radius'] == '9999px'
    assert vars_['--fl-button-size'] == 'var(--fl-fs-lg)'
    assert vars_['--fl-page-header-title-size'] == 'calc(22px * var(--fl-size-scale, 1))'
    assert vars_['--fl-size-lg'] == '15px' and vars_['--fl-size-scale'] == '1'
    assert vars_['--fl-button-transform'] == 'uppercase' and vars_['--fl-card-shadow'] == vars_['--fl-shadow-card']
    assert '--fl-button-bg' not in vars_, 'unset component tokens are left to their fallback'
    assert resolved['enums']['button-transform'] == 'uppercase' and resolved['enums']['sidebar-tone'] == 'dark'
    assert resolved['attrs'] == {'data-density': 'comfortable', 'data-theme': 'client-acme', 'data-fl-contract': '2'}
    assert len(resolve_theme(default_theme_v2())['vars']) == len(registry.PRIMITIVES) + len(registry.SEMANTIC)


def test_resolution_exposes_layout_for_the_workspace_frame():
    value = theme()
    value['layout'].update(scroll='page', density='compact')
    value['layout']['sidebar'].update(side='right', style='panel', width=240, behavior='sticky', surface='flush')
    value['layout']['navbar'].update(position='top', behavior='sticky', height=64, align='center', show_brand=False)
    value['layout']['content'].update(max_width=1200, align='center', padding='none', gap='lg')
    shell = resolve_theme(value)['shell']
    assert shell['attrs'] == {
        'data-fl-sidebar-side': 'right', 'data-fl-sidebar-style': 'panel', 'data-fl-sidebar-surface': 'flush',
        'data-fl-sidebar-behavior': 'sticky', 'data-fl-navbar': 'top', 'data-fl-navbar-behavior': 'sticky',
        'data-fl-navbar-align': 'center', 'data-fl-navbar-brand': 'false', 'data-fl-scroll': 'page', 'data-fl-content-align': 'center'}
    assert shell['vars'] == {
        '--fl-sidebar-w': '240px', '--fl-sidebar-collapse-below': '760px', '--fl-navbar-h': '64px',
        '--fl-content-max-w': '1200px', '--fl-content-pad': '0px', '--fl-content-gap': 'var(--fl-space-lg)'}
    assert resolve_theme(value)['attrs']['data-density'] == 'compact'


def test_fonts_are_only_named_from_the_allow_list():
    value = mutate(prim(font_sans="'Roboto', Arial, sans-serif", font_mono='ui-monospace, monospace', font_display='Papyrus, fantasy'))
    assert resolve_theme(value)['fonts'] == [{'family': 'Roboto', 'weights': [400, 500, 700]}]
    assert resolve_theme(default_theme_v2())['fonts'] == [{'family': 'Inter', 'weights': [400, 500, 600, 700]}]
    assert check_theme(value)['errors'] == []


def test_resolve_rejects_invalid_themes():
    with pytest.raises(ThemeError):
        resolve_theme(mutate(prim(radius='99px')))


def test_a_v2_pin_survives_json_round_trips():
    value = theme()
    value['tokens']['components']['button-radius'] = '{radius-pill}'
    assert validate_theme(json.loads(json.dumps(value))) == value


# ---------------------------------------------------------------- hostile input --

def test_a_long_run_of_commas_is_refused_at_once_not_after_twelve_seconds():
    import time
    for token, text in (("shadow-sm", "," * 60_000), ("shadow-md", "0 1px 2px 0 rgba(0,0,0,0.1)," * 3000),
                        ("ease-standard", "cubic-bezier(" + "1," * 20_000)):
        started = time.monotonic()
        errors = check_theme(mutate(prim(**{token: text})))["errors"]
        assert errors, token
        assert time.monotonic() - started < 1.0, token


@pytest.mark.parametrize("token, text", [
    ("shadow-sm", "0 1px 2px 0 rgba(0,\n0,0,0.05)"),       # newline inside rgba(
    ("shadow-sm", "0 1px 2px 0 rgba(0,0,0,0.05)"),   # no-break space
    ("shadow-sm", "0 1px 2px 0 rgba(0,0,0,0.05) "),  # line separator
    ("ease-standard", "cubic-bezier(\n0,0,1,1)"),
    ("ease-standard", "cubic-bezier(0, 0,1,1)"),
])
def test_only_literal_spaces_separate_the_parts_of_a_shadow_or_easing(token, text):
    assert paths(mutate(prim(**{token: text})))


def test_ordinary_shadows_and_easings_still_pass():
    value = mutate(prim(shadow_sm="0 1px 2px 0 rgba(0, 0, 0, 0.05), 0 0 0 1px #112233",
                        ease_standard="cubic-bezier(0.2, 0, 0, 1)"))
    assert not paths(value)
