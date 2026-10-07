"""API v1 is frozen: published releases are hashed from validate_theme's output.

The fixtures are the three reviewed releases (copied from fll-themes). If one
of these hashes or messages changes, a deployed validator and a stored pin
would disagree; bump an API version instead of editing v1.
"""
import hashlib
import io
import json
import zipfile
from importlib.resources import files
from pathlib import Path

import pytest
from fastlanelabs_sdk.theme_packs import ThemePackError, create_theme_pack, validate_theme_pack
from fastlanelabs_sdk.themes import ThemeError, validate_theme

FIXTURES = Path(__file__).parent / 'fixtures/themes'
RELEASE_HASHES = {
    'fastlane-1.0.0': '6e1cc063240a9d60ef1fc6bc0c9c09be3618cedc462f50d4c1399db4d47cbb72',
    'precision-hose-1.0.0': '6dec50cc95fcfa98e11f83e22412925893aa4c378245dfa087c1d7e8b186ee9f',
    'precision-hose-1.1.0': 'f4ecd890ad16a352dd27e5b359d2c55977e5b3849eb8b710af5c03fd24991db8',
}


def release_hash(theme):
    # Exactly what scripts/publish.py in fll-themes hashes.
    return hashlib.sha256((json.dumps(validate_theme(theme), sort_keys=True, indent=2) + '\n').encode()).hexdigest()


@pytest.mark.parametrize('name', sorted(RELEASE_HASHES))
def test_published_v1_releases_hash_exactly_as_before(name):
    assert release_hash(json.loads((FIXTURES / f'{name}.json').read_text())) == RELEASE_HASHES[name]


def test_the_sdk_fallback_manifest_is_the_fastlane_release():
    theme = json.loads(files('fastlanelabs_sdk.registry_data').joinpath('default-theme.json').read_text())
    assert release_hash(theme) == RELEASE_HASHES['fastlane-1.0.0']


@pytest.mark.parametrize('change,message', [
    (lambda t: t.update(api_version=3), 'Unsupported theme API version'),
    (lambda t: t['tokens'].update({'surface': '#fff;x'}), 'Invalid token surface'),
    (lambda t: t['tokens'].update({'font-sans': 'url(https://x)'}), 'Invalid token font-sans'),
    (lambda t: t['tokens'].update({'radius': '17px'}), 'Invalid token radius'),
    (lambda t: t['tokens'].pop('ink-900'), 'Theme must supply exactly the supported tokens'),
    (lambda t: t['tokens'].update({'ink-900': '#ffffff'}), 'ink-900 on surface must meet 4.5:1 contrast'),
    (lambda t: t['layout'].update({'navigation': 'custom'}), 'Unsupported layout option'),
    (lambda t: t.update(id='../x'), 'Invalid theme id'),
    (lambda t: t.update(version='1'), 'Theme version must be major.minor.patch'),
    (lambda t: t.update(script='a'), 'Theme must contain only api_version, id, version, label, tokens and layout'),
])
def test_v1_error_messages_are_unchanged(change, message):
    theme = json.loads((FIXTURES / 'fastlane-1.0.0.json').read_text())
    change(theme)
    with pytest.raises(ThemeError) as failure:
        validate_theme(theme)
    assert str(failure.value) == message


def pack_inputs():
    theme = json.loads((FIXTURES / 'fastlane-1.0.0.json').read_text())
    theme.update(id='client-acme', label='Acme')
    presentation = {'api_version': 1, 'workspace': {'type': 'column', 'gap': 'md', 'children': [
        {'type': 'slot', 'name': 'actions'},
        {'type': 'row', 'gap': 'sm', 'children': [
            {'type': 'slot', 'name': 'content'}, {'type': 'slot', 'name': 'navigation', 'width': 240}]}]},
        'styles': {'navigation.item': {'variant': 'pill', 'mode': 'label'}}}
    sources = {'website': 'https://example.com', 'retrieved_at': '2026-10-05',
               'observations': [{'url': 'https://example.com', 'kind': 'observed', 'note': 'Blue controls.'}], 'notes': []}
    return theme, presentation, sources


def test_v1_pack_files_are_byte_identical():
    with zipfile.ZipFile(io.BytesIO(create_theme_pack(*pack_inputs()))) as archive:
        hashes = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in sorted(archive.namelist())}
    assert hashes == {
        'pack.json': '867b557394d734179a59a6bfa8b637f2c21fc6489c0d4e7a737e68ab1d27e561',
        'presentation.json': 'd0dcd85db7adbb8d309f7c1139bd65f31cc2f2d5f1cd5f4aed5ba1d695c77c3b',
        'sources.json': '8c654e5e187c63caa87d5522f0b038e54345ca5436308d593c43ef692c8751c5',
        'theme.json': '21eb0b8ac293ecce11e429af4e46ed9ac9357381b8a1f18c738981fb54463691',
    }


def rewrite(change):
    data = create_theme_pack(*pack_inputs())
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        payload = {name: archive.read(name) for name in archive.namelist()}
    change(payload)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in payload.items():
            archive.writestr(name, content)
    return output.getvalue()


@pytest.mark.parametrize('change,path,message', [
    (lambda p: p.update(script=b'x'), '$archive', 'Theme pack must contain exactly four root JSON files'),
    (lambda p: p.pop('sources.json'), '$archive', 'Theme pack must contain exactly four root JSON files'),
    (lambda p: p.pop('presentation.json'), '$archive', 'Theme pack must contain exactly four root JSON files'),
    (lambda p: p.update({'../theme.json': p.pop('theme.json')}), '../theme.json', 'Unexpected file; only the four root JSON files are supported'),
    (lambda p: p.update({'assets/logo.png': p.pop('sources.json')}), 'assets/logo.png', 'Unexpected file; only the four root JSON files are supported'),
    (lambda p: p.update({'theme.json': b'{}'}), 'theme.json', 'Checksum mismatch'),
    (lambda p: p.update({'pack.json': b'{"format":1,"format":2}'}), 'pack.json', 'Duplicate JSON key: format'),
    (lambda p: p.update({'pack.json': b'{"format":NaN}'}), 'pack.json', 'Must contain valid UTF-8 JSON'),
])
def test_v1_archive_errors_are_unchanged(change, path, message):
    with pytest.raises(ThemePackError) as failure:
        validate_theme_pack(rewrite(change))
    assert failure.value.errors == [{'path': path, 'message': message}]


def test_a_v2_theme_cannot_hide_in_a_format_1_pack():
    from fastlanelabs_sdk.themes import default_theme_v2
    theme = default_theme_v2('client-acme')
    with pytest.raises(ThemePackError):
        create_theme_pack(theme, pack_inputs()[1], pack_inputs()[2])
