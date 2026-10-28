import hashlib
import io
import json
import stat
import zipfile
from importlib.resources import files

import pytest
from fastlanelabs_sdk.theme_packs import MAX_FILE_BYTES, MAX_PACK_BYTES, ThemePackError, create_theme_pack_v2, validate_theme_pack


def inputs():
    theme = json.loads(files('fastlanelabs_sdk.registry_data').joinpath('default-theme.json').read_text())
    theme.update(id='client-acme', label='Acme')
    theme['layout']['sidebar']['side'] = 'right'
    sources = {'website': 'https://example.com', 'retrieved_at': '2026-10-05',
               'observations': [{'url': 'https://example.com', 'kind': 'observed', 'note': 'Blue controls.'}], 'notes': []}
    return theme, sources


def rewrite(data, change):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        payload = {name: archive.read(name) for name in archive.namelist()}
    change(payload)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in payload.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_pack_round_trip_is_reproducible_and_preserves_right_navigation():
    values = inputs()
    data = create_theme_pack_v2(*values)
    assert data == create_theme_pack_v2(*values)
    result = validate_theme_pack(data)
    assert (result['theme'], result['sources']) == values
    assert result['sha256'] == hashlib.sha256(data).hexdigest()
    assert result['warnings'] == []


@pytest.mark.parametrize('change', [
    lambda p: p.update(script=b'alert(1)'),
    lambda p: p.pop('sources.json'),
    lambda p: p.update({'../theme.json': p.pop('theme.json')}),
    lambda p: p.update({'assets/logo.png': p.pop('sources.json')}),
    lambda p: p.update({'theme.json': b'{}'}),
    lambda p: p.update({'theme.json': b' ' * (MAX_FILE_BYTES + 1)}),
    lambda p: p.update({'pack.json': b'{"format":1,"format":2}'}),
    lambda p: p.update({'pack.json': b'\xff'}),
    lambda p: p.update({'pack.json': b'{"format":NaN}'}),
])
def test_invalid_archives_cannot_become_ready(change):
    with pytest.raises(ThemePackError) as failure:
        validate_theme_pack(rewrite(create_theme_pack_v2(*inputs()), change))
    assert failure.value.errors[0]['path']


def test_duplicate_archive_entries_and_symlinks_are_rejected():
    data = create_theme_pack_v2(*inputs())
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        payload = {name: archive.read(name) for name in archive.namelist()}
    for mode, names in ((stat.S_IFLNK | 0o777, list(payload)), (stat.S_IFREG | 0o644, ['pack.json', 'theme.json', 'theme.json'])):
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as archive:
            for name in names:
                info = zipfile.ZipInfo(name)
                info.external_attr = mode << 16
                archive.writestr(info, payload[name])
        with pytest.raises(ThemePackError):
            validate_theme_pack(out.getvalue())


def test_corrupt_and_oversized_archives_are_rejected():
    for data in (b'not zip', b'X' * (MAX_PACK_BYTES + 1)):
        with pytest.raises(ThemePackError):
            validate_theme_pack(data)


def test_pack_namespace_identity_and_version_are_checked():
    values = inputs()
    values[0]['id'] = 'fastlane'
    with pytest.raises(ThemePackError):
        create_theme_pack_v2(*values)
    def alter(payload):
        pack = json.loads(payload['pack.json'])
        pack['version'] = '2.0.0'
        payload['pack.json'] = json.dumps(pack).encode()
    with pytest.raises(ThemePackError):
        validate_theme_pack(rewrite(create_theme_pack_v2(*inputs()), alter))


def test_sources_are_validated_and_inference_has_visible_warnings():
    values = inputs()
    values[1]['observations'] = []
    assert validate_theme_pack(create_theme_pack_v2(*values))['warnings']
    values[1]['observations'] = [{'url': 'https://example.com', 'kind': 'inferred', 'note': 'Fallback font.'}]
    assert validate_theme_pack(create_theme_pack_v2(*values))['warnings']
    values[1]['website'] = 'javascript:alert(1)'
    with pytest.raises(ThemePackError):
        create_theme_pack_v2(*values)


def test_corrupt_deflate_stream_returns_a_structured_error():
    data = bytearray(create_theme_pack_v2(*inputs()))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entry = archive.getinfo('theme.json')
        offset = entry.header_offset + 30 + len(entry.filename.encode()) + len(entry.extra)
    # BFINAL=1 and reserved BTYPE=3 creates an invalid DEFLATE block.
    data[offset] = 0x07
    with pytest.raises(ThemePackError) as failure:
        validate_theme_pack(bytes(data))
    assert failure.value.errors == [{'path': '$archive', 'message': 'Unreadable or corrupt ZIP archive'}]
