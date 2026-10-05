"""Publish catalog.json -- the list of installable apps -- to the registry.

    python scripts/publish_catalog.py            # check, show the diff, publish
    python scripts/publish_catalog.py --dry-run  # check and show only
    python scripts/publish_catalog.py --skip-unreleased   # leave out apps
                                                 # with no runtime release yet

The source is this SDK's bundled `registry_data/apps.yaml`, validated by the
same code a tenant install uses to read it. Before anything is written,
every app it lists must have a runtime release in the registry
(`<app>/versions.json` with `runtime_latest`): a catalog naming an app that
cannot be installed would offer tenants a button that fails. Refused unless
--skip-unreleased, which drops those apps and says which.

Written with the caller's `az login` (an operator, or the Jenkins box's
identity), straight to storage -- publishing is never done through the
fll-registry service, which is read-only by design. The service filters this
catalog per tenant key, so every tenant sees only the apps it is entitled to.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

# The bundled file, never the remote catalog this script is about to replace.
os.environ.pop("FASTLANELABS_REGISTRY_REMOTE", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastlanelabs_sdk.registry import _entries, load, storage  # noqa: E402


def az(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["az", *args], capture_output=True, text=True)


def remote_json(account: str, container: str, name: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "blob.json"
        result = az("storage", "blob", "download", "--auth-mode", "login",
                    "--account-name", account, "--container-name", container,
                    "--name", name, "--file", str(path), "-o", "none", "--no-progress")
        if result.returncode:
            if "BlobNotFound" in result.stderr or "does not exist" in result.stderr:
                return None
            raise SystemExit("could not read {0}: {1}".format(name, result.stderr.strip()))
        return json.loads(path.read_text("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-unreleased", action="store_true")
    args = parser.parse_args()

    location = storage()
    apps = {key: {k: v for k, v in asdict(entry).items() if k != "id"}
            for key, entry in load().items()}

    unreleased = []
    for key in sorted(apps):
        manifest = remote_json(location.account, location.container, key + "/versions.json")
        latest = (manifest or {}).get("runtime_latest")
        print("  {0:<16} {1}".format(key, latest or "NO RUNTIME RELEASE"))
        if not latest:
            unreleased.append(key)
    if unreleased and not args.skip_unreleased:
        raise SystemExit("\nRefusing: no runtime release for {0}. Publish them first, or "
                         "pass --skip-unreleased.".format(", ".join(unreleased)))
    for key in unreleased:
        del apps[key]

    catalog = {"api_version": 1, "apps": apps}
    _entries(catalog)  # exactly what a tenant install will run on it
    current = remote_json(location.account, location.container, "catalog.json")
    if current == catalog:
        print("\ncatalog.json is already current ({0} apps).".format(len(apps)))
        return
    before = set((current or {}).get("apps") or {})
    print("\ncatalog.json: {0} apps; added {1}; removed {2}; changed {3}".format(
        len(apps), sorted(set(apps) - before) or "-", sorted(before - set(apps)) or "-",
        sorted(k for k in set(apps) & before if apps[k] != current["apps"][k]) or "-"))
    if unreleased:
        print("left out (no runtime release): " + ", ".join(unreleased))
    if args.dry_run:
        print("dry run: nothing written")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as out:
        json.dump(catalog, out, indent=2, sort_keys=True)
    result = az("storage", "blob", "upload", "--auth-mode", "login",
                "--account-name", location.account, "--container-name", location.container,
                "--name", "catalog.json", "--file", out.name, "--overwrite", "true",
                "--content-type", "application/json", "-o", "none")
    os.unlink(out.name)
    if result.returncode:
        raise SystemExit("upload failed: " + result.stderr.strip())
    print("published catalog.json")


if __name__ == "__main__":
    main()
