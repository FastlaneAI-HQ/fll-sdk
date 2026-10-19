"""The layout tree (registry revision 4): validate_shell, normalise_shell, shell_from_layout and the revision 4 theme.

docs/layout-tree.md is the specification. Every rule has a negative test with the exact path of the node it names; the
limits, enums and defaults are read from the layout vocabulary, which these tests also change to prove nothing is hard-coded.
tests/test_layout_tree_parity.py runs the TypeScript twin over the same trees.
"""
import copy
import json
from pathlib import Path

import pytest
from fastlanelabs_sdk import theme_registry as registry
from fastlanelabs_sdk import themes
from fastlanelabs_sdk.themes import (
    check_theme, default_theme_v2, normalise_shell, project_v1, resolve_theme, shell_from_layout, shell_tree_of,
    validate_shell, validate_theme,
)

ROOT = Path(__file__).resolve().parents[1]
VOCAB = registry.layout_vocabulary()
PRESETS = {item['id']: item['tree'] for item in VOCAB['presets']}
S = 'layout.shell'


def region(name, basis=None, **options):
    """A region; `basis` is its size object (a copy: tests change nodes in place), `options` its options."""
    node = {'type': 'region', 'region': name}
    if basis is not None:
        node['size'] = dict(basis)
    if options:
        node['options'] = options
    return node


def box(direction, *children, **fields):
    if 'size' in fields:
        fields['size'] = dict(fields['size'])
    return dict({'type': 'container', 'direction': direction}, children=list(children), **fields)


FILL = {'basis': 'fill'}


def base():
    """A small valid shell: a sidebar (brand, navigation) and the content, in a row."""
    return {'version': 1, 'root': box('row',
            box('column', region('brand'), region('navigation', FILL), chrome='sidebar', size={'basis': 224}),
            region('content', FILL))}


def result(shell, **kwargs):
    return validate_shell(shell, None, S, **kwargs)


def errors(shell, **kwargs):
    return [(e['path'], e['message']) for e in result(shell, **kwargs)['errors']]


def error_paths(shell, **kwargs):
    return [path for path, _ in errors(shell, **kwargs)]


def mutated(change):
    shell = base()
    change(shell)
    return shell


# --- The vocabulary and the presets --------------------------------------------------------------------------------------

def test_the_built_in_vocabulary_is_a_byte_copy_of_the_themes_apps_file_when_it_is_next_to_the_sdk():
    sdk = (ROOT / 'fastlanelabs_sdk/registry_data/layout-vocabulary.json').read_bytes()
    assert (ROOT / 'frontend/layout-vocabulary.json').read_bytes() == sdk
    themes_copy = ROOT.parent / 'apps/fll-themes/layout-vocabulary.json'
    if themes_copy.is_file():
        assert themes_copy.read_bytes() == sdk
    assert json.loads(sdk) == VOCAB and VOCAB['vocabulary_version'] == VOCAB['shell_version'] == 1


@pytest.mark.parametrize('preset', sorted(PRESETS))
def test_every_vocabulary_preset_validates_without_a_problem(preset):
    assert result(PRESETS[preset]) == {'errors': [], 'warnings': []}
    assert result(PRESETS[preset], scroll='page') == {'errors': [], 'warnings': []}


def test_there_are_six_presets_and_their_ids_are_unique():
    assert len(VOCAB['presets']) == len(PRESETS) == 6
    assert sorted(PRESETS) == ['console', 'launcher-header', 'panel-flush', 'rail', 'right-sidebar', 'top-bar']


def test_normalising_a_preset_fills_every_default_and_is_idempotent():
    tree = normalise_shell(PRESETS['panel-flush'])
    sidebar = tree['root']['children'][0]
    assert tree['root'] == {
        'type': 'container', 'direction': 'row', 'gap': 'none', 'padding': 'none', 'align': 'stretch', 'justify': 'start',
        'chrome': 'none', 'surface': 'flush', 'size': {'basis': 'content'}, 'behavior': 'fixed', 'children': tree['root']['children']}
    assert sidebar['behavior'] == 'fixed' and sidebar['collapse_below'] == 760 and sidebar['size'] == {'basis': 224}
    navigation = sidebar['children'][1]
    assert navigation['options'] == {'style': 'icons-labels', 'orientation': 'vertical', 'groups': 'all', 'overflow': 'menu'}
    assert sidebar['children'][0]['options'] == {'name': 'auto', 'logo': 'auto'}
    assert tree['root']['children'][1] == {'type': 'region', 'region': 'content', 'size': {'basis': 'fill'}, 'options': {}}
    assert normalise_shell(tree) == tree
    assert result(tree) == {'errors': [], 'warnings': []}
    assert PRESETS['panel-flush']['root'].get('gap') is None  # the input is not changed


def test_a_container_without_collapse_below_has_none_after_normalising_and_a_spacer_is_only_its_type():
    shell = base()
    shell['root']['children'][0]['children'].insert(1, {'type': 'spacer'})
    tree = normalise_shell(shell)
    assert 'collapse_below' not in tree['root']['children'][0]
    assert tree['root']['children'][0]['children'][1] == {'type': 'spacer'}


def test_custom_regions_keep_the_module_and_props_only_when_given():
    shell = base()
    shell['root']['children'][0]['children'] += [region('custom', module='acme/header@1', props={'a': [1, 2, {'b': None}]}),
                                                  region('custom', module='acme/footer@12')]
    custom = normalise_shell(shell)['root']['children'][0]['children'][2:]
    assert custom[0]['options'] == {'module': 'acme/header@1', 'props': {'a': [1, 2, {'b': None}]}}
    assert custom[1]['options'] == {'module': 'acme/footer@12'}
    assert result(shell) == {'errors': [], 'warnings': []}


# --- The default, and the mapping from the options ---------------------------------------------------------------------

def normal(preset):
    return normalise_shell(PRESETS[preset])


def test_the_registry_default_layout_maps_to_the_rail_preset():
    assert shell_from_layout(registry.default_layout()) == shell_from_layout(registry.default_layout('rail')) == normal('rail')


def test_the_platform_release_layout_maps_to_the_panel_flush_preset():
    release = json.loads((ROOT / 'fastlanelabs_sdk/registry_data/default-theme-v2.json').read_text())
    assert release['registry_revision'] == 3
    assert shell_from_layout(release['layout']) == normal('panel-flush')


def test_a_panel_on_the_right_maps_to_the_right_sidebar_preset():
    layout = registry.default_layout('panel')
    layout['sidebar']['side'] = 'right'
    assert shell_from_layout(layout) == normal('right-sidebar')


def layouts():
    """A grid of valid revision 1 to 3 layouts: every side, style, surface, navbar position and alignment, the content options."""
    out = []
    for side in ('left', 'right', 'hidden'):
        for style, surface, width in (('rail', 'floating', 56), ('panel', 'flush', 224), ('panel', 'floating', 280)):
            for position in ('hidden', 'top', 'bottom'):
                if side == 'hidden' and position == 'hidden':
                    continue
                for align, brand in (('between', True), ('start', False), ('center', True)):
                    for max_width, content_align in ((0, 'start'), (1200, 'center'), (900, 'start')):
                        layout = registry.default_layout(style)
                        layout['sidebar'].update(side=side, surface=surface, width=width, behavior='sticky' if align == 'start' else 'fixed')
                        layout['navbar'].update(position=position, align=align, show_brand=brand, height=64 if align == 'center' else 56)
                        layout['content'].update(max_width=max_width, align=content_align, padding='lg', gap='sm')
                        out.append(layout)
    return out


