"""Bounded, data-only FastlaneLabs theme packs.

Format 1 carries a v1 theme with a layout tree and component styles (four root
JSON files). Format 2 carries a v2 theme, whose layout lives in the manifest,
so it has no presentation.json (three root JSON files).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
import zlib
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from .themes import ThemeError, _validate_v1, check_theme, validate_theme

MAX_PACK_BYTES = 2 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
PACK_FILES = {'pack.json', 'theme.json', 'presentation.json', 'sources.json'}
PACK_FILES_V2 = {'pack.json', 'theme.json', 'sources.json'}
STYLE_OPTIONS = {
    'navigation.sidebar': {'variant': ('panel', 'rail'), 'tone': ('light', 'dark')},
    'navigation.item': {'variant': ('square', 'pill'), 'mode': ('icon', 'label')},
    'navigation.topbar': {'tone': ('light', 'dark')},
    'page.header': {'variant': ('plain', 'ruled')},
    'surface.card': {'variant': ('bordered', 'raised')},
    'control.button': {'variant': ('solid', 'outline'), 'radius': ('theme', 'square')},
    'control.input': {'variant': ('outline', 'filled')},
    'control.field': {'variant': ('stacked', 'inline')},
    'chat.message': {'variant': ('bubble', 'ruled')},
    'chat.composer': {'variant': ('panel', 'plain')},
}


class ThemePackError(ThemeError):
    """A user-facing error with the offending file or field."""

    def __init__(self, message: str, path: str = 'pack.json'):
        super().__init__(message)
        self.errors = [{'path': path, 'message': message}]


def _json(data: bytes, path: str):
    def pairs(items):
        value = {}
        for key, content in items:
            if key in value:
                raise ThemePackError(f'Duplicate JSON key: {key}', path)
            value[key] = content
        return value
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except ThemePackError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ThemePackError('Must contain valid UTF-8 JSON', path) from exc


def _declared_format(archive: zipfile.ZipFile) -> int:
    """The format_version pack.json declares, or 1 whenever it cannot be read.

    Anything unreadable falls through to the format 1 checks, so their errors
    (and limits) are exactly what they always were.
    """
    try:
        entry = next(entry for entry in archive.infolist() if entry.filename == 'pack.json')
        if entry.file_size > MAX_FILE_BYTES or entry.flag_bits & 1:
            return 1
        with archive.open(entry) as stream:
            declared = json.loads(stream.read(MAX_FILE_BYTES + 1).decode('utf-8')).get('format_version')
    except (StopIteration, AttributeError, UnicodeError, ValueError, OSError, RuntimeError, NotImplementedError, zlib.error, EOFError, RecursionError, zipfile.BadZipFile):
        return 1
    return 2 if type(declared) is int and declared == 2 else 1


def _archive(data: bytes) -> dict[str, bytes]:
    if not isinstance(data, bytes) or not data or len(data) > MAX_PACK_BYTES:
        raise ThemePackError('Theme pack must be a ZIP no larger than 2 MiB', '$archive')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            version = _declared_format(archive)
            allowed, count = (PACK_FILES_V2, 'three') if version == 2 else (PACK_FILES, 'four')
            if len(entries) != len(allowed):
                raise ThemePackError(f'Theme pack must contain exactly {count} root JSON files', '$archive')
            payload = {}
            total = 0
            for entry in entries:
                name = entry.filename
                if name != entry.orig_filename:
                    raise ThemePackError('Unsafe archive filename', name)
                if name in payload:
                    raise ThemePackError('Duplicate archive entry', name)
                if name not in allowed:
                    raise ThemePackError(f'Unexpected file; only the {count} root JSON files are supported', name)
                if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*(?:/[a-zA-Z0-9][a-zA-Z0-9_.-]*)*', name) or any(x in ('.', '..') for x in name.split('/')):
                    raise ThemePackError('Unsafe archive path', name)
                mode = entry.external_attr >> 16
                if entry.is_dir() or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                    raise ThemePackError('Only regular files are supported', name)
                if entry.flag_bits & 1:
                    raise ThemePackError('Encrypted ZIP entries are unsupported', name)
                if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ThemePackError('Unsupported ZIP compression', name)
                if entry.file_size > MAX_FILE_BYTES:
                    raise ThemePackError('File exceeds 512 KiB limit', name)
                total += entry.file_size
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise ThemePackError('Uncompressed pack exceeds 2 MiB limit', '$archive')
                with archive.open(entry) as stream:
                    content = stream.read(MAX_FILE_BYTES + 1)
                if len(content) > MAX_FILE_BYTES or len(content) != entry.file_size:
                    raise ThemePackError('Invalid or oversized archive entry', name)
                payload[name] = content
            return payload
    except ThemePackError:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError, NotImplementedError, zlib.error, EOFError) as exc:
        raise ThemePackError('Unreadable or corrupt ZIP archive', '$archive') from exc


def _keys(value: Any, required: set, path: str, optional: set = frozenset()):
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - optional:
        raise ThemePackError('Missing or unsupported fields', path)


def validate_presentation(value: Any) -> dict:
    """Validate host-owned layout constructors and component variants only."""
    _keys(value, {'api_version', 'workspace', 'styles'}, 'presentation.json')
    if type(value['api_version']) is not int or value['api_version'] != 1:
        raise ThemePackError('Unsupported presentation API version', 'presentation.json.api_version')
    slots = []
    count = 0

    def node(candidate, path, depth):
        nonlocal count
        count += 1
        if depth > 6 or count > 24:
            raise ThemePackError('Workspace exceeds six levels or 24 nodes', path)
        if not isinstance(candidate, dict):
            raise ThemePackError('Workspace node must be an object', path)
        kind = candidate.get('type')
        if kind in ('row', 'column'):
            _keys(candidate, {'type', 'gap', 'children'}, path)
            if candidate['gap'] not in ('none', 'sm', 'md', 'lg'):
                raise ThemePackError('Unsupported spacing', path + '.gap')
            children = candidate['children']
            if not isinstance(children, list) or not 1 <= len(children) <= 8:
                raise ThemePackError('Group must contain 1–8 children', path + '.children')
            return {'type': kind, 'gap': candidate['gap'], 'children': [
                node(child, f'{path}.children[{index}]', depth + 1) for index, child in enumerate(children)]}
        if kind == 'slot':
            _keys(candidate, {'type', 'name'}, path, {'width'})
            name = candidate['name']
            if name not in ('content', 'navigation', 'actions'):
                raise ThemePackError('Unsupported semantic slot', path + '.name')
            slots.append(name)
            normalized = {'type': 'slot', 'name': name}
            if 'width' in candidate:
                if name != 'navigation' or type(candidate['width']) is not int or not 56 <= candidate['width'] <= 320:
                    raise ThemePackError('Only navigation supports a width of 56–320', path + '.width')
                normalized['width'] = candidate['width']
            return normalized
        raise ThemePackError('Unsupported workspace constructor', path + '.type')

    if not isinstance(value['workspace'], dict) or value['workspace'].get('type') not in ('row', 'column'):
        raise ThemePackError('Workspace root must be a row or column', 'presentation.json.workspace')
    workspace = node(value['workspace'], 'presentation.json.workspace', 1)
    if sorted(slots) != ['actions', 'content', 'navigation']:
        raise ThemePackError('Workspace requires exactly one content, navigation and actions slot', 'presentation.json.workspace')
    styles = value['styles']
    if not isinstance(styles, dict):
        raise ThemePackError('Styles must be an object', 'presentation.json.styles')
    result = {}
    for name, style in styles.items():
        path = 'presentation.json.styles.' + name
        if name not in STYLE_OPTIONS:
            raise ThemePackError('Unsupported component style', path)
        options = STYLE_OPTIONS[name]
        _keys(style, set(options), path)
        for key, allowed in options.items():
            if style[key] not in allowed:
                raise ThemePackError('Unsupported style value', path + '.' + key)
        result[name] = dict(style)
    return {'api_version': 1, 'workspace': workspace, 'styles': result}


def validate_sources(value: Any) -> dict:
    _keys(value, {'website', 'retrieved_at', 'observations', 'notes'}, 'sources.json')

    def url(candidate, path):
        if not isinstance(candidate, str) or len(candidate) > 2048:
            raise ThemePackError('Must be an HTTP or HTTPS URL', path)
        try:
            parsed = urlsplit(candidate)
            valid = parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password
            parsed.port  # Reject malformed ports even though URLs are never fetched here.
        except ValueError:
            valid = False
        if not valid or any(character.isspace() for character in candidate):
            raise ThemePackError('Must be an HTTP or HTTPS URL without credentials', path)

    def note(candidate, path):
        if not isinstance(candidate, str) or not 1 <= len(candidate.strip()) <= 1000:
            raise ThemePackError('Must be 1–1000 characters', path)

    url(value['website'], 'sources.json.website')
    try:
        if not isinstance(value['retrieved_at'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value['retrieved_at']):
            raise ValueError()
        date.fromisoformat(value['retrieved_at'])
    except ValueError as exc:
        raise ThemePackError('Retrieval date must be a valid YYYY-MM-DD date', 'sources.json.retrieved_at') from exc
    if not isinstance(value['observations'], list) or len(value['observations']) > 32:
        raise ThemePackError('Provide at most 32 observations', 'sources.json.observations')
    observations = []
    for index, item in enumerate(value['observations']):
        path = f'sources.json.observations[{index}]'
        _keys(item, {'url', 'kind', 'note'}, path)
        url(item['url'], path + '.url')
        if item['kind'] not in ('observed', 'documented', 'inferred'):
            raise ThemePackError('Unsupported observation kind', path + '.kind')
        note(item['note'], path + '.note')
        observations.append(dict(item))
    if not isinstance(value['notes'], list) or len(value['notes']) > 16:
        raise ThemePackError('Provide at most 16 notes', 'sources.json.notes')
    for index, item in enumerate(value['notes']):
        note(item, f'sources.json.notes[{index}]')
    return dict(value, observations=observations, notes=list(value['notes']))


def validate_theme_pack(data: bytes) -> dict:
    """Parse and independently verify a bounded ZIP without extracting it."""
    payload = _archive(data)
    pack = _json(payload['pack.json'], 'pack.json')
    _keys(pack, {'format', 'format_version', 'template_api_version', 'id', 'version', 'files'}, 'pack.json')
    if pack['format'] == 'fastlanelabs-theme-pack' and type(pack['format_version']) is int and pack['format_version'] == 2:
        return _validate_pack_v2(data, payload, pack)
    if pack['format'] != 'fastlanelabs-theme-pack' or type(pack['format_version']) is not int or pack['format_version'] != 1:
        raise ThemePackError('Unsupported theme pack format or version')
    if type(pack['template_api_version']) is not int or pack['template_api_version'] != 1:
        raise ThemePackError('Unsupported template API version', 'pack.json.template_api_version')
    _keys(pack['files'], PACK_FILES - {'pack.json'}, 'pack.json.files')
    for name, checksum in pack['files'].items():
        if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
            raise ThemePackError('Expected a lowercase SHA-256 checksum', 'pack.json.files.' + name)
        if hashlib.sha256(payload[name]).hexdigest() != checksum:
            raise ThemePackError('Checksum mismatch', name)
    try:
        theme = _validate_v1(_json(payload['theme.json'], 'theme.json'))
    except ThemePackError:
        raise
    except (ThemeError, TypeError) as exc:
        raise ThemePackError(str(exc), 'theme.json') from exc
    if not theme['id'].startswith('client-') or theme['id'] == 'client-':
        raise ThemePackError('Uploaded theme IDs must use the client- namespace', 'theme.json.id')
    if pack['id'] != theme['id'] or pack['version'] != theme['version']:
        raise ThemePackError('Pack identity must match theme identity', 'pack.json')
    presentation = validate_presentation(_json(payload['presentation.json'], 'presentation.json'))
    sources = validate_sources(_json(payload['sources.json'], 'sources.json'))
    warnings = []
    if not sources['observations']:
        warnings.append('Brand has no recorded source observations; verify the inferred appearance before applying.')
    if any(item['kind'] == 'inferred' for item in sources['observations']):
        warnings.append('Some brand choices are inferred; review the source notes before applying.')
    return {'theme': theme, 'presentation': presentation, 'sources': sources,
            'sha256': hashlib.sha256(data).hexdigest(), 'warnings': warnings}


def create_theme_pack(theme: Any, presentation: Any, sources: Any) -> bytes:
    """Build a reproducible pack; the same validation runs before it is returned."""
    try:
        theme = _validate_v1(theme)
    except (ThemeError, TypeError) as exc:
        raise ThemePackError(str(exc), 'theme.json') from exc
    presentation = validate_presentation(presentation)
    sources = validate_sources(sources)
    def encoded(value):
        return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    payload = {'theme.json': encoded(theme), 'presentation.json': encoded(presentation), 'sources.json': encoded(sources)}
    payload['pack.json'] = encoded({
        'format': 'fastlanelabs-theme-pack', 'format_version': 1, 'template_api_version': 1,
        'id': theme['id'], 'version': theme['version'],
        'files': {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()},
    })
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(payload):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload[name])
    data = output.getvalue()
    validate_theme_pack(data)
    return data


def _theme_v2(content: bytes) -> dict:
    """Parse theme.json for a format 2 pack; every problem keeps its field path."""
    value = _json(content, 'theme.json')
    if not isinstance(value, dict) or value.get('api_version') != 2 or type(value.get('api_version')) is not int:
        raise ThemePackError('Format 2 packs require a v2 theme', 'theme.json.api_version')
    problems = check_theme(value)
    if problems['errors']:
        first = problems['errors'][0]
        error = ThemePackError(first['message'], 'theme.json' + ('.' + first['path'] if first['path'] else ''))
        error.errors = [{'path': 'theme.json' + ('.' + e['path'] if e['path'] else ''), 'message': e['message']}
                        for e in problems['errors']]
        raise error
    return validate_theme(value)


def _validate_pack_v2(data: bytes, payload: dict, pack: dict) -> dict:
    if type(pack['template_api_version']) is not int or pack['template_api_version'] != 2:
        raise ThemePackError('Unsupported template API version', 'pack.json.template_api_version')
    _keys(pack['files'], PACK_FILES_V2 - {'pack.json'}, 'pack.json.files')
    for name, checksum in pack['files'].items():
        if not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum):
            raise ThemePackError('Expected a lowercase SHA-256 checksum', 'pack.json.files.' + name)
        if hashlib.sha256(payload[name]).hexdigest() != checksum:
            raise ThemePackError('Checksum mismatch', name)
    theme = _theme_v2(payload['theme.json'])
    if not theme['id'].startswith('client-') or theme['id'] == 'client-':
        raise ThemePackError('Uploaded theme IDs must use the client- namespace', 'theme.json.id')
    if pack['id'] != theme['id'] or pack['version'] != theme['version']:
        raise ThemePackError('Pack identity must match theme identity', 'pack.json')
    sources = validate_sources(_json(payload['sources.json'], 'sources.json'))
    warnings = []
    if not sources['observations']:
        warnings.append('Brand has no recorded source observations; verify the inferred appearance before applying.')
    if any(item['kind'] == 'inferred' for item in sources['observations']):
        warnings.append('Some brand choices are inferred; review the source notes before applying.')
    warnings.extend(f"{item['path']}: {item['message']}" for item in check_theme(theme)['warnings'])
    return {'format_version': 2, 'theme': theme, 'presentation': None, 'sources': sources,
            'sha256': hashlib.sha256(data).hexdigest(), 'warnings': warnings}


def create_theme_pack_v2(theme: Any, sources: Any) -> bytes:
    """Build a reproducible format 2 pack; the same validation runs before it is returned."""
    try:
        theme = _theme_v2(json.dumps(theme, allow_nan=False).encode('utf-8'))
    except ThemePackError:
        raise
    except (ThemeError, TypeError, ValueError) as exc:
        raise ThemePackError(str(exc), 'theme.json') from exc
    sources = validate_sources(sources)
    def encoded(value):
        return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    payload = {'theme.json': encoded(theme), 'sources.json': encoded(sources)}
    payload['pack.json'] = encoded({
        'format': 'fastlanelabs-theme-pack', 'format_version': 2, 'template_api_version': 2,
        'id': theme['id'], 'version': theme['version'],
        'files': {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()},
    })
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(payload):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payload[name])
    data = output.getvalue()
    validate_theme_pack(data)
    return data
