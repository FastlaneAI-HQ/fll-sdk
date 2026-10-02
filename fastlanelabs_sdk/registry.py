"""The catalog: which apps exist, and where their published releases live.

A static, bundled file today, deliberately -- the point of this first pass is
proving that an app's code can be pulled in and bound at install time at all.
What decides *which* apps a given client should be offered, discovery beyond
a hand-maintained YAML file, and versioning policy are explicitly future work
(see this repo's README).

`repo` is kept per app as a human reference -- "this is where it was built
from" -- but is no longer read at install time. What an install actually
pulls from is the shared Blob Storage account/container in `storage()`: one
`versions.json` and one wheel/tarball pair per released version, published by
each app repo's own CI on a tag push. See `deploy/install_apps.py` and
`fastlanelabs_sdk.azure_blob`.

Bundled as package data (`registry_data/apps.yaml`) rather than read from a
path relative to the repo checkout, so `load()` works the same way whether
this package was installed with `-e` for local development or pulled from git
as a dependency -- the caller never has to know which.
"""
from __future__ import annotations

import os
import json
import logging
import time
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import yaml

try:
    from importlib.resources import files
except ImportError:  # pragma: no cover - Python <3.9 fallback
    from importlib_resources import files  # type: ignore


@dataclass(frozen=True)
class RegistryEntry:
    id: str
    repo: str
    backend_package: str
    # Empty for a backend-only app (FastAI: its chat UI is core's own, not a
    # separate installable frontend package) -- `deploy/install_apps.py`
    # skips the npm install/import step when this is blank.
    frontend_package: str = ""
    # For showing an app that isn't installed yet in a picker (a live-install
    # deployment's whole point -- see backend/app/live_install.py) -- an app
    # with no code present at all still needs a human-readable name and a
    # one-line description to be chosen from. Kept in sync with the app's
    # own AppSpec.label/.purpose by hand; nothing enforces they match.
    label: str = ""
    purpose: str = ""
    app_id: str = ""
    always: bool = False
    min_role: str = "member"
    group: str = "primary"


@dataclass(frozen=True)
class Storage:
    account: str
    container: str


def _source() -> str:
    # An operator can point at a fork or a local checkout while iterating on
    # the registry itself, without publishing a new fll-sdk release first.
    override = os.environ.get("FASTLANELABS_REGISTRY_PATH")
    if override:
        return Path(override).read_text("utf-8")
    return (files("fastlanelabs_sdk.registry_data")
            .joinpath("apps.yaml").read_text("utf-8"))


_cached_catalog = None
_catalog_expires = 0.0


def load() -> Dict[str, RegistryEntry]:
    """Read registry metadata, without importing application packages.

    Production reads catalog.json from Blob Storage and caches it for a
    minute. A saved catalog keeps Admin available during a registry outage.
    A local path override explicitly selects development/offline mode.
    """
    global _cached_catalog, _catalog_expires
    data = yaml.safe_load(_source()) or {}
    remote = os.environ.get('FASTLANELABS_REGISTRY_REMOTE', '').lower() == 'true'
    if remote and not os.environ.get('FASTLANELABS_REGISTRY_PATH'):
        if _cached_catalog is not None and time.monotonic() < _catalog_expires:
            return dict(_cached_catalog)
        cache = Path(os.environ.get('FASTLANELABS_REGISTRY_CACHE',
                                    str(Path(os.environ.get('DATA_DIR', '/data')) / 'apps/catalog.json')))
        try:
            from . import azure_blob
            location = storage()
            data = azure_blob.get_json(location.account, location.container, 'catalog.json')
            result = _entries(data)
            cache.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile('w', dir=cache.parent, delete=False) as output:
                json.dump(data, output)
                pending = output.name
            os.replace(pending, cache)
        except Exception as exc:
            logging.getLogger(__name__).warning('Registry catalog unavailable: %s', exc)
            if _cached_catalog is not None:
                result = _cached_catalog
            elif cache.exists():
                result = _entries(json.loads(cache.read_text()))
            else:
                result = _entries(yaml.safe_load(_source()) or {})
        _cached_catalog = result
        _catalog_expires = time.monotonic() + 60
        return dict(result)
    return _entries(data)


def _entries(data) -> Dict[str, RegistryEntry]:
    import re
    if data.get('api_version', 1) != 1:
        raise ValueError('Unsupported registry catalog API version')
    apps = data.get('apps')
    if not isinstance(apps, dict):
        raise ValueError('Registry catalog must contain an apps map')
    result = {}
    for key, fields in apps.items():
        entry = RegistryEntry(id=key, **fields)
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', key):
            raise ValueError('Invalid registry selector')
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}', entry.app_id or key):
            raise ValueError('Invalid registry app id')
        if not re.fullmatch(r'fastlanelabs_app_[a-z0-9_]+', entry.backend_package):
            raise ValueError('Invalid registry package')
        if type(entry.always) is not bool:
            raise ValueError('Registry always must be boolean')
        if entry.min_role not in ('member','tenant_admin','fastlane_admin') or entry.group not in ('primary','secondary'):
            raise ValueError('Invalid registry app access metadata')
        result[key] = entry
    if len({e.app_id or e.id for e in result.values()}) != len(result):
        raise ValueError('Duplicate registry app id')
    return result


def storage() -> Storage:
    data = yaml.safe_load(_source()) or {}
    reg = data.get("registry") or {}
    if not reg.get("account") or not reg.get("container"):
        raise RuntimeError(
            "apps.yaml has no registry.account/registry.container -- "
            "where would an install pull artifacts from?")
    return Storage(account=reg["account"], container=reg["container"])
