"""The TypeScript twin (validateShell, normaliseShell, shellFromLayout) gives the same verdicts as Python: the same errors and
warnings, with the same paths, messages and ORDER, and the same normalised tree, over named valid and invalid trees (every rule
once) and a few hundred generated ones.

Both sides read the cases from one JSON file, so what the TypeScript side sees is exactly what Python judged. Needs node >= 20
and the dev dependencies (`npm ci`); CI fails instead of skipping (see conftest.require_node).
"""
import copy
import json
import random
import subprocess
from pathlib import Path

from fastlanelabs_sdk import theme_registry as registry
from fastlanelabs_sdk.themes import brand_logo_for, normalise_brand, normalise_shell, shell_from_layout, validate_brand, validate_shell
from test_brand import brand_cases
from test_layout_tree import FILL, PRESETS, S, VOCAB, base, box, layouts, region

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'tests/golden/run_shell.mjs'


def tweak(vocabulary_change):
    vocab = copy.deepcopy(VOCAB)
    vocabulary_change(vocab)
    return vocab


def edited(change, source=None):
    shell = copy.deepcopy(source or base())
    change(shell)
    return shell


def spacers(count):
    return [{'type': 'spacer'} for _ in range(count)]


def named():
    """(id, shell, scroll, installed_modules, vocabulary): each rule of docs/layout-tree.md at least once, valid and invalid."""
    side = lambda t: t['root']['children'][0]  # noqa: E731 - the sidebar of base()
    cases = [(f'preset-{name}', tree, None, None, None) for name, tree in PRESETS.items()]
    cases += [('base', base(), None, None, None), ('base-scroll-page', base(), 'page', None, None)]
    cases += [
        ('valid-deep-5', {'version': 1, 'root': box('column', region('navigation'), box('column', box('column', box('column', region('content', FILL)), size=FILL), size=FILL), size=FILL)}, None, None, None),
        ('valid-eight-children', edited(lambda t: t['root'].update(children=[region('content', FILL), region('navigation')] + spacers(6))), None, None, None),
        ('valid-24-nodes', {'version': 1, 'root': box('column', box('row', region('navigation'), *spacers(7)), box('row', *spacers(8)),
                                                      box('row', region('content', FILL), *spacers(3), size=FILL))}, None, None, None),
        ('valid-content-max-1920', edited(lambda t: t['root']['children'][1].update(size={'basis': 'fill', 'min': 40, 'max': 1920})), None, None, None),
        ('valid-custom-regions', edited(lambda t: side(t)['children'].extend([region('custom', module='a-b/c-d@12', props={'x': [1, 2.5, None, True, 'é']}), region('custom', module='z/y@0')])), None, None, None),
        ('valid-props-2048', edited(lambda t: side(t)['children'].append(region('custom', module='a/b@1', props={'k': 'x' * (2048 - 8)}))), None, None, None),
        ('valid-props-unicode', edited(lambda t: side(t)['children'].append(region('custom', module='a/b@1', props={'k': 'é' * 1020}))), None, None, None),
        ('valid-collapse-limits', edited(lambda t: (side(t).update(collapse_below=480), t['root'].update(gap='xl', padding='lg', align='end', justify='between'))), None, None, None),
        ('valid-launcher-row', {'version': 1, 'root': box('row', region('navigation', style='launcher'), region('content', FILL))}, None, None, None),
        ('valid-launcher-column', {'version': 1, 'root': box('column', region('navigation', style='launcher', orientation='horizontal'), region('content', FILL))}, None, None, None),
        ('valid-launcher-sidebar', edited(lambda t: side(t)['children'][1].update(options={'style': 'launcher'})), None, None, None),
        ('invalid-launcher-twice', edited(lambda t: side(t)['children'].append(region('navigation', style='launcher'))), None, None, None),
        ('invalid-nav-style-drawer', edited(lambda t: side(t)['children'][1].update(options={'style': 'drawer'})), None, None, None),
        ('vocab-no-launcher', edited(lambda t: side(t)['children'][1].update(options={'style': 'launcher'})), None,
         None, tweak(lambda v: v['regions']['navigation']['options']['style'].update(enum=['icons', 'labels', 'icons-labels']))),
        ('invalid-shell-null', None, None, None, None),
        ('invalid-shell-list', [], None, None, None),
        ('invalid-keys', dict(base(), zzz=1, aaa=2), None, None, None),
        ('invalid-version', dict(base(), version=2), None, None, None),
        ('invalid-version-missing', {'root': base()['root']}, None, None, None),
        ('invalid-root-missing', {'version': 1}, None, None, None),
        ('invalid-root-region', {'version': 1, 'root': region('content')}, None, None, None),
        ('invalid-root-string', {'version': 1, 'root': 'x'}, None, None, None),
        ('invalid-type', edited(lambda t: t['root']['children'].append({'type': 'grid'})), None, None, None),
        ('invalid-node-junk', edited(lambda t: t['root']['children'].extend([None, 3, 'region', [1]])), None, None, None),
        ('invalid-unknown-keys', edited(lambda t: (t['root'].update(color='red'), t['root']['children'][1].update(css='x'),
                                                   side(t)['children'].append({'type': 'spacer', 'size': FILL}),
                                                   t['root']['children'][1]['size'].update(grow=1))), None, None, None),
        ('invalid-direction', edited(lambda t: t['root'].update(direction='diagonal')), None, None, None),
        ('invalid-direction-missing', edited(lambda t: t['root'].pop('direction')), None, None, None),
        ('invalid-enums', edited(lambda t: side(t).update(gap='huge', padding=3, align='between', justify='stretch', chrome='header', surface='raised', behavior='absolute')), None, None, None),
        ('invalid-collapse-low', edited(lambda t: side(t).update(collapse_below=100)), None, None, None),
        ('invalid-collapse-bool', edited(lambda t: side(t).update(collapse_below=True)), None, None, None),
        ('invalid-collapse-float', edited(lambda t: side(t).update(collapse_below=760.5)), None, None, None),
        ('invalid-basis', edited(lambda t: side(t).update(size={'basis': 'wide'})), None, None, None),
        ('invalid-basis-range', edited(lambda t: side(t).update(size={'basis': 641})), None, None, None),
        ('invalid-basis-missing', edited(lambda t: side(t).update(size={'min': 50})), None, None, None),
        ('invalid-size-type', edited(lambda t: side(t).update(size='fill')), None, None, None),
        ('invalid-min-max', edited(lambda t: side(t).update(size={'basis': 200, 'min': 300, 'max': 100})), None, None, None),
        ('invalid-min-max-range', edited(lambda t: side(t).update(size={'basis': 200, 'min': 39, 'max': 1921})), None, None, None),
        ('invalid-region-name', edited(lambda t: t['root']['children'][1].update(region='footer')), None, None, None),
        ('invalid-region-missing', edited(lambda t: t['root']['children'][1].pop('region')), None, None, None),
        ('invalid-options-type', edited(lambda t: side(t)['children'][0].update(options='x')), None, None, None),
        ('invalid-options-null', edited(lambda t: side(t)['children'][0].update(options=None)), None, None, None),
        ('invalid-option-value', edited(lambda t: side(t)['children'][1].update(options={'style': 'text', 'orientation': 'diagonal', 'groups': 'none', 'overflow': 'scroll'})), None, None, None),
        ('invalid-option-unknown', edited(lambda t: side(t)['children'][0].update(options={'name': 'show', 'shine': 1})), None, None, None),
        ('invalid-custom-no-module', edited(lambda t: side(t)['children'].append(region('custom'))), None, None, None),
        ('invalid-custom-module', edited(lambda t: side(t)['children'].append(region('custom', module='Client/Header@1'))), None, None, None),
        ('invalid-custom-module-newline', edited(lambda t: side(t)['children'].append(region('custom', module='a/b@1\n'))), None, None, None),
        ('invalid-custom-props-type', edited(lambda t: side(t)['children'].append(region('custom', module='a/b@1', props=[1]))), None, None, None),
        ('invalid-custom-props-size', edited(lambda t: side(t)['children'].append(region('custom', module='a/b@1', props={'k': 'x' * 2048}))), None, None, None),
        ('invalid-custom-props-bytes', edited(lambda t: side(t)['children'].append(region('custom', module='a/b@1', props={'k': 'é' * 1100}))), None, None, None),
        ('invalid-zero-children', edited(lambda t: t['root'].update(children=[])), None, None, None),
        ('invalid-nine-children', edited(lambda t: t['root'].update(children=spacers(9))), None, None, None),
        ('invalid-children-type', edited(lambda t: t['root'].update(children={})), None, None, None),
        ('invalid-depth-6', {'version': 1, 'root': box('column', region('navigation'), box('column', box('column', box('column', box('column', region('content', FILL)), size=FILL), size=FILL), size=FILL))}, None, None, None),
        ('invalid-nodes-25', {'version': 1, 'root': box('column', box('row', region('navigation'), *spacers(7)), box('row', *spacers(8)),
                                                         box('row', region('content', FILL), *spacers(4), size=FILL))}, None, None, None),
        ('invalid-no-content', edited(lambda t: t['root'].update(children=[side(t)])), None, None, None),
        ('invalid-two-content', edited(lambda t: t['root']['children'].append(region('content', FILL))), None, None, None),
        ('invalid-no-navigation', edited(lambda t: side(t)['children'].pop(1)), None, None, None),
        ('invalid-content-not-fill', {'version': 1, 'root': box('row', region('navigation', {'basis': 100}), box('column', region('content', {'basis': 'content'}), region('actions'), size=FILL))}, None, None, None),
        ('invalid-container-not-fill', {'version': 1, 'root': box('row', region('navigation', {'basis': 100}), box('column', region('content', FILL), region('actions'), size={'basis': 300}))}, None, None, None),
        ('invalid-two-fills', edited(lambda t: side(t)['children'].extend([region('actions', FILL), region('title', FILL)])), None, None, None),
        ('invalid-brand-twice', edited(lambda t: side(t)['children'].append(region('brand'))), None, None, None),
        ('invalid-actions-twice', edited(lambda t: side(t)['children'].extend([region('actions'), region('actions')])), None, None, None),
        ('invalid-custom-five', edited(lambda t: side(t)['children'].extend([region('custom', module=f'a/b{i}@1') for i in range(5)])), None, None, None),
        ('invalid-root-collapse', edited(lambda t: t['root'].update(collapse_below=900)), None, None, None),
        ('invalid-content-collapse', {'version': 1, 'root': box('row', region('navigation', {'basis': 100}), box('column', region('content', FILL), size=FILL, collapse_below=600))}, None, None, None),
        ('invalid-fixed-row', {'version': 1, 'root': box('row', box('row', box('row', region('navigation', FILL), size={'basis': 361}), region('actions', FILL), size={'basis': 600}), region('content', FILL))}, None, None, None),
        ('valid-fixed-960', {'version': 1, 'root': box('row', box('row', box('row', region('navigation', FILL), size={'basis': 360}), region('actions', FILL), size={'basis': 600}), region('content', FILL))}, None, None, None),
        ('invalid-fixed-column', {'version': 1, 'root': box('column', box('column', box('column', region('navigation', FILL), size={'basis': 500}), region('actions', FILL), size={'basis': 461}), region('content', FILL))}, None, None, None),
        ('valid-fixed-mixed-axes', {'version': 1, 'root': box('row', box('column', box('row', region('navigation', FILL), size={'basis': 600}), region('actions', FILL), size={'basis': 600}), region('content', FILL))}, None, None, None),
        ('invalid-off-path-max', edited(lambda t: side(t).update(size={'basis': 224, 'min': 700, 'max': 800})), None, None, None),
        ('invalid-chrome-three', {'version': 1, 'root': box('column', *[box('row', region('navigation', FILL) if i == 0 else {'type': 'spacer'}, chrome='sidebar', size={'basis': 48}) for i in range(3)], region('content', FILL))}, None, None, None),
        ('warn-behavior-panel', edited(lambda t: (side(t).update(behavior='sticky'), t['root'].update(behavior='static'))), 'panel', None, None),
        ('warn-behavior-page', edited(lambda t: side(t).update(behavior='sticky')), 'page', None, None),
        ('warn-behavior-unknown', edited(lambda t: side(t).update(behavior='sticky')), None, None, None),
        ('host-modules-none', edited(lambda t: side(t)['children'].extend([region('custom', module='a/b@1'), region('custom', module='a/c@2')])), None, [], None),
        ('host-modules-some', edited(lambda t: side(t)['children'].extend([region('custom', module='a/b@1'), region('custom', module='a/c@2')])), 'panel', ['a/b@1'], None),
        ('sdk-modules', edited(lambda t: side(t)['children'].extend([region('custom', module='a/b@1')])), None, None, None),
        ('rules-skipped-when-malformed', edited(lambda t: (t['root']['children'][1].update(region='nope'), side(t)['children'].pop(1))), None, None, None),
        ('vocab-max-children', base(), None, None, tweak(lambda v: v['limits'].update(max_children=1))),
        ('vocab-steps', edited(lambda t: t['root'].update(gap='md')), None, None, tweak(lambda v: v.update(steps=['none', 'sm']))),
        ('vocab-defaults', base(), None, None, tweak(lambda v: (v['container']['gap'].update(default='md'), v['regions']['brand']['options']['name'].update(default='show')))),
        ('vocab-required-actions', base(), None, None, tweak(lambda v: v['regions']['actions'].update(required=True))),
        ('vocab-size-px', base(), None, None, tweak(lambda v: v['limits'].update(size_px={'min': 300, 'max': 400}))),
        ('vocab-pattern', edited(lambda t: side(t)['children'].append(region('custom', module='x-1'))), None, None, tweak(lambda v: v['regions']['custom']['options']['module'].update(pattern='^x-[0-9]$'))),
        ('vocab-content-path-px', edited(lambda t: t['root']['children'][1].update(size={'basis': 'fill', 'max': 2000})), None, None, tweak(lambda v: v['limits'].update(content_path_px={'max': 2400}))),
        ('vocab-new-region', edited(lambda t: t['root']['children'].append(region('footer', basis={'basis': 40}, tone='dark'))), None, None,
         tweak(lambda v: v['regions'].update(footer={'max': 1, 'options': {'tone': {'enum': ['dark', 'light'], 'default': 'light'}}}))),
    ]
    return cases


