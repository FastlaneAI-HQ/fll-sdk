"""Registry revision 1 is frozen (D12): everything SDK 1.3 produced for it is still produced, byte for byte.

tests/golden/frozen-r1 was written by SDK 1.3.1 and is never regenerated. A change that makes one of
these tests fail has changed what a published release renders as, and is wrong: a new capability must be
optional, and a rule for an existing (api_version, registry_revision) must never tighten.
"""
import json
from pathlib import Path

import pytest
from fastlanelabs_sdk import themes

FROZEN = sorted((Path(__file__).parent / 'golden/frozen-r1').glob('*.json'))


def test_the_frozen_corpus_is_what_sdk_1_3_wrote():
    assert [p.name for p in FROZEN] == [
        'custom-v2.json', 'default-v2.json', 'fastlane-v1.json', 'pack-right-panel-v1.json',
        'pack-top-navigation-v1.json', 'precision-hose-1.0.0-v1.json', 'precision-hose-1.1.0-v1.json']
    assert all(json.loads(p.read_text())['resolve']['api_version'] == 2 for p in FROZEN)


@pytest.mark.parametrize('path', FROZEN, ids=lambda p: p.stem)
def test_revision_1_results_are_unchanged(path):
    golden = json.loads(path.read_text())
    manifest = golden['input']
    v2 = manifest
    if manifest['api_version'] == 1:
        # Upgrading with the revision pinned reproduces SDK 1.3's upgrade exactly.
        assert json.loads(json.dumps(themes.upgrade_v1_report(manifest, golden['presentation'], registry_revision=1))) == golden['upgrade']
        assert themes.resolve_theme(manifest) == golden['resolve_v1']
        v2 = golden['upgrade']['theme']
        assert themes.project_v1(v2) == golden['project']
    assert v2['registry_revision'] == 1 and v2['color_scheme'] == 'light' and 'modes' not in v2
    assert themes.check_theme(v2)['errors'] == []
    assert themes.validate_theme(v2) == v2
    assert json.loads(json.dumps(themes.resolve_theme(v2))) == golden['resolve']
    assert json.loads(json.dumps(themes.contrast_report(v2))) == golden['contrast']
    # Light-only output gained nothing: no mode keys in the rows, no scheme, no data-fl-mode.
    assert 'scheme' not in golden['resolve'] and 'data-fl-mode' not in golden['resolve']['attrs']
    assert all('mode' not in row for row in golden['contrast'])


def test_a_revision_1_theme_resolves_the_same_when_a_mode_is_asked_for():
    v2 = json.loads(FROZEN[1].read_text())['input']
    assert themes.resolve_theme(v2, 'dark') == themes.resolve_theme(v2) == themes.resolve_theme(v2, 'light')


def test_revision_1_still_reserves_dark_mode_with_the_same_messages():
    v2 = json.loads(FROZEN[1].read_text())['input']
    assert themes.check_theme(dict(v2, color_scheme='dark'))['errors'] == [
        {'path': 'color_scheme', 'message': 'color_scheme must be light; dark mode is reserved for a later registry revision'}]
    assert themes.check_theme(dict(v2, modes={'dark': {}}))['errors'] == [
        {'path': 'modes', 'message': 'modes is reserved for a later registry revision and must be absent'}]
    assert themes.check_theme(dict(v2, color_scheme='auto'))['errors'][0]['path'] == 'color_scheme'
