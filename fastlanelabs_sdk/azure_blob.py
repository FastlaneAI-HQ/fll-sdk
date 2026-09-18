"""Read-only access to the app registry's Blob Storage container.

Deliberately dependency-free, the same way `deploy/vm/backup.py` in core is:
a VM authenticates with the identity it already has (its managed identity, via
IMDS) rather than a stored key or SAS token, and talks to the plain Blob
Storage REST API over `urllib` rather than pulling in `azure-storage-blob` and
`azure-identity` as new dependencies for what is, underneath, two HTTP verbs.

Granting a VM read access to the registry container is
`deploy/vm/setup-app-registry.sh`, which assigns "Storage Blob Data Reader"
scoped to that one container -- mirroring `deploy/vm/setup-backups.sh`.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional

IMDS = "http://169.254.169.254/metadata/identity/oauth2/token"
STORAGE_RESOURCE = "https://storage.azure.com/"
API_VERSION = "2021-08-06"


def _opener() -> urllib.request.OpenerDirector:
    # IMDS is link-local; a proxy configured for the rest of the machine would
    # otherwise swallow the call.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def imds_token() -> str:
    url = "{0}?api-version=2018-02-01&resource={1}".format(
        IMDS, urllib.parse.quote(STORAGE_RESOURCE, safe=""))
    req = urllib.request.Request(url, headers={"Metadata": "true"})
    last = ""
    for attempt in range(5):
        try:
            with _opener().open(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))["access_token"]
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            time.sleep(2 ** attempt)
    raise RuntimeError(
        "could not get a token from the instance identity ({0}). Has this "
        "VM's identity been given access to the app registry container? See "
        "deploy/vm/setup-app-registry.sh".format(last))


def _get(url: str, token: str) -> bytes:
    headers = {
        "Authorization": "Bearer {0}".format(token),
        "x-ms-version": API_VERSION,
        "x-ms-date": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with _opener().open(req, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError("GET {0} -> {1} {2}: {3}".format(
            url.split("?")[0], exc.code, exc.reason, detail)) from None


def get_blob(account: str, container: str, path: str,
             token: Optional[str] = None) -> bytes:
    """The raw bytes of one blob. `path` is relative to the container."""
    url = "https://{0}.blob.core.windows.net/{1}/{2}".format(
        account, container, path)
    return _get(url, token or imds_token())


def get_json(account: str, container: str, path: str,
             token: Optional[str] = None) -> Dict[str, Any]:
    return json.loads(get_blob(account, container, path, token).decode("utf-8"))
