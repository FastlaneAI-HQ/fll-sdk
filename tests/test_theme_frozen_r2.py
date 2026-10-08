"""Registry revision 2 is frozen too: everything SDK 1.4 produced for it is still produced, byte for byte.

tests/golden/frozen-r2 was written by SDK 1.4.0 (it is that release's tests/golden/theme-resolve) and is never
regenerated. Revision 3 changes what a NEW theme starts from and adds checks, but a theme that targets revision 2
validates, resolves, derives its dark palette and reports contrast exactly as before: a change that makes one of these
tests fail has changed what a published release renders as, and is wrong.
"""
import json
from pathlib import Path

import pytest
from fastlanelabs_sdk import themes

FROZEN = sorted((Path(__file__).parent / 'golden/frozen-r2').glob('*.json'))


def test_the_frozen_corpus_is_what_sdk_1_4_wrote():
    assert [p.name for p in FROZEN] == [
        'custom-auto-v2.json', 'custom-v2.json', 'default-auto-v2.json', 'default-dark-v2.json', 'default-v2.json',
        'fastlane-v1.json', 'pack-right-panel-v1.json', 'pack-top-navigation-v1.json', 'precision-hose-1.0.0-v1.json',
        'precision-hose-1.1.0-v1.json', 'tuned-auto-v2.json', 'warm-auto-v2.json', 'warm-dark-v2.json']


@pytest.mark.parametrize('path', FROZEN, ids=lambda p: p.stem)
def test_revision_2_results_are_unchanged(path):
    golden = json.loads(path.read_text())
    manifest = golden['input']
    v2 = manifest
    if manifest['api_version'] == 1:
        assert json.loads(json.dumps(themes.upgrade_v1_report(manifest, golden['presentation'], registry_revision=2))) == golden['upgrade']
        assert themes.resolve_theme(manifest) == golden['resolve_v1']
        v2 = golden['upgrade']['theme']
        assert themes.project_v1(v2) == golden['project']
    assert v2['registry_revision'] == 2
    assert themes.check_theme(v2)['errors'] == []
    assert themes.validate_theme(v2) == v2
    assert json.loads(json.dumps(themes.resolve_theme(v2))) == golden['resolve']
    assert json.loads(json.dumps(themes.contrast_report(v2))) == golden['contrast']
    # None of the revision 3 rows reaches a revision 2 theme.
    assert all('group' not in row for row in golden['contrast'])
    if v2['color_scheme'] != 'light':
        assert json.loads(json.dumps(themes.resolve_theme(v2, 'dark'))) == golden['resolve_dark']
        assert json.loads(json.dumps(themes.check_theme(v2))) == golden['check']
        if v2['color_scheme'] == 'auto':
            assert json.loads(json.dumps(themes.derive_dark(v2))) == golden['derive']


def test_a_new_revision_2_default_is_what_sdk_1_4_started_from():
    golden = json.loads((Path(__file__).parent / 'golden/frozen-r2/default-v2.json').read_text())['input']
    assert themes.default_theme_v2(registry_revision=2) == golden
    auto = json.loads((Path(__file__).parent / 'golden/frozen-r2/default-auto-v2.json').read_text())['input']
    assert themes.default_theme_v2('fastlane', '2.1.0', 'Fastlane', scheme='auto', registry_revision=2) == auto
