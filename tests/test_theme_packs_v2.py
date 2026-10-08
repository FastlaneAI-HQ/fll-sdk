import hashlib
import io
import json
import zipfile

import pytest
from fastlanelabs_sdk.theme_packs import (
    MAX_FILE_BYTES, ThemePackError, create_theme_pack, create_theme_pack_v2, validate_theme_pack,
)
from fastlanelabs_sdk.themes import default_theme_v2, validate_theme


def inputs():
    theme = default_theme_v2('client-acme', '1.0.0', 'Acme')
    theme['tokens']['components']['button-radius'] = '{radius-pill}'
    theme['layout']['navbar'].update(position='top')
    sources = {'website': 'https://example.com', 'retrieved_at': '2026-10-05',
               'observations': [{'url': 'https://example.com', 'kind': 'observed', 'note': 'Pill buttons.'}], 'notes': []}
    return theme, sources


def payload_of(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def pack_of(payload, fix_checksums=True):
    if fix_checksums:
        pack = json.loads(payload['pack.json'])
        pack['files'] = {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()
                         if name in pack['files']}
        payload = dict(payload, **{'pack.json': json.dumps(pack, sort_keys=True).encode()})
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in payload.items():
            archive.writestr(name, content)
    return output.getvalue()


def modified(change, fix_checksums=True):
    payload = payload_of(create_theme_pack_v2(*inputs()))
    change(payload)
    return pack_of(payload, fix_checksums)


def test_v2_pack_round_trip_is_reproducible_and_has_three_files():
    theme, sources = inputs()
    data = create_theme_pack_v2(theme, sources)
    assert data == create_theme_pack_v2(theme, sources)
    assert sorted(payload_of(data)) == ['pack.json', 'sources.json', 'theme.json']
    result = validate_theme_pack(data)
    assert result['format_version'] == 2 and result['presentation'] is None
    assert (result['theme'], result['sources']) == (theme, sources)
    assert result['sha256'] == hashlib.sha256(data).hexdigest()
    assert result['warnings'] == []  # the revision 3 default palette has accessible input borders and placeholders
    pack = json.loads(payload_of(data)['pack.json'])
    assert (pack['format_version'], pack['template_api_version'], sorted(pack['files'])) == (2, 2, ['sources.json', 'theme.json'])


def test_the_pack_hash_is_the_sha_of_the_validated_theme_bytes():
    theme, sources = inputs()
    stored = payload_of(create_theme_pack_v2(theme, sources))['theme.json']
    assert stored == (json.dumps(validate_theme(theme), sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode()


@pytest.mark.parametrize('change,path', [
    (lambda p: p.update({'presentation.json': b'{}'}), '$archive'),
    (lambda p: p.pop('sources.json'), '$archive'),
    (lambda p: p.update({'script.js': p.pop('sources.json')}), 'script.js'),
    (lambda p: p.update({'../theme.json': p.pop('theme.json')}), '../theme.json'),
])
def test_v2_archives_allow_exactly_three_root_files(change, path):
    with pytest.raises(ThemePackError) as failure:
        validate_theme_pack(modified(change, fix_checksums=False))
    assert failure.value.errors[0]['path'] == path
    assert 'three' in failure.value.errors[0]['message']


def test_v2_pack_requires_a_v2_theme_and_template_api():
    v1_theme = json.loads(json.dumps(default_theme_v2()))
    v1_theme = {'api_version': 1, 'id': 'client-acme', 'version': '1.0.0', 'label': 'Acme',
                'tokens': {k: v for k, v in {**v1_theme['tokens']['primitives'], **v1_theme['tokens']['semantic']}.items()
                           if k in ('surface', 'on-primary', 'font-sans', 'font-mono', 'radius') or k[:4] in ('ink-', 'acce')},
                'layout': {'density': 'comfortable', 'navigation': 'rail'}}
    with pytest.raises(ThemePackError) as failure:
        validate_theme_pack(modified(lambda p: p.update({'theme.json': json.dumps(v1_theme).encode()})))
    assert failure.value.errors == [{'path': 'theme.json.api_version', 'message': 'Format 2 packs require a v2 theme'}]

    def bad_template(p):
        pack = json.loads(p['pack.json'])
        pack['template_api_version'] = 1
        p['pack.json'] = json.dumps(pack).encode()
    with pytest.raises(ThemePackError) as failure:
        validate_theme_pack(modified(bad_template))
    assert failure.value.errors[0]['path'] == 'pack.json.template_api_version'


def test_theme_errors_keep_their_field_paths_inside_the_pack():
    def corrupt(p):
        theme = json.loads(p['theme.json'])
        theme['tokens']['primitives']['radius'] = '99px'
        theme['tokens']['components']['button-height'] = '10px'
        p['theme.json'] = json.dumps(theme).encode()
    with pytest.raises(ThemePackError) as failure:
        validate_theme_pack(modified(corrupt))
    assert [e['path'] for e in failure.value.errors] == [
        'theme.json.tokens.primitives.radius', 'theme.json.tokens.components.button-height']


def test_identity_namespace_and_checksums_are_enforced():
    theme, sources = inputs()
    with pytest.raises(ThemePackError) as failure:
        create_theme_pack_v2(dict(theme, id='fastlane'), sources)
    assert failure.value.errors[0]['path'] == 'theme.json.id'

    def rename(p):
        pack = json.loads(p['pack.json'])
        pack['version'] = '9.9.9'
        p['pack.json'] = json.dumps(pack).encode()
    with pytest.raises(ThemePackError, match='Pack identity must match'):
        validate_theme_pack(modified(rename))
    with pytest.raises(ThemePackError, match='Checksum mismatch'):
        validate_theme_pack(modified(lambda p: p.update({'sources.json': p['sources.json'] + b' '}), fix_checksums=False))


@pytest.mark.parametrize('change', [
    lambda p: p.update({'theme.json': b'{"a":1,"a":2}'}),
    lambda p: p.update({'theme.json': b'{"api_version":NaN}'}),
    lambda p: p.update({'theme.json': b'\xff'}),
    lambda p: p.update({'theme.json': b' ' * (MAX_FILE_BYTES + 1)}),
    lambda p: p.update({'sources.json': b'{}'}),
])
def test_invalid_v2_files_cannot_become_ready(change):
    with pytest.raises(ThemePackError) as failure:
        validate_theme_pack(modified(change))
    assert failure.value.errors[0]['path']


def test_creation_rejects_invalid_input():
    theme, sources = inputs()
    for bad in (dict(theme, color_scheme='dark'), {}, [], dict(theme, layout={})):
        with pytest.raises(ThemePackError):
            create_theme_pack_v2(bad, sources)
    with pytest.raises(ThemePackError):
        create_theme_pack_v2(theme, {})
    nan = default_theme_v2('client-acme')
    nan['tokens']['primitives']['size-scale'] = float('nan')
    with pytest.raises(ThemePackError):
        create_theme_pack_v2(nan, sources)


def test_format_1_packs_still_round_trip_beside_format_2():
    from fastlanelabs_sdk.themes import project_v1
    v1 = project_v1(default_theme_v2('client-old', '1.0.0', 'Old'))
    presentation = {'api_version': 1, 'workspace': {'type': 'row', 'gap': 'md', 'children': [
        {'type': 'slot', 'name': 'navigation'}, {'type': 'column', 'gap': 'md', 'children': [
            {'type': 'slot', 'name': 'actions'}, {'type': 'slot', 'name': 'content'}]}]}, 'styles': {}}
    _, sources = inputs()
    data = create_theme_pack(v1, presentation, sources)
    result = validate_theme_pack(data)
    assert result['theme'] == v1 and 'format_version' not in result and result['presentation']['api_version'] == 1