def test_every_layout_the_options_can_express_maps_to_a_valid_tree():
    grid = layouts()
    assert len(grid) > 100
    for layout in grid:
        tree = shell_from_layout(layout)
        found = result(tree, scroll='page')
        assert found == {'errors': [], 'warnings': []}, (layout, found)
        assert normalise_shell(tree) == tree
        assert tree['root']['direction'] == ('row' if layout['sidebar']['side'] != 'hidden' else 'column')


def tree_regions(node):
    if node['type'] == 'region':
        return [node['region']]
    if node['type'] == 'spacer':
        return []
    return [name for child in node['children'] for name in tree_regions(child)]


def test_the_mapping_places_each_region_where_the_spec_says():
    layout = registry.default_layout('panel')
    layout['sidebar'].update(side='left', surface='floating')
    layout['navbar'].update(position='top', align='between', show_brand=True)
    tree = shell_from_layout(layout)['root']
    assert (tree['gap'], tree['padding']) == ('md', 'md')  # the sidebar floats: content.gap and content.padding
    sidebar, column = tree['children']
    assert [c['region'] for c in sidebar['children']] == ['brand', 'navigation']  # a navbar carries the actions
    navbar, page = column['children']
    assert navbar['chrome'] == 'navbar' and navbar['size'] == {'basis': 56}
    assert [c.get('region', c['type']) for c in navbar['children']] == ['spacer', 'actions']  # the sidebar carries brand and navigation
    assert page['region'] == 'content' and column['size'] == {'basis': 'fill'}
    # No sidebar: the navbar carries brand, navigation, a spacer and the actions; bottom puts it after the content.
    layout['sidebar']['side'] = 'hidden'
    layout['navbar']['position'] = 'bottom'
    tree = shell_from_layout(layout)['root']
    assert tree['direction'] == 'column' and tree['children'][0]['region'] == 'content'
    assert [c.get('region', c['type']) for c in tree['children'][1]['children']] == ['brand', 'navigation', 'spacer', 'actions']
    layout['navbar']['show_brand'] = False
    assert tree_regions(shell_from_layout(layout)['root']).count('brand') == 0


def test_content_max_width_and_align_become_size_max_and_justify_on_the_content_row():
    layout = registry.default_layout('panel')
    layout['content'].update(max_width=1200, align='center')
    row = shell_from_layout(layout)['root']['children'][1]
    assert row['type'] == 'container' and row['direction'] == 'row' and row['justify'] == 'center' and row['size'] == {'basis': 'fill'}
    assert row['children'][0]['size'] == {'basis': 'fill', 'max': 1200}
    layout['content']['align'] = 'start'
    assert shell_from_layout(layout)['root']['children'][1]['justify'] == 'start'


def test_both_bars_hidden_still_has_a_navigation_row_above_the_content():
    layout = registry.default_layout()
    layout['sidebar']['side'] = 'hidden'
    shell = shell_from_layout(layout)
    tree = shell['root']
    assert tree['direction'] == 'column'
    assert [c['region'] for c in tree['children']] == ['navigation', 'content']
    assert tree['children'][0]['options']['orientation'] == 'horizontal'
    assert result(shell)['errors'] == []
    # The layout validator still rejects this layout: the mapping is total, the options are not.
    assert ('layout', 'At least one of the sidebar and the navbar must be visible') in [
        (e['path'], e['message']) for e in check_theme(dict(default_theme_v2(), layout=layout))['errors']]


# --- Structure: keys, types, enums, ranges -------------------------------------------------------------------------------

def test_a_valid_shell_has_no_problem_and_every_rule_below_starts_from_it():
    assert result(base()) == {'errors': [], 'warnings': []}


@pytest.mark.parametrize('shell,path,message', [
    (None, S, 'Shell must be an object'),
    ([], S, 'Shell must be an object'),
    ('root', S, 'Shell must be an object'),
])
def test_the_shell_must_be_an_object(shell, path, message):
    assert errors(shell) == [(path, message + ' with version and root')]


def test_version_must_be_the_vocabularys_shell_version_and_root_is_required():
    assert errors({'root': base()['root']}) == [(f'{S}.version', 'Required')]
    for version in (2, 0, '1', 1.5, True, None, [1]):
        assert errors(dict(base(), version=version)) == [(f'{S}.version', 'version must be 1')], version
    assert errors({'version': 1}) == [(f'{S}.root', 'Required')]
    assert errors(dict(base(), extra=1, another=2)) == [(f'{S}.another', 'Unknown key another'), (f'{S}.extra', 'Unknown key extra')]


def test_the_root_must_be_a_container():
    assert errors({'version': 1, 'root': region('content')}) == [(f'{S}.root', 'The root of a shell must be a container')]
    assert errors({'version': 1, 'root': {'type': 'spacer'}}) == [(f'{S}.root', 'The root of a shell must be a container')]
    assert errors({'version': 1, 'root': 'x'}) == [(f'{S}.root', 'A node must be an object')]
    assert errors({'version': 1, 'root': None}) == [(f'{S}.root', 'A node must be an object')]


def test_a_node_needs_a_known_type():
    shell = mutated(lambda t: t['root']['children'].append({'type': 'grid'}))
    assert errors(shell) == [(f'{S}.root.children[2].type', 'type must be container, region or spacer')]
    shell = mutated(lambda t: t['root']['children'].append({'direction': 'row'}))
    assert error_paths(shell) == [f'{S}.root.children[2].type']
    for junk in (None, 3, 'region', ['region']):
        shell = mutated(lambda t: t['root']['children'].append(junk))
        assert error_paths(shell) == [f'{S}.root.children[2]'], junk


def test_unknown_keys_are_errors_at_every_level():
    shell = mutated(lambda t: (t['root'].update(color='red'), t['root']['children'][1].update(css='x'),
                               t['root']['children'][0]['children'].append({'type': 'spacer', 'size': FILL}),
                               t['root']['children'][1]['size'].update(grow=1),
                               t['root']['children'][0]['children'][0].update(options={'name': 'show', 'shine': 1})))
    assert errors(shell) == [
        (f'{S}.root.color', 'Unknown key color'),
        (f'{S}.root.children[0].children[0].options.shine', 'Unknown option shine'),
        (f'{S}.root.children[0].children[2].size', 'Unknown key size'),
        (f'{S}.root.children[1].css', 'Unknown key css'),
        (f'{S}.root.children[1].size.grow', 'Unknown key grow'),
    ]


def test_a_container_needs_a_direction_from_the_vocabulary():
    del_direction = mutated(lambda t: t['root'].pop('direction'))
    assert errors(del_direction) == [(f'{S}.root.direction', 'Required')]
    for value in ('diagonal', None, 1, ['row']):
        assert errors(mutated(lambda t: t['root'].update(direction=value))) == [(f'{S}.root.direction', 'Must be one of row, column')], value


