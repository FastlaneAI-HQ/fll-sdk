"""Bounded, data-only FastlaneLabs theme packs.

A pack (format 2) is three root JSON files: pack.json, theme.json (the manifest, which carries its own layout) and
sources.json (where the brand was observed).
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

from .themes import ThemeError, check_theme, validate_theme

MAX_PACK_BYTES = 2 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024
PACK_FORMAT_VERSION = 2
PACK_FILES = {'pack.json', 'theme.json', 'sources.json'}


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


def _archive(data: bytes) -> dict[str, bytes]:
    if not isinstance(data, bytes) or not data or len(data) > MAX_PACK_BYTES:
        raise ThemePackError('Theme pack must be a ZIP no larger than 2 MiB', '$archive')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            allowed, count = PACK_FILES, 'three'
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
    if pack['format'] != 'fastlanelabs-theme-pack' or type(pack['format_version']) is not int or pack['format_version'] != PACK_FORMAT_VERSION:
        raise ThemePackError('Unsupported theme pack format or version')
    return _validate_pack_v2(data, payload, pack)


def _theme_v2(content: bytes) -> dict:
    """Parse theme.json for a format 2 pack; every problem keeps its field path."""
    value = _json(content, 'theme.json')
    if not isinstance(value, dict) or value.get('api_version') != 2 or type(value.get('api_version')) is not int:
        raise ThemePackError('A theme pack requires an API v2 theme', 'theme.json.api_version')
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
    _keys(pack['files'], PACK_FILES - {'pack.json'}, 'pack.json.files')
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
    return {'format_version': PACK_FORMAT_VERSION, 'theme': theme, 'sources': sources,
            'sha256': hashlib.sha256(data).hexdigest(), 'warnings': warnings}


def create_theme_pack_v2(theme: Any, sources: Any) -> bytes:
    """Build a reproducible pack; the same validation runs before it is returned."""
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
        'format': 'fastlanelabs-theme-pack', 'format_version': PACK_FORMAT_VERSION, 'template_api_version': 2,
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