def mutants(count, seed=4):
    """Generated trees: a preset or the base tree with one to three random edits (a junk value for a key, a deleted key, a
    duplicated or dropped child), so every rule gets stressed from both sides of its limit."""
    rng = random.Random(seed)
    sources = [base()] + [copy.deepcopy(tree) for tree in PRESETS.values()]
    keys = ['type', 'direction', 'children', 'gap', 'padding', 'align', 'justify', 'chrome', 'surface', 'size', 'behavior', 'collapse_below',
            'region', 'options', 'basis', 'min', 'max', 'module', 'props', 'name', 'style', 'orientation', 'version', 'root', 'extra']
    junk = [None, True, False, 0, 1, -1, 39, 40, 41, 56, 224, 480, 640, 641, 960, 961, 1280, 1281, 1920, 1921, 100000, 2.5, '', 'x', 'fill', 'content',
            'row', 'column', 'sm', 'md', 'xl', '2xl', 'start', 'end', 'between', 'stretch', 'sidebar', 'navbar', 'none', 'sticky', 'static', 'brand',
            'navigation', 'actions', 'title', 'content', 'custom', 'client-acme/header@1', 'A/b@1', [], [1], {}, {'a': 1}, {'basis': 'fill'},
            {'basis': 100, 'max': 50}, {'basis': 800}, {'name': 'hide'}, {'module': 'a/b@1'}, {'type': 'spacer'}, {'type': 'region', 'region': 'content'},
            {'type': 'container', 'direction': 'row', 'children': [{'type': 'spacer'}]}]

    def nodes(node, found):
        found.append(node)
        for child in node.get('children', []) if isinstance(node.get('children'), list) else []:
            if isinstance(child, dict):
                nodes(child, found)
        for key in ('size', 'options'):
            if isinstance(node.get(key), dict):
                found.append(node[key])
        return found

    out = []
    for index in range(count):
        shell = copy.deepcopy(rng.choice(sources))
        for _ in range(rng.randint(1, 3)):
            targets = nodes(shell['root'], [shell]) if isinstance(shell.get('root'), dict) else [shell]
            target = rng.choice(targets)
            action = rng.random()
            if action < 0.55:
                target[rng.choice(keys)] = copy.deepcopy(rng.choice(junk))
            elif action < 0.7 and target:
                del target[rng.choice(sorted(target))]
            elif action < 0.85 and isinstance(target.get('children'), list) and target['children']:
                target['children'].append(copy.deepcopy(rng.choice(target['children'])))
            elif isinstance(target.get('children'), list) and target['children']:
                target['children'].pop(rng.randrange(len(target['children'])))
        scroll = rng.choice([None, 'panel', 'page'])
        out.append((f'mutant-{index:03d}', shell, scroll, rng.choice([None, None, [], ['client-acme/header@1']]), None))
    return out