@pytest.mark.parametrize('field,good,bad', [
    ('gap', ['none', 'xs', 'sm', 'md', 'lg', 'xl'], ['2xl', 'huge', 4, None]),
    ('padding', ['none', 'xl'], ['2xl', '', None]),
    ('align', ['start', 'center', 'end', 'stretch'], ['between', 'baseline', None]),
    ('justify', ['start', 'center', 'end', 'between'], ['stretch', 'around', 0]),
    ('chrome', ['none', 'sidebar', 'navbar'], ['header', None]),
    ('surface', ['floating', 'flush'], ['raised', None]),
    ('behavior', ['fixed', 'sticky', 'static'], ['absolute', None]),
])
def test_container_enums_and_steps_come_from_the_vocabulary(field, good, bad):
    spec = VOCAB['container'][field]
    options = VOCAB['steps'] if spec.get('step') else spec['enum']
    for value in good:
        assert errors(mutated(lambda t: t['root']['children'][0].update({field: value}))) == [], value
    for value in bad:
        assert errors(mutated(lambda t: t['root']['children'][0].update({field: value}))) == [
            (f'{S}.root.children[0].{field}', 'Must be one of ' + ', '.join(options))], value


def test_collapse_below_is_a_whole_number_in_the_vocabulary_range():
    low, high = VOCAB['limits']['collapse_below']['min'], VOCAB['limits']['collapse_below']['max']
    for value in (low, high, 760):
        assert errors(mutated(lambda t: t['root']['children'][0].update(collapse_below=value))) == []
    for value in (low - 1, high + 1, 0, -760, 760.5, True, '760', None):
        assert errors(mutated(lambda t: t['root']['children'][0].update(collapse_below=value))) == [
            (f'{S}.root.children[0].collapse_below', f'Must be a whole number {low}-{high}')], value


def test_size_basis_is_fill_content_or_a_whole_number_of_px_in_range():
    low, high = VOCAB['limits']['size_px']['min'], VOCAB['limits']['size_px']['max']
    for basis in ('content', low, high, 224):
        assert errors(mutated(lambda t: t['root']['children'][0].update(size={'basis': basis}))) == [], basis
    # `fill` is accepted as a basis (here on the navigation, which is the sidebar's only fill).
    assert errors(mutated(lambda t: t['root']['children'][0]['children'][1].update(size={'basis': 'fill'}))) == []
    message = f'Must be fill, content or a whole number of px {low}-{high}'
    for basis in ('wide', low - 1, high + 1, 0, -1, 56.5, True, None, [], '224'):
        assert errors(mutated(lambda t: t['root']['children'][0].update(size={'basis': basis}))) == [
            (f'{S}.root.children[0].size.basis', message)], basis
    assert errors(mutated(lambda t: t['root']['children'][0].update(size={}))) == [(f'{S}.root.children[0].size.basis', 'Required')]
    for junk in (None, 5, 'fill', ['fill']):
        assert errors(mutated(lambda t: t['root']['children'][0].update(size=junk))) == [(f'{S}.root.children[0].size', 'size must be an object')]


def test_size_min_and_max_are_whole_numbers_and_min_is_at_most_max():
    for size in ({'basis': 200, 'min': 100, 'max': 300}, {'basis': 'content', 'max': 600}, {'basis': 'content', 'min': 40}):
        assert errors(mutated(lambda t: t['root']['children'][0].update(size=size))) == [], size
    path = f'{S}.root.children[0].size'
    assert errors(mutated(lambda t: t['root']['children'][0].update(size={'basis': 200, 'min': 300, 'max': 100}))) == [
        (path + '.max', 'max must be at least min')]
    for key in ('min', 'max'):
        for value in (39, 1921, 100.5, True, '100', None):
            assert errors(mutated(lambda t: t['root']['children'][0].update(size={'basis': 200, key: value}))) == [
                (f'{path}.{key}', 'Must be a whole number 40-1920')], (key, value)


def test_region_names_and_options_follow_the_vocabulary():
    assert errors(mutated(lambda t: t['root']['children'][1].update(region='footer'))) == [
        (f'{S}.root.children[1].region', 'region must be brand, navigation, actions, title, content or custom')]
    assert errors(mutated(lambda t: t['root']['children'][1].pop('region'))) == [(f'{S}.root.children[1].region', 'Required')]
    assert errors(mutated(lambda t: t['root']['children'][1].update(region=['content']))) == [
        (f'{S}.root.children[1].region', 'region must be brand, navigation, actions, title, content or custom')]
    brand = f'{S}.root.children[0].children[0]'
    for value in ('show', 'hide', 'auto'):
        assert errors(mutated(lambda t: t['root']['children'][0]['children'][0].update(options={'name': value}))) == []
    assert errors(mutated(lambda t: t['root']['children'][0]['children'][0].update(options={'name': 'bold'}))) == [
        (f'{brand}.options.name', 'Must be one of show, hide, auto')]
    assert errors(mutated(lambda t: t['root']['children'][0]['children'][0].update(options=['name']))) == [(f'{brand}.options', 'options must be an object')]
    assert errors(mutated(lambda t: t['root']['children'][0]['children'][0].update(options=None))) == [(f'{brand}.options', 'options must be an object')]
    nav = f'{S}.root.children[0].children[1].options'
    bad = {'style': 'text', 'orientation': 'diagonal', 'groups': 'none', 'overflow': 'scroll'}
    assert errors(mutated(lambda t: t['root']['children'][0]['children'][1].update(options=bad))) == [
        (f'{nav}.style', 'Must be one of icons, labels, icons-labels, launcher'), (f'{nav}.orientation', 'Must be one of vertical, horizontal'),
        (f'{nav}.groups', 'Must be one of all, primary, secondary'), (f'{nav}.overflow', 'Must be one of menu, wrap')]
    content = f'{S}.root.children[1].options.x'
    assert errors(mutated(lambda t: t['root']['children'][1].update(options={'x': 1}))) == [(content, 'Unknown option x')]


# --- navigation.style launcher (the vocabulary's sixth preset, launcher-header) -----------------------------------------

def launcher(**options):
    return region('navigation', **dict({'style': 'launcher'}, **options))


def test_the_navigation_style_enum_offers_launcher_and_the_default_stays_icons_labels():
    style = VOCAB['regions']['navigation']['options']['style']
    assert style['enum'] == ['icons', 'labels', 'icons-labels', 'launcher'] and style['default'] == 'icons-labels'
    assert normalise_shell(base())['root']['children'][0]['children'][1]['options']['style'] == 'icons-labels'


