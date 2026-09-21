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


def load() -> Dict[str, RegistryEntry]:
    data = yaml.safe_load(_source()) or {}
    return {
        app_id: RegistryEntry(id=app_id, **fields)
        for app_id, fields in (data.get("apps") or {}).items()
    }


def storage() -> Storage:
    data = yaml.safe_load(_source()) or {}
    reg = data.get("registry") or {}
    if not reg.get("account") or not reg.get("container"):
        raise RuntimeError(
            "apps.yaml has no registry.account/registry.container -- "
            "where would an install pull artifacts from?")
    return Storage(account=reg["account"], container=reg["container"])