def typescript(cases, grid, require_node, tmp_path, themes=(), brands=(), options=()):
    require_node('esbuild')
    path = tmp_path / 'cases.json'
    path.write_text(json.dumps({'cases': [{'id': i, 'shell': s, 'scroll': sc, 'installed': inst, 'vocabulary': v} for i, s, sc, inst, v in cases],
                                'layouts': grid, 'themes': list(themes),
                                'brands': [{'id': i, 'brand': b, 'vocabulary': v} for i, b, v in brands], 'options': list(options)}, allow_nan=False))
    run = subprocess.run(['node', str(RUNNER), str(path)], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def python_side(shell, scroll, installed, vocabulary):
    found = validate_shell(shell, vocabulary, S, scroll, installed)
    return {'errors': found['errors'], 'warnings': found['warnings'],
            'tree': None if found['errors'] else normalise_shell(shell, vocabulary)}


def test_python_and_typescript_agree_on_every_rule_and_on_generated_trees(require_node, tmp_path):
    cases = named() + mutants(400)
    assert len({case[0] for case in cases}) == len(cases) >= 100
    produced = typescript(cases, [], require_node, tmp_path)['results']
    different = []
    valid = invalid = warned = 0
    for case_id, shell, scroll, installed, vocabulary in cases:
        expected = json.loads(json.dumps(python_side(shell, scroll, installed, vocabulary)))
        if produced[case_id] != expected:
            different.append(case_id)
        valid += not expected['errors']
        invalid += bool(expected['errors'])
        warned += bool(expected['warnings'])
    assert different == []
    # The corpus really covers both outcomes and the warnings.
    assert valid >= 25 and invalid >= 60 and warned >= 3, (valid, invalid, warned)


def test_the_named_cases_cover_every_rule_of_the_spec():
    """Each rule's error text appears among the named cases' problems, so a rule cannot go untested across languages."""
    seen = set()
    for case_id, shell, scroll, installed, vocabulary in named():
        found = python_side(shell, scroll, installed, vocabulary)
        seen.update(item['message'].split(':')[0].split(' (')[0] for item in found['errors'] + found['warnings'])
    wanted = ['A shell is at most 5 levels deep', 'A shell has at most 24 nodes', 'A container has 1 to 8 children',
              'A shell needs a content region', 'A shell needs a navigation region, so the user can always navigate',
              'At most one child of a container may fill', 'At most 1 brand region', 'At most 1 actions region', 'At most 4 custom regions',
              'The container that holds the content cannot collapse into a drawer', 'module not installed',
              'At most 2 containers may have chrome sidebar', 'Must match ^[a-z0-9-]+/[a-z0-9-]+@[0-9]+$', 'Must be at most 2048 bytes of JSON',
              'Unknown key zzz', 'Unknown option shine', 'max must be at least min', 'Must be one of row, column',
              'The root of a shell must be a container', 'Off the content path a size is at most 640px', 'Must be a JSON object', 'version must be 1']
    for text in wanted:
        assert any(message.startswith(text) for message in seen), text
    assert any(message.startswith('Fixed sizes on one root-to-leaf path add up to at most 960px along the row') for message in seen)
    assert any(message.startswith('Fixed sizes on one root-to-leaf path add up to at most 960px along the column') for message in seen)
    assert any(message.startswith('behavior sticky has no visible effect while scroll is panel') for message in seen)
    assert any(message.startswith('The content region, and every container on the way to it') for message in seen)


def test_shell_from_layout_is_identical_in_typescript(require_node, tmp_path):
    grid = layouts() + [registry.default_layout('rail'), registry.default_layout('panel')]
    produced = typescript([], grid, require_node, tmp_path)['layouts']
    assert len(produced) == len(grid) > 100
    wrong = [index for index, layout in enumerate(grid) if produced[index] != shell_from_layout(layout)]
    assert wrong == []


def test_every_layout_the_options_express_validates_in_typescript_too(require_node, tmp_path):
    grid = layouts()
    trees = [shell_from_layout(layout) for layout in grid]
    produced = typescript([(f'layout-{i}', tree, 'page', None, None) for i, tree in enumerate(trees)], [], require_node, tmp_path)['results']
    assert all(item['errors'] == [] and item['warnings'] == [] for item in produced.values())
    assert [produced[f'layout-{i}']['tree'] for i in range(len(trees))] == trees


def test_typescript_resolves_a_revision_4_theme_to_its_own_tree_and_older_ones_to_the_derived_tree(require_node, tmp_path):
    """resolveTheme(...).shell.tree and shellTreeOf are what core renders; the goldens (tests/golden/layout-tree) hold the exact
    trees, this checks a theme edited on the spot: `layout.shell` changes the resolved tree and nothing else."""
    from fastlanelabs_sdk.themes import default_theme_v2, resolve_theme
    theme = default_theme_v2()
    theme['layout']['shell'] = copy.deepcopy(PRESETS['top-bar'])
    theme['layout']['sidebar']['side'] = 'hidden'
    theme['layout']['navbar']['position'] = 'top'
    older = default_theme_v2(registry_revision=3)
    first, second = typescript([], [], require_node, tmp_path, [theme, older])['themes']
    assert first['resolved']['shell']['tree'] == first['tree'] == resolve_theme(theme)['shell']['tree'] == normalise_shell(PRESETS['top-bar'])
    assert second['resolved']['shell']['tree'] == second['tree'] == resolve_theme(older)['shell']['tree'] == normalise_shell(PRESETS['rail'])
    assert first['resolved']['shell']['attrs'] == resolve_theme(theme)['shell']['attrs']
    assert second['resolved']['shell']['vars'] == resolve_theme(older)['shell']['vars']


# --- Registry revision 4: the brand -------------------------------------------------------------------------------------

def test_python_and_typescript_agree_on_every_brand_rule_and_on_generated_brands(require_node, tmp_path):
    """validateBrand / normaliseBrand give the same errors (same paths, messages and ORDER) and the same normalised brand as
    validate_brand / normalise_brand over the named cases of tests/test_brand.py (every rule, every forbidden SVG construct, the
    size limits from the vocabulary) and 220 generated mutants."""
    cases = brand_cases()
    assert len({case[0] for case in cases}) == len(cases) >= 60
    produced = typescript([], [], require_node, tmp_path, brands=cases)['brands']
    different = []
    valid = invalid = 0
    for case_id, brand, vocabulary in cases:
        found = validate_brand(brand, vocabulary)
        norm = None if found['errors'] else normalise_brand(brand, vocabulary)
        expected = json.loads(json.dumps({'errors': found['errors'], 'warnings': found['warnings'], 'brand': norm,
                                          'logo_for': None if norm is None else {'light': brand_logo_for(norm, False), 'dark': brand_logo_for(norm, True)}}))
        if produced[case_id] != expected:
            different.append(case_id)
        valid += not expected['errors']
        invalid += bool(expected['errors'])
    assert different == []
    assert valid >= 20 and invalid >= 100, (valid, invalid)


def test_typescript_resolves_the_brand_of_a_revision_4_theme_and_nothing_for_older_ones(require_node, tmp_path):
    from fastlanelabs_sdk.themes import default_theme_v2, resolve_theme
    from test_brand import good
    theme = default_theme_v2()
    theme['brand'] = good()
    theme['brand']['tagline'] = '  padded  '
    older = default_theme_v2(registry_revision=3)
    plain = default_theme_v2()
    first, second, third = typescript([], [], require_node, tmp_path, [theme, older, plain])['themes']
    assert first['resolved']['brand'] == resolve_theme(theme)['brand'] and first['resolved']['brand']['tagline'] == 'padded'
    assert second['resolved']['brand'] is None and third['resolved']['brand'] is None
    assert first['resolved'] == json.loads(json.dumps(resolve_theme(theme)))
    assert third['resolved'] == json.loads(json.dumps(resolve_theme(plain)))


def test_typescript_offers_the_same_enum_options_per_revision_as_python(require_node, tmp_path):
    asked = [[token.name, revision] for token in registry.INDEX.values() if token.type == 'enum' for revision in (1, 2, 3, 4)]
    produced = typescript([], [], require_node, tmp_path, options=asked)['options']
    assert produced == [list(registry.INDEX[name].options_for(revision)) for name, revision in asked]
    assert ['nav-item-variant', 3] in asked and produced[asked.index(['nav-item-variant', 3])] == ['square', 'pill']
    assert produced[asked.index(['nav-item-variant', 4])] == ['square', 'pill', 'tab']