def test_the_launcher_header_preset_validates_and_normalises_to_a_horizontal_launcher_in_a_navbar():
    tree = normal('launcher-header')
    assert result(PRESETS['launcher-header']) == {'errors': [], 'warnings': []}
    assert result(PRESETS['launcher-header'], scroll='page') == {'errors': [], 'warnings': []}
    assert normalise_shell(tree) == tree
    bar, content = tree['root']['children']
    assert (tree['root']['direction'], bar['direction'], bar['chrome'], bar['size']) == ('column', 'row', 'navbar', {'basis': 56})
    assert [child.get('region', child['type']) for child in bar['children']] == ['navigation', 'brand', 'title', 'spacer', 'actions']
    nav = bar['children'][0]
    assert nav == {'type': 'region', 'region': 'navigation', 'size': {'basis': 'content'},
                   'options': {'style': 'launcher', 'orientation': 'horizontal', 'groups': 'all', 'overflow': 'menu'}}
    assert bar['children'][1]['options'] == {'name': 'auto', 'logo': 'auto'}
    assert bar['children'][4]['options'] == {'style': 'icons', 'orientation': 'horizontal'}
    assert content['region'] == 'content' and content['size'] == {'basis': 'fill'}


def test_a_launcher_navigation_needs_no_size_and_sits_in_a_row_or_a_column():
    for direction in ('row', 'column'):
        shell = {'version': 1, 'root': box(direction, launcher(), region('content', FILL))}
        assert result(shell) == {'errors': [], 'warnings': []}, direction
        assert normalise_shell(shell)['root']['children'][0]['size'] == {'basis': 'content'}
    shell = {'version': 1, 'root': box('row', box('column', region('brand'), launcher(orientation='vertical'), chrome='sidebar', size={'basis': 224}),
                                       region('content', FILL))}
    assert result(shell) == {'errors': [], 'warnings': []}
    # In a drawer-collapsing container the navigation is still reachable, as for any style.
    shell['root']['children'][0]['collapse_below'] = 760
    assert result(shell) == {'errors': [], 'warnings': []}


def test_launcher_adds_no_rule_of_its_own_a_fill_or_fixed_size_is_judged_as_for_any_style():
    one = {'version': 1, 'root': box('row', launcher(), region('content', FILL))}
    assert result(dict(one, root=box('row', dict(launcher(), size={'basis': 56}), region('content', FILL))))['errors'] == []
    assert result(dict(one, root=box('row', dict(launcher(), size=FILL), region('content', FILL))))['errors'][0]['message'] == (
        'At most one child of a container may fill (basis fill)')
    assert errors({'version': 1, 'root': box('row', region('content', FILL), launcher(), launcher())}) == [
        (f'{S}.root.children[2]', 'At most 1 navigation region (a shell has exactly one)')]
    assert errors({'version': 1, 'root': box('row', region('content', FILL), launcher(style='drawer'))}) == [
        (f'{S}.root.children[1].options.style', 'Must be one of icons, labels, icons-labels, launcher')]


def test_shell_from_layout_never_emits_a_launcher():
    seen = set()
    def walk(node):
        if node['type'] == 'region' and node['region'] == 'navigation':
            seen.add(node['options']['style'])
        for child in node.get('children', []):
            walk(child)
    for layout in layouts():
        walk(shell_from_layout(layout)['root'])
    flat = registry.default_layout()
    flat['sidebar']['side'] = 'hidden'
    walk(shell_from_layout(flat)['root'])
    assert seen == {'icons', 'icons-labels'}


def test_a_launcher_header_theme_validates_resolves_and_keeps_its_classic_fallback_options():
    top = dict(registry.default_layout()['sidebar'], side='hidden')
    bar = dict(registry.default_layout()['navbar'], position='top', height=56)
    theme = tree_theme(copy.deepcopy(PRESETS['launcher-header']), sidebar=top, navbar=bar)
    found = check_theme(theme)
    assert (found['errors'], found['warnings']) == ([], [])
    resolved = resolve_theme(theme)
    assert resolved['shell']['tree'] == normal('launcher-header')
    assert resolved['shell']['attrs']['data-fl-navbar'] == 'top' and resolved['shell']['attrs']['data-fl-sidebar-side'] == 'hidden'
    # The options a host without the renderer falls back to still map to a navigation row, never a launcher.
    classic = shell_from_layout(theme['layout'])
    navigation = next(c for c in classic['root']['children'][0]['children'] if c.get('region') == 'navigation')
    assert navigation['options']['style'] == 'icons-labels'
    assert project_v1(theme)['layout']['navigation'] == project_v1(tree_theme(copy.deepcopy(PRESETS['top-bar']), sidebar=top, navbar=bar))['layout']['navigation']


def test_title_and_actions_options_come_from_the_vocabulary():
    for name, option, good in (('title', 'size', ['sm', 'md', 'lg']), ('actions', 'style', ['icons', 'labels']),
                               ('actions', 'orientation', ['vertical', 'horizontal'])):
        for value in good:
            shell = mutated(lambda t: t['root']['children'][0]['children'].append(region(name, **{option: value})))
            assert errors(shell) == []
        shell = mutated(lambda t: t['root']['children'][0]['children'].append(region(name, **{option: 'nope'})))
        assert errors(shell) == [(f'{S}.root.children[0].children[2].options.{option}', 'Must be one of ' + ', '.join(good))]


def test_custom_regions_need_a_module_that_matches_the_pattern():
    def with_custom(**options):
        return mutated(lambda t: t['root']['children'][0]['children'].append(region('custom', **options)))
    path = f'{S}.root.children[0].children[2].options'
    assert errors(with_custom()) == [(path + '.module', 'Required')]
    assert errors(with_custom(props={})) == [(path + '.module', 'Required')]
    for module in ('client-acme/header@1', 'a/b@0', 'a-b-1/c-d-2@123'):
        assert errors(with_custom(module=module)) == [], module
    for module in ('Client/header@1', 'client/header', 'client/header@', 'client/header@1.2', 'client header@1', '/header@1',
                   'client/header@1\n', 'client/Header@1', '', 3, None, ['a/b@1']):
        assert errors(with_custom(module=module)) == [(path + '.module', 'Must match ^[a-z0-9-]+/[a-z0-9-]+@[0-9]+$')], module


def test_custom_props_are_an_object_of_at_most_2_kb():
    def with_props(props):
        return mutated(lambda t: t['root']['children'][0]['children'].append(region('custom', module='a/b@1', props=props)))
    path = f'{S}.root.children[0].children[2].options.props'
    for junk in ([], 'x', 5, None, True):
        assert errors(with_props(junk)) == [(path, 'Must be a JSON object')], junk
    limit = VOCAB['limits']['custom_props_bytes']
    exact = {'k': 'x' * (limit - len('{"k":""}'))}
    assert len(json.dumps(exact, separators=(',', ':'))) == limit
    assert errors(with_props(exact)) == []
    assert errors(with_props({'k': 'x' * (limit - len('{"k":""}') + 1)})) == [(path, f'Must be at most {limit} bytes of JSON')]
    # Bytes, not characters: two bytes per `é`.
    assert errors(with_props({'k': 'é' * (limit // 2)})) == [(path, f'Must be at most {limit} bytes of JSON')]
    assert errors(with_props({'k': 'é' * (limit // 2 - 4)})) == []
    nested = {}
    for _ in range(300):
        nested = {'a': nested}
    assert len(errors(with_props(nested))) <= 1


# --- Limits ------------------------------------------------------------------------------------------------------------

def test_a_shell_is_at_most_five_levels_deep():
    five = {'version': 1, 'root': box('column', region('navigation'), box('column', box('column', box('column', region('content', FILL)), size=FILL), size=FILL), size=FILL)}
    assert errors(five) == []  # root, three containers and the content: five levels
    six = {'version': 1, 'root': box('column', region('navigation'), box('column', box('column', box('column', box('column', region('content', FILL)), size=FILL), size=FILL), size=FILL), size=FILL)}
    assert errors(six) == [(f'{S}.root.children[1]' + '.children[0]' * 4, 'A shell is at most 5 levels deep')]  # the sixth level is not descended into


def test_a_shell_has_at_most_24_nodes():
    def tree(last_group):
        """1 root + 3 containers + 8 + 8 + `last_group` leaves; the last group holds the content."""
        first = box('row', region('navigation'), *[{'type': 'spacer'}] * 7)
        second = box('row', *[{'type': 'spacer'}] * 8)
        third = box('row', region('content', FILL), *[{'type': 'spacer'}] * (last_group - 1), size=FILL)
        return {'version': 1, 'root': box('column', first, second, third)}
    assert errors(tree(4)) == []  # 24 nodes
    found = errors(tree(5))  # 25: the 25th node in document order is the fifth leaf of the third group
    assert found == [(f'{S}.root.children[2].children[4]', 'A shell has at most 24 nodes')]  # and nothing after it is judged
    assert errors(tree(8)) == found


def test_a_container_has_one_to_eight_children():
    assert errors(mutated(lambda t: t['root'].update(children=[]))) == [(f'{S}.root.children', 'A container has 1 to 8 children')]
    nine = mutated(lambda t: t['root'].update(children=[{'type': 'spacer'}] * 9))
    assert errors(nine) == [(f'{S}.root.children', 'A container has 1 to 8 children')]
    eight = mutated(lambda t: t['root'].update(children=[region('content', FILL)] + [{'type': 'spacer'}] * 7))
    assert errors(eight) == [(f'{S}.root', 'A shell needs a navigation region, so the user can always navigate')]
    for junk in (None, 'x', {}, 3):
        assert errors(mutated(lambda t: t['root'].update(children=junk))) == [(f'{S}.root.children', 'A container has 1 to 8 children')]
    assert errors(mutated(lambda t: t['root'].pop('children'))) == [(f'{S}.root.children', 'A container has 1 to 8 children')]


# --- Rules -------------------------------------------------------------------------------------------------------------

def test_exactly_one_content_region():
    no_content = mutated(lambda t: t['root'].update(children=[t['root']['children'][0]]))
    assert errors(no_content) == [(f'{S}.root', 'A shell needs a content region (the page itself)')]
    two = mutated(lambda t: t['root']['children'].append(region('content', FILL)))
    found = errors(two)
    assert found[0] == (f'{S}.root.children[2].size', 'At most one child of a container may fill (basis fill)')
    assert (f'{S}.root.children[2]', 'At most 1 content region (a shell has exactly one)') in found
    assert errors(mutated(lambda t: t['root']['children'].append(region('content', {'basis': 100})))) == [
        (f'{S}.root.children[2]', 'At most 1 content region (a shell has exactly one)')]


def test_the_content_and_every_container_above_it_fill_or_are_the_only_child():
    message = 'The content region, and every container on the way to it, must fill (basis fill) or be the only child, so the page is never squeezed away'
    nav = region('navigation', {'basis': 100})
    # Fills all the way down.
    assert errors({'version': 1, 'root': box('row', nav, box('column', region('content', FILL), region('actions'), size=FILL))}) == []
    # The content is its parent's only child: it need not fill.
    assert errors({'version': 1, 'root': box('row', nav, box('column', region('content', {'basis': 'content'}), size=FILL))}) == []
    # Not the only child and not a fill: the content region itself, then the container above it.
    two = {'version': 1, 'root': box('row', nav, box('column', region('content', {'basis': 'content'}), region('actions'), size=FILL))}
    assert errors(two) == [(f'{S}.root.children[1].children[0].size', message)]
    squeezed = {'version': 1, 'root': box('row', nav, box('column', region('content', FILL), region('actions'), size={'basis': 300}))}
    assert errors(squeezed) == [(f'{S}.root.children[1].size', message)]
    # The default size is content, which is not a fill; a number is not one either.
    assert errors({'version': 1, 'root': box('row', region('navigation', FILL), region('content'))}) == [(f'{S}.root.children[1].size', message)]
    # The only child of its parent: a column holding a row holding the content alone, beside the navigation.
    alone = {'version': 1, 'root': box('row', nav, box('column', box('row', region('content'))))}
    assert errors(alone) == [(f'{S}.root.children[1].size', message)]  # the column is one of two children of the root and does not fill
    assert errors({'version': 1, 'root': box('column', box('row', region('content')), region('navigation', {'basis': 60}))}) == [
        (f'{S}.root.children[0].size', message)]
    assert errors({'version': 1, 'root': box('column', region('navigation', {'basis': 60}), box('row', box('column', region('content')), size=FILL))}) == []


def test_the_root_has_no_parent_so_it_is_exempt_from_the_fill_rule_and_the_size_rules():
    shell = base()
    shell['root']['size'] = {'basis': 40, 'max': 40}
    assert errors(shell) == []


def test_at_most_one_child_of_a_container_fills():
    shell = mutated(lambda t: t['root']['children'][0]['children'].append(region('actions', FILL)))
    assert errors(shell) == [(f'{S}.root.children[0].children[2].size', 'At most one child of a container may fill (basis fill)')]
    three = mutated(lambda t: t['root']['children'][0]['children'].extend([region('actions', FILL), region('title', FILL)]))
    assert error_paths(three) == [f'{S}.root.children[0].children[2].size', f'{S}.root.children[0].children[3].size']
    # A spacer takes the free space too, but it is not a fill child: it never competes by size.
    spacer = mutated(lambda t: t['root']['children'][0]['children'].append({'type': 'spacer'}))
    assert errors(spacer) == []


@pytest.mark.parametrize('name,maximum', [('brand', 1), ('navigation', 1), ('actions', 1), ('title', 1), ('custom', 4)])
def test_region_counts_never_exceed_the_vocabulary_maximum(name, maximum):
    def add(count):
        def change(tree):
            tree['root']['children'][0]['children'] += [region(name, **({'module': f'a/b{i}@1'} if name == 'custom' else {})) for i in range(count)]
        return mutated(change)
    existing = {'brand': 1, 'navigation': 1}.get(name, 0)
    allowed = maximum - existing
    assert errors(add(allowed)) == []
    found = errors(add(allowed + 1))
    plural = '' if maximum == 1 else 's'
    exactly = ' (a shell has exactly one)' if VOCAB['regions'][name].get('required') else ''
    assert found == [(f'{S}.root.children[0].children[{2 + allowed}]', f'At most {maximum} {name} region{plural}{exactly}')]


def test_a_shell_needs_a_navigation_region():
    shell = mutated(lambda t: t['root']['children'][0]['children'].pop(1))
    assert errors(shell) == [(f'{S}.root', 'A shell needs a navigation region, so the user can always navigate')]
    # Inside a container that collapses is fine: a collapsed container always shows its menu button.
    assert errors(base()) == [] and base()['root']['children'][0].get('collapse_below') is None
    shell = mutated(lambda t: t['root']['children'][0].update(collapse_below=760))
    assert errors(shell) == []


def test_the_container_that_holds_the_content_cannot_collapse():
    message = 'The container that holds the content cannot collapse into a drawer'
    assert errors(mutated(lambda t: t['root'].update(collapse_below=900))) == [(f'{S}.root.collapse_below', message)]
    nested = {'version': 1, 'root': box('row', region('navigation', {'basis': 100}), box('column', region('content', FILL), size=FILL, collapse_below=600))}
    assert errors(nested) == [(f'{S}.root.children[1].collapse_below', message)]


def test_fixed_sizes_on_one_path_add_up_to_at_most_960_px_on_one_axis():
    limit = VOCAB['limits']['max_fixed_path_px']
    assert limit == 960

    def nested(outer, inner, outer_direction='row', inner_direction='row'):
        return {'version': 1, 'root': box('row', box(outer_direction, box(inner_direction, region('navigation', FILL), size={'basis': inner}),
                                                    region('content', FILL), size={'basis': outer}), region('actions', FILL))}
    # Not on the content path (the outer container holds the content, so it must fill or be an only child): use a sibling branch.
    def branch(outer, inner, outer_direction, inner_direction):
        return {'version': 1, 'root': box('row',
                box(outer_direction, box(inner_direction, region('navigation', FILL), size={'basis': inner}), region('actions', FILL), size={'basis': outer}),
                region('content', FILL))}
    assert errors(branch(600, 360, 'row', 'row')) == []  # 600 + 360 = 960
    over = errors(branch(600, 361, 'row', 'row'))
    assert over == [(f'{S}.root.children[0].children[0].size', 'Fixed sizes on one root-to-leaf path add up to at most 960px along the row axis')]
    # The axes are separate: the inner container sits in a column parent, so it adds to the vertical sum instead.
    assert errors(branch(600, 600, 'column', 'row')) == []
    assert errors(branch(600, 361, 'column', 'column')) == []
    deep_vertical = {'version': 1, 'root': box('column',
        box('column', box('column', region('navigation', FILL), size={'basis': 500}), region('actions', FILL), size={'basis': 461}),
        region('content', FILL))}
    assert errors(deep_vertical) == [(f'{S}.root.children[0].children[0].size', 'Fixed sizes on one root-to-leaf path add up to at most 960px along the column axis')]
    # Siblings do not add up: each root-to-leaf path is judged on its own.
    wide = {'version': 1, 'root': box('row', box('column', region('navigation', FILL), size={'basis': 600}), box('column', region('actions', FILL), size={'basis': 600}),
                                      region('content', FILL))}
    assert errors(wide) == []


def test_off_the_content_path_a_size_is_at_most_640_px_on_the_content_path_1920():
    px_max = VOCAB['limits']['size_px']['max']
    off = mutated(lambda t: t['root']['children'][0].update(size={'basis': 224, 'max': px_max + 1}))
    assert errors(off) == [(f'{S}.root.children[0].size.max', f'Off the content path a size is at most {px_max}px')]
    off = mutated(lambda t: t['root']['children'][0].update(size={'basis': 'content', 'min': 700, 'max': 800}))
    assert errors(off) == [(f'{S}.root.children[0].size.min', 'Off the content path a size is at most 640px'),
                           (f'{S}.root.children[0].size.max', 'Off the content path a size is at most 640px')]
    on = mutated(lambda t: t['root']['children'][1].update(size={'basis': 'fill', 'max': 1920, 'min': 700}))
    assert errors(on) == []
    column = {'version': 1, 'root': box('row', region('navigation', {'basis': 100}), box('column', region('content', FILL), region('actions'), size={'basis': 'fill', 'max': 1500}))}
    assert errors(column) == []


def test_chrome_sidebar_and_navbar_each_at_most_twice():
    def with_bars(chrome, count):
        return {'version': 1, 'root': box('column', *[box('row', region('navigation', FILL) if i == 0 else {'type': 'spacer'}, chrome=chrome, size={'basis': 48}) for i in range(count)],
                                          region('content', FILL))}
    for chrome in ('sidebar', 'navbar'):
        assert errors(with_bars(chrome, 2)) == []
        assert errors(with_bars(chrome, 3)) == [(f'{S}.root.children[2].chrome', f'At most 2 containers may have chrome {chrome}')]
    mixed = {'version': 1, 'root': box('column', box('row', region('navigation', FILL), chrome='sidebar', size={'basis': 48}),
                                       box('row', {'type': 'spacer'}, chrome='sidebar', size={'basis': 48}), box('row', {'type': 'spacer'}, chrome='navbar', size={'basis': 48}),
                                       box('row', {'type': 'spacer'}, chrome='navbar', size={'basis': 48}), box('row', {'type': 'spacer'}, chrome='none', size={'basis': 48}),
                                       region('content', FILL))}
    assert errors(mixed) == []


def test_a_behavior_other_than_fixed_needs_scroll_page_and_warns_otherwise():
    shell = mutated(lambda t: t['root']['children'][0].update(behavior='sticky'))
    path = f'{S}.root.children[0].behavior'
    assert result(shell, scroll='page') == {'errors': [], 'warnings': []}
    assert result(shell) == {'errors': [], 'warnings': []}  # scroll unknown: nothing to judge
    found = result(shell, scroll='panel')
    assert found['errors'] == [] and [(w['path'], w['message']) for w in found['warnings']] == [
        (path, 'behavior sticky has no visible effect while scroll is panel; use scroll page or fixed')]
    both = mutated(lambda t: (t['root'].update(behavior='static'), t['root']['children'][0].update(behavior='sticky')))
    assert [w['path'] for w in result(both, scroll='panel')['warnings']] == [f'{S}.root.behavior', path]
    assert result(mutated(lambda t: t['root']['children'][0].update(behavior='fixed')), scroll='panel')['warnings'] == []


def test_a_custom_region_naming_a_module_is_valid_in_the_sdk_and_warns_only_at_the_host():
    shell = mutated(lambda t: t['root']['children'][0]['children'].extend([region('custom', module='client-acme/header@1'),
                                                                           region('custom', module='client-acme/footer@2')]))
    assert result(shell) == {'errors': [], 'warnings': []}  # the SDK level
    host = result(shell, installed_modules={'client-acme/header@1'})
    assert host['errors'] == []
    assert [(w['path'], w['message'].split(';')[0]) for w in host['warnings']] == [
        (f'{S}.root.children[0].children[3].options.module', 'module not installed: client-acme/footer@2')]
    assert result(shell, installed_modules=[])['warnings'][0]['path'].endswith('children[2].options.module')
    assert result(shell, installed_modules=['client-acme/header@1', 'client-acme/footer@2'])['warnings'] == []
    theme = default_theme_v2()
    theme['layout']['shell'] = shell
    assert check_theme(theme)['warnings'] == [] and check_theme(theme)['errors'] == []
    hosted = check_theme(theme, installed_modules={'client-acme/header@1'})
    assert [w['path'] for w in hosted['warnings']] == [f'{S}.root.children[0].children[3].options.module'] and hosted['errors'] == []
    validate_theme(theme, installed_modules=set())  # a warning never rejects a theme


def test_the_rules_are_judged_only_on_a_well_formed_tree():
    shell = mutated(lambda t: (t['root']['children'][1].update(region='nope'), t['root']['children'][0]['children'].pop(1)))
    assert error_paths(shell) == [f'{S}.root.children[1].region']  # no "needs a navigation region" on top of it


def test_problems_come_in_a_fixed_order():
    shell = mutated(lambda t: (t['root'].update(zzz=1, aaa=2), t['root']['children'][1].update(size={'basis': 'x', 'max': 5, 'extra': 0})))
    assert [p for p, _ in errors(shell)] == [f'{S}.root.aaa', f'{S}.root.zzz', f'{S}.root.children[1].size.extra',
                                              f'{S}.root.children[1].size.basis', f'{S}.root.children[1].size.max']


def with_vocabulary(change):
    vocab = copy.deepcopy(VOCAB)
    change(vocab)
    return vocab


def vocab_errors(shell, change):
    return [(e['path'], e['message']) for e in validate_shell(shell, with_vocabulary(change), S)['errors']]


def test_nothing_in_the_validator_is_hard_coded_the_vocabulary_decides():
    # Every limit, enum, step and region fact below is changed in a copy of the vocabulary and the verdict follows it.
    assert vocab_errors(base(), lambda v: v['limits'].update(max_children=1)) == [(f'{S}.root.children', 'A container has 1 to 1 children')]
    chain4 = {'version': 1, 'root': box('column', region('navigation'), box('column', box('column', region('content', FILL), size=FILL), size=FILL))}
    assert errors(chain4) == []
    assert vocab_errors(chain4, lambda v: v['limits'].update(max_depth=3)) == [(f'{S}.root.children[1].children[0].children[0]', 'A shell is at most 3 levels deep')]
    assert vocab_errors(base(), lambda v: v['limits'].update(max_nodes=4)) == [(f'{S}.root.children[1]', 'A shell has at most 4 nodes')]
    assert vocab_errors(base(), lambda v: v['limits'].update(size_px={'min': 300, 'max': 400})) == [
        (f'{S}.root.children[0].size.basis', 'Must be fill, content or a whole number of px 300-400')]
    assert vocab_errors(base(), lambda v: v['limits'].update(max_fixed_path_px=100)) == [
        (f'{S}.root.children[0].size', 'Fixed sizes on one root-to-leaf path add up to at most 100px along the row axis')]
    assert vocab_errors(base(), lambda v: v['limits'].update(max_chrome_per_family=0)) == [
        (f'{S}.root.children[0].chrome', 'At most 0 containers may have chrome sidebar')]
    gap = mutated(lambda t: t['root'].update(gap='md'))
    assert vocab_errors(gap, lambda v: v.update(steps=['none', 'sm'])) == [(f'{S}.root.gap', 'Must be one of none, sm')]
    assert vocab_errors(gap, lambda v: v['container']['gap'].update(step=False, enum=['a', 'b'])) == [(f'{S}.root.gap', 'Must be one of a, b')]
    assert vocab_errors(base(), lambda v: v['container']['direction'].update(enum=['column'])) == [
        (f'{S}.root.direction', 'Must be one of column')]  # the sidebar is a column
    sticky = mutated(lambda t: t['root']['children'][0].update(collapse_below=760))
    assert vocab_errors(sticky, lambda v: v['limits'].update(collapse_below={'min': 600, 'max': 700})) == [
        (f'{S}.root.children[0].collapse_below', 'Must be a whole number 600-700')]
    assert vocab_errors(base(), lambda v: v['regions']['brand'].update(max=0)) == [
        (f'{S}.root.children[0].children[0]', 'At most 0 brand regions')]
    assert vocab_errors(base(), lambda v: v['regions']['actions'].update(required=True)) == [(f'{S}.root', 'A shell needs the actions region')]
    assert vocab_errors(base(), lambda v: v['regions']['content'].update(required=False, max=0)) == [
        (f'{S}.root.children[1]', 'At most 0 content regions')]
    assert vocab_errors(base(), lambda v: v['regions']['navigation'].update(required=False)) == []
    no_nav = mutated(lambda t: t['root']['children'][0]['children'].pop(1))
    assert vocab_errors(no_nav, lambda v: v['regions']['navigation'].update(required=False)) == []
    assert vocab_errors(no_nav, lambda v: None) == [(f'{S}.root', 'A shell needs a navigation region, so the user can always navigate')]
    assert vocab_errors(base(), lambda v: v.update(shell_version=2)) == [(f'{S}.version', 'version must be 2')]
    assert vocab_errors(dict(base(), version=2), lambda v: v.update(shell_version=2)) == []
    # A region the vocabulary does not list is unknown; one it adds is known (the host's renderer decides whether it can draw it).
    footer = mutated(lambda t: t['root']['children'].append(region('footer')))
    assert vocab_errors(footer, lambda v: None) == [(f'{S}.root.children[2].region', 'region must be brand, navigation, actions, title, content or custom')]
    assert vocab_errors(footer, lambda v: v['regions'].update(footer={'max': 1, 'options': {}})) == []
    assert vocab_errors(footer, lambda v: v['regions'].update(footer={'max': 1, 'options': {}}, header={'max': 1, 'options': {}})) == []


def test_option_shapes_come_from_the_vocabulary_too():
    custom = mutated(lambda t: t['root']['children'][0]['children'].append(region('custom', module='x-1', props={'abcdef': 1})))
    path = f'{S}.root.children[0].children[2].options'
    assert vocab_errors(custom, lambda v: None) == [(path + '.module', 'Must match ^[a-z0-9-]+/[a-z0-9-]+@[0-9]+$')]
    assert vocab_errors(custom, lambda v: v['regions']['custom']['options']['module'].update(pattern='^x-[0-9]$')) == []
    assert vocab_errors(custom, lambda v: (v['regions']['custom']['options']['module'].update(pattern='^x-[0-9]$'), v['limits'].update(custom_props_bytes=8))) == [
        (path + '.props', 'Must be at most 8 bytes of JSON')]
    title = mutated(lambda t: t['root']['children'][0]['children'].append(region('title', size='lg')))
    assert errors(title) == []
    assert vocab_errors(title, lambda v: v['regions']['title']['options']['size'].update(enum=['sm'])) == [(path + '.size', 'Must be one of sm')]
    # An option with no default and not optional is required.
    assert vocab_errors(base(), lambda v: v['regions']['brand']['options'].update(tagline={'enum': ['a']})) == [
        (f'{S}.root.children[0].children[0].options.tagline', 'Required')]


def test_a_newer_vocabulary_changes_defaults_without_a_code_change():
    vocab = copy.deepcopy(VOCAB)
    vocab['container']['gap']['default'] = 'md'
    vocab['regions']['brand']['options']['name']['default'] = 'show'
    tree = normalise_shell(base(), vocab)
    assert tree['root']['gap'] == 'md' and tree['root']['children'][0]['children'][0]['options'] == {'name': 'show', 'logo': 'auto'}
    assert normalise_shell(base())['root']['gap'] == 'none'
    assert shell_from_layout(registry.default_layout(), vocab)['root']['children'][0]['gap'] == 'xs'  # an explicit gap stays
    assert resolve_theme(default_theme_v2(), vocabulary=vocab)['shell']['tree']['root']['gap'] == 'md'


# --- The theme ---------------------------------------------------------------------------------------------------------

def tree_theme(shell=None, **layout):
    theme = default_theme_v2()
    theme['layout'].update(layout)
    theme['layout']['shell'] = shell if shell is not None else copy.deepcopy(PRESETS['panel-flush'])
    return theme


def test_a_revision_4_theme_may_carry_a_shell_and_keeps_every_other_layout_key():
    theme = tree_theme()
    assert theme['registry_revision'] == 4
    assert check_theme(theme)['errors'] == [] and validate_theme(theme) == theme
    for key in list(theme['layout']):
        if key != 'shell':
            broken = copy.deepcopy(theme)
            del broken['layout'][key]
            assert check_theme(broken)['errors'] == [{'path': 'layout', 'message': 'Layout must supply exactly density, scroll, sidebar, navbar, content and may add shell'}], key


def test_a_theme_at_revision_3_or_earlier_must_not_carry_a_shell():
    for revision in (1, 2, 3):
        theme = default_theme_v2(registry_revision=revision)
        theme['layout']['shell'] = copy.deepcopy(PRESETS['panel-flush'])
        assert check_theme(theme)['errors'] == [{'path': 'layout.shell', 'message': 'layout.shell needs registry_revision 4 or later'}], revision
        with pytest.raises(themes.ThemeError) as caught:
            validate_theme(theme)
        assert caught.value.path == 'layout.shell'
    # An older theme without it is exactly as before, whatever the validator's revision.
    assert check_theme(default_theme_v2(registry_revision=3))['errors'] == []


def test_shell_errors_in_a_theme_carry_the_full_path_and_do_not_stop_the_contrast_report():
    shell = copy.deepcopy(PRESETS['panel-flush'])
    shell['root']['children'][1]['size'] = {'basis': 'content'}
    shell['root']['children'][0]['size']['basis'] = 5
    found = check_theme(tree_theme(shell))
    assert [(e['path'], e['message'][:24]) for e in found['errors']] == [('layout.shell.root.children[0].size.basis', 'Must be fill, content or')]
    assert found['contrast'] and any(row['id'] == 'text-on-surface' for row in found['contrast'])
    shell['root']['children'][0]['size']['basis'] = 224
    found = check_theme(tree_theme(shell))
    assert [e['path'] for e in found['errors']] == ['layout.shell.root.children[1].size']
    with pytest.raises(themes.ThemeError) as caught:
        validate_theme(tree_theme(shell))
    assert caught.value.path == 'layout.shell.root.children[1].size'


def test_a_shell_error_does_not_hide_a_layout_option_error_and_the_other_way_round():
    shell = copy.deepcopy(PRESETS['panel-flush'])
    shell['root']['children'][0]['gap'] = 'huge'
    theme = tree_theme(shell)
    theme['layout']['sidebar']['width'] = 999
    paths = [e['path'] for e in check_theme(theme)['errors']]
    assert paths == ['layout.sidebar.width', 'layout.shell.root.children[0].gap']


def test_shell_warnings_follow_the_theme_scroll():
    shell = copy.deepcopy(PRESETS['panel-flush'])
    shell['root']['children'][0]['behavior'] = 'sticky'
    panel = check_theme(tree_theme(shell, scroll='panel'))
    assert [w['path'] for w in panel['warnings']] == ['layout.shell.root.children[0].behavior']
    assert check_theme(tree_theme(shell, scroll='page'))['warnings'] == []


def test_a_shell_never_changes_the_contrast_report_or_the_v1_projection():
    plain = default_theme_v2()
    shelled = tree_theme()
    assert check_theme(shelled)['contrast'] == check_theme(plain)['contrast']
    assert project_v1(shelled) == project_v1(plain)
    right = tree_theme(copy.deepcopy(PRESETS['right-sidebar']), sidebar=dict(registry.default_layout('panel')['sidebar'], side='right'))
    projected = project_v1(right)
    assert projected['api_version'] == 1 and projected['layout'] == {'density': 'comfortable', 'navigation': 'sidebar'}
    assert validate_theme(projected) == projected


def test_resolve_theme_returns_the_themes_own_tree_or_the_one_its_options_describe():
    with_tree = resolve_theme(tree_theme(copy.deepcopy(PRESETS['top-bar']), sidebar=dict(registry.default_layout()['sidebar'], side='hidden'),
                                         navbar=dict(registry.default_layout()['navbar'], position='top')))
    assert with_tree['shell']['tree'] == normal('top-bar') and set(with_tree['shell']) == {'attrs', 'vars', 'tree'}
    assert with_tree['layout']['shell'] == PRESETS['top-bar']
    plain = resolve_theme(default_theme_v2())
    assert plain['shell']['tree'] == normal('rail') == shell_tree_of(default_theme_v2())
    assert plain['shell']['attrs']['data-fl-sidebar-style'] == 'rail'
    older = resolve_theme(default_theme_v2(registry_revision=3))
    assert older['shell']['tree'] == normal('rail') and older['shell']['attrs'] == plain['shell']['attrs'] and older['shell']['vars'] == plain['shell']['vars']


def test_the_attributes_and_variables_of_the_shell_do_not_depend_on_the_tree():
    a = resolve_theme(default_theme_v2())['shell']
    b = resolve_theme(tree_theme(copy.deepcopy(PRESETS['rail']), sidebar=registry.default_layout()['sidebar']))['shell']
    assert (a['attrs'], a['vars']) == (b['attrs'], b['vars'])


def test_the_tree_is_plain_data_with_no_markup_class_names_styles_or_urls():
    for theme in (default_theme_v2(), tree_theme(), tree_theme(copy.deepcopy(PRESETS['console']))):
        text = json.dumps(resolve_theme(theme)['shell']['tree'])
        for word in ('<', 'class', 'style=', 'http', 'url(', 'px;'):
            assert word not in text, word


def test_the_default_release_is_still_registry_revision_3_and_resolves_to_panel_flush():
    release = json.loads((ROOT / 'fastlanelabs_sdk/registry_data/default-theme-v2.json').read_text())
    assert release['registry_revision'] == 3 and 'shell' not in release['layout']
    assert resolve_theme(release)['shell']['tree'] == normal('panel-flush')


def test_the_registry_data_names_the_revision_that_introduced_the_shell():
    data = json.loads((ROOT / 'frontend/theme-registry.json').read_text())
    assert data['registry_revision'] == 4 and data['shell'] == {'since': 4, 'vocabulary': 'layout-vocabulary.json'}
    assert 'shell' not in data['layout']  # the skill's vendored reference reads LAYOUT_SPEC as flat fields
    assert themes.CONTENT_PATH_MAX_PX == registry.LAYOUT_SPEC['content']['max_width']['max'] == 1920


def test_the_builtin_vocabulary_loads_once_and_is_shared():
    assert registry.layout_vocabulary() is registry.layout_vocabulary()
